# S001 Fundamental Data v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace v2's narrow 15-cell mag/gate sweep with a full-grid v3 sweep — 72 coarse cells per numeric field (2 ops × 4 mags × 3 gates × 3 percentile-based thresholds), adaptive dimension prune, then a refine pass of ~26 cells around the coarse winner. Adds an offline universe scanner that records per-bake `{p10, p25, p50, p75, p90}` of each field across the QQQ universe so coarse thresholds are universe-aware.

**Architecture:** Three-stage state machine (Phase 1 default → Phase 2 v3 coarse → Phase 3 v3 refine → Phase 4 sealed) replacing v2's two-stage. Eight new library functions in `s001/fundamental_probes.py` (`coarse_grid`, `dimension_prune`, `refine_grid`, `emit_v3_coarse`, `emit_v3_refine`, `pick_v3_coarse_candidates`, `pick_v3_refine_candidates`, `update_v3_winner`) plus two helpers (`_format_threshold`, `_neighbors`). One modified function (`emit_probes_for_db`). Two new scripts (`gen_scan_spec.py`, `parse_scan_log.py`) and one extended (`score_probes.py`). Schema gains 9 `fundamental_fields` columns, 1 `probe_results` column, and 1 new table `field_universe_stats`. v2 sealed fields (75 currently) get one-time renumbered to `phase=4, sweep_version=2`.

**Tech Stack:** Python 3.13, SQLite3 (S001.db at `/home/txy/qc_work/data/S001.db`), pytest. Numpy used for percentile computation in the scanner parser. Builds on v2 spec at `/home/txy/qc_work/docs/superpowers/specs/2026-04-27-s001-fundamental-data-auto-sweep-design.md`.

**Note:** The repo at `/home/txy/qc_work/data` is git-tracked. Auto-commit per-task is authorized once tests pass (see memory: `feedback_auto_commit_authorized.md`); do not push or amend without asking.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `scripts/migrate_schema.py` | Modify | Add v3 columns, new `field_universe_stats` table, `probe_results.sweep_stage`, one-time renumber of v2 sealed fields |
| `s001/fundamental_probes.py` | Modify | Add v3 constants, helpers, picker/emitter/winner functions; modify `emit_probes_for_db` |
| `scripts/score_probes.py` | Modify | Add `V3_COARSE_NAME_RE`, `V3_REFINE_NAME_RE`, dispatch logic, post-scoring triggers |
| `scripts/gen_scan_spec.py` | Create | One-shot universe scanner spec generator (priority=0) |
| `scripts/parse_scan_log.py` | Create | Parse scanner log payload into `field_universe_stats` |
| `tests/conftest.py` | Modify | Extend `tmp_db` fixture with v3 columns + `field_universe_stats` table |
| `tests/test_migrate_schema.py` | Modify | Tests for v3 column additions, new table, renumber |
| `tests/test_fundamental_probes.py` | Modify | Tests for new library functions |
| `tests/test_score_probes.py` | Modify | Tests for v3 regex routing + post-scoring triggers |
| `tests/test_emit_probes.py` | Modify | Tests for `k_coarse_fields` / `k_refine_fields` integration + `k_sweep_fields` deprecation |
| `tests/test_scan_spec.py` | Create | Tests for scanner spec generator |
| `tests/test_parse_scan_log.py` | Create | Tests for log parser |
| `gen_s001_R{N}.py` | Update template | New rounds use `k_coarse_fields`, `k_refine_fields` |

Pytest discovers tests automatically; no test file path changes needed.

---

## Task 0: Schema Migration + conftest Update

**Files:**
- Modify: `/home/txy/qc_work/data/scripts/migrate_schema.py`
- Modify: `/home/txy/qc_work/data/tests/conftest.py`
- Modify: `/home/txy/qc_work/data/tests/test_migrate_schema.py`

- [ ] **Step 1: Append the failing test for v3 schema**

Append to `/home/txy/qc_work/data/tests/test_migrate_schema.py`:

```python
def test_migration_adds_v3_columns_and_table(tmp_db):
    """V3: sweep_version + coarse_winner_* + refine_*_set on fundamental_fields,
    sweep_stage on probe_results, new field_universe_stats table."""
    import sqlite3
    from scripts.migrate_schema import apply_schema_migration

    apply_schema_migration(tmp_db)

    with sqlite3.connect(tmp_db) as con:
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


def test_migration_renumbers_v2_sealed_fields(tmp_db):
    """V2 sealed fields (sweep_phase=2 with sweep_winner_delta NOT NULL) become
    sweep_version=2, sweep_phase=4 after v3 migration."""
    import sqlite3
    from scripts.migrate_schema import apply_schema_migration

    # Run an initial migration so schema includes v3 columns
    apply_schema_migration(tmp_db)
    with sqlite3.connect(tmp_db) as con:
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

    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("SELECT sweep_version, sweep_phase FROM fundamental_fields WHERE id=1")
        v, p = cur.fetchone()
        assert v == 2
        assert p == 4
        cur.execute("SELECT sweep_version, sweep_phase FROM fundamental_fields WHERE id=2")
        v, p = cur.fetchone()
        assert v == 1  # default — never sealed
        assert p == 0
```

- [ ] **Step 2: Run test to verify it fails**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_migrate_schema.py::test_migration_adds_v3_columns_and_table -v
```

Expected: FAIL with `'sweep_version' not in ff_cols` or similar AssertionError.

- [ ] **Step 3: Implement v3 schema additions in `migrate_schema.py`**

Open `/home/txy/qc_work/data/scripts/migrate_schema.py`. Append after the existing `NEW_COLUMNS` list:

```python
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
```

Inside `apply_schema_migration`, after the existing `for name, sqltype, default_clause in PROBE_RESULTS_V2_COLUMNS:` block, add:

```python
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

        # v3 field_universe_stats table
        cur.execute(FIELD_UNIVERSE_STATS_DDL)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fus_bake "
                    "ON field_universe_stats(bake_hash)")

        # One-time renumber: v2 sealed fields → v3-compatible phase=4
        cur.execute("""UPDATE fundamental_fields
                       SET sweep_version = 2, sweep_phase = 4
                       WHERE sweep_phase = 2 AND sweep_winner_delta IS NOT NULL""")
```

- [ ] **Step 4: Run migration tests to verify they pass**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_migrate_schema.py -v
```

Expected: 2 new tests PASS, plus the existing v2 tests still PASS.

- [ ] **Step 5: Update conftest.py**

Open `/home/txy/qc_work/data/tests/conftest.py`. Replace the `fundamental_fields` CREATE TABLE block with the version that includes v3 columns:

```python
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
```

Replace the `probe_results` CREATE TABLE block with:

```python
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
```

After the `settings` table create, append:

```python
        cur.execute("""CREATE TABLE IF NOT EXISTS field_universe_stats (
            field_id INTEGER NOT NULL REFERENCES fundamental_fields(id),
            bake_hash TEXT NOT NULL,
            p10 REAL, p25 REAL, p50 REAL, p75 REAL, p90 REAL,
            sample_size INTEGER NOT NULL,
            scanned_at TEXT NOT NULL,
            PRIMARY KEY (field_id, bake_hash)
        )""")
```

- [ ] **Step 6: Run full test suite to verify nothing broke**

```
cd /home/txy/qc_work/data
python -m pytest -v
```

Expected: existing tests PASS; new migration tests PASS.

- [ ] **Step 7: Apply migration to live S001.db**

```
cd /home/txy/qc_work/data
python -m scripts.migrate_schema /home/txy/qc_work/data/S001.db
```

Expected output: `Migration applied to /home/txy/qc_work/data/S001.db`

Verify the renumber:

```
python -c "import sqlite3; con=sqlite3.connect('/home/txy/qc_work/data/S001.db'); print('phase=4, ver=2:', con.execute(\"SELECT COUNT(*) FROM fundamental_fields WHERE sweep_phase=4 AND sweep_version=2\").fetchone())"
```

Expected: a count > 0 matching the v2 sealed field count (~75 fields).

- [ ] **Step 8: Commit**

```
cd /home/txy/qc_work/data
git add scripts/migrate_schema.py tests/test_migrate_schema.py tests/conftest.py
git commit -m "feat(s001): v3 schema migration — coarse_winner_*, refine_*_set, field_universe_stats; renumber v2 sealed"
```

---

## Task 1: `_format_threshold` Helper

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Write the failing test**

Append to `/home/txy/qc_work/data/tests/test_fundamental_probes.py`:

```python
class TestFormatThreshold:
    def test_zero_returns_zero_string(self):
        from s001.fundamental_probes import _format_threshold
        assert _format_threshold(0, 'absolute_amount') == '0'

    def test_large_amounts_use_scientific(self):
        from s001.fundamental_probes import _format_threshold
        assert _format_threshold(1.5e9, 'absolute_amount') == '1.5e+09'
        assert _format_threshold(7.2e8, 'absolute_amount') == '7.2e+08'

    def test_small_ratios_use_two_sigfigs(self):
        from s001.fundamental_probes import _format_threshold
        assert _format_threshold(0.10, 'ratio') == '0.1'
        assert _format_threshold(0.123, 'ratio') == '0.12'

    def test_tiny_values_use_scientific(self):
        from s001.fundamental_probes import _format_threshold
        assert _format_threshold(0.0005, 'ratio') == '5.0e-04'

    def test_modest_integer_no_scientific(self):
        from s001.fundamental_probes import _format_threshold
        assert _format_threshold(120, 'count') == '1.2e+02'  # 120 >= 1e2 means 2 sig figs gives '1.2e+02'
        assert _format_threshold(15, 'ratio') == '15'
```

- [ ] **Step 2: Run test to verify it fails**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_fundamental_probes.py::TestFormatThreshold -v
```

Expected: FAIL with `ImportError` or `AttributeError` — function doesn't exist.

- [ ] **Step 3: Implement `_format_threshold`**

Append to `/home/txy/qc_work/data/s001/fundamental_probes.py` (after `_threshold_short`):

```python
def _format_threshold(value, hint):
    """Format a numeric threshold for display in spec names and storage.

    - Returns '0' for exact zero.
    - For |value| >= 1e6 or |value| < 1e-3, uses scientific notation with 1 fractional digit ('1.5e+09').
    - Otherwise, uses 2 significant figures via Python's '{:.2g}' ('0.10', '15', '120').
    - hint is reserved for future per-type formatting; currently unused.
    """
    if value == 0:
        return '0'
    abs_v = abs(value)
    if abs_v >= 1e6 or abs_v < 1e-3:
        return f'{value:.1e}'
    return f'{value:.2g}'
```

- [ ] **Step 4: Run test to verify it passes**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_fundamental_probes.py::TestFormatThreshold -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```
cd /home/txy/qc_work/data
git add s001/fundamental_probes.py tests/test_fundamental_probes.py
git commit -m "feat(s001): _format_threshold helper for v3 spec naming"
```

---

## Task 2: `coarse_grid` Function

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fundamental_probes.py`:

```python
class TestCoarseGrid:
    def _seed_field_and_stats(self, db_path, hint='absolute_amount'):
        import sqlite3
        with sqlite3.connect(db_path) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, ?)""", (hint,))
            cur.execute("""INSERT INTO field_universe_stats
                (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
                VALUES (1, 'BAKE_TEST', 1e7, 1e8, 5e8, 1e9, 5e9, 100, '2026-04-27')""")
            con.commit()

    def test_returns_72_cells_for_numeric(self, tmp_db):
        from s001.fundamental_probes import coarse_grid
        self._seed_field_and_stats(tmp_db)
        import sqlite3
        with sqlite3.connect(tmp_db) as con:
            con.row_factory = sqlite3.Row
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        cells = coarse_grid(row, 'BAKE_TEST', tmp_db)
        # 2 ops × 4 mags × 3 gates × 3 thresholds = 72
        assert len(cells) == 72

    def test_returns_none_when_no_universe_stats(self, tmp_db):
        from s001.fundamental_probes import coarse_grid
        import sqlite3
        with sqlite3.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount')""")
            con.commit()
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        cells = coarse_grid(row, 'BAKE_TEST', tmp_db)
        assert cells is None

    def test_categorical_uses_15_cell_fallback(self, tmp_db):
        from s001.fundamental_probes import coarse_grid
        import sqlite3
        with sqlite3.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint)
                VALUES (1, 'ac', 'fin_health', '_ac_z.fin_health', 'asset_classification',
                        'eq', '"A"', 1.08, 'categorical')""")
            con.commit()
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        cells = coarse_grid(row, 'BAKE_TEST', tmp_db)
        assert len(cells) == 15  # 5 mags × 3 gates, no inversion or threshold sweep
        # All cells have op == 'eq' (no inversion)
        assert {c[0] for c in cells} == {'eq'}

    def test_thresholds_drawn_from_p25_p50_p75(self, tmp_db):
        from s001.fundamental_probes import coarse_grid
        self._seed_field_and_stats(tmp_db)
        import sqlite3
        with sqlite3.connect(tmp_db) as con:
            con.row_factory = sqlite3.Row
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        cells = coarse_grid(row, 'BAKE_TEST', tmp_db)
        thresholds = {c[3] for c in cells}
        assert thresholds == {'1.0e+08', '5.0e+08', '1.0e+09'}  # p25, p50, p75 formatted
```

- [ ] **Step 2: Run test to verify it fails**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_fundamental_probes.py::TestCoarseGrid -v
```

Expected: FAIL — `coarse_grid` doesn't exist.

- [ ] **Step 3: Implement `coarse_grid`**

Append to `s001/fundamental_probes.py`:

```python
COARSE_OPS = ['>', '<']
COARSE_MAGS = [1.04, 1.08, 1.13, 1.20]
COARSE_GATES = ['.05', '.10', '.15']
COARSE_THRESHOLD_PERCENTILES = ('p25', 'p50', 'p75')


def coarse_grid(field_row, bake_hash, db_path):
    """Build the v3 coarse Cartesian grid for one field.

    Returns: list of (op, mag, gate, threshold_str) tuples, or None if no
    field_universe_stats row exists for this (field_id, bake_hash).

    For numeric fields: 2 ops × 4 mags × 3 gates × 3 thresholds (p25/p50/p75) = 72 cells.
    For categorical fields (op in {'eq', 'in'}): falls back to v2-style
    SWEEP_MAGS × SWEEP_GATES = 15 cells, op held fixed (no inversion).
    """
    op = field_row['probe_op']

    if op in ('eq', 'in'):
        thr = field_row['probe_threshold']
        cells = []
        for mag in SWEEP_MAGS:
            for gate in SWEEP_GATES:
                cells.append((op, float(mag), gate, thr))
        return cells

    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT p25, p50, p75 FROM field_universe_stats "
            "WHERE field_id = ? AND bake_hash = ?",
            (field_row['id'], bake_hash)).fetchone()
    if row is None:
        return None

    hint = field_row.get('data_type_hint') or 'numeric'
    thresholds = [_format_threshold(row[col], hint) for col in ('p25', 'p50', 'p75')]

    cells = []
    for op_val in COARSE_OPS:
        for mag in COARSE_MAGS:
            for gate in COARSE_GATES:
                for thr in thresholds:
                    cells.append((op_val, mag, gate, thr))
    return cells
```

- [ ] **Step 4: Run test to verify it passes**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_fundamental_probes.py::TestCoarseGrid -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```
cd /home/txy/qc_work/data
git add s001/fundamental_probes.py tests/test_fundamental_probes.py
git commit -m "feat(s001): coarse_grid for v3 numeric (72 cells) + categorical fallback (15 cells)"
```

---

## Task 3: `emit_v3_coarse` Renderer + Spec Naming

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fundamental_probes.py`:

```python
class TestEmitV3Coarse:
    def _seed(self, db_path):
        import sqlite3
        with sqlite3.connect(db_path) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount')""")
            cur.execute("""INSERT INTO field_universe_stats
                (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
                VALUES (1, 'BAKE_TEST', 1e7, 1e8, 5e8, 1e9, 5e9, 100, '2026-04-27')""")
            con.commit()

    def test_emit_returns_72_named_specs(self, tmp_db):
        from s001.fundamental_probes import emit_v3_coarse
        self._seed(tmp_db)
        import sqlite3
        with sqlite3.connect(tmp_db) as con:
            con.row_factory = sqlite3.Row
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        specs = emit_v3_coarse(row, round_n=500, bake_hash='BAKE_TEST', db_path=tmp_db)
        assert len(specs) == 72
        # Names follow the v3c format
        for name, body in specs:
            assert name.startswith('S001_R500_v3c_bs_cash_')
            assert '_o' in name
            assert '_m' in name
            assert '_g' in name
            assert '_t' in name
            assert len(name) <= 100
            # Body uses the standard try/except shape
            assert '_v = f_(_bs_z.cash)' in body
            assert 'except: pass' in body

    def test_emit_uses_inverse_op(self, tmp_db):
        from s001.fundamental_probes import emit_v3_coarse
        self._seed(tmp_db)
        import sqlite3
        with sqlite3.connect(tmp_db) as con:
            con.row_factory = sqlite3.Row
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        specs = emit_v3_coarse(row, round_n=500, bake_hash='BAKE_TEST', db_path=tmp_db)
        # Names with _ogt and _olt should both be present
        ops_seen = set()
        for name, _ in specs:
            if '_ogt_' in name:
                ops_seen.add('gt')
            if '_olt_' in name:
                ops_seen.add('lt')
        assert ops_seen == {'gt', 'lt'}

    def test_emit_returns_empty_when_no_stats(self, tmp_db):
        from s001.fundamental_probes import emit_v3_coarse
        import sqlite3
        with sqlite3.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount')""")
            con.commit()
            con.row_factory = sqlite3.Row
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        specs = emit_v3_coarse(row, round_n=500, bake_hash='BAKE_TEST', db_path=tmp_db)
        assert specs == []
```

- [ ] **Step 2: Run test to verify it fails**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_fundamental_probes.py::TestEmitV3Coarse -v
```

Expected: FAIL — `emit_v3_coarse` doesn't exist.

- [ ] **Step 3: Implement `emit_v3_coarse` and the spec name helper**

Append to `s001/fundamental_probes.py`:

```python
V3_COARSE_PREFIX = 'v3c'
V3_REFINE_PREFIX = 'v3r'

OP_TO_SHORT_V3 = {'>': 'gt', '<': 'lt'}

# Indexes used in spec names so the `_t{NN}` token decodes to a percentile slot
COARSE_THRESHOLD_INDEX = {'p25': '25', 'p50': '50', 'p75': '75'}


def _v3_spec_name(prefix, round_n, container, field_name, op, mag, gate, thr_index):
    """Build a v3 spec name. Truncates to 100 chars; UNIQUE constraint is the safety net."""
    cs = CONTAINER_SHORT[container]
    op_s = OP_TO_SHORT_V3[op]
    mag_int = int(round(mag * 100))
    gate_int = gate.lstrip('.').lstrip('0') or '0'  # e.g. '.05' -> '5', '.10' -> '10'
    # Pad gate to 2 chars for stable parsing
    gate_padded = gate.lstrip('.')
    name = (f"S001_R{round_n}_{prefix}_{cs}_{field_name}"
            f"_o{op_s}_m{mag_int:03d}_g{gate_padded}_t{thr_index}")
    return name[:100]


def emit_v3_coarse(field_row, round_n, bake_hash, db_path):
    """Render the v3 coarse grid for a field as [(spec_name, body), ...].

    Returns [] if `coarse_grid` returns None (no universe stats).
    Each body is the per-probe try/except block (BIND injected once per spec
    by the caller in `gen_s001_R{N}.py`)."""
    cells = coarse_grid(field_row, bake_hash, db_path)
    if cells is None:
        return []

    # Map each threshold string back to its percentile slot for stable naming
    if field_row['probe_op'] in ('eq', 'in'):
        thr_to_pct = {field_row['probe_threshold']: '25'}  # categorical fallback uses one slot
    else:
        with sqlite3.connect(db_path) as con:
            con.row_factory = sqlite3.Row
            stats = con.execute(
                "SELECT p25, p50, p75 FROM field_universe_stats "
                "WHERE field_id = ? AND bake_hash = ?",
                (field_row['id'], bake_hash)).fetchone()
        hint = field_row.get('data_type_hint') or 'numeric'
        thr_to_pct = {
            _format_threshold(stats[col], hint): COARSE_THRESHOLD_INDEX[col]
            for col in ('p25', 'p50', 'p75')
        }

    specs = []
    for (op, mag, gate, thr) in cells:
        thr_idx = thr_to_pct[thr]
        name = _v3_spec_name(V3_COARSE_PREFIX, round_n, field_row['container'],
                             field_row['field_name'], op, mag, gate, thr_idx)
        # Build a row dict suitable for render_probe with this cell's overrides
        cell_row = dict(field_row)
        cell_row['probe_op'] = op
        cell_row['probe_threshold'] = thr
        cell_row['probe_gate'] = f'decline > {gate}'
        cell_row['probe_boost'] = mag
        body = render_probe(cell_row)
        specs.append((name, body))
    return specs
```

- [ ] **Step 4: Run test to verify it passes**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_fundamental_probes.py::TestEmitV3Coarse -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```
cd /home/txy/qc_work/data
git add s001/fundamental_probes.py tests/test_fundamental_probes.py
git commit -m "feat(s001): emit_v3_coarse + v3c spec naming with op/mag/gate/threshold encoding"
```

---

## Task 4: `pick_v3_coarse_candidates`

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fundamental_probes.py`:

```python
class TestPickV3CoarseCandidates:
    def _seed(self, db_path):
        import sqlite3
        with sqlite3.connect(db_path) as con:
            cur = con.cursor()
            # Field 1: phase=1, has Phase 1 delta of +0.0005, has stats — eligible
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint, sweep_phase)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount', 1)""")
            cur.execute("""INSERT INTO field_universe_stats
                (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
                VALUES (1, 'BAKE_TEST', 1e7, 1e8, 5e8, 1e9, 5e9, 100, '2026-04-27')""")
            cur.execute("""INSERT INTO probe_results
                (field_id, experiment_name, round_n, bake_hash, noop_baseline,
                 spec_car_mdd, delta, classification, applied_op, applied_threshold,
                 applied_boost, recorded_at)
                VALUES (1, 'F1_phase1', 500, 'BAKE_TEST', 2.0, 2.0005, 0.0005,
                        'neutral', '>', '1e9', 1.08, '2026-04-27')""")

            # Field 2: phase=1, has Phase 1 delta below threshold (+0.00005) — ineligible
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint, sweep_phase)
                VALUES (2, 'bs', 'debt', '_bs_z.debt', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount', 1)""")
            cur.execute("""INSERT INTO field_universe_stats
                (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
                VALUES (2, 'BAKE_TEST', 1e7, 1e8, 5e8, 1e9, 5e9, 100, '2026-04-27')""")
            cur.execute("""INSERT INTO probe_results
                (field_id, experiment_name, round_n, bake_hash, noop_baseline,
                 spec_car_mdd, delta, classification, applied_op, applied_threshold,
                 applied_boost, recorded_at)
                VALUES (2, 'F2_phase1', 500, 'BAKE_TEST', 2.0, 2.00005, 0.00005,
                        'neutral', '>', '1e9', 1.08, '2026-04-27')""")

            # Field 3: phase=1, has delta but NO universe stats — ineligible
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint, sweep_phase)
                VALUES (3, 'bs', 'rev', '_bs_z.rev', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount', 1)""")
            cur.execute("""INSERT INTO probe_results
                (field_id, experiment_name, round_n, bake_hash, noop_baseline,
                 spec_car_mdd, delta, classification, applied_op, applied_threshold,
                 applied_boost, recorded_at)
                VALUES (3, 'F3_phase1', 500, 'BAKE_TEST', 2.0, 2.0005, 0.0005,
                        'neutral', '>', '1e9', 1.08, '2026-04-27')""")
            con.commit()

    def test_picks_only_eligible_field(self, tmp_db):
        from s001.fundamental_probes import pick_v3_coarse_candidates
        self._seed(tmp_db)
        picked = pick_v3_coarse_candidates(tmp_db, k=10, bake_hash='BAKE_TEST')
        assert len(picked) == 1
        assert picked[0]['id'] == 1

    def test_picking_bumps_phase_to_2(self, tmp_db):
        from s001.fundamental_probes import pick_v3_coarse_candidates
        self._seed(tmp_db)
        pick_v3_coarse_candidates(tmp_db, k=10, bake_hash='BAKE_TEST')
        import sqlite3
        with sqlite3.connect(tmp_db) as con:
            phase = con.execute(
                "SELECT sweep_phase FROM fundamental_fields WHERE id=1").fetchone()[0]
        assert phase == 2

    def test_returns_empty_when_k_zero(self, tmp_db):
        from s001.fundamental_probes import pick_v3_coarse_candidates
        self._seed(tmp_db)
        picked = pick_v3_coarse_candidates(tmp_db, k=0, bake_hash='BAKE_TEST')
        assert picked == []
```

- [ ] **Step 2: Run test to verify it fails**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_fundamental_probes.py::TestPickV3CoarseCandidates -v
```

Expected: FAIL — function doesn't exist.

- [ ] **Step 3: Implement `pick_v3_coarse_candidates`**

Append to `s001/fundamental_probes.py`:

```python
COARSE_TRIGGER_DELTA = 0.0001


def pick_v3_coarse_candidates(db_path, k, bake_hash):
    """Pick up to k fields ready for v3 coarse sweep.

    Eligibility:
      - sweep_phase = 1 (Phase 1 default-template probe complete)
      - max(|delta|) >= COARSE_TRIGGER_DELTA across this field's probe_results
        for this bake_hash
      - field_universe_stats row exists for this (field_id, bake_hash)
      - probe_threshold IS NOT NULL

    Side effect: each picked field's sweep_phase bumped to 2.
    Returns list of field dicts (sqlite3.Row → dict)."""
    if k <= 0:
        return []
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT f.* FROM fundamental_fields f
            WHERE f.sweep_phase = 1
              AND f.probe_threshold IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM field_universe_stats s
                WHERE s.field_id = f.id AND s.bake_hash = ?)
              AND (
                SELECT MAX(ABS(p.delta)) FROM probe_results p
                WHERE p.field_id = f.id AND p.bake_hash = ?
              ) >= ?
            ORDER BY f.id ASC
            LIMIT ?
        """, (bake_hash, bake_hash, COARSE_TRIGGER_DELTA, k))
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            cur.execute("UPDATE fundamental_fields SET sweep_phase = 2 WHERE id = ?",
                        (r['id'],))
        con.commit()
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_fundamental_probes.py::TestPickV3CoarseCandidates -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```
cd /home/txy/qc_work/data
git add s001/fundamental_probes.py tests/test_fundamental_probes.py
git commit -m "feat(s001): pick_v3_coarse_candidates filters phase=1 + delta + stats; bumps to phase=2"
```

---

## Task 5: `dimension_prune` + `_neighbors` Helper

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fundamental_probes.py`:

```python
class TestNeighbors:
    def test_returns_value_and_one_above_one_below(self):
        from s001.fundamental_probes import _neighbors
        assert _neighbors(0.10, ['.05', '.10', '.15'], k=1) == ['.05', '.10', '.15']

    def test_at_lower_boundary(self):
        from s001.fundamental_probes import _neighbors
        assert _neighbors(1.04, [1.04, 1.08, 1.13, 1.20], k=1) == [1.04, 1.08]

    def test_at_upper_boundary(self):
        from s001.fundamental_probes import _neighbors
        assert _neighbors(1.20, [1.04, 1.08, 1.13, 1.20], k=1) == [1.13, 1.20]

    def test_value_not_in_set_returns_nearest(self):
        from s001.fundamental_probes import _neighbors
        # 1.10 isn't in the set; nearest below is 1.08, nearest above is 1.13
        assert _neighbors(1.10, [1.04, 1.08, 1.13, 1.20], k=1) == [1.08, 1.13]


class TestDimensionPrune:
    def test_drops_bottom_half_of_3plus_value_dimension(self):
        from s001.fundamental_probes import dimension_prune
        # Synthetic results: mag=1.04 wins, 1.08 ties, 1.13 loses, 1.20 loses
        results = []
        for mag, delta in [(1.04, 0.001), (1.08, 0.000), (1.13, -0.005), (1.20, -0.005)]:
            for op in ['>', '<']:
                for gate in ['.05', '.10', '.15']:
                    for thr in ['p25', 'p50', 'p75']:
                        results.append({
                            'op': op, 'mag': mag, 'gate': gate, 'threshold': thr,
                            'delta': delta + (0.0001 if op == '>' else 0.0)})
        survivors = dimension_prune(results)
        # Bottom-half mags should be dropped
        assert 1.04 in survivors['mag']
        assert 1.08 in survivors['mag']
        assert 1.13 not in survivors['mag']
        assert 1.20 not in survivors['mag']

    def test_two_value_dim_drops_loser_only_when_dominance_threshold_met(self):
        from s001.fundamental_probes import dimension_prune
        # `>` median = 0.001, `<` median = -0.0001 → diff = 0.0011 ≥ 0.001 → drop `<`
        results = []
        for op, op_delta in [('>', 0.001), ('<', -0.0001)]:
            for mag in [1.04, 1.08]:
                for gate in ['.05']:
                    for thr in ['p25']:
                        results.append({'op': op, 'mag': mag, 'gate': gate,
                                        'threshold': thr, 'delta': op_delta})
        survivors = dimension_prune(results)
        assert survivors['op'] == {'>'}

    def test_two_value_dim_keeps_both_when_close(self):
        from s001.fundamental_probes import dimension_prune
        # `>` median = 0.001, `<` median = 0.0005 → diff = 0.0005 < 0.001 → keep both
        results = []
        for op, op_delta in [('>', 0.001), ('<', 0.0005)]:
            for mag in [1.04, 1.08]:
                for gate in ['.05']:
                    for thr in ['p25']:
                        results.append({'op': op, 'mag': mag, 'gate': gate,
                                        'threshold': thr, 'delta': op_delta})
        survivors = dimension_prune(results)
        assert survivors['op'] == {'>', '<'}
```

- [ ] **Step 2: Run test to verify it fails**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_fundamental_probes.py::TestNeighbors tests/test_fundamental_probes.py::TestDimensionPrune -v
```

Expected: FAIL — `_neighbors` and `dimension_prune` don't exist.

- [ ] **Step 3: Implement `_neighbors` and `dimension_prune`**

Append to `s001/fundamental_probes.py`:

```python
import statistics


PRUNE_DOMINANCE_THRESHOLD = 0.001


def _neighbors(value, allowed_set, k=1):
    """Return up to 2k+1 values around `value` from `allowed_set`.

    Includes value itself if present (or the nearest values otherwise) plus the
    k nearest above and k nearest below within allowed_set, sorted ascending.
    """
    sorted_set = sorted(allowed_set)
    if value in sorted_set:
        idx = sorted_set.index(value)
    else:
        # Find insertion point; pick neighbors around that point
        idx = next((i for i, v in enumerate(sorted_set) if v >= value), len(sorted_set))
    lo = max(0, idx - k)
    hi = min(len(sorted_set), idx + k + 1)
    if value not in sorted_set:
        # No center element; just return the bracket
        lo = max(0, idx - k)
        hi = min(len(sorted_set), idx + k)
    return sorted_set[lo:hi]


def dimension_prune(coarse_results):
    """Compute survivors per dimension from completed coarse_results.

    coarse_results: iterable of dicts with keys op, mag, gate, threshold, delta.

    Returns: {'op': set, 'mag': set, 'gate': set, 'threshold': set} of survivors.

    Rules:
      - For dimensions with ≥3 distinct values: drop values whose median delta is
        below the median of medians.
      - For dimensions with exactly 2 distinct values: drop the loser only if its
        median is ≥ PRUNE_DOMINANCE_THRESHOLD worse than the winner.
      - For dimensions with 1 distinct value: keep the singleton.
    """
    dims = ('op', 'mag', 'gate', 'threshold')
    survivors = {}
    for dim in dims:
        groups = {}
        for r in coarse_results:
            groups.setdefault(r[dim], []).append(r['delta'])
        if not groups:
            survivors[dim] = set()
            continue
        medians = {v: statistics.median(deltas) for v, deltas in groups.items()}
        if len(medians) == 1:
            survivors[dim] = set(medians)
        elif len(medians) == 2:
            (winner_v, winner_m), (loser_v, loser_m) = sorted(
                medians.items(), key=lambda kv: kv[1], reverse=True)
            if winner_m - loser_m >= PRUNE_DOMINANCE_THRESHOLD:
                survivors[dim] = {winner_v}
            else:
                survivors[dim] = {winner_v, loser_v}
        else:
            cutoff = statistics.median(list(medians.values()))
            survivors[dim] = {v for v, m in medians.items() if m >= cutoff}
    return survivors
```

- [ ] **Step 4: Run test to verify it passes**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_fundamental_probes.py::TestNeighbors tests/test_fundamental_probes.py::TestDimensionPrune -v
```

Expected: 7 PASS.

- [ ] **Step 5: Commit**

```
cd /home/txy/qc_work/data
git add s001/fundamental_probes.py tests/test_fundamental_probes.py
git commit -m "feat(s001): _neighbors helper + dimension_prune (median rule + 2-value dominance)"
```

---

## Task 6: `refine_grid` + `emit_v3_refine`

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fundamental_probes.py`:

```python
class TestRefineGrid:
    def test_uses_neighbors_within_survivors(self):
        from s001.fundamental_probes import refine_grid
        coarse_winner = {'op': '>', 'mag': 1.08, 'gate': '.10',
                         'threshold': '5.0e+08'}
        refine_sets = {
            'op': {'>'},
            'mag': {1.04, 1.08, 1.13, 1.20},
            'gate': {'.05', '.10', '.15'},
            'threshold': {'1.0e+08', '5.0e+08', '1.0e+09'},
        }
        cells = refine_grid(coarse_winner, refine_sets)
        # 1 op × 3 mag (1.04, 1.08, 1.13) × 3 gate × 3 thr = 27 - 1 (winner) = 26
        assert len(cells) == 26
        # Coarse winner not in refine cells
        assert ('>', 1.08, '.10', '5.0e+08') not in cells

    def test_handles_singleton_survivor(self):
        from s001.fundamental_probes import refine_grid
        coarse_winner = {'op': '>', 'mag': 1.08, 'gate': '.10',
                         'threshold': '5.0e+08'}
        refine_sets = {
            'op': {'>'}, 'mag': {1.08}, 'gate': {'.10'},
            'threshold': {'5.0e+08'},
        }
        cells = refine_grid(coarse_winner, refine_sets)
        # Only one cell exists and it's the winner; refine excludes it → empty
        assert cells == []


class TestEmitV3Refine:
    def _seed(self, db_path):
        import sqlite3, json
        with sqlite3.connect(db_path) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint, sweep_phase,
                 coarse_winner_op, coarse_winner_mag, coarse_winner_gate,
                 coarse_winner_threshold, coarse_winner_delta,
                 refine_op_set, refine_mag_set, refine_gate_set, refine_threshold_set)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount', 3,
                        '>', 1.08, '.10', '5.0e+08', 0.0008,
                        ?, ?, ?, ?)""",
                (json.dumps(['>']),
                 json.dumps([1.04, 1.08, 1.13]),
                 json.dumps(['.05', '.10', '.15']),
                 json.dumps(['1.0e+08', '5.0e+08', '1.0e+09'])))
            con.commit()

    def test_emit_returns_26_named_specs(self, tmp_db):
        from s001.fundamental_probes import emit_v3_refine
        self._seed(tmp_db)
        import sqlite3
        with sqlite3.connect(tmp_db) as con:
            con.row_factory = sqlite3.Row
            row = dict(con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone())
        specs = emit_v3_refine(row, round_n=501)
        assert len(specs) == 26
        for name, body in specs:
            assert name.startswith('S001_R501_v3r_bs_cash_')
            assert len(name) <= 100
```

- [ ] **Step 2: Run test to verify it fails**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_fundamental_probes.py::TestRefineGrid tests/test_fundamental_probes.py::TestEmitV3Refine -v
```

Expected: FAIL — neither function exists.

- [ ] **Step 3: Implement `refine_grid` and `emit_v3_refine`**

Append to `s001/fundamental_probes.py`:

```python
import json as _json


def refine_grid(coarse_winner, refine_sets):
    """Build the refine cells around `coarse_winner` within `refine_sets`.

    coarse_winner: dict with keys op, mag, gate, threshold.
    refine_sets: dict {dim: set} from dimension_prune.

    Returns list of (op, mag, gate, threshold) tuples — the Cartesian product of
    ±1 neighbors of the coarse winner within refine_sets, excluding the winner
    itself."""
    op_choices = [coarse_winner['op']] if coarse_winner['op'] in refine_sets['op'] else []
    mag_choices = _neighbors(coarse_winner['mag'], refine_sets['mag'], k=1)
    gate_choices = _neighbors(coarse_winner['gate'], refine_sets['gate'], k=1)
    thr_choices = _neighbors(coarse_winner['threshold'], refine_sets['threshold'], k=1)

    winner = (coarse_winner['op'], coarse_winner['mag'],
              coarse_winner['gate'], coarse_winner['threshold'])
    cells = []
    for op in op_choices:
        for mag in mag_choices:
            for gate in gate_choices:
                for thr in thr_choices:
                    cell = (op, mag, gate, thr)
                    if cell == winner:
                        continue
                    cells.append(cell)
    return cells


def emit_v3_refine(field_row, round_n):
    """Render the v3 refine grid for a field as [(spec_name, body), ...].

    Reads coarse_winner_* and refine_*_set from field_row; returns [] if
    coarse_winner_op is NULL (refine not yet ready)."""
    if field_row.get('coarse_winner_op') is None:
        return []
    coarse_winner = {
        'op': field_row['coarse_winner_op'],
        'mag': field_row['coarse_winner_mag'],
        'gate': field_row['coarse_winner_gate'],
        'threshold': field_row['coarse_winner_threshold'],
    }
    refine_sets = {
        'op': set(_json.loads(field_row['refine_op_set'])),
        'mag': set(_json.loads(field_row['refine_mag_set'])),
        'gate': set(_json.loads(field_row['refine_gate_set'])),
        'threshold': set(_json.loads(field_row['refine_threshold_set'])),
    }
    cells = refine_grid(coarse_winner, refine_sets)

    # Map each threshold string to its percentile slot for stable naming
    thr_to_pct = {coarse_winner['threshold']: '50'}  # default
    sorted_thresholds = sorted(refine_sets['threshold'])
    for i, thr in enumerate(sorted_thresholds):
        thr_to_pct[thr] = ['25', '50', '75'][i] if i < 3 else str(i)

    specs = []
    for (op, mag, gate, thr) in cells:
        thr_idx = thr_to_pct.get(thr, '50')
        name = _v3_spec_name(V3_REFINE_PREFIX, round_n, field_row['container'],
                             field_row['field_name'], op, mag, gate, thr_idx)
        cell_row = dict(field_row)
        cell_row['probe_op'] = op
        cell_row['probe_threshold'] = thr
        cell_row['probe_gate'] = f'decline > {gate}'
        cell_row['probe_boost'] = mag
        body = render_probe(cell_row)
        specs.append((name, body))
    return specs
```

- [ ] **Step 4: Run test to verify it passes**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_fundamental_probes.py::TestRefineGrid tests/test_fundamental_probes.py::TestEmitV3Refine -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```
cd /home/txy/qc_work/data
git add s001/fundamental_probes.py tests/test_fundamental_probes.py
git commit -m "feat(s001): refine_grid + emit_v3_refine using coarse winner ± neighbors within survivors"
```

---

## Task 7: `pick_v3_refine_candidates`

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fundamental_probes.py`:

```python
class TestPickV3RefineCandidates:
    def _seed(self, db_path):
        import sqlite3
        with sqlite3.connect(db_path) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint, sweep_phase)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount', 2)""")
            cur.execute("""INSERT INTO field_universe_stats
                (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
                VALUES (1, 'BAKE_TEST', 1e7, 1e8, 5e8, 1e9, 5e9, 100, '2026-04-27')""")
            # Insert all 72 coarse results with synthetic deltas
            for i, op in enumerate(['>', '<']):
                for j, mag in enumerate([1.04, 1.08, 1.13, 1.20]):
                    for k, gate in enumerate(['.05', '.10', '.15']):
                        for m, thr in enumerate(['1.0e+08', '5.0e+08', '1.0e+09']):
                            # Best at op=>, mag=1.08, gate=.10, thr=5.0e+08
                            best = (op == '>' and mag == 1.08 and gate == '.10'
                                    and thr == '5.0e+08')
                            delta = 0.001 if best else -0.001
                            uniq = i * 1000 + j * 100 + k * 10 + m
                            cur.execute("""INSERT INTO probe_results
                                (field_id, experiment_name, round_n, bake_hash,
                                 noop_baseline, spec_car_mdd, delta, classification,
                                 applied_op, applied_threshold, applied_gate,
                                 applied_boost, recorded_at, sweep_stage)
                                VALUES (?, ?, 500, 'BAKE_TEST', 2.0, ?, ?, 'neutral',
                                        ?, ?, ?, ?, '2026-04-27', 'coarse')""",
                                (1, f'F1_coarse_{uniq}', 2.0 + delta, delta,
                                 op, thr, f'decline > {gate}', mag))
            con.commit()

    def test_picks_field_with_72_coarse_done(self, tmp_db):
        from s001.fundamental_probes import pick_v3_refine_candidates
        self._seed(tmp_db)
        picked = pick_v3_refine_candidates(tmp_db, k=10, bake_hash='BAKE_TEST')
        assert len(picked) == 1
        assert picked[0]['id'] == 1

    def test_persists_refine_sets_and_coarse_winner(self, tmp_db):
        from s001.fundamental_probes import pick_v3_refine_candidates
        self._seed(tmp_db)
        pick_v3_refine_candidates(tmp_db, k=10, bake_hash='BAKE_TEST')
        import sqlite3, json
        with sqlite3.connect(tmp_db) as con:
            con.row_factory = sqlite3.Row
            row = con.execute("SELECT * FROM fundamental_fields WHERE id=1").fetchone()
        assert row['sweep_phase'] == 3
        assert row['coarse_winner_op'] == '>'
        assert row['coarse_winner_mag'] == 1.08
        assert row['coarse_winner_gate'] == '.10'
        assert row['coarse_winner_threshold'] == '5.0e+08'
        assert row['coarse_winner_delta'] == 0.001
        # JSON-encoded sets are populated
        assert row['refine_op_set'] is not None
        assert row['refine_mag_set'] is not None
```

- [ ] **Step 2: Run test to verify it fails**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_fundamental_probes.py::TestPickV3RefineCandidates -v
```

Expected: FAIL.

- [ ] **Step 3: Implement `pick_v3_refine_candidates`**

Append to `s001/fundamental_probes.py`:

```python
EXPECTED_COARSE_CELLS_NUMERIC = 72
EXPECTED_COARSE_CELLS_CATEGORICAL = 15  # SWEEP_MAGS × SWEEP_GATES


def _expected_coarse_count(field_row):
    if field_row['probe_op'] in ('eq', 'in'):
        return EXPECTED_COARSE_CELLS_CATEGORICAL
    return EXPECTED_COARSE_CELLS_NUMERIC


def pick_v3_refine_candidates(db_path, k, bake_hash):
    """Pick fields with all coarse cells scored, run prune+winner detection,
    persist refine_*_set and coarse_winner_*, bump phase to 3.

    Returns list of field dicts."""
    if k <= 0:
        return []
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("SELECT * FROM fundamental_fields WHERE sweep_phase = 2 ORDER BY id ASC")
        candidates = [dict(r) for r in cur.fetchall()]

        ready = []
        for f in candidates:
            cur.execute(
                "SELECT COUNT(*) FROM probe_results "
                "WHERE field_id = ? AND bake_hash = ? AND sweep_stage = 'coarse'",
                (f['id'], bake_hash))
            count = cur.fetchone()[0]
            if count >= _expected_coarse_count(f):
                ready.append(f)
            if len(ready) >= k:
                break

        picked = []
        for f in ready[:k]:
            cur.execute(
                """SELECT applied_op, applied_threshold, applied_gate, applied_boost, delta
                   FROM probe_results
                   WHERE field_id = ? AND bake_hash = ? AND sweep_stage = 'coarse'""",
                (f['id'], bake_hash))
            results = []
            for r in cur.fetchall():
                gate = r['applied_gate'].split('decline > ')[-1] if r['applied_gate'] else ''
                results.append({
                    'op': r['applied_op'],
                    'mag': r['applied_boost'],
                    'gate': gate,
                    'threshold': r['applied_threshold'],
                    'delta': r['delta'],
                })

            survivors = dimension_prune(results)
            best = max(results, key=lambda r: r['delta'])

            cur.execute("""UPDATE fundamental_fields SET
                sweep_phase = 3,
                coarse_winner_op = ?, coarse_winner_mag = ?, coarse_winner_gate = ?,
                coarse_winner_threshold = ?, coarse_winner_delta = ?,
                refine_op_set = ?, refine_mag_set = ?,
                refine_gate_set = ?, refine_threshold_set = ?
                WHERE id = ?""",
                (best['op'], best['mag'], best['gate'], best['threshold'], best['delta'],
                 _json.dumps(sorted(survivors['op'])),
                 _json.dumps(sorted(survivors['mag'])),
                 _json.dumps(sorted(survivors['gate'])),
                 _json.dumps(sorted(survivors['threshold'])),
                 f['id']))

            cur.execute("SELECT * FROM fundamental_fields WHERE id = ?", (f['id'],))
            picked.append(dict(cur.fetchone()))
        con.commit()
    return picked
```

- [ ] **Step 4: Run test to verify it passes**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_fundamental_probes.py::TestPickV3RefineCandidates -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```
cd /home/txy/qc_work/data
git add s001/fundamental_probes.py tests/test_fundamental_probes.py
git commit -m "feat(s001): pick_v3_refine_candidates runs prune + persists refine_*_set + coarse_winner_*"
```

---

## Task 8: `update_v3_winner`

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fundamental_probes.py`:

```python
class TestUpdateV3Winner:
    def _seed(self, db_path):
        import sqlite3, json
        with sqlite3.connect(db_path) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint, sweep_phase,
                 coarse_winner_op, coarse_winner_mag, coarse_winner_gate,
                 coarse_winner_threshold, coarse_winner_delta,
                 refine_op_set, refine_mag_set, refine_gate_set, refine_threshold_set)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount', 3,
                        '>', 1.08, '.10', '5.0e+08', 0.0008,
                        ?, ?, ?, ?)""",
                (json.dumps(['>']),
                 json.dumps([1.04, 1.08, 1.13]),
                 json.dumps(['.05', '.10', '.15']),
                 json.dumps(['1.0e+08', '5.0e+08', '1.0e+09'])))
            # Insert refine results — best is mag=1.13, delta=0.0015
            for mag in [1.04, 1.08, 1.13]:
                for gate in ['.05', '.10', '.15']:
                    for thr in ['1.0e+08', '5.0e+08', '1.0e+09']:
                        if (mag, gate, thr) == (1.08, '.10', '5.0e+08'):
                            continue  # skip coarse winner
                        delta = 0.0015 if mag == 1.13 and gate == '.10' and thr == '5.0e+08' else 0.0005
                        cur.execute("""INSERT INTO probe_results
                            (field_id, experiment_name, round_n, bake_hash,
                             noop_baseline, spec_car_mdd, delta, classification,
                             applied_op, applied_threshold, applied_gate,
                             applied_boost, recorded_at, sweep_stage)
                            VALUES (?, ?, 501, 'BAKE_TEST', 2.0, ?, ?, 'neutral',
                                    '>', ?, ?, ?, '2026-04-27', 'refine')""",
                            (1, f'F1_refine_{mag}_{gate}_{thr}', 2.0 + delta, delta,
                             thr, f'decline > {gate}', mag))
            con.commit()

    def test_writes_sweep_winner_and_phase4_version3(self, tmp_db):
        from s001.fundamental_probes import update_v3_winner
        self._seed(tmp_db)
        import sqlite3
        with sqlite3.connect(tmp_db) as con:
            update_v3_winner(con, field_id=1, bake_hash='BAKE_TEST')
            con.commit()
            row = con.execute(
                "SELECT sweep_phase, sweep_version, sweep_winner_op, "
                "sweep_winner_threshold, sweep_winner_gate, sweep_winner_boost, "
                "sweep_winner_delta FROM fundamental_fields WHERE id=1").fetchone()
        phase, version, op, thr, gate, boost, delta = row
        assert phase == 4
        assert version == 3
        assert op == '>'
        assert boost == 1.13
        assert gate == 'decline > .10'
        assert thr == '5.0e+08'
        assert abs(delta - 0.0015) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_fundamental_probes.py::TestUpdateV3Winner -v
```

Expected: FAIL.

- [ ] **Step 3: Implement `update_v3_winner`**

Append to `s001/fundamental_probes.py`:

```python
def update_v3_winner(con, field_id, bake_hash):
    """After all v3 refine variants have scored for `field_id`, find the best
    overall (coarse winner + refine cells), write to sweep_winner_* columns,
    set sweep_phase=4 and sweep_version=3.

    Caller is responsible for con.commit()."""
    cur = con.cursor()
    cur.execute(
        """SELECT applied_op, applied_threshold, applied_gate, applied_boost, delta
           FROM probe_results
           WHERE field_id = ? AND bake_hash = ?
             AND sweep_stage IN ('coarse', 'refine')""",
        (field_id, bake_hash))
    rows = cur.fetchall()
    if not rows:
        return
    best = max(rows, key=lambda r: r[4])  # delta is index 4
    op, thr, gate, boost, delta = best
    cur.execute("""UPDATE fundamental_fields SET
        sweep_winner_op = ?, sweep_winner_threshold = ?,
        sweep_winner_gate = ?, sweep_winner_boost = ?, sweep_winner_delta = ?,
        sweep_phase = 4, sweep_version = 3
        WHERE id = ?""",
        (op, thr, gate, boost, delta, field_id))
```

- [ ] **Step 4: Run test to verify it passes**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_fundamental_probes.py::TestUpdateV3Winner -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```
cd /home/txy/qc_work/data
git add s001/fundamental_probes.py tests/test_fundamental_probes.py
git commit -m "feat(s001): update_v3_winner picks max delta across coarse+refine, seals at phase=4 ver=3"
```

---

## Task 9: `emit_probes_for_db` Routing + Deprecation

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_emit_probes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_emit_probes.py`:

```python
class TestEmitProbesV3:
    def _seed_for_v3(self, db_path):
        import sqlite3
        with sqlite3.connect(db_path) as con:
            cur = con.cursor()
            cur.execute("""INSERT OR REPLACE INTO settings
                (category, key, value, description)
                VALUES ('strategy', 'current_bake_hash', 'BAKE_TEST', 'test')""")
            # Coarse-eligible field
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint, sweep_phase)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount', 1)""")
            cur.execute("""INSERT INTO field_universe_stats
                (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
                VALUES (1, 'BAKE_TEST', 1e7, 1e8, 5e8, 1e9, 5e9, 100, '2026-04-27')""")
            cur.execute("""INSERT INTO probe_results
                (field_id, experiment_name, round_n, bake_hash, noop_baseline,
                 spec_car_mdd, delta, classification, applied_op, applied_threshold,
                 applied_boost, recorded_at)
                VALUES (1, 'F1_phase1', 500, 'BAKE_TEST', 2.0, 2.0005, 0.0005,
                        'neutral', '>', '1e9', 1.08, '2026-04-27')""")
            con.commit()

    def test_k_coarse_fields_emits_72_per_field(self, tmp_db):
        from s001.fundamental_probes import emit_probes_for_db
        self._seed_for_v3(tmp_db)
        results = emit_probes_for_db(
            db_path=tmp_db, round_n=501,
            k_new=0, k_verify=0,
            k_coarse_fields=1, k_refine_fields=0)
        coarse_specs = [n for n, _ in results if '_v3c_' in n]
        assert len(coarse_specs) == 72

    def test_k_sweep_fields_alias_warns(self, tmp_db):
        import warnings
        from s001.fundamental_probes import emit_probes_for_db
        self._seed_for_v3(tmp_db)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            results = emit_probes_for_db(
                db_path=tmp_db, round_n=501,
                k_new=0, k_verify=0, k_sweep_fields=1)
        assert any(issubclass(warning.category, DeprecationWarning) for warning in w)
        # Aliased to k_coarse_fields; should still emit coarse specs
        coarse_specs = [n for n, _ in results if '_v3c_' in n]
        assert len(coarse_specs) == 72
```

- [ ] **Step 2: Run test to verify it fails**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_emit_probes.py::TestEmitProbesV3 -v
```

Expected: FAIL.

- [ ] **Step 3: Modify `emit_probes_for_db`**

Open `s001/fundamental_probes.py`. Locate the existing `emit_probes_for_db` function (signature: `def emit_probes_for_db(db_path, round_n, k_new, k_verify=0, k_sweep_fields=0, include_bind=False):`). Replace it with:

```python
def emit_probes_for_db(db_path, round_n, k_new=0, k_verify=0,
                      k_coarse_fields=0, k_refine_fields=0,
                      k_sweep_fields=None, include_bind=False):
    """Emit probe specs for round_n.

    Returns list of (spec_name, body) tuples.

    k_new        : Phase 1 default-template specs (one per untested field).
    k_coarse_fields : v3 coarse pass — k fields × 72 specs (or 15 if categorical).
    k_refine_fields : v3 refine pass — k fields × ~26 specs.
    k_sweep_fields  : DEPRECATED alias for k_coarse_fields.
    """
    import warnings
    if k_sweep_fields is not None:
        warnings.warn(
            "k_sweep_fields is deprecated; use k_coarse_fields instead.",
            DeprecationWarning, stacklevel=2)
        k_coarse_fields = k_sweep_fields

    bake_hash = current_bake_hash(db_path)
    out = []

    # Phase 1: untested fields
    if k_new:
        new_fields = pick_fields(db_path, k=k_new, classification='untested',
                                 bake_hash=bake_hash)
        for f in new_fields:
            body = (BIND if include_bind else '') + render_probe(f)
            name = spec_name(f, round_n)
            out.append((name, body))

    # v3 coarse
    if k_coarse_fields:
        coarse_fields = pick_v3_coarse_candidates(db_path, k=k_coarse_fields,
                                                  bake_hash=bake_hash)
        for f in coarse_fields:
            specs = emit_v3_coarse(f, round_n, bake_hash, db_path)
            out.extend(specs)

    # v3 refine
    if k_refine_fields:
        refine_fields = pick_v3_refine_candidates(db_path, k=k_refine_fields,
                                                  bake_hash=bake_hash)
        for f in refine_fields:
            specs = emit_v3_refine(f, round_n)
            out.extend(specs)

    return out
```

Note: This replaces v2's `k_sweep_fields` codepath entirely — the v2 `emit_phase2_sweep` is no longer invoked. v2 specs still in flight will still be matched by `score_probes.py`'s `SWEEP_NAME_RE` (untouched).

- [ ] **Step 4: Run test to verify it passes**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_emit_probes.py -v
```

Expected: new tests PASS, existing tests still PASS.

- [ ] **Step 5: Commit**

```
cd /home/txy/qc_work/data
git add s001/fundamental_probes.py tests/test_emit_probes.py
git commit -m "feat(s001): emit_probes_for_db gains k_coarse_fields/k_refine_fields; k_sweep_fields deprecated alias"
```

---

## Task 10: `score_probes` v3 Routing + Triggers

**Files:**
- Modify: `/home/txy/qc_work/data/scripts/score_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_score_probes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_score_probes.py`:

```python
class TestV3ScoreRouting:
    def _seed_field_and_stats(self, db_path):
        import sqlite3
        with sqlite3.connect(db_path) as con:
            cur = con.cursor()
            cur.execute("""INSERT OR REPLACE INTO settings
                (category, key, value, description)
                VALUES ('strategy', 'current_bake_hash', 'BAKE_TEST', 'test')""")
            cur.execute("""INSERT INTO fundamental_fields
                (id, category, field_name, accessor, container, probe_op,
                 probe_threshold, probe_boost, data_type_hint, sweep_phase)
                VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                        '>', '1e9', 1.08, 'absolute_amount', 2)""")
            cur.execute("""INSERT INTO field_universe_stats
                (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
                VALUES (1, 'BAKE_TEST', 1e7, 1e8, 5e8, 1e9, 5e9, 100, '2026-04-27')""")
            con.commit()

    def test_v3_coarse_spec_inserted_with_sweep_stage_coarse(self, tmp_db):
        from scripts.score_probes import score_round
        import sqlite3
        self._seed_field_and_stats(tmp_db)
        with sqlite3.connect(tmp_db) as con:
            cur = con.cursor()
            # Insert a NOOP and one v3c spec into experiments
            cur.execute("""INSERT INTO experiments (name, status, car_mdd)
                VALUES ('S001_R501_VBAKE45_NOOP_0', 'imported', 2.0)""")
            cur.execute("""INSERT INTO experiments (name, status, car_mdd)
                VALUES ('S001_R501_v3c_bs_cash_ogt_m108_g10_t50', 'imported', 2.001)""")
            con.commit()

        score_round(db_path=tmp_db, round_n=501, bake_hash='BAKE_TEST')

        with sqlite3.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute("SELECT applied_op, applied_threshold, applied_gate, "
                        "applied_boost, sweep_stage FROM probe_results")
            row = cur.fetchone()
        assert row[0] == '>'      # applied_op
        assert row[1] == '5.0e+08'  # p50 threshold
        assert row[2] == 'decline > .10'
        assert row[3] == 1.08
        assert row[4] == 'coarse'

    def test_v3_refine_spec_inserted_with_sweep_stage_refine(self, tmp_db):
        from scripts.score_probes import score_round
        import sqlite3
        self._seed_field_and_stats(tmp_db)
        with sqlite3.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO experiments (name, status, car_mdd)
                VALUES ('S001_R501_VBAKE45_NOOP_0', 'imported', 2.0)""")
            cur.execute("""INSERT INTO experiments (name, status, car_mdd)
                VALUES ('S001_R501_v3r_bs_cash_olt_m104_g05_t25', 'imported', 1.999)""")
            con.commit()

        score_round(db_path=tmp_db, round_n=501, bake_hash='BAKE_TEST')

        with sqlite3.connect(tmp_db) as con:
            cur = con.cursor()
            cur.execute("SELECT applied_op, applied_threshold, applied_gate, "
                        "applied_boost, sweep_stage FROM probe_results")
            row = cur.fetchone()
        assert row[0] == '<'
        assert row[1] == '1.0e+08'  # p25 threshold
        assert row[2] == 'decline > .05'
        assert row[3] == 1.04
        assert row[4] == 'refine'
```

- [ ] **Step 2: Run test to verify it fails**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_score_probes.py::TestV3ScoreRouting -v
```

Expected: FAIL.

- [ ] **Step 3: Modify `score_probes.py`**

Open `/home/txy/qc_work/data/scripts/score_probes.py`. After the existing `SWEEP_NAME_RE` definition, add:

```python
V3_COARSE_NAME_RE = re.compile(
    r'^S001_R(?P<round>\d+)_v3c_(?P<cs>[a-z]+)_(?P<field>[a-z0-9_]+?)'
    r'_o(?P<op>gt|lt)_m(?P<mag>\d+)_g(?P<gate>\d+)_t(?P<thr>\d+)$')

V3_REFINE_NAME_RE = re.compile(
    r'^S001_R(?P<round>\d+)_v3r_(?P<cs>[a-z]+)_(?P<field>[a-z0-9_]+?)'
    r'_o(?P<op>gt|lt)_m(?P<mag>\d+)_g(?P<gate>\d+)_t(?P<thr>\d+)$')

OP_FROM_SHORT_V3 = {'gt': '>', 'lt': '<'}
```

Add a parser:

```python
def _parse_v3_spec_name(name):
    """Return (kind, container, field_name, op, mag, gate_str, thr_idx) for v3 coarse/refine specs.
    kind is 'coarse' or 'refine'. Returns None if no match."""
    for kind, regex in (('coarse', V3_COARSE_NAME_RE), ('refine', V3_REFINE_NAME_RE)):
        m = regex.match(name)
        if not m:
            continue
        cs = m.group('cs')
        cont = CONTAINER_FROM_SHORT.get(cs)
        if cont is None:
            return None
        op = OP_FROM_SHORT_V3[m.group('op')]
        mag = int(m.group('mag')) / 100.0
        gate_str = '.' + m.group('gate').zfill(2) if len(m.group('gate')) == 1 else '.' + m.group('gate')
        return kind, cont, m.group('field'), op, mag, gate_str, m.group('thr')
    return None
```

Then add an import at the top alongside the existing v2 import:

```python
from s001.fundamental_probes import (  # noqa: E402
    classify_delta, field_rollup, CONTAINER_SHORT, _threshold_short,
    update_sweep_winner, SWEEP_MAGS, SWEEP_GATES,
    update_v3_winner, _expected_coarse_count, _format_threshold,
    EXPECTED_COARSE_CELLS_NUMERIC,
)
```

Inside `score_round`'s loop over experiments rows, **before** the existing sweep regex check, insert v3 routing:

```python
            # v3 coarse / refine routing (most specific — try first)
            v3_parsed = _parse_v3_spec_name(row['name'])
            if v3_parsed is not None:
                kind, container, field_name, op, mag, gate_str, thr_idx = v3_parsed
                cur.execute(
                    "SELECT * FROM fundamental_fields WHERE container = ? AND field_name = ?",
                    (container, field_name))
                f = cur.fetchone()
                if f is None:
                    continue
                # Look up the threshold value from field_universe_stats by percentile slot
                cur.execute(
                    "SELECT p25, p50, p75 FROM field_universe_stats "
                    "WHERE field_id = ? AND bake_hash = ?",
                    (f['id'], bake_hash))
                stats = cur.fetchone()
                if stats is None:
                    continue
                pct_to_col = {'25': 'p25', '50': 'p50', '75': 'p75'}
                col = pct_to_col.get(thr_idx)
                if col is None:
                    continue
                hint = f['data_type_hint'] or 'numeric'
                applied_threshold = _format_threshold(stats[col], hint)
                applied_gate = f'decline > {gate_str}'
                applied_boost = mag
                delta = row['car_mdd'] - baseline
                cls = classify_delta(delta)
                try:
                    cur.execute(
                        """INSERT INTO probe_results
                           (field_id, experiment_name, round_n, bake_hash, noop_baseline,
                            spec_car_mdd, delta, classification, applied_op,
                            applied_threshold, applied_gate, applied_boost,
                            recorded_at, is_sweep_variant, sweep_stage)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                        (f['id'], row['name'], round_n, bake_hash, baseline,
                         row['car_mdd'], delta, cls, op, applied_threshold,
                         applied_gate, applied_boost, now, kind))
                    n_results += 1
                except sqlite3.IntegrityError:
                    pass
                touched_field_ids.add(f['id'])
                if kind == 'coarse':
                    sweep_field_ids.add(('v3_coarse', f['id']))
                else:
                    sweep_field_ids.add(('v3_refine', f['id']))
                continue
```

Replace the existing per-field winner update block (the part after the touched_field_ids loop) with both v2 and v3 handling:

```python
        # Refresh field-row classification for each touched field (unchanged)
        for fid in touched_field_ids:
            cur.execute(
                "SELECT classification FROM probe_results "
                "WHERE field_id = ? AND bake_hash = ?", (fid, bake_hash))
            results = [{'classification': r[0]} for r in cur.fetchall()]
            rollup = field_rollup(results)
            cur.execute(
                "UPDATE fundamental_fields SET classification = ?, "
                "last_classified_at = ? WHERE id = ?", (rollup, now, fid))

        # v2 sweep winner update (legacy specs only — sweep_stage IS NULL but
        # is_sweep_variant=1)
        v2_field_ids = {fid for kind, fid in sweep_field_ids if kind == 'v2'}
        for fid in v2_field_ids:
            cur.execute(
                "SELECT COUNT(*) FROM probe_results "
                "WHERE field_id = ? AND bake_hash = ? AND is_sweep_variant = 1 "
                "AND sweep_stage IS NULL",
                (fid, bake_hash))
            count = cur.fetchone()[0]
            if count >= len(SWEEP_MAGS) * len(SWEEP_GATES):
                update_sweep_winner(con, fid, bake_hash)

        # v3 refine completion check — when refine done, seal as final winner
        v3_refine_field_ids = {fid for kind, fid in sweep_field_ids if kind == 'v3_refine'}
        for fid in v3_refine_field_ids:
            cur.execute("SELECT * FROM fundamental_fields WHERE id = ?", (fid,))
            f = cur.fetchone()
            if f['sweep_phase'] != 3:
                continue
            # expected_refine_count: build refine_grid and count
            from s001.fundamental_probes import refine_grid
            import json as _json
            try:
                refine_sets = {
                    'op': set(_json.loads(f['refine_op_set'])),
                    'mag': set(_json.loads(f['refine_mag_set'])),
                    'gate': set(_json.loads(f['refine_gate_set'])),
                    'threshold': set(_json.loads(f['refine_threshold_set'])),
                }
            except (TypeError, _json.JSONDecodeError):
                continue
            coarse_winner = {
                'op': f['coarse_winner_op'], 'mag': f['coarse_winner_mag'],
                'gate': f['coarse_winner_gate'], 'threshold': f['coarse_winner_threshold'],
            }
            expected = len(refine_grid(coarse_winner, refine_sets))
            cur.execute(
                "SELECT COUNT(*) FROM probe_results "
                "WHERE field_id = ? AND bake_hash = ? AND sweep_stage = 'refine'",
                (fid, bake_hash))
            count = cur.fetchone()[0]
            if count >= expected:
                update_v3_winner(con, fid, bake_hash)
```

Update the existing v2 sweep regex block to add `('v2', f['id'])` instead of just `f['id']` to `sweep_field_ids`:

```python
                touched_field_ids.add(f['id'])
                sweep_field_ids.add(('v2', f['id']))
                continue
```

- [ ] **Step 4: Run test to verify it passes**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_score_probes.py -v
```

Expected: new tests PASS, existing v2 tests still PASS.

- [ ] **Step 5: Commit**

```
cd /home/txy/qc_work/data
git add scripts/score_probes.py tests/test_score_probes.py
git commit -m "feat(s001): score_probes routes v3c/v3r specs + triggers update_v3_winner"
```

---

## Task 11: Universe Scanner Spec Generator

**Files:**
- Create: `/home/txy/qc_work/data/scripts/gen_scan_spec.py`
- Create: `/home/txy/qc_work/data/tests/test_scan_spec.py`

- [ ] **Step 1: Write the failing test**

Create `/home/txy/qc_work/data/tests/test_scan_spec.py`:

```python
"""Tests for the universe scanner spec generator."""
import sqlite3
from scripts.gen_scan_spec import generate_scan_spec


def test_generate_scan_spec_inserts_priority_zero_spec(tmp_db, tmp_path):
    base = tmp_path / 'base.py'
    base.write_text(
        "import math\n"
        "class S001(QCAlgorithm):\n"
        "    def Initialize(self): pass\n"
        "    def OnData(self, data):\n"
        "        for sym in self.qqq_list:\n"
        "            score = 1.0\n"
        "            candidates.append((sym, score, conv))\n")
    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("""INSERT INTO fundamental_fields
            (id, category, field_name, accessor, container, probe_op,
             probe_threshold, probe_boost, data_type_hint)
            VALUES (1, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                    '>', '1e9', 1.08, 'absolute_amount')""")
        con.commit()

    generate_scan_spec(db_path=tmp_db, base_path=str(base), bake_hash='BAKE_TEST')

    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("SELECT name, priority FROM backtest_queue "
                    "WHERE name LIKE 'S001_SCAN_FUNDAMENTALS_%'")
        row = cur.fetchone()
    assert row is not None
    assert row[0] == 'S001_SCAN_FUNDAMENTALS_BAKE_TEST'
    assert row[1] == 0  # priority 0 jumps the queue


def test_generate_scan_spec_skips_categorical(tmp_db, tmp_path):
    """Categorical fields aren't scanned — only numeric fields with a usable accessor."""
    base = tmp_path / 'base.py'
    base.write_text(
        "import math\n"
        "class S001(QCAlgorithm):\n"
        "    def OnData(self, data):\n"
        "        candidates.append((sym, score, conv))\n")
    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("""INSERT INTO fundamental_fields
            (id, category, field_name, accessor, container, probe_op,
             probe_threshold, probe_boost, data_type_hint)
            VALUES (1, 'ac', 'fin_health', '_ac_z.fin_health', 'asset_classification',
                    'eq', '"A"', 1.08, 'categorical')""")
        cur.execute("""INSERT INTO fundamental_fields
            (id, category, field_name, accessor, container, probe_op,
             probe_threshold, probe_boost, data_type_hint)
            VALUES (2, 'bs', 'cash', '_bs_z.cash', 'balance_sheet',
                    '>', '1e9', 1.08, 'absolute_amount')""")
        con.commit()

    generate_scan_spec(db_path=tmp_db, base_path=str(base), bake_hash='BAKE_TEST')

    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        code = cur.execute(
            "SELECT code FROM backtest_queue "
            "WHERE name = 'S001_SCAN_FUNDAMENTALS_BAKE_TEST'").fetchone()[0]
    assert '_ac_z.fin_health' not in code
    assert '_bs_z.cash' in code
```

- [ ] **Step 2: Run test to verify it fails**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_scan_spec.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create the scanner generator**

Create `/home/txy/qc_work/data/scripts/gen_scan_spec.py`:

```python
"""Generate the universe scanner backtest spec.

The scanner runs once per bake. It iterates every QQQ symbol, reads each
non-categorical fundamental field via its accessor, and emits a JSON log line
per (symbol, field_id, value) triple. After the backtest completes, run
`scripts/parse_scan_log.py` to populate field_universe_stats.

Usage:
    python -m scripts.gen_scan_spec --base /home/txy/qc_work/data/s001/s001_*.py \\
        --bake-hash <md5> [--db /home/txy/qc_work/data/S001.db]
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from s001.fundamental_probes import BIND, CONTAINER_ALIAS  # noqa: E402


SCAN_BLOCK_TEMPLATE = """\
   # === SCANNER BLOCK ===
   if not getattr(self, '_scanner_done', False):
    self._scanner_done = True
    for sym in self.qqq_list:
{accessors}
   # === END SCANNER BLOCK ===
"""


def _build_accessor_block(fields):
    """Render the per-field log statements that live inside the scanner loop."""
    lines = []
    for f in fields:
        accessor = f['accessor']
        # Add period suffix if present
        if f['period']:
            accessor = f"{accessor}.{f['period']}"
        # Replace top-level container alias with self.securities[sym].fundamentals.<...>
        # The BIND block already aliases _bs_z, _ops_z, etc. — we keep using those.
        line = (
            f"     try:\n"
            f"      _v = {accessor}\n"
            f"      if _v is not None:\n"
            f"       self.log(json.dumps(['SCAN', str(sym), {f['id']}, float(_v)]))\n"
            f"     except: pass"
        )
        lines.append(line)
    return '\n'.join(lines)


def generate_scan_spec(db_path, base_path, bake_hash):
    """Generate and queue the scanner backtest spec.

    Reads non-categorical fundamental_fields, builds a single backtest spec that
    iterates every QQQ symbol on the first trading day and logs every field
    value, queues at priority=0.
    """
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""SELECT id, accessor, container, period, data_type_hint, field_name
                       FROM fundamental_fields
                       WHERE data_type_hint IS NULL OR data_type_hint != 'categorical'
                       ORDER BY id""")
        fields = [dict(r) for r in cur.fetchall()]

    with open(base_path) as fh:
        base_code = fh.read()
    if 'import json' not in base_code:
        base_code = 'import json\n' + base_code
    accessors = _build_accessor_block(fields)
    scan_block = SCAN_BLOCK_TEMPLATE.format(accessors=accessors)
    anchor = '   candidates.append((sym, score, conv))'
    code = base_code.replace(anchor, BIND + scan_block + anchor)
    name = f'S001_SCAN_FUNDAMENTALS_{bake_hash[:8]}' if len(bake_hash) > 8 else f'S001_SCAN_FUNDAMENTALS_{bake_hash}'
    h = hashlib.md5(code.encode()).hexdigest()

    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        try:
            cur.execute(
                "INSERT INTO backtest_queue "
                "(name, code, status, priority, submitted_at, code_hash, project_id) "
                "VALUES (?, ?, 'queued', 0, datetime('now'), ?, NULL)",
                (name, code, h))
            con.commit()
            return name
        except sqlite3.IntegrityError as e:
            print(f'Skip {name}: {e}', file=sys.stderr)
            return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base', required=True, help='Path to s001_*_base.py')
    p.add_argument('--bake-hash', required=True)
    p.add_argument('--db', default='/home/txy/qc_work/data/S001.db')
    args = p.parse_args()
    name = generate_scan_spec(args.db, args.base, args.bake_hash)
    if name:
        print(f'Queued scan spec: {name}')


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run test to verify it passes**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_scan_spec.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```
cd /home/txy/qc_work/data
git add scripts/gen_scan_spec.py tests/test_scan_spec.py
git commit -m "feat(s001): gen_scan_spec.py emits priority-0 universe scanner backtest"
```

---

## Task 12: Universe Scanner Log Parser

**Files:**
- Create: `/home/txy/qc_work/data/scripts/parse_scan_log.py`
- Create: `/home/txy/qc_work/data/tests/test_parse_scan_log.py`

- [ ] **Step 1: Write the failing test**

Create `/home/txy/qc_work/data/tests/test_parse_scan_log.py`:

```python
"""Tests for the universe scanner log parser."""
import json
import sqlite3
from scripts.parse_scan_log import parse_scan_log


def _seed_field(db, field_id):
    with sqlite3.connect(db) as con:
        con.execute("""INSERT INTO fundamental_fields
            (id, category, field_name, accessor, container, probe_op,
             probe_threshold, probe_boost)
            VALUES (?, 'bs', 'cash', ?, 'balance_sheet', '>', '1e9', 1.08)""",
            (field_id, f'_bs_z.cash_{field_id}'))
        con.commit()


def test_parses_log_and_inserts_percentiles(tmp_db):
    _seed_field(tmp_db, 1)
    log_lines = []
    for i in range(1, 101):  # 100 symbols, values 1.0..100.0
        log_lines.append(json.dumps(['SCAN', f'S{i}', 1, float(i)]))

    parse_scan_log(db_path=tmp_db, log_lines=log_lines, bake_hash='BAKE_TEST',
                   scanned_at='2026-04-27T00:00:00+00:00')

    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        row = cur.execute(
            "SELECT p10, p25, p50, p75, p90, sample_size FROM field_universe_stats "
            "WHERE field_id=1 AND bake_hash='BAKE_TEST'").fetchone()
    p10, p25, p50, p75, p90, n = row
    assert n == 100
    assert abs(p10 - 10.9) < 1.0   # numpy.percentile linear interp ≈ 10.9
    assert abs(p25 - 25.75) < 1.0
    assert abs(p50 - 50.5) < 1.0
    assert abs(p75 - 75.25) < 1.0
    assert abs(p90 - 90.1) < 1.0


def test_skips_field_below_sample_threshold(tmp_db):
    _seed_field(tmp_db, 1)
    log_lines = [json.dumps(['SCAN', f'S{i}', 1, float(i)]) for i in range(1, 30)]  # 29 obs

    parse_scan_log(db_path=tmp_db, log_lines=log_lines, bake_hash='BAKE_TEST',
                   scanned_at='2026-04-27T00:00:00+00:00')

    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT COUNT(*) FROM field_universe_stats WHERE field_id=1").fetchone()
    assert row[0] == 0  # below 50-sample threshold, skipped


def test_ignores_non_scan_log_lines(tmp_db):
    _seed_field(tmp_db, 1)
    log_lines = ['some unrelated log line', '{"hello": "world"}']
    log_lines.extend(json.dumps(['SCAN', f'S{i}', 1, float(i)]) for i in range(1, 60))

    parse_scan_log(db_path=tmp_db, log_lines=log_lines, bake_hash='BAKE_TEST',
                   scanned_at='2026-04-27T00:00:00+00:00')

    with sqlite3.connect(tmp_db) as con:
        row = con.execute(
            "SELECT sample_size FROM field_universe_stats WHERE field_id=1").fetchone()
    assert row[0] == 59  # only the 59 SCAN lines were counted
```

- [ ] **Step 2: Run test to verify it fails**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_parse_scan_log.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create the log parser**

Create `/home/txy/qc_work/data/scripts/parse_scan_log.py`:

```python
"""Parse the universe scanner backtest log into field_universe_stats.

Reads SCAN log lines of the form ['SCAN', <symbol>, <field_id>, <value>],
groups by field_id, computes {p10, p25, p50, p75, p90} per field, persists
to field_universe_stats with sample_size threshold = 50.

Usage:
    python -m scripts.parse_scan_log --bake-hash <md5> [--db S001.db]

If --bake-hash matches a queued/done scan spec named S001_SCAN_FUNDAMENTALS_<bake_hash[:8]>,
reads its log payload from backtest_queue.result_json. Otherwise reads from stdin.
"""
import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np


SAMPLE_SIZE_THRESHOLD = 50


def _scanned_at_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def parse_scan_log(db_path, log_lines, bake_hash, scanned_at=None):
    """Parse SCAN log lines into field_universe_stats rows.

    log_lines: iterable of strings (one per log line).
    bake_hash: the bake hash to associate with these stats.
    scanned_at: ISO-8601 timestamp; defaults to now.
    """
    if scanned_at is None:
        scanned_at = _scanned_at_now()

    by_field = defaultdict(list)
    for line in log_lines:
        line = line.strip()
        if not line.startswith('[') or 'SCAN' not in line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, list) or len(parsed) < 4 or parsed[0] != 'SCAN':
            continue
        try:
            field_id = int(parsed[2])
            value = float(parsed[3])
        except (ValueError, TypeError):
            continue
        by_field[field_id].append(value)

    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        for field_id, values in by_field.items():
            if len(values) < SAMPLE_SIZE_THRESHOLD:
                continue
            arr = np.array(values, dtype=float)
            p10, p25, p50, p75, p90 = np.percentile(arr, [10, 25, 50, 75, 90])
            cur.execute(
                """INSERT OR REPLACE INTO field_universe_stats
                   (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (field_id, bake_hash, float(p10), float(p25), float(p50),
                 float(p75), float(p90), len(values), scanned_at))
        con.commit()


def _read_log_from_db(db_path, bake_hash):
    spec_name = f'S001_SCAN_FUNDAMENTALS_{bake_hash[:8]}'
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        row = cur.execute(
            "SELECT result_json FROM backtest_queue WHERE name = ?",
            (spec_name,)).fetchone()
    if not row or not row[0]:
        raise SystemExit(f'No completed scan spec named {spec_name}')
    payload = json.loads(row[0])
    # Lean log entries land under various keys; payload['logs'] is the convention here
    return payload.get('logs', [])


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bake-hash', required=True)
    p.add_argument('--db', default='/home/txy/qc_work/data/S001.db')
    p.add_argument('--from-stdin', action='store_true',
                   help='Read log lines from stdin instead of from backtest_queue')
    args = p.parse_args()
    if args.from_stdin:
        lines = sys.stdin.read().splitlines()
    else:
        lines = _read_log_from_db(args.db, args.bake_hash)
    parse_scan_log(args.db, lines, args.bake_hash)
    print('Universe stats persisted.')


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run test to verify it passes**

```
cd /home/txy/qc_work/data
python -m pytest tests/test_parse_scan_log.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```
cd /home/txy/qc_work/data
git add scripts/parse_scan_log.py tests/test_parse_scan_log.py
git commit -m "feat(s001): parse_scan_log.py — populate field_universe_stats from scanner output"
```

---

## Task 13: Generator Template Update

**Files:**
- Create: `/home/txy/qc_work/data/gen_s001_R493.py` (template for first v3-driven round)

- [ ] **Step 1: Create the new generator**

Create `/home/txy/qc_work/data/gen_s001_R493.py`:

```python
"""R493 — first v3-driven round on BAKE-45.

Requires field_universe_stats populated for BAKE-45 (run gen_scan_spec +
parse_scan_log first). Falls back to Phase 1-only emission if stats are missing.
"""
import ast, hashlib, sqlite3, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from s001.fundamental_probes import emit_probes_for_db, BIND

BASE = '/home/txy/qc_work/data/s001/s001_20260425_base.py'
EXPECTED = '7d340db8c58a1da6a40a2872e82a1890'
with open(BASE) as f: base_code = f.read()
assert hashlib.md5(base_code.encode()).hexdigest() == EXPECTED
print('Base verified (BAKE-45)')

ANCHOR = '   candidates.append((sym, score, conv))'
specs = []

for i in range(3):
    code = base_code.replace(ANCHOR, f'   # vbake45_noop_{i}\n' + ANCHOR)
    specs.append((f'S001_R493_VBAKE45_NOOP_{i}', code))
for i in range(3):
    code = base_code.replace(ANCHOR, f'   # verify_bake45_baseline_rep{i}\n' + ANCHOR)
    specs.append((f'S001_R493_VERIFY_bake45_rep{i}', code))

auto = emit_probes_for_db(
    db_path='/home/txy/qc_work/data/S001.db',
    round_n=493,
    k_new=20, k_verify=0,
    k_coarse_fields=2, k_refine_fields=2,
    include_bind=False)
phase1 = sum(1 for n, _ in auto if '_v3c_' not in n and '_v3r_' not in n)
v3c = sum(1 for n, _ in auto if '_v3c_' in n)
v3r = sum(1 for n, _ in auto if '_v3r_' in n)
print(f'Auto-emitted {len(auto)} ({phase1} Phase 1 + {v3c} v3 coarse + {v3r} v3 refine)')

for name, body in auto:
    code = base_code.replace(ANCHOR, BIND + body + '\n' + ANCHOR)
    specs.append((name, code))

print(f'Total: {len(specs)}')
for name, code in specs:
    try: ast.parse(code)
    except SyntaxError as e: print(f'SYNTAX ERROR in {name}: {e}'); sys.exit(1)
print('All parse OK')

con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
cur = con.cursor()
inserted = 0
for n, c in specs:
    h = hashlib.md5(c.encode()).hexdigest()
    try:
        cur.execute(
            "INSERT INTO backtest_queue (name, code, status, priority, submitted_at, code_hash, project_id) "
            "VALUES (?, ?, 'queued', ?, ?, ?, NULL)",
            (n, c, 1 if 'VBAKE' in n or 'VERIFY' in n else 5, '2026-05-05 03:30:00', h))
        inserted += 1
    except sqlite3.IntegrityError as e: print(f'Skip {n}: {e}')
con.commit()
print(f'Inserted {inserted} R493 specs')
```

- [ ] **Step 2: Run the generator (after universe scanner has populated stats)**

Pre-flight: ensure scanner has run first.

```
cd /home/txy/qc_work/data
python -c "import sqlite3; con=sqlite3.connect('S001.db'); print('field_universe_stats rows:', con.execute('SELECT COUNT(*) FROM field_universe_stats WHERE bake_hash=\"7d340db8c58a1da6a40a2872e82a1890\"').fetchone())"
```

If 0 rows: stop here, run scanner first via:
```
python -m scripts.gen_scan_spec --base /home/txy/qc_work/data/s001/s001_20260425_base.py \
    --bake-hash 7d340db8c58a1da6a40a2872e82a1890
# wait for backtest worker to drain the priority-0 spec
python -m scripts.parse_scan_log --bake-hash 7d340db8c58a1da6a40a2872e82a1890
```

If >0 rows: proceed:
```
python gen_s001_R493.py
```

Expected output:
```
Base verified (BAKE-45)
Auto-emitted 162 (20 Phase 1 + 142 v3 coarse + 0 v3 refine)
Total: 168
All parse OK
Inserted 168 R493 specs
```

(Refine count starts at 0 — no fields are at phase=3 yet because no coarse has completed; refine will populate in subsequent rounds.)

- [ ] **Step 3: Commit**

```
cd /home/txy/qc_work/data
git add gen_s001_R493.py
git commit -m "feat(s001): R493 first v3-driven generator on BAKE-45"
```

---

## Self-Review Checklist (Engineer running this plan)

After all tasks complete:

- [ ] All migration tests pass: `pytest tests/test_migrate_schema.py`
- [ ] All library function tests pass: `pytest tests/test_fundamental_probes.py`
- [ ] All score-routing tests pass: `pytest tests/test_score_probes.py`
- [ ] All emit tests pass: `pytest tests/test_emit_probes.py`
- [ ] Scanner tests pass: `pytest tests/test_scan_spec.py tests/test_parse_scan_log.py`
- [ ] Full suite: `pytest -v` — no failures
- [ ] Live migration applied to S001.db; v2 sealed fields renumbered to phase=4 ver=2
- [ ] Universe scanner spec queued and drained for current bake
- [ ] `field_universe_stats` populated for ≥800 fields (sample_size ≥ 50)
- [ ] R493 generator emits ≥150 specs (20 Phase 1 + 144 v3 coarse + 0 v3 refine + 6 NOOP/VERIFY)
- [ ] First round drains in cluster; `score_probes --round 493` reports v3c hits
- [ ] After R493 + R494: at least one field reaches phase=3 (coarse complete, refine in flight)
- [ ] After R495: at least one field reaches phase=4 with sweep_version=3 (v3 sealed)

If any check fails, return to the relevant task and fix.
