"""Schema migration tests."""
import qc_storage as storage

from s001.tools.migrate_schema import apply_schema_migration


def test_migration_adds_columns_and_table(tmp_db):
    # tmp_db already has the new schema baked in via conftest;
    # to simulate the legacy state we drop the new columns first.
    con = storage.connect(tmp_db)
    cur = con.cursor()
    # Recreate the legacy fundamental_fields shape (no new columns).
    cur.execute("DROP TABLE field_universe_stats")
    cur.execute("DROP TABLE probe_results")
    cur.execute("DROP TABLE fundamental_fields")
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
        test_notes TEXT
    )""")
    cur.execute(
        "INSERT INTO fundamental_fields (category, field_name, accessor) "
        "VALUES (?, ?, ?)", ('valuation', 'pe_ratio', '_vr.pe_ratio'))
    con.commit()
    con.close()

    apply_schema_migration(tmp_db)

    con = storage.connect(tmp_db)
    cur = con.cursor()
    cur.execute("PRAGMA table_info(fundamental_fields)")
    cols = {r[1] for r in cur.fetchall()}
    expected_new = {'period', 'container', 'probe_op', 'probe_threshold',
                    'probe_gate', 'probe_boost', 'classification',
                    'last_classified_at', 'data_type_hint'}
    assert expected_new <= cols

    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in cur.fetchall()}
    assert 'probe_results' in tables

    cur.execute("SELECT classification FROM fundamental_fields WHERE field_name=?", ('pe_ratio',))
    assert cur.fetchone()[0] == 'untested'  # legacy untested → 'untested'
    con.close()


def test_migration_idempotent(tmp_db):
    # Already migrated; running again must not fail.
    apply_schema_migration(tmp_db)  # second run on already-migrated db
    apply_schema_migration(tmp_db)  # third run
    # No assertion needed beyond no-exception.


def test_migration_adds_v2_columns_and_settings(tmp_db):
    """V2: sweep_phase + sweep_winner_* on fundamental_fields,
    is_sweep_variant on probe_results, idx_pr_field_bake."""
    # Drop and recreate as a true legacy state (v1 only) to test the migration.
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("DROP TABLE field_universe_stats")
        cur.execute("DROP TABLE probe_results")
        cur.execute("DROP TABLE fundamental_fields")
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

    apply_schema_migration(tmp_db)

    with storage.connect(tmp_db) as con:
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
    apply_schema_migration(tmp_db)
    apply_schema_migration(tmp_db)  # second run must not fail


def test_migration_adds_v3_columns_and_table(tmp_db):
    """V3: sweep_version + coarse_winner_* + refine_*_set on fundamental_fields,
    sweep_stage on probe_results, new field_universe_stats table."""
    import qc_storage as storage
    from s001.tools.migrate_schema import apply_schema_migration

    apply_schema_migration(tmp_db)

    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        ff_cols = {r[1] for r in cur.execute("PRAGMA table_info(fundamental_fields)")}
        assert 'sweep_version' in ff_cols
        for col in ('coarse_winner_op', 'coarse_winner_threshold', 'coarse_winner_gate',
                   'coarse_winner_mag', 'coarse_winner_delta',
                   'refine_op_set', 'refine_mag_set', 'refine_gate_set', 'refine_threshold_set'):
            assert col in ff_cols, f'fundamental_fields missing column {col}'

        pr_cols = {r[1] for r in cur.execute("PRAGMA table_info(probe_results)")}
        assert 'sweep_stage' in pr_cols

        tables = {r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert 'field_universe_stats' in tables

        fus_cols = {r[1] for r in cur.execute("PRAGMA table_info(field_universe_stats)")}
        for col in ('field_id', 'bake_hash', 'p10', 'p25', 'p50', 'p75', 'p90',
                    'sample_size', 'scanned_at'):
            assert col in fus_cols


def test_migration_adds_mechanism_column(tmp_db):
    """Mega-round migration adds `mechanism` column to probe_results
    and creates idx_probe_results_mechanism."""
    # Drop and recreate probe_results without `mechanism` to simulate the legacy state.
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("DROP TABLE probe_results")
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
            recorded_at TEXT NOT NULL,
            is_sweep_variant INTEGER DEFAULT 0,
            sweep_stage TEXT
        )""")
        cur.execute("PRAGMA table_info(probe_results)")
        cols_before = {r[1] for r in cur.fetchall()}
        assert 'mechanism' not in cols_before, 'precondition: mechanism not yet added'

    apply_schema_migration(tmp_db)

    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("PRAGMA table_info(probe_results)")
        cols_after = {r[1] for r in cur.fetchall()}
        assert 'mechanism' in cols_after, f'mechanism column missing after migration: {cols_after}'

        cur.execute("SELECT name FROM sqlite_master WHERE type='index' "
                    "AND name='idx_probe_results_mechanism'")
        assert cur.fetchone() is not None, 'idx_probe_results_mechanism missing'


def test_migration_idempotent_on_mechanism(tmp_db):
    """Re-running migration on an already-migrated DB must not fail."""
    apply_schema_migration(tmp_db)
    apply_schema_migration(tmp_db)


def test_migration_renumbers_v2_sealed_fields(tmp_db):
    """V2 sealed fields (sweep_phase=2 with sweep_winner_delta NOT NULL) become
    sweep_version=2, sweep_phase=4 after v3 migration."""
    import qc_storage as storage
    from s001.tools.migrate_schema import apply_schema_migration

    apply_schema_migration(tmp_db)
    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("""INSERT INTO fundamental_fields
            (id, category, field_name, accessor, container, probe_op, probe_threshold,
             probe_boost, sweep_phase, sweep_winner_delta)
            VALUES (1, 'vr', 'pe_ratio', '_vr_z.pe_ratio', 'valuation_ratios',
                    '<', '15', 1.08, 2, -0.005)""")
        cur.execute("""INSERT INTO fundamental_fields
            (id, category, field_name, accessor, container, probe_op, probe_threshold,
             probe_boost, sweep_phase, sweep_winner_delta)
            VALUES (2, 'vr', 'untouched', '_vr_z.untouched', 'valuation_ratios',
                    '>', '5', 1.08, 0, NULL)""")
        con.commit()

    apply_schema_migration(tmp_db)  # idempotent re-run triggers renumber

    with storage.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("SELECT sweep_version, sweep_phase FROM fundamental_fields WHERE id=1")
        v, p = cur.fetchone()
        assert v == 2
        assert p == 4
        cur.execute("SELECT sweep_version, sweep_phase FROM fundamental_fields WHERE id=2")
        v, p = cur.fetchone()
        assert v == 1  # default — never sealed
        assert p == 0
