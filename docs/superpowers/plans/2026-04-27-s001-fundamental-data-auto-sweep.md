# S001 Fundamental Data Auto-Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a two-phase auto-sweep on top of the v1 fundamental-data library — when a field's Phase 1 default-template probe yields any non-zero delta (`|Δ| ≥ 0.0001`), the next round emits a 5×3 (magnitude × decline gate) Phase 2 sweep for that field, captures the best variant, and surfaces it for promotion. Also fix v1's bake-hash scoping bug so classifications reset per bake.

**Architecture:** Three new library functions (`current_bake_hash`, `pick_sweep_candidates`, `emit_phase2_sweep`, `update_sweep_winner`) + two modified (`pick_fields` becomes bake-aware, `emit_probes_for_db` gains `k_sweep_fields`). `score_probes.py` learns a second regex (`_sw_` prefix) and reconstructs `applied_*` from name parts. Schema gains 6 columns on existing tables + 1 index, no new tables.

**Tech Stack:** Python 3.13, SQLite3 (S001.db at `/home/txy/qc_work/data/S001.db`), pytest. Builds on v1 spec at `/home/txy/qc_work/docs/superpowers/specs/2026-04-27-s001-fundamental-data-coverage-design.md`.

**Note:** The repo is git-tracked but the user controls all commits. Use "tests pass" as the per-task checkpoint; do not run `git commit` unless the user explicitly asks. The settings table (`category, key, value, description, updated_at`) already exists in S001.db.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `scripts/migrate_schema.py` | Modify | Add 6 ALTERs, 1 INDEX, 1 SETTINGS INSERT to existing migration |
| `s001/fundamental_probes.py` | Modify | Add `current_bake_hash`, `pick_sweep_candidates`, `emit_phase2_sweep`, `update_sweep_winner`, `SWEEP_MAGS`, `SWEEP_GATES`; modify `pick_fields` (bake-aware) and `emit_probes_for_db` (k_sweep_fields) |
| `scripts/score_probes.py` | Modify | Add `SWEEP_NAME_RE` regex, parse sweep specs, reconstruct `applied_*`, write `is_sweep_variant=1`, call `update_sweep_winner` after scoring |
| `tests/test_fundamental_probes.py` | Modify | 5 new test classes covering new/modified library functions |
| `tests/test_score_probes.py` | Modify | 3 new tests for sweep regex + winner update |
| `tests/test_emit_probes.py` | Modify | 3 new tests for `k_sweep_fields` integration |
| `tests/test_migrate_schema.py` | Modify | 1 new test for v2 schema additions |
| `gen_s001_R463.py` | Create | First library-driven generator using `k_sweep_fields=3` |

Pytest discovers tests automatically; no test file path changes needed.

---

## Task 0: Extend Schema Migration

**Files:**
- Modify: `/home/txy/qc_work/data/scripts/migrate_schema.py`
- Modify: `/home/txy/qc_work/data/tests/test_migrate_schema.py`

- [ ] **Step 1: Append the failing test**

Append to `/home/txy/qc_work/data/tests/test_migrate_schema.py`:

```python
def test_migration_adds_v2_columns_and_settings(tmp_db):
    """V2: sweep_phase + sweep_winner_* on fundamental_fields,
    is_sweep_variant on probe_results, current_bake_hash in settings."""
    # tmp_db fixture already has the v1+v2 schema baked in.
    # Drop and recreate as a true legacy state (v1 only) to test the migration.
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("DROP TABLE fundamental_fields")
        cur.execute("DROP TABLE probe_results")
        cur.execute("""CREATE TABLE fundamental_fields (
            id INTEGER PRIMARY KEY,
            category TEXT NOT NULL,
            field_name TEXT NOT NULL,
            accessor TEXT NOT NULL UNIQUE,
            data_type TEXT DEFAULT 'double',
            needs_dot_value INTEGER DEFAULT 0,
            status TEXT DEFAULT 'untested',
            tested_in TEXT,
            description TEXT,
            test_notes TEXT,
            period TEXT,
            container TEXT,
            probe_op TEXT,
            probe_threshold TEXT,
            probe_gate TEXT,
            probe_boost REAL,
            classification TEXT DEFAULT 'untested',
            last_classified_at TEXT,
            data_type_hint TEXT
        )""")
        cur.execute("""CREATE TABLE probe_results (
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
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS settings (
            category TEXT, key TEXT, value TEXT, description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (category, key)
        )""")

    from scripts.migrate_schema import apply_schema_migration
    apply_schema_migration(tmp_db)

    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("PRAGMA table_info(fundamental_fields)")
        cols = {r[1] for r in cur.fetchall()}
        v2_field_cols = {'sweep_phase', 'sweep_winner_op',
                         'sweep_winner_threshold', 'sweep_winner_gate',
                         'sweep_winner_boost', 'sweep_winner_delta'}
        assert v2_field_cols <= cols, f'missing: {v2_field_cols - cols}'

        cur.execute("PRAGMA table_info(probe_results)")
        pr_cols = {r[1] for r in cur.fetchall()}
        assert 'is_sweep_variant' in pr_cols

        cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_pr_field_bake'")
        assert cur.fetchone() is not None, 'idx_pr_field_bake missing'


def test_migration_v2_idempotent(tmp_db):
    from scripts.migrate_schema import apply_schema_migration
    apply_schema_migration(tmp_db)
    apply_schema_migration(tmp_db)  # second run must not fail
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/txy/qc_work/data && pytest tests/test_migrate_schema.py -v`
Expected: 2 new tests fail (columns missing or unique-constraint error).

- [ ] **Step 3: Extend the migration script**

In `/home/txy/qc_work/data/scripts/migrate_schema.py`, modify `NEW_COLUMNS` to add v2 entries at the end:

```python
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

PROBE_RESULTS_V2_COLUMNS = [
    ('is_sweep_variant', 'INTEGER', 'DEFAULT 0'),
]
```

Append to `INDEXES`:

```python
INDEXES = [
    ("idx_ff_classification", "fundamental_fields(classification)"),
    ("idx_ff_container", "fundamental_fields(container)"),
    ("idx_pr_field", "probe_results(field_id)"),
    ("idx_pr_classification", "probe_results(classification)"),
    ("idx_pr_bake_hash", "probe_results(bake_hash)"),
    ("idx_pr_field_bake", "probe_results(field_id, bake_hash)"),  # v2
]
```

Modify `apply_schema_migration` to also handle `probe_results` ALTERs and add settings seed. Replace the function body with:

```python
def apply_schema_migration(db_path):
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()

        # fundamental_fields columns
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

        for name, target in INDEXES:
            cur.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {target}")

        # Legacy classification migration (idempotent)
        cur.execute("""UPDATE fundamental_fields
                       SET classification = 'untested'
                       WHERE status = 'untested' AND classification IS NULL""")
        cur.execute("""UPDATE fundamental_fields
                       SET classification = 'neutral'
                       WHERE status = 'tested_in' AND classification IS NULL""")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/txy/qc_work/data && pytest tests/test_migrate_schema.py -v`
Expected: 4 passed (2 v1 + 2 v2).

- [ ] **Step 5: Run full suite**

Run: `cd /home/txy/qc_work/data && pytest tests/ 2>&1 | tail -3`
Expected: All previously-passing tests still pass; new count includes 2 added.

---

## Task 1: `current_bake_hash` helper

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Append the failing test**

Append to `/home/txy/qc_work/data/tests/test_fundamental_probes.py`:

```python
from s001.fundamental_probes import current_bake_hash


class TestCurrentBakeHash:
    def test_reads_value(self, tmp_db):
        import sqlite3
        with sqlite3.connect(tmp_db) as con:
            con.execute("""INSERT OR REPLACE INTO settings
                (category, key, value, description, updated_at)
                VALUES ('strategy', 'current_bake_hash',
                        'abc123def456', 'test', CURRENT_TIMESTAMP)""")
        assert current_bake_hash(tmp_db) == 'abc123def456'

    def test_raises_when_unset(self, tmp_db):
        import pytest as _pt
        with _pt.raises(RuntimeError, match='current_bake_hash'):
            current_bake_hash(tmp_db)
```

- [ ] **Step 2: Add a settings table to conftest tmp_db fixture**

Edit `/home/txy/qc_work/data/tests/conftest.py` to add a `settings` table to the `tmp_db` fixture. Inside the existing `with sqlite3.connect(str(db)) as con:` block, after the `backtest_queue` CREATE, add:

```python
        cur.execute("""CREATE TABLE IF NOT EXISTS settings (
            category TEXT, key TEXT, value TEXT, description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (category, key)
        )""")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestCurrentBakeHash -v`
Expected: ImportError on `current_bake_hash`.

- [ ] **Step 4: Implement**

Append to `/home/txy/qc_work/data/s001/fundamental_probes.py`:

```python
def current_bake_hash(db_path):
    """Read settings.current_bake_hash. Raise if unset.

    Used by pick_fields and pick_sweep_candidates to scope queries
    to the current S001 base hash.
    """
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.execute("""SELECT value FROM settings
                       WHERE category = 'strategy'
                         AND key = 'current_bake_hash'""")
        row = cur.fetchone()
    if row is None:
        raise RuntimeError(
            "settings.current_bake_hash not set; "
            "INSERT INTO settings (category, key, value) "
            "VALUES ('strategy', 'current_bake_hash', '<md5>') after baking.")
    return row[0]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestCurrentBakeHash -v`
Expected: 2 passed.

---

## Task 2: Bake-aware `pick_fields`

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Append the failing test**

Append to `/home/txy/qc_work/data/tests/test_fundamental_probes.py`:

```python
class TestPickFieldsBakeAware:
    @staticmethod
    def _seed(tmp_db):
        import sqlite3
        with sqlite3.connect(tmp_db) as con:
            cur = con.cursor()
            # Seed fields
            cur.execute(
                """INSERT INTO fundamental_fields
                   (id, category, field_name, accessor, container, period,
                    probe_op, probe_threshold, probe_gate, probe_boost,
                    classification, data_type_hint)
                   VALUES (1, 'v', 'a', '_vr_z.a', 'valuation_ratios', NULL,
                           '>', '5', NULL, 1.10, 'untested', 'numeric')""")
            cur.execute(
                """INSERT INTO fundamental_fields
                   (id, category, field_name, accessor, container, period,
                    probe_op, probe_threshold, probe_gate, probe_boost,
                    classification, data_type_hint)
                   VALUES (2, 'v', 'b', '_vr_z.b', 'valuation_ratios', NULL,
                           '>', '5', NULL, 1.10, 'untested', 'numeric')""")
            # Seed probe_result on OLD bake for field 1 only
            cur.execute(
                """INSERT INTO probe_results
                   (field_id, experiment_name, round_n, bake_hash,
                    noop_baseline, spec_car_mdd, delta, classification,
                    applied_op, applied_threshold, applied_gate, applied_boost, recorded_at)
                   VALUES (1, 'S001_R100_vr_a_gt5', 100, 'old_bake',
                           1.98, 1.98, 0, 'neutral', '>', '5', NULL, 1.10, '2026-01-01')""")
            con.execute("""INSERT OR REPLACE INTO settings
                (category, key, value, description, updated_at)
                VALUES ('strategy', 'current_bake_hash', 'new_bake', 't', CURRENT_TIMESTAMP)""")

    def test_pick_fields_untested_excludes_current_bake_results(self, tmp_db):
        from s001.fundamental_probes import pick_fields
        self._seed(tmp_db)
        # On 'new_bake', field 1 has NO probe_results (all rows are 'old_bake').
        # Both fields should be picked as 'untested'.
        picked = pick_fields(tmp_db, k=10, classification='untested')
        names = sorted(p['field_name'] for p in picked)
        assert names == ['a', 'b']

    def test_pick_fields_untested_filters_when_current_bake_results_exist(self, tmp_db):
        from s001.fundamental_probes import pick_fields
        self._seed(tmp_db)
        # Add a probe_result on the CURRENT bake for field 2.
        import sqlite3
        with sqlite3.connect(tmp_db) as con:
            con.execute(
                """INSERT INTO probe_results
                   (field_id, experiment_name, round_n, bake_hash,
                    noop_baseline, spec_car_mdd, delta, classification,
                    applied_op, applied_threshold, applied_gate, applied_boost, recorded_at)
                   VALUES (2, 'S001_R200_vr_b_gt5', 200, 'new_bake',
                           1.99, 1.99, 0, 'neutral', '>', '5', NULL, 1.10, '2026-02-01')""")
        # Now field 2 has a current-bake result; only field 1 is 'untested'.
        picked = pick_fields(tmp_db, k=10, classification='untested')
        names = [p['field_name'] for p in picked]
        assert names == ['a']

    def test_pick_fields_explicit_bake_hash_arg(self, tmp_db):
        from s001.fundamental_probes import pick_fields
        self._seed(tmp_db)
        # Pass explicit bake_hash='old_bake' — field 1 has a result there, so
        # only field 2 is 'untested' on that bake.
        picked = pick_fields(tmp_db, k=10, classification='untested', bake_hash='old_bake')
        names = [p['field_name'] for p in picked]
        assert names == ['b']
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestPickFieldsBakeAware -v`
Expected: 3 fail (existing `pick_fields` ignores bake_hash).

- [ ] **Step 3: Modify `pick_fields`**

Replace the existing `pick_fields` in `/home/txy/qc_work/data/s001/fundamental_probes.py` with:

```python
def pick_fields(db_path, k, classification='untested', bake_hash=None):
    """Pick up to k fields with the given classification on the CURRENT bake_hash.

    For 'untested': fields with NO probe_results for this bake_hash.
    For 'hot'/'neutral'/'harmful': fields with at least one matching
    probe_results.classification on this bake_hash.

    Within each container, ORDER BY id ASC. Cycles through containers until
    k fields collected (or pool exhausted). Skips rows with NULL probe_threshold.
    """
    if bake_hash is None:
        bake_hash = current_bake_hash(db_path)

    queues = {}
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        for cont in CONTAINER_CYCLE:
            if classification == 'untested':
                cur.execute("""
                    SELECT * FROM fundamental_fields f
                    WHERE f.container = ?
                      AND f.probe_threshold IS NOT NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM probe_results p
                        WHERE p.field_id = f.id AND p.bake_hash = ?
                      )
                    ORDER BY f.id ASC
                """, (cont, bake_hash))
            else:
                cur.execute("""
                    SELECT DISTINCT f.* FROM fundamental_fields f
                    JOIN probe_results p ON p.field_id = f.id
                    WHERE f.container = ? AND p.bake_hash = ?
                      AND p.classification = ?
                      AND f.probe_threshold IS NOT NULL
                    ORDER BY f.id ASC
                """, (cont, bake_hash, classification))
            queues[cont] = [dict(r) for r in cur.fetchall()]

    picked = []
    while len(picked) < k:
        progress = False
        for cont in CONTAINER_CYCLE:
            if queues[cont]:
                picked.append(queues[cont].pop(0))
                progress = True
                if len(picked) >= k:
                    break
        if not progress:
            break
    return picked
```

- [ ] **Step 4: Run new tests + existing pick tests to verify**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestPickFields tests/test_fundamental_probes.py::TestPickFieldsBakeAware -v`
Expected: 5 + 3 = 8 passed (3 new + the existing 5 pick tests).

If existing `TestPickFields` tests fail because they don't seed `settings.current_bake_hash`, update those tests to either pass `bake_hash=` explicitly OR add the settings seed in `_seed_fields`. Picking the explicit-arg approach minimizes test changes:

```python
# In TestPickFields helper class, change every pick_fields(...) call to:
picked = pick_fields(tmp_db, k=3, classification='untested', bake_hash='test_bake')
```

(Update each of the 5 pick_fields calls in `TestPickFields` accordingly.)

- [ ] **Step 5: Run full suite**

Run: `cd /home/txy/qc_work/data && pytest tests/ 2>&1 | tail -3`
Expected: all tests pass (count = previous + 5 new from Tasks 0–2).

---

## Task 3: `SWEEP_MAGS`, `SWEEP_GATES`, `emit_phase2_sweep`

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Append the failing test**

Append to `/home/txy/qc_work/data/tests/test_fundamental_probes.py`:

```python
class TestEmitPhase2Sweep:
    def test_returns_15_specs(self):
        from s001.fundamental_probes import emit_phase2_sweep
        row = {
            'id': 7,
            'container': 'cash_flow_statement',
            'field_name': 'change_in_account_payable',
            'period': 'twelve_months',
            'probe_op': '>',
            'probe_threshold': '1e9',
            'probe_gate': 'decline > .12',
            'probe_boost': 1.08,
            'data_type_hint': 'absolute_amount',
        }
        out = emit_phase2_sweep(row, round_n=475)
        assert len(out) == 15
        names = [n for n, _ in out]
        # All names start with the sweep prefix
        for n in names:
            assert n.startswith('S001_R475_sw_cfs_change_in_account_payable_m')
        # All 15 (mag, gate) combos covered
        assert sorted(set(names)) == sorted(names)  # all unique
        assert len(set(names)) == 15

    def test_grid_covers_expected_mags_and_gates(self):
        from s001.fundamental_probes import emit_phase2_sweep, SWEEP_MAGS, SWEEP_GATES
        assert SWEEP_MAGS == ['1.04', '1.06', '1.08', '1.10', '1.13']
        assert SWEEP_GATES == ['.05', '.10', '.15']

        row = {
            'id': 1, 'container': 'valuation_ratios', 'field_name': 'pe_ratio',
            'period': None, 'probe_op': '<', 'probe_threshold': '15',
            'probe_gate': 'decline > .12', 'probe_boost': 1.10,
            'data_type_hint': 'numeric',
        }
        out = emit_phase2_sweep(row, round_n=999)
        # Expect names with each (mag_short, gate_short) combo
        suffixes = sorted(n.rsplit('_', 2)[-2] + '_' + n.rsplit('_', 1)[-1] for n, _ in out)
        expected = sorted(f'm{m.replace(".","")}_g{g.replace(".","")}' for m in SWEEP_MAGS for g in SWEEP_GATES)
        assert suffixes == expected

    def test_bodies_parse_as_python(self):
        import ast as _ast
        from s001.fundamental_probes import emit_phase2_sweep
        row = {
            'id': 1, 'container': 'valuation_ratios', 'field_name': 'pe_ratio',
            'period': None, 'probe_op': '<', 'probe_threshold': '15',
            'probe_gate': 'decline > .12', 'probe_boost': 1.10,
            'data_type_hint': 'numeric',
        }
        for name, body in emit_phase2_sweep(row, round_n=999):
            wrapped = "def _f():\n  for sym in []:\n" + body + "\n   pass\n"
            _ast.parse(wrapped)

    def test_variant_overrides_mag_and_gate(self):
        from s001.fundamental_probes import emit_phase2_sweep
        row = {
            'id': 1, 'container': 'valuation_ratios', 'field_name': 'pe_ratio',
            'period': None, 'probe_op': '<', 'probe_threshold': '15',
            'probe_gate': 'decline > .12', 'probe_boost': 1.10,
            'data_type_hint': 'numeric',
        }
        out = dict(emit_phase2_sweep(row, round_n=999))
        # Pick a known variant: mag=1.06, gate=.05
        body = out['S001_R999_sw_vr_pe_ratio_m106_g05']
        # Body must use 1.06 and decline > .05, not the row's defaults
        assert 'score *= 1.06' in body
        assert 'decline > .05' in body
        assert 'score *= 1.1' not in body  # row default 1.10 must be overridden
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestEmitPhase2Sweep -v`
Expected: ImportError on `emit_phase2_sweep`/`SWEEP_MAGS`.

- [ ] **Step 3: Implement**

Append to `/home/txy/qc_work/data/s001/fundamental_probes.py`:

```python
SWEEP_MAGS = ['1.04', '1.06', '1.08', '1.10', '1.13']
SWEEP_GATES = ['.05', '.10', '.15']


def emit_phase2_sweep(field_row, round_n):
    """Emit 15 (name, code) tuples for one field's Phase 2 sweep.

    Grid: 5 magnitudes × 3 decline gates. Threshold and op stay at the
    field's authored values.
    """
    out = []
    for mag in SWEEP_MAGS:
        for gate in SWEEP_GATES:
            row = dict(field_row)
            row['probe_boost'] = float(mag)
            row['probe_gate'] = f'decline > {gate}'
            body = render_probe(row)
            mag_short = mag.replace('.', '')
            gate_short = gate.replace('.', '').lstrip('-') or '0'
            cs = CONTAINER_SHORT[field_row['container']]
            name = (f"S001_R{round_n}_sw_{cs}_{field_row['field_name']}"
                    f"_m{mag_short}_g{gate_short}")[:100]
            out.append((name, body))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestEmitPhase2Sweep -v`
Expected: 4 passed.

---

## Task 4: `pick_sweep_candidates`

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Append the failing test**

Append to `/home/txy/qc_work/data/tests/test_fundamental_probes.py`:

```python
class TestPickSweepCandidates:
    @staticmethod
    def _seed(tmp_db):
        import sqlite3
        with sqlite3.connect(tmp_db) as con:
            cur = con.cursor()
            # 3 fields, all sweep_phase=0
            for fid, name in [(1, 'a'), (2, 'b'), (3, 'c')]:
                cur.execute(
                    """INSERT INTO fundamental_fields
                       (id, category, field_name, accessor, container, period,
                        probe_op, probe_threshold, probe_gate, probe_boost,
                        classification, data_type_hint, sweep_phase)
                       VALUES (?, 'v', ?, ?, 'valuation_ratios', NULL,
                               '>', '5', NULL, 1.10, 'untested', 'numeric', 0)""",
                    (fid, name, f'_vr_z.{name}'))
            # Seed Phase 1 results on 'cur_bake':
            #   field 1 delta = 0.0008 (above .0001 trigger)
            #   field 2 delta = 0.00005 (below .0001 trigger)
            #   field 3 delta = 0.0020 (above trigger; biggest)
            for fid, delta in [(1, 0.0008), (2, 0.00005), (3, 0.0020)]:
                cur.execute(
                    """INSERT INTO probe_results
                       (field_id, experiment_name, round_n, bake_hash,
                        noop_baseline, spec_car_mdd, delta, classification,
                        applied_op, applied_threshold, applied_gate, applied_boost,
                        recorded_at, is_sweep_variant)
                       VALUES (?, ?, 1, 'cur_bake',
                               1.98, ?, ?, 'neutral',
                               '>', '5', NULL, 1.10, '2026-01-01', 0)""",
                    (fid, f'S001_R1_x_{fid}', 1.98 + delta, delta))

    def test_returns_only_above_trigger_threshold(self, tmp_db):
        from s001.fundamental_probes import pick_sweep_candidates
        self._seed(tmp_db)
        out = pick_sweep_candidates(tmp_db, k=10, bake_hash='cur_bake')
        ids = [r['id'] for r in out]
        # field 2 has delta below trigger; should be excluded
        assert 2 not in ids
        assert set(ids) == {1, 3}

    def test_sorted_by_max_abs_delta_desc(self, tmp_db):
        from s001.fundamental_probes import pick_sweep_candidates
        self._seed(tmp_db)
        out = pick_sweep_candidates(tmp_db, k=10, bake_hash='cur_bake')
        ids = [r['id'] for r in out]
        # Field 3 has largest |delta|=0.0020, then field 1 (0.0008)
        assert ids == [3, 1]

    def test_respects_k_limit(self, tmp_db):
        from s001.fundamental_probes import pick_sweep_candidates
        self._seed(tmp_db)
        out = pick_sweep_candidates(tmp_db, k=1, bake_hash='cur_bake')
        assert len(out) == 1
        assert out[0]['id'] == 3  # highest |delta|

    def test_skips_fields_with_sweep_phase_nonzero(self, tmp_db):
        from s001.fundamental_probes import pick_sweep_candidates
        self._seed(tmp_db)
        # Mark field 3 as sweep_phase=1 (already swept)
        import sqlite3
        with sqlite3.connect(tmp_db) as con:
            con.execute("UPDATE fundamental_fields SET sweep_phase = 1 WHERE id = 3")
        out = pick_sweep_candidates(tmp_db, k=10, bake_hash='cur_bake')
        ids = [r['id'] for r in out]
        assert 3 not in ids
        assert ids == [1]

    def test_empty_when_no_eligible_fields(self, tmp_db):
        from s001.fundamental_probes import pick_sweep_candidates
        # Don't seed anything — empty DB has no eligible fields
        out = pick_sweep_candidates(tmp_db, k=10, bake_hash='cur_bake')
        assert out == []

    def test_uses_default_min_abs_delta_0001(self, tmp_db):
        from s001.fundamental_probes import pick_sweep_candidates
        self._seed(tmp_db)
        # Default min_abs_delta=0.0001 (default)
        out = pick_sweep_candidates(tmp_db, k=10, bake_hash='cur_bake')
        assert {r['id'] for r in out} == {1, 3}
        # With higher trigger 0.0010, only field 3 qualifies
        out2 = pick_sweep_candidates(tmp_db, k=10, bake_hash='cur_bake', min_abs_delta=0.0010)
        assert {r['id'] for r in out2} == {3}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestPickSweepCandidates -v`
Expected: ImportError on `pick_sweep_candidates`.

- [ ] **Step 3: Implement**

Append to `/home/txy/qc_work/data/s001/fundamental_probes.py`:

```python
def pick_sweep_candidates(db_path, k, bake_hash, min_abs_delta=0.0001):
    """Pick up to k fields with |Phase 1 delta| >= min_abs_delta AND sweep_phase = 0.

    Sorted by max(|delta|) DESC so highest-impact fields sweep first.
    """
    sql = """
    SELECT f.*, MAX(ABS(p.delta)) AS max_abs_delta
    FROM fundamental_fields f
    JOIN probe_results p ON p.field_id = f.id
    WHERE p.bake_hash = ?
      AND p.is_sweep_variant = 0
      AND ABS(p.delta) >= ?
      AND f.sweep_phase = 0
      AND f.probe_threshold IS NOT NULL
    GROUP BY f.id
    ORDER BY max_abs_delta DESC
    LIMIT ?
    """
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(sql, (bake_hash, min_abs_delta, k))
        return [dict(r) for r in cur.fetchall()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestPickSweepCandidates -v`
Expected: 6 passed.

---

## Task 5: `update_sweep_winner`

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Append the failing test**

Append to `/home/txy/qc_work/data/tests/test_fundamental_probes.py`:

```python
class TestUpdateSweepWinner:
    def test_writes_max_delta_variant(self, tmp_db):
        from s001.fundamental_probes import update_sweep_winner
        import sqlite3
        with sqlite3.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute(
                """INSERT INTO fundamental_fields
                   (id, category, field_name, accessor, container, period,
                    probe_op, probe_threshold, probe_gate, probe_boost,
                    classification, data_type_hint, sweep_phase)
                   VALUES (1, 'v', 'a', '_vr_z.a', 'valuation_ratios', NULL,
                           '>', '5', NULL, 1.10, 'untested', 'numeric', 1)""")
            # 3 sweep variants, max delta is on (1.06, .05)
            for mag, gate, delta in [(1.04, '.10', 0.0010),
                                      (1.06, '.05', 0.0035),
                                      (1.08, '.15', 0.0008)]:
                cur.execute(
                    """INSERT INTO probe_results
                       (field_id, experiment_name, round_n, bake_hash,
                        noop_baseline, spec_car_mdd, delta, classification,
                        applied_op, applied_threshold, applied_gate, applied_boost,
                        recorded_at, is_sweep_variant)
                       VALUES (1, ?, 1, 'cur_bake',
                               1.98, ?, ?, 'hot',
                               '>', '5', ?, ?, '2026-01-01', 1)""",
                    (f'S001_R1_sw_vr_a_m{int(mag*100)}_g{gate.replace(".","")}',
                     1.98 + delta, delta, f'decline > {gate}', mag))
            update_sweep_winner(con, 1, 'cur_bake')
            cur.execute(
                """SELECT sweep_winner_op, sweep_winner_threshold,
                          sweep_winner_gate, sweep_winner_boost,
                          sweep_winner_delta, sweep_phase
                   FROM fundamental_fields WHERE id = 1""")
            op, thr, gate, boost, delta, phase = cur.fetchone()
        assert op == '>'
        assert thr == '5'
        assert gate == 'decline > .05'
        assert abs(boost - 1.06) < 1e-6
        assert abs(delta - 0.0035) < 1e-6
        assert phase == 2

    def test_no_variants_no_update(self, tmp_db):
        from s001.fundamental_probes import update_sweep_winner
        import sqlite3
        with sqlite3.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute(
                """INSERT INTO fundamental_fields
                   (id, category, field_name, accessor, container, period,
                    probe_op, probe_threshold, probe_gate, probe_boost,
                    classification, data_type_hint, sweep_phase)
                   VALUES (1, 'v', 'a', '_vr_z.a', 'valuation_ratios', NULL,
                           '>', '5', NULL, 1.10, 'untested', 'numeric', 1)""")
            # No sweep variants exist
            update_sweep_winner(con, 1, 'cur_bake')
            cur.execute(
                "SELECT sweep_winner_op, sweep_phase FROM fundamental_fields WHERE id = 1")
            op, phase = cur.fetchone()
        assert op is None
        assert phase == 1  # unchanged because no variants
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestUpdateSweepWinner -v`
Expected: ImportError on `update_sweep_winner`.

- [ ] **Step 3: Implement**

Append to `/home/txy/qc_work/data/s001/fundamental_probes.py`:

```python
def update_sweep_winner(con, field_id, bake_hash):
    """After Phase 2 sweep completes for a field, find the variant with
    max delta and write it to fundamental_fields.sweep_winner_* columns.
    Set sweep_phase = 2.

    Caller passes an open sqlite3 connection so the update is part of
    the same transaction as the result inserts.
    """
    cur = con.cursor()
    cur.execute("""
        SELECT applied_op, applied_threshold, applied_gate, applied_boost, delta
        FROM probe_results
        WHERE field_id = ? AND bake_hash = ? AND is_sweep_variant = 1
        ORDER BY delta DESC LIMIT 1
    """, (field_id, bake_hash))
    row = cur.fetchone()
    if row is None:
        return  # no sweep variants yet; not ready
    op, thr, gate, boost, delta = row
    cur.execute("""
        UPDATE fundamental_fields
        SET sweep_winner_op = ?, sweep_winner_threshold = ?,
            sweep_winner_gate = ?, sweep_winner_boost = ?,
            sweep_winner_delta = ?, sweep_phase = 2
        WHERE id = ?
    """, (op, thr, gate, boost, delta, field_id))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestUpdateSweepWinner -v`
Expected: 2 passed.

---

## Task 6: `emit_probes_for_db` with `k_sweep_fields`

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_emit_probes.py`

- [ ] **Step 1: Append the failing test**

Append to `/home/txy/qc_work/data/tests/test_emit_probes.py`:

```python
def test_emit_includes_phase2_sweep_when_eligible(tmp_db):
    """If a field has a Phase 1 delta >= 0.0001 and sweep_phase = 0,
    emit_probes_for_db includes its 15-spec sweep."""
    from scripts.emit_probes import emit_probes_for_db
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                classification, data_type_hint, sweep_phase)
               VALUES (1, 'v', 'a', '_vr_z.a', 'valuation_ratios', NULL,
                       '>', '5', 'decline > .12', 1.10, 'untested', 'numeric', 0)""")
        cur.execute(
            """INSERT INTO probe_results
               (field_id, experiment_name, round_n, bake_hash,
                noop_baseline, spec_car_mdd, delta, classification,
                applied_op, applied_threshold, applied_gate, applied_boost,
                recorded_at, is_sweep_variant)
               VALUES (1, 'S001_R1_vr_a_gt5', 1, 'cur_bake',
                       1.98, 1.9805, 0.0005, 'neutral',
                       '>', '5', 'decline > .12', 1.10, '2026-01-01', 0)""")
        con.execute("""INSERT OR REPLACE INTO settings
            (category, key, value, description, updated_at)
            VALUES ('strategy', 'current_bake_hash', 'cur_bake', 't', CURRENT_TIMESTAMP)""")
    specs = emit_probes_for_db(db_path=tmp_db, round_n=2,
                               k_new=0, k_verify=0, k_sweep_fields=3)
    assert len(specs) == 15
    names = [n for n, _ in specs]
    for n in names:
        assert n.startswith('S001_R2_sw_vr_a_m')


def test_emit_marks_sweep_phase_after_emission(tmp_db):
    """After emit_probes_for_db emits sweep for a field, fundamental_fields
    row has sweep_phase = 1 (sweep in flight)."""
    from scripts.emit_probes import emit_probes_for_db
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                classification, data_type_hint, sweep_phase)
               VALUES (1, 'v', 'a', '_vr_z.a', 'valuation_ratios', NULL,
                       '>', '5', 'decline > .12', 1.10, 'untested', 'numeric', 0)""")
        cur.execute(
            """INSERT INTO probe_results
               (field_id, experiment_name, round_n, bake_hash,
                noop_baseline, spec_car_mdd, delta, classification,
                applied_op, applied_threshold, applied_gate, applied_boost,
                recorded_at, is_sweep_variant)
               VALUES (1, 'S001_R1_vr_a_gt5', 1, 'cur_bake',
                       1.98, 1.9805, 0.0005, 'neutral',
                       '>', '5', 'decline > .12', 1.10, '2026-01-01', 0)""")
        con.execute("""INSERT OR REPLACE INTO settings
            (category, key, value, description, updated_at)
            VALUES ('strategy', 'current_bake_hash', 'cur_bake', 't', CURRENT_TIMESTAMP)""")
    emit_probes_for_db(db_path=tmp_db, round_n=2,
                       k_new=0, k_verify=0, k_sweep_fields=3)
    with sqlite3.connect(tmp_db) as con:
        sweep_phase = con.execute(
            "SELECT sweep_phase FROM fundamental_fields WHERE id = 1"
        ).fetchone()[0]
    assert sweep_phase == 1


def test_emit_combines_phase1_and_phase2(tmp_db):
    """k_new=2 + k_sweep_fields=1 → 2 Phase 1 specs + 15 Phase 2 specs."""
    from scripts.emit_probes import emit_probes_for_db
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        # Phase 1 candidates (untested, no probe_results on cur_bake)
        for fid, name in [(2, 'b'), (3, 'c')]:
            cur.execute(
                """INSERT INTO fundamental_fields
                   (id, category, field_name, accessor, container, period,
                    probe_op, probe_threshold, probe_gate, probe_boost,
                    classification, data_type_hint, sweep_phase)
                   VALUES (?, 'v', ?, ?, 'valuation_ratios', NULL,
                           '>', '5', 'decline > .12', 1.10, 'untested', 'numeric', 0)""",
                (fid, name, f'_vr_z.{name}'))
        # Phase 2 candidate (has probe_results with delta >= 0.0001)
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                classification, data_type_hint, sweep_phase)
               VALUES (1, 'v', 'a', '_vr_z.a', 'valuation_ratios', NULL,
                       '>', '5', 'decline > .12', 1.10, 'untested', 'numeric', 0)""")
        cur.execute(
            """INSERT INTO probe_results
               (field_id, experiment_name, round_n, bake_hash,
                noop_baseline, spec_car_mdd, delta, classification,
                applied_op, applied_threshold, applied_gate, applied_boost,
                recorded_at, is_sweep_variant)
               VALUES (1, 'S001_R1_vr_a_gt5', 1, 'cur_bake',
                       1.98, 1.9810, 0.0010, 'neutral',
                       '>', '5', 'decline > .12', 1.10, '2026-01-01', 0)""")
        con.execute("""INSERT OR REPLACE INTO settings
            (category, key, value, description, updated_at)
            VALUES ('strategy', 'current_bake_hash', 'cur_bake', 't', CURRENT_TIMESTAMP)""")
    specs = emit_probes_for_db(db_path=tmp_db, round_n=3,
                               k_new=2, k_verify=0, k_sweep_fields=1)
    assert len(specs) == 17  # 2 Phase 1 + 15 Phase 2
    sweep_count = sum(1 for n, _ in specs if '_sw_' in n)
    assert sweep_count == 15
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/txy/qc_work/data && pytest tests/test_emit_probes.py -v`
Expected: 3 new tests fail (`emit_probes_for_db` lacks `k_sweep_fields`).

- [ ] **Step 3: Modify `emit_probes_for_db`**

In `/home/txy/qc_work/data/s001/fundamental_probes.py`, replace the existing `emit_probes_for_db` with:

```python
def emit_probes_for_db(db_path, round_n, k_new, k_verify=0,
                       k_sweep_fields=0, include_bind=False):
    """Emit (name, code) tuples for the given round.

    - k_new Phase 1 default-template probes for untested fields.
    - k_sweep_fields × 15 Phase 2 sweep specs for fields with prior delta >= 0.0001.
    - k_verify rep0/rep1/rep2 specs for hot-classified fields (re-render with
      same template; spec name suffix '_VERIFY_repN').

    Pre-flight: probe_op valid, probe_threshold present, ast.parse succeeds.
    """
    VALID_OPS = {'>', '>=', '<', '<=', 'eq', 'in'}
    bake_hash = current_bake_hash(db_path)
    new_picks = pick_fields(db_path, k=k_new, classification='untested',
                            bake_hash=bake_hash)
    sweep_picks = pick_sweep_candidates(db_path, k=k_sweep_fields,
                                        bake_hash=bake_hash) if k_sweep_fields > 0 else []
    hot_picks = pick_fields(db_path, k=k_verify, classification='hot',
                            bake_hash=bake_hash) if k_verify > 0 else []

    out = []
    import ast as _ast

    # Phase 1
    for row in new_picks:
        if row['probe_op'] not in VALID_OPS:
            continue
        if row['probe_threshold'] is None:
            continue
        body = render_probe(row)
        scaffold = "def _f():\n  for sym in []:\n" + body + "\n   pass\n"
        try:
            _ast.parse(scaffold)
        except SyntaxError:
            continue
        name = spec_name(row, round_n)
        if include_bind:
            body = BIND + body
        out.append((name, body))

    # Phase 2 sweep
    sweep_field_ids_emitted = []
    for row in sweep_picks:
        sweep_specs = emit_phase2_sweep(row, round_n)
        if include_bind:
            sweep_specs = [(n, BIND + b) for n, b in sweep_specs]
        out.extend(sweep_specs)
        sweep_field_ids_emitted.append(row['id'])

    # Mark sweep_phase = 1 in a single transaction so the picker won't
    # re-emit them next round
    if sweep_field_ids_emitted:
        with sqlite3.connect(db_path) as con:
            for fid in sweep_field_ids_emitted:
                con.execute(
                    "UPDATE fundamental_fields SET sweep_phase = 1 WHERE id = ?",
                    (fid,))

    # Hot verifies (existing v1 behavior — unchanged shape)
    for row in hot_picks:
        for rep in range(3):
            body = render_probe(row)
            scaffold = "def _f():\n  for sym in []:\n" + body + "\n   pass\n"
            try:
                _ast.parse(scaffold)
            except SyntaxError:
                continue
            name = f"{spec_name(row, round_n)}_VERIFY_rep{rep}"[:100]
            if include_bind:
                body = BIND + body
            out.append((name, body))

    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/txy/qc_work/data && pytest tests/test_emit_probes.py -v`
Expected: 6 passed (3 v1 + 3 v2).

---

## Task 7: `score_probes.py` sweep regex

**Files:**
- Modify: `/home/txy/qc_work/data/scripts/score_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_score_probes.py`

- [ ] **Step 1: Append the failing test**

Append to `/home/txy/qc_work/data/tests/test_score_probes.py`:

```python
def test_score_recognizes_sweep_name(tmp_db):
    """Sweep spec name → INSERT into probe_results with is_sweep_variant=1
    and reconstructed applied_* values."""
    from scripts.score_probes import score_round
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                classification, data_type_hint, sweep_phase)
               VALUES (1, 'v', 'pe_ratio', '_vr_z.pe_ratio', 'valuation_ratios', NULL,
                       '<', '15', 'decline > .12', 1.10, 'untested', 'numeric', 1)""")
        # 3 NOOPs for baseline
        for i, v in enumerate([1.8998, 1.9000, 1.9002]):
            cur.execute(
                "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
                (f'S001_R500_VBAKE40_NOOP_{i}', v))
        # Sweep variant (mag=1.06, gate=.05) with delta = 0.005
        cur.execute(
            "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
            ('S001_R500_sw_vr_pe_ratio_m106_g05', 1.9050))

    score_round(db_path=tmp_db, round_n=500, bake_hash='c0ed7f31')

    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT is_sweep_variant, applied_boost, applied_gate, classification, delta "
            "FROM probe_results WHERE experiment_name = 'S001_R500_sw_vr_pe_ratio_m106_g05'")
        row = cur.fetchone()
    assert row is not None, 'sweep spec not scored'
    is_sweep, boost, gate, cls, delta = row
    assert is_sweep == 1
    assert abs(boost - 1.06) < 1e-6
    assert gate == 'decline > .05'
    assert cls == 'hot'  # delta=0.005 > 0.0015


def test_score_calls_update_sweep_winner_when_15_complete(tmp_db):
    """When all 15 sweep variants for a field are scored in one round,
    sweep_winner_* and sweep_phase=2 are populated."""
    from scripts.score_probes import score_round
    from s001.fundamental_probes import SWEEP_MAGS, SWEEP_GATES
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                classification, data_type_hint, sweep_phase)
               VALUES (1, 'v', 'pe_ratio', '_vr_z.pe_ratio', 'valuation_ratios', NULL,
                       '<', '15', 'decline > .12', 1.10, 'untested', 'numeric', 1)""")
        # 3 NOOPs
        for i, v in enumerate([1.8998, 1.9000, 1.9002]):
            cur.execute(
                "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
                (f'S001_R501_VBAKE40_NOOP_{i}', v))
        # All 15 sweep variants. Best is mag=1.06, gate=.05 with delta=0.005.
        for mag in SWEEP_MAGS:
            for gate in SWEEP_GATES:
                if mag == '1.06' and gate == '.05':
                    car_mdd = 1.9050  # delta = 0.005, the best
                else:
                    car_mdd = 1.9005  # delta = 0.0005
                mag_short = mag.replace('.', '')
                gate_short = gate.replace('.', '').lstrip('-') or '0'
                cur.execute(
                    "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
                    (f'S001_R501_sw_vr_pe_ratio_m{mag_short}_g{gate_short}', car_mdd))

    score_round(db_path=tmp_db, round_n=501, bake_hash='c0ed7f31')

    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT sweep_phase, sweep_winner_boost, sweep_winner_gate, sweep_winner_delta "
            "FROM fundamental_fields WHERE id = 1")
        phase, boost, gate, delta = cur.fetchone()
    assert phase == 2
    assert abs(boost - 1.06) < 1e-6
    assert gate == 'decline > .05'
    assert abs(delta - 0.005) < 1e-6


def test_score_partial_sweep_no_winner(tmp_db):
    """If only some variants score (not all 15), sweep_winner stays NULL
    and sweep_phase stays at 1."""
    from scripts.score_probes import score_round
    import sqlite3
    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                classification, data_type_hint, sweep_phase)
               VALUES (1, 'v', 'pe_ratio', '_vr_z.pe_ratio', 'valuation_ratios', NULL,
                       '<', '15', 'decline > .12', 1.10, 'untested', 'numeric', 1)""")
        for i, v in enumerate([1.8998, 1.9000, 1.9002]):
            cur.execute(
                "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
                (f'S001_R502_VBAKE40_NOOP_{i}', v))
        # Only 5 of 15 sweep variants scored
        for mag, gate in [('1.04', '.05'), ('1.06', '.05'), ('1.08', '.10'),
                           ('1.10', '.15'), ('1.13', '.10')]:
            mag_short = mag.replace('.', '')
            gate_short = gate.replace('.', '').lstrip('-') or '0'
            cur.execute(
                "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
                (f'S001_R502_sw_vr_pe_ratio_m{mag_short}_g{gate_short}', 1.9020))

    score_round(db_path=tmp_db, round_n=502, bake_hash='c0ed7f31')

    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT sweep_phase, sweep_winner_boost FROM fundamental_fields WHERE id = 1")
        phase, boost = cur.fetchone()
    assert phase == 1  # not yet 2
    assert boost is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/txy/qc_work/data && pytest tests/test_score_probes.py -v`
Expected: 3 new tests fail (sweep regex doesn't exist).

- [ ] **Step 3: Modify `score_probes.py`**

In `/home/txy/qc_work/data/scripts/score_probes.py`, add a sweep-name regex and parser, modify `score_round` to recognize both default and sweep specs, and call `update_sweep_winner` after scoring. Replace the file with this complete revision:

```python
"""Score probe specs from a completed round: compute deltas, classify, write
probe_results, refresh field classifications and sweep winners.

Usage:
  python -m scripts.score_probes --round 407 --bake-hash <md5>
"""
import argparse
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from s001.fundamental_probes import (  # noqa: E402
    classify_delta, field_rollup, CONTAINER_SHORT, _threshold_short,
    update_sweep_winner, SWEEP_MAGS, SWEEP_GATES,
)

CONTAINER_FROM_SHORT = {v: k for k, v in CONTAINER_SHORT.items()}


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# Default probe spec name pattern (existing v1 behavior).
SPEC_NAME_RE = re.compile(
    r'^S001_R(?P<round>\d+)_(?P<cs>[a-z]+)_(?P<field>[a-z0-9_]+?)_'
    r'(?P<op>gt|gte|lt|lte|eq|in)(?P<thr>.+)$'
)

# v2: Phase 2 sweep spec name pattern.
SWEEP_NAME_RE = re.compile(
    r'^S001_R(?P<round>\d+)_sw_(?P<cs>[a-z]+)_(?P<field>[a-z0-9_]+?)'
    r'_m(?P<mag>\d+)_g(?P<gate>\d+)$'
)


def _parse_probe_spec_name(name):
    """Return (container, field_name, op_short, thr_short) for default probes,
    or None if name doesn't match. Used for is_sweep_variant=0 flow."""
    m = SPEC_NAME_RE.match(name)
    if not m:
        return None
    cs = m.group('cs')
    cont = CONTAINER_FROM_SHORT.get(cs)
    if cont is None:
        return None
    return cont, m.group('field'), m.group('op'), m.group('thr')


def _parse_sweep_spec_name(name):
    """Return (container, field_name, mag, gate) for sweep specs, or None."""
    m = SWEEP_NAME_RE.match(name)
    if not m:
        return None
    cs = m.group('cs')
    cont = CONTAINER_FROM_SHORT.get(cs)
    if cont is None:
        return None
    mag_short = m.group('mag')
    gate_short = m.group('gate')
    # Reconstruct the actual mag and gate values used by emit_phase2_sweep
    # by matching against the canonical SWEEP_MAGS / SWEEP_GATES lists.
    mag_canonical = next((x for x in SWEEP_MAGS if x.replace('.', '') == mag_short), None)
    gate_canonical = next((x for x in SWEEP_GATES if x.replace('.', '').lstrip('-') == gate_short), None)
    if mag_canonical is None or gate_canonical is None:
        return None
    return cont, m.group('field'), mag_canonical, gate_canonical


def _noop_baseline(cur, round_n):
    cur.execute(
        "SELECT car_mdd FROM experiments "
        "WHERE name LIKE ? AND status IN ('imported', 'success') AND car_mdd IS NOT NULL",
        (f'S001_R{round_n}_VBAKE%_NOOP_%',))
    vals = [r[0] for r in cur.fetchall()]
    assert len(vals) >= 1, f'Round {round_n} has no NOOP experiments'
    spread = max(vals) - min(vals)
    assert spread <= 0.0005, (
        f'Round {round_n} NOOP spread {spread:.5f} > 0.0005 — base nondeterministic')
    return sum(vals) / len(vals)


def score_round(db_path, round_n, bake_hash):
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        baseline = _noop_baseline(cur, round_n)
        now = _now_iso()

        cur.execute(
            "SELECT name, car_mdd FROM experiments "
            "WHERE name LIKE ? AND status IN ('imported', 'success') AND car_mdd IS NOT NULL",
            (f'S001_R{round_n}_%',))
        touched_field_ids = set()
        sweep_field_ids = set()
        n_results = 0
        for row in cur.fetchall():
            # Try sweep regex first (more specific)
            sweep_parsed = _parse_sweep_spec_name(row['name'])
            if sweep_parsed is not None:
                container, field_name, mag, gate = sweep_parsed
                cur.execute(
                    "SELECT * FROM fundamental_fields WHERE container = ? AND field_name = ?",
                    (container, field_name))
                f = cur.fetchone()
                if f is None:
                    continue
                delta = row['car_mdd'] - baseline
                cls = classify_delta(delta)
                applied_op = f['probe_op']
                applied_threshold = f['probe_threshold']
                applied_gate = f'decline > {gate}'
                applied_boost = float(mag)
                try:
                    cur.execute(
                        """INSERT INTO probe_results
                           (field_id, experiment_name, round_n, bake_hash, noop_baseline,
                            spec_car_mdd, delta, classification, applied_op,
                            applied_threshold, applied_gate, applied_boost,
                            recorded_at, is_sweep_variant)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                        (f['id'], row['name'], round_n, bake_hash, baseline,
                         row['car_mdd'], delta, cls, applied_op,
                         applied_threshold, applied_gate, applied_boost, now))
                    n_results += 1
                except sqlite3.IntegrityError:
                    pass
                touched_field_ids.add(f['id'])
                sweep_field_ids.add(f['id'])
                continue

            # Default probe regex (existing v1 behavior)
            parsed = _parse_probe_spec_name(row['name'])
            if parsed is None:
                continue
            container, field_name, op_short, thr_short = parsed
            cur.execute(
                "SELECT * FROM fundamental_fields WHERE container = ? AND field_name = ?",
                (container, field_name))
            f = cur.fetchone()
            if f is None:
                continue
            if f['probe_threshold'] is not None:
                expected_thr = _threshold_short(f['probe_threshold'], f['probe_op'])
                if thr_short != expected_thr:
                    continue
            delta = row['car_mdd'] - baseline
            cls = classify_delta(delta)
            try:
                cur.execute(
                    """INSERT INTO probe_results
                       (field_id, experiment_name, round_n, bake_hash, noop_baseline,
                        spec_car_mdd, delta, classification, applied_op,
                        applied_threshold, applied_gate, applied_boost,
                        recorded_at, is_sweep_variant)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                    (f['id'], row['name'], round_n, bake_hash, baseline,
                     row['car_mdd'], delta, cls, f['probe_op'],
                     f['probe_threshold'], f['probe_gate'], f['probe_boost'], now))
                n_results += 1
            except sqlite3.IntegrityError:
                pass
            touched_field_ids.add(f['id'])

        # Refresh field-row classification for each touched field
        for fid in touched_field_ids:
            cur.execute(
                "SELECT classification FROM probe_results "
                "WHERE field_id = ? AND bake_hash = ?", (fid, bake_hash))
            results = [{'classification': r[0]} for r in cur.fetchall()]
            rollup = field_rollup(results)
            cur.execute(
                "UPDATE fundamental_fields SET classification = ?, "
                "last_classified_at = ? WHERE id = ?", (rollup, now, fid))

        # For each field that got sweep results, check if all 15 are present
        # and update sweep_winner if so.
        for fid in sweep_field_ids:
            cur.execute(
                "SELECT COUNT(*) FROM probe_results "
                "WHERE field_id = ? AND bake_hash = ? AND is_sweep_variant = 1",
                (fid, bake_hash))
            count = cur.fetchone()[0]
            if count >= len(SWEEP_MAGS) * len(SWEEP_GATES):
                update_sweep_winner(con, fid, bake_hash)

        return {'n_results': n_results, 'baseline': baseline,
                'fields_touched': len(touched_field_ids),
                'sweep_fields': len(sweep_field_ids)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--round', dest='round_n', type=int, required=True)
    p.add_argument('--bake-hash', required=True)
    p.add_argument('--db', default='/home/txy/qc_work/data/S001.db')
    args = p.parse_args()
    out = score_round(db_path=args.db, round_n=args.round_n, bake_hash=args.bake_hash)
    print(f"Round {args.round_n}: scored {out['n_results']} probes, "
          f"baseline={out['baseline']:.4f}, "
          f"fields_touched={out['fields_touched']}, "
          f"sweep_fields={out['sweep_fields']}")


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/txy/qc_work/data && pytest tests/test_score_probes.py -v`
Expected: 8 passed (5 v1 + 3 v2).

---

## Task 8: Apply migration to real S001.db + seed settings

**Files:**
- (none — operational manual step)

- [ ] **Step 1: Backup the production DB**

```bash
cp /home/txy/qc_work/data/S001.db /home/txy/qc_work/data/S001.db.pre_v2.bak
ls -lh /home/txy/qc_work/data/S001.db.pre_v2.bak
```

- [ ] **Step 2: Apply v2 migration**

```bash
cd /home/txy/qc_work/data && python3 -m scripts.migrate_schema
```
Expected output: `Migration applied to /home/txy/qc_work/data/S001.db`.

- [ ] **Step 3: Verify v2 schema**

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
cur = con.cursor()
cur.execute('PRAGMA table_info(fundamental_fields)')
cols = {r[1] for r in cur.fetchall()}
v2 = {'sweep_phase', 'sweep_winner_op', 'sweep_winner_threshold',
      'sweep_winner_gate', 'sweep_winner_boost', 'sweep_winner_delta'}
print('fundamental_fields v2 cols present:', v2 <= cols)

cur.execute('PRAGMA table_info(probe_results)')
prc = {r[1] for r in cur.fetchall()}
print('probe_results.is_sweep_variant present:', 'is_sweep_variant' in prc)

cur.execute(\"SELECT name FROM sqlite_master WHERE type='index' AND name='idx_pr_field_bake'\")
print('idx_pr_field_bake exists:', cur.fetchone() is not None)
"
```
Expected: all three lines print `True`.

- [ ] **Step 4: Seed settings.current_bake_hash**

The current production base hash is BAKE-44 = `d941d57fdf50faa8a42ce2902e0c9d00`. Seed it:

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
con.execute('''INSERT OR REPLACE INTO settings
    (category, key, value, description, updated_at)
    VALUES ('strategy', 'current_bake_hash',
            'd941d57fdf50faa8a42ce2902e0c9d00',
            'BAKE-44: cfsap_decl_05 mag 1.06 baked',
            CURRENT_TIMESTAMP)''')
con.commit()
print('seeded current_bake_hash =', con.execute(
    \"SELECT value FROM settings WHERE category='strategy' AND key='current_bake_hash'\"
).fetchone()[0])
"
```
Expected: `seeded current_bake_hash = d941d57fdf50faa8a42ce2902e0c9d00`.

- [ ] **Step 5: Verify all production tests still pass**

Run: `cd /home/txy/qc_work/data && pytest tests/ 2>&1 | tail -3`
Expected: 100% pass; new tests added by Tasks 0-7 also pass.

---

## Task 9: First sweep-enabled generator (R463)

**Files:**
- Create: `/home/txy/qc_work/data/gen_s001_R463.py`

- [ ] **Step 1: Write the generator**

Create `/home/txy/qc_work/data/gen_s001_R463.py`:

```python
"""R463 — first round on BAKE-44 base with v2 auto-sweep enabled.

Layout:
  - 3 NOOP (BAKE-44 baseline ~1.9958)
  - 3 VERIFY no-change baseline
  - 3 VERIFY grad_0194 baseline (still in-base from BAKE-43)
  - 10 Phase 1 default-template probes (k_new=10)
  - 45 Phase 2 sweep specs (k_sweep_fields=3 × 15 variants)
  = 64
"""
import ast
import hashlib
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s001.fundamental_probes import emit_probes_for_db, BIND  # noqa: E402

BASE = '/home/txy/qc_work/data/s001/s001_20260425_base.py'
EXPECTED = 'd941d57fdf50faa8a42ce2902e0c9d00'  # BAKE-44
with open(BASE) as f:
    base_code = f.read()
got = hashlib.md5(base_code.encode()).hexdigest()
assert got == EXPECTED, f'base hash mismatch: {got}'
print(f'Base verified (BAKE-44): {EXPECTED}')

ANCHOR = '   candidates.append((sym, score, conv))'
specs = []

# 3 NOOP
for i in range(3):
    code = base_code.replace(ANCHOR, f'   # vbake44_noop_{i}\n' + ANCHOR)
    specs.append((f'S001_R463_VBAKE44_NOOP_{i}', code))

# 3 VERIFY (no-change BAKE-44 baseline)
for i in range(3):
    code = base_code.replace(ANCHOR, f'   # verify_bake44_baseline_rep{i}\n' + ANCHOR)
    specs.append((f'S001_R463_VERIFY_bake44_rep{i}', code))

# 3 VERIFY grad_0194
GRAD = "GRAD_RANGE    = .0194   # BAKE-43 R448-R449: .020→.0194 (joint with b13t2 1.40 + b22xb .87, +0.0034 verified 5/5 deterministic on BAKE-42)"
for i in range(3):
    code = base_code.replace(ANCHOR, f'   # verify_grad0194_rep{i}\n' + ANCHOR)
    specs.append((f'S001_R463_VERIFY_grad0194_rep{i}', code))

# Library-emitted Phase 1 + Phase 2 sweep
auto = emit_probes_for_db(
    db_path='/home/txy/qc_work/data/S001.db',
    round_n=463, k_new=10, k_verify=0, k_sweep_fields=3, include_bind=False)
print(f'Auto-emitted {len(auto)} probes (Phase 1 + Phase 2)')

for name, body in auto:
    code = base_code.replace(ANCHOR, BIND + body + '\n' + ANCHOR)
    specs.append((name, code))

print(f'Total: {len(specs)}')
print(f'Unique: {len({hashlib.md5(c.encode()).hexdigest() for n, c in specs})}/{len(specs)}')
# Note: round size may exceed 64. Per memory rule feedback_s001_round_size_flexible,
# 64 is a floor, not a cap — do NOT truncate to fit 64.

for name, code in specs:
    try:
        ast.parse(code)
    except SyntaxError as e:
        print(f'SYNTAX ERROR in {name}: {e}')
        sys.exit(1)
print('All parse OK')

con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
cur = con.cursor()
inserted = 0
for n, c in specs:
    h = hashlib.md5(c.encode()).hexdigest()
    try:
        cur.execute(
            "INSERT INTO backtest_queue "
            "(name, code, status, priority, submitted_at, code_hash, project_id) "
            "VALUES (?, ?, 'queued', ?, ?, ?, NULL)",
            (n, c, 1 if 'VBAKE' in n or 'VERIFY' in n else 5,
             '2026-05-04 21:30:00', h))
        inserted += 1
    except sqlite3.IntegrityError as e:
        print(f'Skip {n}: {e}')
con.commit()
print(f'Inserted {inserted} R463 specs')
```

- [ ] **Step 2: Run the generator**

Run: `cd /home/txy/qc_work/data && python3 gen_s001_R463.py`
Expected output:
- `Base verified (BAKE-44): d941d57fdf50faa8a42ce2902e0c9d00`
- `Auto-emitted 55 probes (Phase 1 + Phase 2)` (10 + 45) — actual count may be less if not enough sweep candidates exist
- `Total: 64` (or 64 minus shortfall if Phase 2 was undersized)
- `All parse OK`
- `Inserted 64 R463 specs`

- [ ] **Step 3: Inspect the queued specs**

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
cur = con.cursor()
cur.execute(\"SELECT COUNT(*) FROM backtest_queue WHERE name LIKE 'S001_R463_sw_%'\")
print('Phase 2 sweep specs queued:', cur.fetchone()[0])
cur.execute(\"SELECT name FROM backtest_queue WHERE name LIKE 'S001_R463_sw_%' LIMIT 5\")
print('Sample names:')
for (n,) in cur.fetchall(): print(f'  {n}')
"
```
Expected: 45 sweep specs (or fewer if k_sweep_fields didn't hit 3); names follow `S001_R463_sw_<container>_<field>_m<NNN>_g<NN>` pattern.

- [ ] **Step 4: Verify sweep_phase marked**

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
cur = con.cursor()
cur.execute(\"SELECT field_name, sweep_phase FROM fundamental_fields WHERE sweep_phase = 1\")
print('Fields with sweep_phase=1 (sweep in flight):')
for r in cur.fetchall(): print(f'  {r[0]:35s} sweep_phase={r[1]}')
"
```
Expected: up to 3 fields shown with `sweep_phase = 1`. (If 0 are shown, no Phase 1 results existed yet on BAKE-44 with `|delta| ≥ 0.0001` — that's possible early on.)

---

## Task 10: End-to-end smoke (after R463 backtests complete)

**Files:**
- (none — operational manual step)

- [ ] **Step 1: Wait for R463 to complete in cron**

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
cur = con.cursor()
cur.execute(\"SELECT status, COUNT(*) FROM backtest_queue WHERE name LIKE 'S001_R463_%' GROUP BY status\")
for r in cur.fetchall(): print(' ', r)
"
```
Expected: `('done', 64)`. If not, wait and retry.

- [ ] **Step 2: Score R463**

```bash
cd /home/txy/qc_work/data && python3 -m scripts.score_probes --round 463 --bake-hash d941d57fdf50faa8a42ce2902e0c9d00
```
Expected output:
- `Round 463: scored N probes, baseline=1.99XX, fields_touched=M, sweep_fields=K` where N matches the count of probes (Phase 1 + Phase 2), K ≤ 3.

- [ ] **Step 3: Inspect probe_results**

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
cur = con.cursor()
cur.execute(\"SELECT is_sweep_variant, classification, COUNT(*) FROM probe_results WHERE round_n=463 GROUP BY is_sweep_variant, classification\")
print('R463 probe_results breakdown:')
for r in cur.fetchall(): print(f'  is_sweep={r[0]}  {r[1]:10s} {r[2]}')

cur.execute(\"SELECT experiment_name, applied_boost, applied_gate, delta FROM probe_results WHERE round_n=463 AND is_sweep_variant=1 ORDER BY delta DESC LIMIT 5\")
print('\\nTop 5 sweep variants by delta:')
for r in cur.fetchall(): print(f'  {r[0]:55s} mag={r[1]} gate={r[2]} delta={r[3]:+.5f}')
"
```
Expected: rows with `is_sweep=1` exist (15 per swept field if all completed). At least one variant with positive delta.

- [ ] **Step 4: Verify sweep_winner populated**

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
cur = con.cursor()
cur.execute(\"\"\"SELECT field_name, sweep_phase, sweep_winner_boost, sweep_winner_gate,
                       sweep_winner_delta FROM fundamental_fields
                WHERE sweep_phase = 2\"\"\")
print('Fields with sweep complete (sweep_phase=2):')
for r in cur.fetchall():
    print(f'  {r[0]:35s} winner_mag={r[2]} winner_gate={r[3]} delta={r[4]:+.5f}')
"
```
Expected: rows where all 15 sweep variants completed. Each shows the chosen winner.

- [ ] **Step 5: Run promotion query**

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
cur = con.cursor()
cur.execute(\"\"\"SELECT field_name, container,
                       sweep_winner_boost, sweep_winner_gate, sweep_winner_delta
                FROM fundamental_fields
                WHERE sweep_phase = 2 AND sweep_winner_delta >= 0.003
                ORDER BY sweep_winner_delta DESC\"\"\")
print('Sweep-winner promotion candidates (delta >= +0.003):')
for r in cur.fetchall():
    print(f'  {r[0]:35s} {r[1]:25s} mag={r[2]} gate={r[3]} delta={r[4]:+.5f}')
"
```
Expected: any field whose sweep winner clears the bake threshold appears here. The user reviews each, runs a 3-rep verify next round, then bakes.

---

## Self-Review Checklist

After completing all tasks:

**Spec coverage:**
- §5.1 fundamental_fields v2 columns → Task 0
- §5.2 probe_results.is_sweep_variant → Task 0
- §5.3 idx_pr_field_bake → Task 0
- §5.5 settings seed → Task 8
- §6.1 sweep grid → Task 3 (constants)
- §6.2 spec naming → Task 3
- §6.3 score regex → Task 7
- §7.1 bake-aware pick_fields → Task 2
- §7.2 current_bake_hash helper → Task 1
- §8.1 pick_sweep_candidates → Task 4
- §8.2 emit_phase2_sweep → Task 3
- §8.3 update_sweep_winner → Task 5
- §8.4 emit_probes_for_db k_sweep_fields → Task 6
- §8.5 score_round sweep handling → Task 7
- §9 promotion query → documented in Task 10 step 5 (no implementation needed; manual SQL)
- §10 generator integration → Task 9
- §12 testing → Tasks 0-7 all add tests
- §14 migration sequence → Tasks 0, 8, 9, 10

**Placeholder scan:** none used. All steps have exact code, exact commands, exact expected output.

**Type / signature consistency:**
- `current_bake_hash(db_path)` ←→ used by `pick_fields`, `pick_sweep_candidates`, `emit_probes_for_db`
- `pick_fields(db_path, k, classification, bake_hash=None)` ←→ called by `emit_probes_for_db`
- `pick_sweep_candidates(db_path, k, bake_hash, min_abs_delta=0.0001)` ←→ called by `emit_probes_for_db`
- `emit_phase2_sweep(field_row, round_n)` ←→ called by `emit_probes_for_db`
- `update_sweep_winner(con, field_id, bake_hash)` ←→ called by `score_round`
- `SWEEP_MAGS`, `SWEEP_GATES` ←→ shared between `emit_phase2_sweep` and `_parse_sweep_spec_name` in score_probes
- All consistent.
