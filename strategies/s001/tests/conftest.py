"""Shared pytest fixtures for s001 tests."""
import qc_storage as storage

import pytest


@pytest.fixture
def tmp_db(tmp_path):
    """Empty temporary SQLite db with the production schema applied."""
    db = tmp_path / 'test.duckdb'
    with storage.connect(str(db)) as con:
        cur = con.cursor()
        # Mirror minimum production schema needed for tests.
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
            data_type_hint TEXT,
            sweep_phase INTEGER DEFAULT 0,
            sweep_winner_op TEXT,
            sweep_winner_threshold TEXT,
            sweep_winner_gate TEXT,
            sweep_winner_boost REAL,
            sweep_winner_delta REAL,
            sweep_version INTEGER DEFAULT 1,
            coarse_winner_op TEXT,
            coarse_winner_threshold TEXT,
            coarse_winner_gate TEXT,
            coarse_winner_mag REAL,
            coarse_winner_delta REAL,
            refine_op_set TEXT,
            refine_mag_set TEXT,
            refine_gate_set TEXT,
            refine_threshold_set TEXT
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
            recorded_at TEXT NOT NULL,
            is_sweep_variant INTEGER DEFAULT 0,
            sweep_stage TEXT,
            mechanism TEXT
        )""")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_probe_results_mechanism "
            "ON probe_results(field_id, mechanism, bake_hash)")
        cur.execute("""CREATE TABLE experiments (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            car_mdd REAL,
            cagr REAL,
            dd REAL
        )""")
        cur.execute("""CREATE TABLE backtest_queue (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            code TEXT,
            status TEXT,
            priority INTEGER,
            submitted_at TEXT,
            code_hash TEXT,
            project_id INTEGER
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS settings (
            category TEXT, key TEXT, value TEXT, description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (category, key)
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS field_universe_stats (
            field_id INTEGER NOT NULL REFERENCES fundamental_fields(id),
            bake_hash TEXT NOT NULL,
            p10 REAL, p25 REAL, p50 REAL, p75 REAL, p90 REAL,
            sample_size INTEGER NOT NULL,
            scanned_at TEXT NOT NULL,
            PRIMARY KEY (field_id, bake_hash)
        )""")
        con.commit()
    return str(db)
