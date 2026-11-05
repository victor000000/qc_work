"""Apply schema migration to S001.duckdb: extend fundamental_fields,
create probe_results, migrate legacy classifications.

Idempotent: safe to re-run on an already-migrated database."""

from s001.paths import WORKSPACE_ROOT, DATA_DIR

import qc_storage as storage
import sys


# Columns to add to fundamental_fields (name, type, default-clause-or-empty).
NEW_COLUMNS = [
    ('period', 'TEXT', ''),
    ('container', 'TEXT', ''),
    ('probe_op', 'TEXT', ''),
    ('probe_threshold', 'TEXT', ''),
    ('probe_gate', 'TEXT', ''),
    ('probe_boost', 'REAL', ''),
    ('classification', 'TEXT', "DEFAULT 'untested'"),
    ('last_classified_at', 'TEXT', ''),
    ('data_type_hint', 'TEXT', ''),
    # v2 (auto-sweep)
    ('sweep_phase', 'INTEGER', 'DEFAULT 0'),
    ('sweep_winner_op', 'TEXT', ''),
    ('sweep_winner_threshold', 'TEXT', ''),
    ('sweep_winner_gate', 'TEXT', ''),
    ('sweep_winner_boost', 'REAL', ''),
    ('sweep_winner_delta', 'REAL', ''),
]

# Columns to add to probe_results (v2 only — v1 had its full schema in PROBE_RESULTS_DDL).
PROBE_RESULTS_V2_COLUMNS = [
    ('is_sweep_variant', 'INTEGER', 'DEFAULT 0'),
]

# v3 (full-grid coarse + refine + universe-aware thresholds)
V3_FUNDAMENTAL_COLUMNS = [
    ('sweep_version', 'INTEGER', 'DEFAULT 1'),
    ('coarse_winner_op', 'TEXT', ''),
    ('coarse_winner_threshold', 'TEXT', ''),
    ('coarse_winner_gate', 'TEXT', ''),
    ('coarse_winner_mag', 'REAL', ''),
    ('coarse_winner_delta', 'REAL', ''),
    ('refine_op_set', 'TEXT', ''),
    ('refine_mag_set', 'TEXT', ''),
    ('refine_gate_set', 'TEXT', ''),
    ('refine_threshold_set', 'TEXT', ''),
]

V3_PROBE_RESULTS_COLUMNS = [
    ('sweep_stage', 'TEXT', ''),
]

# Mega-round: distinguish per-mechanism cells (score/skip/stop/petgt/convg/convb)
MEGA_PROBE_RESULTS_COLUMNS = [
    ('mechanism', 'TEXT', ''),
]

FIELD_UNIVERSE_STATS_DDL = """CREATE TABLE IF NOT EXISTS field_universe_stats (
    field_id INTEGER NOT NULL REFERENCES fundamental_fields(id),
    bake_hash TEXT NOT NULL,
    p10 REAL,
    p25 REAL,
    p50 REAL,
    p75 REAL,
    p90 REAL,
    sample_size INTEGER NOT NULL,
    scanned_at TEXT NOT NULL,
    PRIMARY KEY (field_id, bake_hash)
)"""


PROBE_RESULTS_DDL = """CREATE TABLE IF NOT EXISTS probe_results (
    id INTEGER PRIMARY KEY,
    field_id INTEGER NOT NULL REFERENCES fundamental_fields(id),
    experiment_name TEXT NOT NULL UNIQUE,
    round_n INTEGER NOT NULL,
    bake_hash TEXT NOT NULL,
    noop_baseline REAL NOT NULL,
    spec_car_mdd REAL NOT NULL,
    delta REAL NOT NULL,
    classification TEXT NOT NULL,
    applied_op TEXT NOT NULL,
    applied_threshold TEXT NOT NULL,
    applied_gate TEXT,
    applied_boost REAL NOT NULL,
    recorded_at TEXT NOT NULL
)"""

INDEXES = [
    ("idx_ff_classification", "fundamental_fields(classification)"),
    ("idx_ff_container", "fundamental_fields(container)"),
    ("idx_pr_field", "probe_results(field_id)"),
    ("idx_pr_classification", "probe_results(classification)"),
    ("idx_pr_bake_hash", "probe_results(bake_hash)"),
    ("idx_pr_field_bake", "probe_results(field_id, bake_hash)"),  # v2
]


def existing_columns(cur, table):
    cur.execute(f"PRAGMA table_info({table})")
    return {r[1] for r in cur.fetchall()}


def apply_schema_migration(db_path):
    with storage.connect(db_path) as con:
        cur = con.cursor()

        # fundamental_fields columns (v1 + v2)
        cols = existing_columns(cur, 'fundamental_fields')
        for name, sqltype, default_clause in NEW_COLUMNS:
            if name in cols:
                continue
            ddl = f"ALTER TABLE fundamental_fields ADD COLUMN {name} {sqltype}"
            if default_clause:
                ddl += f" {default_clause}"
            cur.execute(ddl)

        # probe_results table (v1)
        cur.execute(PROBE_RESULTS_DDL)

        # probe_results columns (v2 additions)
        pr_cols = existing_columns(cur, 'probe_results')
        for name, sqltype, default_clause in PROBE_RESULTS_V2_COLUMNS:
            if name in pr_cols:
                continue
            ddl = f"ALTER TABLE probe_results ADD COLUMN {name} {sqltype}"
            if default_clause:
                ddl += f" {default_clause}"
            cur.execute(ddl)

        # v3 fundamental_fields columns
        cols = existing_columns(cur, 'fundamental_fields')
        for name, sqltype, default_clause in V3_FUNDAMENTAL_COLUMNS:
            if name in cols:
                continue
            ddl = f"ALTER TABLE fundamental_fields ADD COLUMN {name} {sqltype}"
            if default_clause:
                ddl += f" {default_clause}"
            cur.execute(ddl)

        # v3 probe_results columns
        pr_cols = existing_columns(cur, 'probe_results')
        for name, sqltype, default_clause in V3_PROBE_RESULTS_COLUMNS:
            if name in pr_cols:
                continue
            ddl = f"ALTER TABLE probe_results ADD COLUMN {name} {sqltype}"
            if default_clause:
                ddl += f" {default_clause}"
            cur.execute(ddl)

        # mega-round probe_results columns
        pr_cols = existing_columns(cur, 'probe_results')
        for name, sqltype, default_clause in MEGA_PROBE_RESULTS_COLUMNS:
            if name in pr_cols:
                continue
            ddl = f"ALTER TABLE probe_results ADD COLUMN {name} {sqltype}"
            if default_clause:
                ddl += f" {default_clause}"
            cur.execute(ddl)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_probe_results_mechanism "
                    "ON probe_results(field_id, mechanism, bake_hash)")

        # v3 field_universe_stats table
        cur.execute(FIELD_UNIVERSE_STATS_DDL)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fus_bake "
                    "ON field_universe_stats(bake_hash)")

        # One-time renumber: v2 sealed fields → v3-compatible phase=4
        cur.execute("""UPDATE fundamental_fields
                       SET sweep_version = 2, sweep_phase = 4
                       WHERE sweep_phase = 2 AND sweep_winner_delta IS NOT NULL""")

        for name, target in INDEXES:
            cur.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {target}")

        # Legacy classification migration (idempotent — only updates rows that
        # don't already have a classification matching the rule).
        cur.execute("""UPDATE fundamental_fields
                       SET classification = 'untested'
                       WHERE status = 'untested' AND classification IS NULL""")
        cur.execute("""UPDATE fundamental_fields
                       SET classification = 'neutral'
                       WHERE status = 'tested_in' AND classification IS NULL""")

        con.commit()


if __name__ == '__main__':
    db = sys.argv[1] if len(sys.argv) > 1 else str(DATA_DIR / 'S001.duckdb')
    apply_schema_migration(db)
    print(f"Migration applied to {db}")
