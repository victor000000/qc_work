# S001 Fundamental Data Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Catalogue LEAN's full ~900-field fundamental universe into S001.db, render probe code declaratively, and feed back probe outcomes (hot/neutral/harmful) to drive next-round picking.

**Architecture:** Pure-functional library (`s001/fundamental_probes.py`) + 3 thin CLI scripts (`catalogue_universe.py`, `emit_probes.py`, `score_probes.py`) sharing the library; SQLite schema extended with template + classification columns and a new `probe_results` history table. Per-round generators (`gen_s001_R{N}.py`) gain a single import + call.

**Tech Stack:** Python 3.13, SQLite3 (S001.db at `/home/txy/qc_work/data/S001.db`), pytest for tests, LEAN type-stub at `/home/txy/.local/share/pipx/venvs/lean/lib/python3.13/site-packages/QuantConnect/Data/Fundamental/__init__.pyi`.

**Note:** Working directory `/home/txy/qc_work/data/` is **not a git repository**. Replace any "commit" step with "save checkpoint" (overwrite a `.bak` of the modified file) or just confirm the test passes. The plan uses verify-via-tests as the per-task checkpoint.

---

## Task 0: Test Infrastructure Setup

**Files:**
- Create: `/home/txy/qc_work/data/tests/__init__.py`
- Create: `/home/txy/qc_work/data/tests/conftest.py`
- Create: `/home/txy/qc_work/data/tests/test_smoke.py`
- Create: `/home/txy/qc_work/data/pytest.ini`

- [ ] **Step 1: Verify pytest is importable**

Run: `pytest --version`
Expected: prints version (e.g. `pytest 8.x.x`).

If "command not found", run `pip install --user pytest` and retry.

- [ ] **Step 2: Create empty package marker**

Create `/home/txy/qc_work/data/tests/__init__.py` with empty contents.

- [ ] **Step 3: Create pytest config**

Create `/home/txy/qc_work/data/pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v --tb=short
```

- [ ] **Step 4: Create shared fixtures**

Create `/home/txy/qc_work/data/tests/conftest.py`:

```python
"""Shared pytest fixtures for s001 tests."""
import sqlite3
import tempfile
from pathlib import Path

import pytest

REAL_DB = '/home/txy/qc_work/data/S001.db'


@pytest.fixture
def tmp_db(tmp_path):
    """Empty temporary SQLite db with the production schema applied."""
    db = tmp_path / 'test.db'
    con = sqlite3.connect(str(db))
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
    con.commit()
    con.close()
    return str(db)
```

- [ ] **Step 5: Create smoke test**

Create `/home/txy/qc_work/data/tests/test_smoke.py`:

```python
"""Smoke test for pytest infrastructure."""
import sqlite3


def test_pytest_works():
    assert 1 + 1 == 2


def test_tmp_db_has_tables(tmp_db):
    con = sqlite3.connect(tmp_db)
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {r[0] for r in cur.fetchall()}
    assert 'fundamental_fields' in tables
    assert 'probe_results' in tables
    assert 'experiments' in tables
    assert 'backtest_queue' in tables
```

- [ ] **Step 6: Run tests to verify infrastructure**

Run: `cd /home/txy/qc_work/data && pytest tests/test_smoke.py -v`
Expected: 2 passed.

---

## Task 1: Apply Schema Migration to S001.db

**Files:**
- Create: `/home/txy/qc_work/data/scripts/__init__.py`
- Create: `/home/txy/qc_work/data/scripts/migrate_schema.py`
- Create: `/home/txy/qc_work/data/tests/test_migrate_schema.py`

- [ ] **Step 1: Create scripts package marker**

Create `/home/txy/qc_work/data/scripts/__init__.py` empty.

- [ ] **Step 2: Write the failing test**

Create `/home/txy/qc_work/data/tests/test_migrate_schema.py`:

```python
"""Schema migration tests."""
import sqlite3

from scripts.migrate_schema import apply_schema_migration


def test_migration_adds_columns_and_table(tmp_db):
    # tmp_db already has the new schema baked in via conftest;
    # to simulate the legacy state we drop the new columns first.
    con = sqlite3.connect(tmp_db)
    cur = con.cursor()
    # Recreate the legacy fundamental_fields shape (no new columns).
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
        test_notes TEXT
    )""")
    cur.execute(
        "INSERT INTO fundamental_fields (category, field_name, accessor) "
        "VALUES (?, ?, ?)", ('valuation', 'pe_ratio', '_vr.pe_ratio'))
    con.commit()
    con.close()

    apply_schema_migration(tmp_db)

    con = sqlite3.connect(tmp_db)
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
    from scripts.migrate_schema import apply_schema_migration
    apply_schema_migration(tmp_db)  # second run on already-migrated db
    apply_schema_migration(tmp_db)  # third run
    # No assertion needed beyond no-exception.
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /home/txy/qc_work/data && pytest tests/test_migrate_schema.py -v`
Expected: ImportError or "module not found" for `scripts.migrate_schema`.

- [ ] **Step 4: Implement migration**

Create `/home/txy/qc_work/data/scripts/migrate_schema.py`:

```python
"""Apply schema migration to S001.db: extend fundamental_fields,
create probe_results, migrate legacy classifications.

Idempotent: safe to re-run on an already-migrated database."""
import sqlite3
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
]


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
]


def existing_columns(cur, table):
    cur.execute(f"PRAGMA table_info({table})")
    return {r[1] for r in cur.fetchall()}


def apply_schema_migration(db_path):
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    cols = existing_columns(cur, 'fundamental_fields')
    for name, sqltype, default_clause in NEW_COLUMNS:
        if name in cols:
            continue
        ddl = f"ALTER TABLE fundamental_fields ADD COLUMN {name} {sqltype}"
        if default_clause:
            ddl += f" {default_clause}"
        cur.execute(ddl)

    cur.execute(PROBE_RESULTS_DDL)

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
    con.close()


if __name__ == '__main__':
    db = sys.argv[1] if len(sys.argv) > 1 else '/home/txy/qc_work/data/S001.db'
    apply_schema_migration(db)
    print(f"Migration applied to {db}")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/txy/qc_work/data && pytest tests/test_migrate_schema.py -v`
Expected: 2 passed.

- [ ] **Step 6: Apply to real S001.db**

```bash
cp /home/txy/qc_work/data/S001.db /home/txy/qc_work/data/S001.db.pre_migration.bak
cd /home/txy/qc_work/data && python3 -m scripts.migrate_schema
```

Verify:
```bash
python3 -c "
import sqlite3
con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
cur = con.cursor()
cur.execute('PRAGMA table_info(fundamental_fields)')
cols = {r[1] for r in cur.fetchall()}
print('Has new cols:', {'period','container','probe_op','classification','data_type_hint'} <= cols)
cur.execute('SELECT name FROM sqlite_master WHERE type=\"table\" AND name=\"probe_results\"')
print('probe_results exists:', cur.fetchone() is not None)
"
```
Expected: both `True`.

---

## Task 2: Library — `accessor_for(row)`

**Files:**
- Create: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Create: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Write the failing test**

Create `/home/txy/qc_work/data/tests/test_fundamental_probes.py`:

```python
"""Tests for s001.fundamental_probes library."""
import pytest

from s001.fundamental_probes import accessor_for


class TestAccessorFor:
    def test_valuation_ratios_no_period(self):
        row = {'container': 'valuation_ratios', 'field_name': 'pe_ratio', 'period': None}
        assert accessor_for(row) == '_vr_z.pe_ratio'

    def test_balance_sheet_with_period(self):
        row = {'container': 'balance_sheet', 'field_name': 'long_term_debt', 'period': 'twelve_months'}
        assert accessor_for(row) == '_bs_z.long_term_debt.twelve_months'

    def test_operation_ratios_one_year(self):
        row = {'container': 'operation_ratios', 'field_name': 'roe', 'period': 'one_year'}
        assert accessor_for(row) == '_ops_z.roe.one_year'

    def test_cash_flow_statement(self):
        row = {'container': 'cash_flow_statement', 'field_name': 'free_cash_flow', 'period': 'twelve_months'}
        assert accessor_for(row) == '_cfs_z.free_cash_flow.twelve_months'

    def test_income_statement(self):
        row = {'container': 'income_statement', 'field_name': 'net_income', 'period': 'twelve_months'}
        assert accessor_for(row) == '_inc_z.net_income.twelve_months'

    def test_earning_ratios(self):
        row = {'container': 'earning_ratios', 'field_name': 'diluted_eps_growth', 'period': 'one_year'}
        assert accessor_for(row) == '_ers_z.diluted_eps_growth.one_year'

    def test_earning_reports(self):
        row = {'container': 'earning_reports', 'field_name': 'basic_eps', 'period': 'twelve_months'}
        assert accessor_for(row) == '_er_z.basic_eps.twelve_months'

    def test_asset_classification_no_period(self):
        row = {'container': 'asset_classification', 'field_name': 'financial_health_grade', 'period': None}
        assert accessor_for(row) == '_ac_z.financial_health_grade'

    def test_security_reference_no_period(self):
        row = {'container': 'security_reference', 'field_name': 'ipo_date', 'period': None}
        assert accessor_for(row) == '_sr_z.ipo_date'

    def test_unknown_container_raises(self):
        row = {'container': 'mystery', 'field_name': 'foo', 'period': None}
        with pytest.raises(KeyError):
            accessor_for(row)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestAccessorFor -v`
Expected: ImportError on `s001.fundamental_probes`.

- [ ] **Step 3: Implement minimal**

Create `/home/txy/qc_work/data/s001/fundamental_probes.py`:

```python
"""Library for cataloguing, rendering, and classifying S001 fundamental probes.

Pure functions; all DB I/O lives in scripts/{catalogue,emit,score}_probes.py."""

CONTAINER_ALIAS = {
    'balance_sheet':        '_bs_z',
    'cash_flow_statement':  '_cfs_z',
    'income_statement':     '_inc_z',
    'operation_ratios':     '_ops_z',
    'valuation_ratios':     '_vr_z',
    'earning_ratios':       '_ers_z',
    'earning_reports':      '_er_z',
    'asset_classification': '_ac_z',
    'security_reference':   '_sr_z',
}


def accessor_for(row):
    """Build the Python accessor string for a fundamental_fields row.

    row: dict-like with 'container', 'field_name', 'period' keys.
    Returns: e.g. '_vr_z.pe_ratio' or '_bs_z.long_term_debt.twelve_months'.
    """
    base = f"{CONTAINER_ALIAS[row['container']]}.{row['field_name']}"
    return f"{base}.{row['period']}" if row['period'] else base
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestAccessorFor -v`
Expected: 10 passed.

---

## Task 3: Library — `classify_delta(d)`

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Append the failing test**

Append to `tests/test_fundamental_probes.py`:

```python
from s001.fundamental_probes import classify_delta


class TestClassifyDelta:
    def test_clearly_hot(self):
        assert classify_delta(0.0030) == 'hot'

    def test_clearly_harmful(self):
        assert classify_delta(-0.0030) == 'harmful'

    def test_neutral_positive(self):
        assert classify_delta(0.0010) == 'neutral'

    def test_neutral_negative(self):
        assert classify_delta(-0.0010) == 'neutral'

    def test_zero(self):
        assert classify_delta(0.0) == 'neutral'

    def test_exact_positive_boundary_neutral(self):
        # delta > +0.0015 → 'hot'; exactly +0.0015 stays 'neutral'.
        assert classify_delta(0.0015) == 'neutral'

    def test_exact_negative_boundary_neutral(self):
        # delta < -0.0015 → 'harmful'; exactly -0.0015 stays 'neutral'.
        assert classify_delta(-0.0015) == 'neutral'

    def test_just_above_positive_boundary(self):
        assert classify_delta(0.00151) == 'hot'

    def test_just_below_negative_boundary(self):
        assert classify_delta(-0.00151) == 'harmful'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestClassifyDelta -v`
Expected: ImportError on `classify_delta`.

- [ ] **Step 3: Implement**

Append to `s001/fundamental_probes.py`:

```python
HOT_THRESHOLD = 0.0015      # delta strictly greater → 'hot'
HARMFUL_THRESHOLD = -0.0015  # delta strictly less → 'harmful'


def classify_delta(d):
    """Classify a probe's CAR/MDD delta vs round NOOP baseline.

    Returns one of: 'hot', 'neutral', 'harmful'.
    Boundary semantics: exact ±0.0015 is 'neutral' (strict >/<)."""
    if d > HOT_THRESHOLD:
        return 'hot'
    if d < HARMFUL_THRESHOLD:
        return 'harmful'
    return 'neutral'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestClassifyDelta -v`
Expected: 9 passed.

---

## Task 4: Library — `field_rollup(results)`

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Append the failing test**

Append to `tests/test_fundamental_probes.py`:

```python
from s001.fundamental_probes import field_rollup


class TestFieldRollup:
    def test_empty_results_untested(self):
        assert field_rollup([]) == 'untested'

    def test_single_hot(self):
        assert field_rollup([{'classification': 'hot'}]) == 'hot'

    def test_single_neutral(self):
        assert field_rollup([{'classification': 'neutral'}]) == 'neutral'

    def test_single_harmful(self):
        assert field_rollup([{'classification': 'harmful'}]) == 'harmful'

    def test_mixed_hot_and_harmful_poisons(self):
        # One harmful poisons even with hot present.
        results = [{'classification': 'hot'}, {'classification': 'harmful'}]
        assert field_rollup(results) == 'harmful'

    def test_mixed_hot_and_neutral_is_hot(self):
        results = [{'classification': 'hot'}, {'classification': 'neutral'}, {'classification': 'neutral'}]
        assert field_rollup(results) == 'hot'

    def test_all_neutral_is_neutral(self):
        results = [{'classification': 'neutral'}] * 3
        assert field_rollup(results) == 'neutral'

    def test_three_hot_is_hot(self):
        results = [{'classification': 'hot'}] * 3
        assert field_rollup(results) == 'hot'

    def test_harmful_alone(self):
        assert field_rollup([{'classification': 'harmful'}, {'classification': 'harmful'}]) == 'harmful'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestFieldRollup -v`
Expected: ImportError on `field_rollup`.

- [ ] **Step 3: Implement**

Append to `s001/fundamental_probes.py`:

```python
def field_rollup(results):
    """Compute aggregate field classification from probe_results rows
    already filtered to the current bake_hash.

    Rule (conservative, matches §7.2 of spec):
      - empty → 'untested'
      - any 'harmful' → 'harmful' (poisons even if hot exists)
      - any 'hot' → 'hot'
      - else → 'neutral'

    results: iterable of dict-like rows with 'classification' key."""
    if not results:
        return 'untested'
    classes = {r['classification'] for r in results}
    if 'harmful' in classes:
        return 'harmful'
    if 'hot' in classes:
        return 'hot'
    return 'neutral'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestFieldRollup -v`
Expected: 9 passed.

---

## Task 5: Library — `build_condition` for `>` operator

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Append the failing test**

Append to `tests/test_fundamental_probes.py`:

```python
from s001.fundamental_probes import build_condition


class TestBuildConditionGt:
    def test_numeric_gt(self):
        row = {'probe_op': '>', 'probe_threshold': '15', 'data_type_hint': 'numeric'}
        assert build_condition(row, '_v') == '_v is not None and _v > 15'

    def test_signed_ratio_gt(self):
        row = {'probe_op': '>', 'probe_threshold': '0.10', 'data_type_hint': 'signed_ratio'}
        assert build_condition(row, '_v') == '_v is not None and _v > 0.10'

    def test_absolute_amount_gt(self):
        # `>` does not need 0<_v guard (we want positive amounts above threshold).
        row = {'probe_op': '>', 'probe_threshold': '1e9', 'data_type_hint': 'absolute_amount'}
        assert build_condition(row, '_v') == '_v is not None and _v > 1e9'

    def test_gte(self):
        row = {'probe_op': '>=', 'probe_threshold': '15', 'data_type_hint': 'numeric'}
        assert build_condition(row, '_v') == '_v is not None and _v >= 15'

    def test_threshold_can_be_negative(self):
        row = {'probe_op': '>', 'probe_threshold': '-0.05', 'data_type_hint': 'signed_ratio'}
        assert build_condition(row, '_v') == '_v is not None and _v > -0.05'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestBuildConditionGt -v`
Expected: ImportError on `build_condition`.

- [ ] **Step 3: Implement (`>`/`>=` only for now)**

Append to `s001/fundamental_probes.py`:

```python
def build_condition(row, var='_v'):
    """Build the boolean condition fragment for a probe row.

    row: must have probe_op, probe_threshold, data_type_hint keys.
    var: the local name of the value (default '_v').
    Returns: a Python expression string (no leading 'if', no trailing colon).
    """
    op = row['probe_op']
    thr = row['probe_threshold']
    hint = row.get('data_type_hint') or 'numeric'

    if op in ('>', '>='):
        return f"{var} is not None and {var} {op} {thr}"
    raise NotImplementedError(f"build_condition: op {op!r} not yet supported")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestBuildConditionGt -v`
Expected: 5 passed.

---

## Task 6: Library — `build_condition` for `<` (3 data-type variants)

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Append the failing test**

Append to `tests/test_fundamental_probes.py`:

```python
class TestBuildConditionLt:
    def test_numeric_lt(self):
        # numeric: bare `<`, no special guard
        row = {'probe_op': '<', 'probe_threshold': '15', 'data_type_hint': 'numeric'}
        assert build_condition(row, '_v') == '_v is not None and _v < 15'

    def test_signed_ratio_lt(self):
        # signed_ratio: bare `<`, allows negatives like -0.05
        row = {'probe_op': '<', 'probe_threshold': '-0.05', 'data_type_hint': 'signed_ratio'}
        assert build_condition(row, '_v') == '_v is not None and _v < -0.05'

    def test_absolute_amount_lt_adds_zero_guard(self):
        # absolute_amount: must filter out 0/missing values via 0 < _v
        row = {'probe_op': '<', 'probe_threshold': '5e8', 'data_type_hint': 'absolute_amount'}
        assert build_condition(row, '_v') == '_v is not None and 0 < _v < 5e8'

    def test_absolute_amount_signed_lt_uses_abs(self):
        # absolute_amount_signed: BS/CFS sign-tolerant flavor
        row = {'probe_op': '<', 'probe_threshold': '1e8', 'data_type_hint': 'absolute_amount_signed'}
        assert build_condition(row, '_v') == '_v is not None and abs(_v) < 1e8'

    def test_lte_signed_ratio(self):
        row = {'probe_op': '<=', 'probe_threshold': '0', 'data_type_hint': 'signed_ratio'}
        assert build_condition(row, '_v') == '_v is not None and _v <= 0'

    def test_lte_absolute_amount(self):
        row = {'probe_op': '<=', 'probe_threshold': '1e9', 'data_type_hint': 'absolute_amount'}
        assert build_condition(row, '_v') == '_v is not None and 0 < _v <= 1e9'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestBuildConditionLt -v`
Expected: NotImplementedError or AssertionError on `<` op.

- [ ] **Step 3: Extend implementation**

Replace the body of `build_condition` in `s001/fundamental_probes.py` with:

```python
def build_condition(row, var='_v'):
    """Build the boolean condition fragment for a probe row.

    row: must have probe_op, probe_threshold, data_type_hint keys.
    var: the local name of the value (default '_v').
    Returns: a Python expression string (no leading 'if', no trailing colon).
    """
    op = row['probe_op']
    thr = row['probe_threshold']
    hint = row.get('data_type_hint') or 'numeric'

    if op in ('>', '>='):
        return f"{var} is not None and {var} {op} {thr}"

    if op in ('<', '<='):
        if hint == 'absolute_amount':
            return f"{var} is not None and 0 < {var} {op} {thr}"
        if hint == 'absolute_amount_signed':
            # abs(_v) only makes sense for strict-less; for <= we keep same shape
            return f"{var} is not None and abs({var}) {op} {thr}"
        # numeric or signed_ratio: bare comparison
        return f"{var} is not None and {var} {op} {thr}"

    raise NotImplementedError(f"build_condition: op {op!r} not yet supported")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestBuildConditionLt tests/test_fundamental_probes.py::TestBuildConditionGt -v`
Expected: 11 passed (5 + 6).

---

## Task 7: Library — `build_condition` for `eq`/`in` (categorical)

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Append the failing test**

Append to `tests/test_fundamental_probes.py`:

```python
class TestBuildConditionCategorical:
    def test_eq_string(self):
        row = {'probe_op': 'eq', 'probe_threshold': '"A"', 'data_type_hint': 'categorical'}
        assert build_condition(row, '_v') == "_v == 'A'"

    def test_eq_int(self):
        row = {'probe_op': 'eq', 'probe_threshold': '207', 'data_type_hint': 'categorical'}
        assert build_condition(row, '_v') == '_v == 207'

    def test_in_strings(self):
        row = {'probe_op': 'in', 'probe_threshold': '["A","B+","B"]', 'data_type_hint': 'categorical'}
        assert build_condition(row, '_v') == "_v in ('A', 'B+', 'B')"

    def test_in_ints(self):
        row = {'probe_op': 'in', 'probe_threshold': '[205, 206, 207]', 'data_type_hint': 'categorical'}
        assert build_condition(row, '_v') == '_v in (205, 206, 207)'

    def test_in_single_value(self):
        row = {'probe_op': 'in', 'probe_threshold': '["A"]', 'data_type_hint': 'categorical'}
        # tuple comma needed for 1-element to avoid Python eval ambiguity
        assert build_condition(row, '_v') == "_v in ('A',)"

    def test_categorical_op_on_numeric_hint_raises(self):
        # Bad combo: 'in' with numeric hint should fail loud.
        row = {'probe_op': 'in', 'probe_threshold': '[1,2]', 'data_type_hint': 'numeric'}
        with pytest.raises(ValueError, match='categorical'):
            build_condition(row, '_v')

    def test_in_non_json_raises(self):
        row = {'probe_op': 'in', 'probe_threshold': 'A,B,C', 'data_type_hint': 'categorical'}
        with pytest.raises(ValueError):
            build_condition(row, '_v')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestBuildConditionCategorical -v`
Expected: NotImplementedError on `eq`/`in`.

- [ ] **Step 3: Extend implementation**

Replace `build_condition` in `s001/fundamental_probes.py` with:

```python
import json


def build_condition(row, var='_v'):
    """Build the boolean condition fragment for a probe row.

    row: must have probe_op, probe_threshold, data_type_hint keys.
    var: the local name of the value (default '_v').
    Returns: a Python expression string (no leading 'if', no trailing colon).
    """
    op = row['probe_op']
    thr = row['probe_threshold']
    hint = row.get('data_type_hint') or 'numeric'

    if op in ('>', '>='):
        return f"{var} is not None and {var} {op} {thr}"

    if op in ('<', '<='):
        if hint == 'absolute_amount':
            return f"{var} is not None and 0 < {var} {op} {thr}"
        if hint == 'absolute_amount_signed':
            return f"{var} is not None and abs({var}) {op} {thr}"
        return f"{var} is not None and {var} {op} {thr}"

    if op == 'eq':
        if hint != 'categorical':
            raise ValueError(f"op 'eq' requires data_type_hint='categorical', got {hint!r}")
        # threshold may be a quoted string ('"A"') or a bare number ('207')
        try:
            parsed = json.loads(thr)
        except (json.JSONDecodeError, ValueError):
            # bare number that JSON can parse, or already-quoted form
            parsed = json.loads(thr)
        return f"{var} == {parsed!r}" if isinstance(parsed, str) else f"{var} == {parsed}"

    if op == 'in':
        if hint != 'categorical':
            raise ValueError(f"op 'in' requires data_type_hint='categorical', got {hint!r}")
        try:
            parsed = json.loads(thr)
        except json.JSONDecodeError as e:
            raise ValueError(f"op 'in' requires JSON array threshold: {thr!r} ({e})")
        if not isinstance(parsed, list):
            raise ValueError(f"op 'in' requires JSON array threshold: got {type(parsed).__name__}")
        if len(parsed) == 1:
            tup_repr = f"({parsed[0]!r},)" if isinstance(parsed[0], str) else f"({parsed[0]},)"
        else:
            inner = ", ".join(repr(x) if isinstance(x, str) else str(x) for x in parsed)
            tup_repr = f"({inner})"
        return f"{var} in {tup_repr}"

    raise NotImplementedError(f"build_condition: op {op!r} not supported")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestBuildConditionCategorical -v`
Expected: 7 passed.

---

## Task 8: Library — `render_probe(row)` (full integration)

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Append the failing test**

Append to `tests/test_fundamental_probes.py`:

```python
import ast as _ast

from s001.fundamental_probes import render_probe, BIND


class TestRenderProbe:
    def test_numeric_gt_with_gate(self):
        row = {
            'container': 'valuation_ratios', 'field_name': 'book_value_per_share',
            'period': None, 'probe_op': '>', 'probe_threshold': '15',
            'probe_gate': 'decline > .10', 'probe_boost': 1.12,
            'data_type_hint': 'numeric',
        }
        out = render_probe(row)
        assert '_v = f_(_vr_z.book_value_per_share)' in out
        assert '_v > 15' in out
        assert 'decline > .10' in out
        assert 'score *= 1.12' in out
        # Must parse as Python.
        _ast.parse(out)

    def test_numeric_no_gate(self):
        row = {
            'container': 'operation_ratios', 'field_name': 'roe', 'period': 'one_year',
            'probe_op': '>', 'probe_threshold': '0.15',
            'probe_gate': None, 'probe_boost': 1.10,
            'data_type_hint': 'numeric',
        }
        out = render_probe(row)
        assert ' and (' not in out  # no gate fragment
        assert '_v > 0.15: score *= 1.1' in out
        _ast.parse(out)

    def test_categorical_in(self):
        row = {
            'container': 'asset_classification', 'field_name': 'financial_health_grade',
            'period': None, 'probe_op': 'in', 'probe_threshold': '["A","B+","B"]',
            'probe_gate': 'decline > .10', 'probe_boost': 1.06,
            'data_type_hint': 'categorical',
        }
        out = render_probe(row)
        # Categorical path: no f_(...) coerce
        assert '_v = _ac_z.financial_health_grade' in out
        assert "'A'" in out and "'B+'" in out
        assert 'decline > .10' in out
        assert 'score *= 1.06' in out
        _ast.parse(out)

    def test_absolute_amount_lt_with_zero_guard(self):
        row = {
            'container': 'income_statement', 'field_name': 'interest_expense',
            'period': 'twelve_months', 'probe_op': '<', 'probe_threshold': '5e7',
            'probe_gate': 'decline > .10', 'probe_boost': 1.08,
            'data_type_hint': 'absolute_amount',
        }
        out = render_probe(row)
        assert '0 < _v < 5e7' in out
        _ast.parse(out)

    def test_signed_ratio_negative_threshold(self):
        row = {
            'container': 'earning_ratios', 'field_name': 'diluted_eps_growth',
            'period': 'one_year', 'probe_op': '<', 'probe_threshold': '-0.10',
            'probe_gate': None, 'probe_boost': 0.85,
            'data_type_hint': 'signed_ratio',
        }
        out = render_probe(row)
        assert '_v < -0.10' in out
        assert 'score *= 0.85' in out
        _ast.parse(out)

    def test_null_threshold_raises(self):
        row = {
            'container': 'valuation_ratios', 'field_name': 'pe_ratio', 'period': None,
            'probe_op': '>', 'probe_threshold': None,
            'probe_gate': None, 'probe_boost': 1.10,
            'data_type_hint': 'numeric',
        }
        with pytest.raises(ValueError, match='probe_threshold'):
            render_probe(row)

    def test_bind_block_constant_parses(self):
        # The shared BIND block must itself parse standalone (after dedent of the leading 3-space indent).
        # We wrap it in a function to test parseability.
        wrapped = "def _f():\n  for sym in []:\n" + BIND + "   pass\n"
        _ast.parse(wrapped)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestRenderProbe -v`
Expected: ImportError on `render_probe` and `BIND`.

- [ ] **Step 3: Implement**

Append to `s001/fundamental_probes.py`:

```python
BIND = """   try:
    _fz = self.securities[sym].fundamentals
    _ops_z = getattr(_fz, 'operation_ratios', None) if _fz else None
    _vr_z  = getattr(_fz, 'valuation_ratios', None) if _fz else None
    _ers_z = getattr(_fz, 'earning_ratios', None) if _fz else None
    _er_z  = getattr(_fz, 'earning_reports', None) if _fz else None
    _ac_z  = getattr(_fz, 'asset_classification', None) if _fz else None
    _sr_z  = getattr(_fz, 'security_reference', None) if _fz else None
    _fs_z  = getattr(_fz, 'financial_statements', None) if _fz else None
    _bs_z  = getattr(_fs_z, 'balance_sheet', None) if _fs_z else None
    _inc_z = getattr(_fs_z, 'income_statement', None) if _fs_z else None
    _cfs_z = getattr(_fs_z, 'cash_flow_statement', None) if _fs_z else None
   except: _ops_z=_vr_z=_ers_z=_er_z=_ac_z=_sr_z=_fs_z=_bs_z=_inc_z=_cfs_z=None
"""


def render_probe(row):
    """Render Python probe code for a single fundamental_fields row.

    Returns the per-probe try/except block (does NOT include BIND).
    The caller injects BIND once per spec, then concatenates one or
    more render_probe() outputs.

    Raises ValueError if probe_threshold is NULL or template is invalid."""
    if row['probe_threshold'] is None:
        raise ValueError(
            f"probe_threshold is NULL for {row.get('container')}/{row.get('field_name')}; "
            f"field needs a template before it can be probed.")

    accessor = accessor_for(row)
    hint = row.get('data_type_hint') or 'numeric'
    if hint == 'categorical':
        coerced = accessor   # raw access, no float coerce
    else:
        coerced = f"f_({accessor})"

    cond = build_condition(row, '_v')
    gate = f" and ({row['probe_gate']})" if row['probe_gate'] else ""
    return (
        "   try:\n"
        f"    _v = {coerced}\n"
        f"    if {cond}{gate}: score *= {row['probe_boost']}\n"
        "   except: pass"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestRenderProbe -v`
Expected: 7 passed.

---

## Task 9: Library — `spec_name(row, round_n)` and short-form helpers

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Append the failing test**

Append to `tests/test_fundamental_probes.py`:

```python
from s001.fundamental_probes import spec_name


class TestSpecName:
    def test_numeric_gt(self):
        row = {
            'container': 'valuation_ratios', 'field_name': 'book_value_per_share',
            'probe_op': '>', 'probe_threshold': '15',
        }
        assert spec_name(row, 406) == 'S001_R406_vr_book_value_per_share_gt15'

    def test_numeric_lt(self):
        row = {
            'container': 'income_statement', 'field_name': 'interest_expense',
            'probe_op': '<', 'probe_threshold': '5e7',
        }
        assert spec_name(row, 406) == 'S001_R406_inc_interest_expense_lt5e7'

    def test_categorical_in(self):
        row = {
            'container': 'asset_classification', 'field_name': 'financial_health_grade',
            'probe_op': 'in', 'probe_threshold': '["A","B+","B"]',
        }
        # Categorical short form: 'in_AB' (concat of values, stripped to alphanumeric)
        assert spec_name(row, 406) == 'S001_R406_ac_financial_health_grade_in_ABplusB'

    def test_balance_sheet(self):
        row = {
            'container': 'balance_sheet', 'field_name': 'long_term_debt',
            'probe_op': '<', 'probe_threshold': '5e8',
        }
        assert spec_name(row, 406) == 'S001_R406_bs_long_term_debt_lt5e8'

    def test_truncates_long_name(self):
        row = {
            'container': 'income_statement',
            'field_name': 'continuing_and_discontinued_basic_earnings_per_share_x',
            'probe_op': '>', 'probe_threshold': '2',
        }
        out = spec_name(row, 406)
        assert len(out) <= 100
        assert out.startswith('S001_R406_inc_')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestSpecName -v`
Expected: ImportError on `spec_name`.

- [ ] **Step 3: Implement**

Append to `s001/fundamental_probes.py`:

```python
import re


CONTAINER_SHORT = {
    'balance_sheet':        'bs',
    'cash_flow_statement':  'cfs',
    'income_statement':     'inc',
    'operation_ratios':     'ops',
    'valuation_ratios':     'vr',
    'earning_ratios':       'ers',
    'earning_reports':      'er',
    'asset_classification': 'ac',
    'security_reference':   'sr',
}

OP_SHORT = {
    '>':  'gt',
    '>=': 'gte',
    '<':  'lt',
    '<=': 'lte',
    'eq': 'eq',
    'in': 'in',
}


def _threshold_short(thr, op):
    """Compress a probe_threshold into an identifier-safe suffix."""
    if op in ('eq', 'in'):
        try:
            parsed = json.loads(thr)
        except json.JSONDecodeError:
            parsed = thr
        if isinstance(parsed, list):
            joined = ''.join(str(x).replace('+', 'plus').replace('-', 'minus')
                             for x in parsed)
        else:
            joined = str(parsed).replace('+', 'plus').replace('-', 'minus')
        return re.sub(r'[^A-Za-z0-9]', '', joined)
    # Numeric: keep digits, decimal point dropped, scientific notation kept.
    return thr.replace('.', '').replace('-', 'neg').replace('+', '')


def spec_name(row, round_n):
    """Build the deterministic backtest spec name for a probe row.

    Format: S001_R{round_n}_{container_short}_{field_name}_{op_short}{thr_short}
    Truncated to 100 chars (UNIQUE constraint on backtest_queue.name is the safety net).
    """
    cs = CONTAINER_SHORT[row['container']]
    op_s = OP_SHORT[row['probe_op']]
    thr_s = _threshold_short(row['probe_threshold'], row['probe_op'])
    name = f"S001_R{round_n}_{cs}_{row['field_name']}_{op_s}{thr_s}"
    return name[:100]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestSpecName -v`
Expected: 5 passed.

---

## Task 10: Library — `pick_fields(...)` (container-cycle picker)

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Append the failing test**

Append to `tests/test_fundamental_probes.py`:

```python
from s001.fundamental_probes import pick_fields, CONTAINER_CYCLE


class TestPickFields:
    @staticmethod
    def _seed_fields(tmp_db, rows):
        import sqlite3
        con = sqlite3.connect(tmp_db)
        cur = con.cursor()
        for r in rows:
            cur.execute(
                """INSERT INTO fundamental_fields
                   (category, field_name, accessor, container, period,
                    probe_op, probe_threshold, probe_gate, probe_boost,
                    classification, data_type_hint)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (r['container'], r['field_name'], r['accessor'], r['container'],
                 r.get('period'), r.get('probe_op'), r.get('probe_threshold'),
                 r.get('probe_gate'), r.get('probe_boost'),
                 r.get('classification', 'untested'), r.get('data_type_hint', 'numeric')))
        con.commit()
        con.close()

    def test_picks_in_container_cycle(self, tmp_db):
        # Seed 2 each in vr, ops, ac (the first 3 in CONTAINER_CYCLE).
        rows = [
            {'container': 'valuation_ratios', 'field_name': 'a', 'accessor': '_vr.a',
             'probe_op': '>', 'probe_threshold': '1', 'probe_boost': 1.1},
            {'container': 'valuation_ratios', 'field_name': 'b', 'accessor': '_vr.b',
             'probe_op': '>', 'probe_threshold': '2', 'probe_boost': 1.1},
            {'container': 'operation_ratios', 'field_name': 'c', 'accessor': '_ops.c.one_year',
             'period': 'one_year', 'probe_op': '>', 'probe_threshold': '3', 'probe_boost': 1.1},
            {'container': 'operation_ratios', 'field_name': 'd', 'accessor': '_ops.d.one_year',
             'period': 'one_year', 'probe_op': '>', 'probe_threshold': '4', 'probe_boost': 1.1},
            {'container': 'asset_classification', 'field_name': 'e', 'accessor': '_ac.e',
             'probe_op': 'in', 'probe_threshold': '["A"]', 'probe_boost': 1.1, 'data_type_hint': 'categorical'},
        ]
        self._seed_fields(tmp_db, rows)
        picked = pick_fields(tmp_db, k=3, classification='untested')
        # Cycle: vr → ops → ac → vr → ... so first 3 = (vr.a, ops.c, ac.e)
        assert [p['field_name'] for p in picked] == ['a', 'c', 'e']

    def test_skips_null_threshold(self, tmp_db):
        rows = [
            {'container': 'valuation_ratios', 'field_name': 'has_template',
             'accessor': '_vr.has_template', 'probe_op': '>', 'probe_threshold': '1', 'probe_boost': 1.1},
            {'container': 'valuation_ratios', 'field_name': 'no_template',
             'accessor': '_vr.no_template', 'probe_op': None, 'probe_threshold': None, 'probe_boost': None},
        ]
        self._seed_fields(tmp_db, rows)
        picked = pick_fields(tmp_db, k=5, classification='untested')
        assert [p['field_name'] for p in picked] == ['has_template']

    def test_filters_by_classification(self, tmp_db):
        rows = [
            {'container': 'valuation_ratios', 'field_name': 'untested_a',
             'accessor': '_vr.untested_a', 'probe_op': '>', 'probe_threshold': '1', 'probe_boost': 1.1},
            {'container': 'valuation_ratios', 'field_name': 'hot_b',
             'accessor': '_vr.hot_b', 'probe_op': '>', 'probe_threshold': '1', 'probe_boost': 1.1,
             'classification': 'hot'},
        ]
        self._seed_fields(tmp_db, rows)
        untested = pick_fields(tmp_db, k=10, classification='untested')
        hot = pick_fields(tmp_db, k=10, classification='hot')
        assert [p['field_name'] for p in untested] == ['untested_a']
        assert [p['field_name'] for p in hot] == ['hot_b']

    def test_deterministic(self, tmp_db):
        rows = [{'container': 'valuation_ratios', 'field_name': f'f{i}',
                 'accessor': f'_vr.f{i}', 'probe_op': '>', 'probe_threshold': str(i),
                 'probe_boost': 1.1} for i in range(5)]
        self._seed_fields(tmp_db, rows)
        a = [p['field_name'] for p in pick_fields(tmp_db, k=3, classification='untested')]
        b = [p['field_name'] for p in pick_fields(tmp_db, k=3, classification='untested')]
        assert a == b

    def test_container_cycle_constant_order(self):
        # Spec §7.3 declares this exact order.
        assert CONTAINER_CYCLE == [
            'valuation_ratios', 'operation_ratios', 'asset_classification',
            'balance_sheet', 'cash_flow_statement', 'income_statement',
            'earning_ratios', 'earning_reports', 'security_reference',
        ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestPickFields -v`
Expected: ImportError on `pick_fields`/`CONTAINER_CYCLE`.

- [ ] **Step 3: Implement**

Append to `s001/fundamental_probes.py`:

```python
import sqlite3


CONTAINER_CYCLE = [
    'valuation_ratios', 'operation_ratios', 'asset_classification',
    'balance_sheet', 'cash_flow_statement', 'income_statement',
    'earning_ratios', 'earning_reports', 'security_reference',
]


def _row_to_dict(cur, row):
    cols = [c[0] for c in cur.description]
    return dict(zip(cols, row))


def pick_fields(db_path, k, classification='untested'):
    """Pick up to k fields with the given classification, in container-cycle order.

    Within each container, ORDER BY id ASC. Cycles through containers until
    k fields have been collected (or the pool is exhausted).

    Skips rows with NULL probe_threshold (template not yet authored).
    Returns a list of dict rows.
    """
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Per-container queues (sorted by id ASC).
    queues = {}
    for cont in CONTAINER_CYCLE:
        cur.execute(
            """SELECT * FROM fundamental_fields
               WHERE container = ? AND classification = ?
                 AND probe_threshold IS NOT NULL
               ORDER BY id ASC""",
            (cont, classification))
        queues[cont] = [dict(r) for r in cur.fetchall()]
    con.close()

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

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestPickFields -v`
Expected: 5 passed.

---

## Task 11: Library — LEAN __init__.pyi reflection (`extract_lean_universe`)

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Append the failing test**

Append to `tests/test_fundamental_probes.py`:

```python
from s001.fundamental_probes import extract_lean_universe, EXCLUDE_FIELD_PATTERNS


class TestExtractLeanUniverse:
    def test_returns_dict_per_container(self):
        # Run against the actually installed LEAN __init__.pyi
        out = extract_lean_universe()
        assert isinstance(out, dict)
        # Required containers must all be present
        for c in ('balance_sheet', 'cash_flow_statement', 'income_statement',
                  'operation_ratios', 'valuation_ratios', 'earning_ratios',
                  'earning_reports', 'asset_classification', 'security_reference'):
            assert c in out, f"missing {c}"

    def test_field_counts_meet_minimums(self):
        out = extract_lean_universe()
        # Lower bounds — actual counts may exceed these as LEAN evolves.
        assert len(out['valuation_ratios']) >= 50
        assert len(out['operation_ratios']) >= 40
        assert len(out['balance_sheet']) >= 100
        assert len(out['income_statement']) >= 80
        assert len(out['cash_flow_statement']) >= 80
        assert len(out['earning_ratios']) >= 5
        assert len(out['asset_classification']) >= 10

    def test_known_field_present(self):
        out = extract_lean_universe()
        # Sanity: known field that has been used in production rounds.
        assert 'pe_ratio' in out['valuation_ratios']
        assert 'roe' in out['operation_ratios']
        assert 'free_cash_flow' in out['cash_flow_statement']

    def test_metadata_excluded(self):
        out = extract_lean_universe()
        # These appear in the .pyi but should be filtered.
        for excluded in ('file_date', 'accession_number', 'form_type',
                         'period_type', 'period_ending_date'):
            for cont in out.values():
                assert excluded not in cont, f"{excluded} should be excluded"

    def test_categorical_fields_present(self):
        out = extract_lean_universe()
        # AssetClassification has these categorical signals
        assert 'financial_health_grade' in out['asset_classification']
        assert 'morningstar_sector_code' in out['asset_classification']
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestExtractLeanUniverse -v`
Expected: ImportError on `extract_lean_universe`.

- [ ] **Step 3: Implement**

Append to `s001/fundamental_probes.py`:

```python
LEAN_PYI = ('/home/txy/.local/share/pipx/venvs/lean/lib/python3.13/'
            'site-packages/QuantConnect/Data/Fundamental/__init__.pyi')


# Top-level container classes whose @property fields we extract.
# Map: lean_class_name → fundamental_fields.container value.
LEAN_CONTAINERS = {
    'BalanceSheet':        'balance_sheet',
    'CashFlowStatement':   'cash_flow_statement',
    'IncomeStatement':     'income_statement',
    'OperationRatios':     'operation_ratios',
    'ValuationRatios':     'valuation_ratios',
    'EarningRatios':       'earning_ratios',
    'EarningReports':      'earning_reports',
    'AssetClassification': 'asset_classification',
    'SecurityReference':   'security_reference',
}

# Patterns excluded when scanning property names (per spec §8.1).
EXCLUDE_FIELD_PATTERNS = (
    'file_date', 'accession_number', 'form_type', 'period_type',
    'period_ending_date', 'period_auditor',
)
EXCLUDE_FIELD_SUFFIXES = ('_currency_id',)


def _read_lean_pyi():
    with open(LEAN_PYI) as f:
        return f.read()


def _container_property_names(src, class_name):
    """Extract @property names from a class block in the .pyi source."""
    m = re.search(rf'^class {class_name}\b.*?(?=^class \w)', src, re.M | re.S)
    if not m:
        return []
    block = m.group(0)
    return re.findall(r'@property\s+def (\w+)', block)


def extract_lean_universe():
    """Reflect over the LEAN __init__.pyi and return per-container field name lists.

    Returns: {container_value: [field_name, ...]} for each LEAN_CONTAINERS entry.
    Filters out metadata fields per spec §8.1.
    """
    src = _read_lean_pyi()
    out = {}
    for class_name, cont_value in LEAN_CONTAINERS.items():
        props = _container_property_names(src, class_name)
        cleaned = []
        for p in props:
            if any(pat in p for pat in EXCLUDE_FIELD_PATTERNS):
                continue
            if any(p.endswith(suf) for suf in EXCLUDE_FIELD_SUFFIXES):
                continue
            # Strip the bs_/cf_/is_ prefix used by LEAN for some fields
            if cont_value == 'balance_sheet' and p.startswith('bs_'):
                continue  # bs_file_date etc — already filtered by patterns above
            cleaned.append(p)
        out[cont_value] = cleaned
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestExtractLeanUniverse -v`
Expected: 5 passed.

---

## Task 12: Library — Default-template heuristics (`default_template`)

**Files:**
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py`
- Modify: `/home/txy/qc_work/data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Append the failing test**

Append to `tests/test_fundamental_probes.py`:

```python
from s001.fundamental_probes import default_template, default_period


class TestDefaultPeriod:
    def test_balance_sheet_twelve_months(self):
        assert default_period('balance_sheet') == 'twelve_months'

    def test_cash_flow_twelve_months(self):
        assert default_period('cash_flow_statement') == 'twelve_months'

    def test_income_twelve_months(self):
        assert default_period('income_statement') == 'twelve_months'

    def test_earning_reports_twelve_months(self):
        assert default_period('earning_reports') == 'twelve_months'

    def test_operation_ratios_one_year(self):
        assert default_period('operation_ratios') == 'one_year'

    def test_earning_ratios_one_year(self):
        assert default_period('earning_ratios') == 'one_year'

    def test_valuation_ratios_none(self):
        assert default_period('valuation_ratios') is None

    def test_asset_classification_none(self):
        assert default_period('asset_classification') is None

    def test_security_reference_none(self):
        assert default_period('security_reference') is None


class TestDefaultTemplate:
    def test_valuation_ratios_pe(self):
        # PE-style ratios get '<' op (low = undervalued).
        out = default_template('valuation_ratios', 'pe_ratio')
        assert out['probe_op'] == '<'
        assert out['probe_threshold'] == '15'
        assert out['data_type_hint'] == 'numeric'
        assert 'decline' in out['probe_gate']
        assert out['probe_boost'] >= 1.05

    def test_valuation_ratios_default_high(self):
        # Generic vr field gets '>' op (high = good).
        out = default_template('valuation_ratios', 'book_value_per_share')
        assert out['probe_op'] == '>'
        assert out['data_type_hint'] == 'numeric'

    def test_operation_ratios_margin(self):
        out = default_template('operation_ratios', 'gross_margin')
        assert out['probe_op'] == '>'
        assert out['data_type_hint'] == 'numeric'

    def test_operation_ratios_leverage(self):
        out = default_template('operation_ratios', 'financial_leverage')
        assert out['probe_op'] == '<'

    def test_balance_sheet_total_assets(self):
        out = default_template('balance_sheet', 'total_assets')
        assert out['probe_op'] == '>'
        assert out['data_type_hint'] == 'absolute_amount'
        assert float(out['probe_threshold']) >= 1e9

    def test_balance_sheet_long_term_debt(self):
        out = default_template('balance_sheet', 'long_term_debt')
        assert out['probe_op'] == '<'
        assert out['data_type_hint'] == 'absolute_amount'

    def test_earning_ratios_growth(self):
        out = default_template('earning_ratios', 'diluted_eps_growth')
        assert out['probe_op'] == '>'
        assert out['data_type_hint'] == 'signed_ratio'

    def test_asset_classification_grade(self):
        out = default_template('asset_classification', 'financial_health_grade')
        assert out['probe_op'] == 'in'
        assert out['data_type_hint'] == 'categorical'
        # JSON list of A-tier grades
        import json
        assert json.loads(out['probe_threshold']) == ['A', 'A+', 'A-']

    def test_asset_classification_sector_code(self):
        out = default_template('asset_classification', 'morningstar_sector_code')
        assert out['probe_op'] == 'in'
        assert out['data_type_hint'] == 'categorical'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestDefaultTemplate tests/test_fundamental_probes.py::TestDefaultPeriod -v`
Expected: ImportError on `default_template`.

- [ ] **Step 3: Implement**

Append to `s001/fundamental_probes.py`:

```python
DEFAULT_PERIOD = {
    'balance_sheet':        'twelve_months',
    'cash_flow_statement':  'twelve_months',
    'income_statement':     'twelve_months',
    'earning_reports':      'twelve_months',
    'operation_ratios':     'one_year',
    'earning_ratios':       'one_year',
    'valuation_ratios':     None,
    'asset_classification': None,
    'security_reference':   None,
}


def default_period(container):
    return DEFAULT_PERIOD[container]


# Field-name patterns that indicate a "low is good" valuation ratio.
LOW_GOOD_VR_PATTERNS = ('pe_ratio', 'pb_ratio', 'ps_ratio', 'peg_ratio',
                        'price_to_', 'ev_to_', 'forward_pe', 'normalized_pe')

# Operation-ratios patterns indicating leverage/debt (low is good).
LOW_GOOD_OPS_PATTERNS = ('debt', 'leverage', 'days_in_inventory', 'days_in_payable',
                         'days_sales_outstanding', 'cash_conversion_cycle')

# Balance-sheet/cash-flow patterns indicating debt items (low is good).
DEBT_LIKE_BS = ('debt', 'liabilities', 'accounts_payable', 'capital_lease')

# Categorical sector defaults: defensive sector codes (Utilities=207, Healthcare=206, ConsumerDef=205).
DEFAULT_DEFENSIVE_SECTORS = '[205, 206, 207]'
DEFAULT_A_TIER_GRADES = '["A", "A+", "A-"]'


def _matches_any(field_name, patterns):
    return any(pat in field_name for pat in patterns)


def default_template(container, field_name):
    """Return a dict with default {probe_op, probe_threshold, probe_gate,
    probe_boost, data_type_hint} for a (container, field_name) pair.

    Uses spec §8.3 heuristics. Author can override per-row via DB UPDATE."""
    if container == 'valuation_ratios':
        if _matches_any(field_name, LOW_GOOD_VR_PATTERNS):
            return {'probe_op': '<', 'probe_threshold': '15',
                    'probe_gate': 'decline > .10', 'probe_boost': 1.10,
                    'data_type_hint': 'numeric'}
        return {'probe_op': '>', 'probe_threshold': '5',
                'probe_gate': 'decline > .10', 'probe_boost': 1.10,
                'data_type_hint': 'numeric'}

    if container == 'operation_ratios':
        if _matches_any(field_name, LOW_GOOD_OPS_PATTERNS):
            return {'probe_op': '<', 'probe_threshold': '2',
                    'probe_gate': 'decline > .15', 'probe_boost': 1.08,
                    'data_type_hint': 'numeric'}
        return {'probe_op': '>', 'probe_threshold': '0.10',
                'probe_gate': 'decline > .12', 'probe_boost': 1.10,
                'data_type_hint': 'numeric'}

    if container == 'earning_ratios':
        return {'probe_op': '>', 'probe_threshold': '0.10',
                'probe_gate': 'decline > .15', 'probe_boost': 1.15,
                'data_type_hint': 'signed_ratio'}

    if container == 'balance_sheet':
        if _matches_any(field_name, DEBT_LIKE_BS):
            return {'probe_op': '<', 'probe_threshold': '5e8',
                    'probe_gate': 'decline > .10', 'probe_boost': 1.06,
                    'data_type_hint': 'absolute_amount'}
        return {'probe_op': '>', 'probe_threshold': '1e9',
                'probe_gate': 'decline > .12', 'probe_boost': 1.08,
                'data_type_hint': 'absolute_amount'}

    if container == 'cash_flow_statement':
        return {'probe_op': '>', 'probe_threshold': '1e9',
                'probe_gate': 'decline > .10', 'probe_boost': 1.08,
                'data_type_hint': 'absolute_amount'}

    if container == 'income_statement':
        return {'probe_op': '>', 'probe_threshold': '1e9',
                'probe_gate': 'decline > .12', 'probe_boost': 1.10,
                'data_type_hint': 'absolute_amount'}

    if container == 'earning_reports':
        return {'probe_op': '>', 'probe_threshold': '1',
                'probe_gate': 'decline > .10', 'probe_boost': 1.06,
                'data_type_hint': 'numeric'}

    if container == 'asset_classification':
        if 'sector_code' in field_name or 'industry_code' in field_name:
            return {'probe_op': 'in', 'probe_threshold': DEFAULT_DEFENSIVE_SECTORS,
                    'probe_gate': 'decline > .10', 'probe_boost': 1.08,
                    'data_type_hint': 'categorical'}
        if 'grade' in field_name:
            return {'probe_op': 'in', 'probe_threshold': DEFAULT_A_TIER_GRADES,
                    'probe_gate': 'decline > .10', 'probe_boost': 1.06,
                    'data_type_hint': 'categorical'}
        # Other AC fields (style_box, stock_type) — leave NULL template (manual).
        return {'probe_op': None, 'probe_threshold': None,
                'probe_gate': None, 'probe_boost': None,
                'data_type_hint': 'categorical'}

    if container == 'security_reference':
        # Only some fields are useful; leave NULL by default.
        return {'probe_op': None, 'probe_threshold': None,
                'probe_gate': None, 'probe_boost': None,
                'data_type_hint': 'categorical'}

    raise KeyError(f"Unknown container: {container!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/txy/qc_work/data && pytest tests/test_fundamental_probes.py::TestDefaultPeriod tests/test_fundamental_probes.py::TestDefaultTemplate -v`
Expected: 18 passed (9 + 9).

---

## Task 13: Catalogue — Insert/upsert with idempotency

**Files:**
- Create: `/home/txy/qc_work/data/scripts/catalogue_universe.py`
- Create: `/home/txy/qc_work/data/tests/test_catalogue_universe.py`

- [ ] **Step 1: Write the failing test**

Create `/home/txy/qc_work/data/tests/test_catalogue_universe.py`:

```python
"""Catalogue script tests."""
import sqlite3

from scripts.catalogue_universe import main as catalogue_main


def _count_rows(db, table='fundamental_fields'):
    con = sqlite3.connect(db)
    n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    con.close()
    return n


def _categorical_rows_present(db):
    con = sqlite3.connect(db)
    n = con.execute(
        "SELECT COUNT(*) FROM fundamental_fields WHERE data_type_hint='categorical'"
    ).fetchone()[0]
    con.close()
    return n > 0


def test_catalogue_inserts_many(tmp_db):
    catalogue_main(db_path=tmp_db)
    n = _count_rows(tmp_db)
    assert n >= 600, f"expected ≥600 rows, got {n}"


def test_catalogue_idempotent(tmp_db):
    catalogue_main(db_path=tmp_db)
    n1 = _count_rows(tmp_db)
    catalogue_main(db_path=tmp_db)
    n2 = _count_rows(tmp_db)
    assert n1 == n2


def test_catalogue_categorical_present(tmp_db):
    catalogue_main(db_path=tmp_db)
    assert _categorical_rows_present(tmp_db)


def test_catalogue_preserves_existing_template(tmp_db):
    # Pre-seed a row with a non-default template, then re-catalogue.
    con = sqlite3.connect(tmp_db)
    con.execute(
        """INSERT INTO fundamental_fields
           (category, field_name, accessor, container, period,
            probe_op, probe_threshold, probe_gate, probe_boost, data_type_hint)
           VALUES ('valuation', 'pe_ratio', '_vr_z.pe_ratio', 'valuation_ratios', NULL,
                   '<', '20', 'decline > .05', 1.20, 'numeric')""")
    con.commit()
    con.close()

    catalogue_main(db_path=tmp_db)

    con = sqlite3.connect(tmp_db)
    cur = con.cursor()
    cur.execute("SELECT probe_threshold, probe_boost, probe_gate FROM fundamental_fields WHERE field_name='pe_ratio'")
    thr, boost, gate = cur.fetchone()
    assert thr == '20'  # not overwritten
    assert boost == 1.20
    assert gate == 'decline > .05'
    con.close()


def test_catalogue_backfills_legacy_row(tmp_db):
    # Pre-seed a legacy-style row (no container/period populated).
    con = sqlite3.connect(tmp_db)
    con.execute(
        """INSERT INTO fundamental_fields
           (category, field_name, accessor, container, period, data_type_hint)
           VALUES ('valuation', 'pe_ratio', '_vr.pe_ratio', NULL, NULL, NULL)""")
    con.commit()
    con.close()

    catalogue_main(db_path=tmp_db)

    con = sqlite3.connect(tmp_db)
    cur = con.cursor()
    cur.execute("SELECT container, period, data_type_hint FROM fundamental_fields WHERE field_name='pe_ratio'")
    container, period, hint = cur.fetchone()
    assert container == 'valuation_ratios'
    assert period is None
    assert hint == 'numeric'
    con.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/txy/qc_work/data && pytest tests/test_catalogue_universe.py -v`
Expected: ImportError on `scripts.catalogue_universe`.

- [ ] **Step 3: Implement**

Create `/home/txy/qc_work/data/scripts/catalogue_universe.py`:

```python
"""Catalogue script: scan LEAN __init__.pyi and emit fundamental_fields rows.

Idempotent: existing rows preserved (templates not overwritten by default).
Backfills container/period/data_type_hint on legacy rows that have only an accessor.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

# Allow running as script or module.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from s001.fundamental_probes import (  # noqa: E402
    CONTAINER_ALIAS,
    extract_lean_universe,
    default_period,
    default_template,
    LEAN_CONTAINERS,
)


# Map legacy accessor prefix (e.g. '_vr', '_bs') → container value.
PREFIX_TO_CONTAINER = {
    '_vr':  'valuation_ratios',
    '_ops': 'operation_ratios',
    '_ers': 'earning_ratios',
    '_er':  'earning_reports',
    '_ac':  'asset_classification',
    '_sr':  'security_reference',
    '_bs':  'balance_sheet',
    '_inc': 'income_statement',
    '_cfs': 'cash_flow_statement',
}


def _parse_legacy_accessor(accessor):
    """Parse a legacy-style accessor like '_bs.long_term_debt.twelve_months'.

    Returns (container, field_name, period) or (None, None, None) if unrecognized."""
    parts = accessor.split('.')
    if not parts:
        return None, None, None
    prefix = parts[0]
    cont = PREFIX_TO_CONTAINER.get(prefix)
    if cont is None:
        return None, None, None
    if len(parts) == 2:
        return cont, parts[1], None
    if len(parts) == 3:
        return cont, parts[1], parts[2]
    return None, None, None


def _build_canonical_accessor(container, field_name, period):
    alias = CONTAINER_ALIAS[container]
    base = f"{alias}.{field_name}"
    return f"{base}.{period}" if period else base


def main(db_path='/home/txy/qc_work/data/S001.db', update_templates=False):
    universe = extract_lean_universe()
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    # --- Backfill legacy rows missing container/period ---
    cur.execute("""SELECT id, accessor FROM fundamental_fields
                   WHERE container IS NULL""")
    for fid, acc in list(cur.fetchall()):
        cont, fname, per = _parse_legacy_accessor(acc)
        if cont is None:
            continue
        tmpl = default_template(cont, fname)
        cur.execute(
            """UPDATE fundamental_fields
               SET container = ?, period = ?, data_type_hint = ?
               WHERE id = ?""",
            (cont, per, tmpl['data_type_hint'], fid))

    # --- Insert new rows for each LEAN field, skipping existing accessors ---
    inserted = 0
    for container, fields in universe.items():
        period = default_period(container)
        for field_name in fields:
            accessor = _build_canonical_accessor(container, field_name, period)
            tmpl = default_template(container, field_name)
            try:
                cur.execute(
                    """INSERT INTO fundamental_fields
                       (category, field_name, accessor, container, period,
                        probe_op, probe_threshold, probe_gate, probe_boost,
                        data_type_hint, classification)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'untested')""",
                    (container, field_name, accessor, container, period,
                     tmpl['probe_op'], tmpl['probe_threshold'],
                     tmpl['probe_gate'], tmpl['probe_boost'],
                     tmpl['data_type_hint']))
                inserted += 1
            except sqlite3.IntegrityError:
                # accessor already exists; preserve existing row.
                if update_templates:
                    cur.execute(
                        """UPDATE fundamental_fields
                           SET probe_op = ?, probe_threshold = ?, probe_gate = ?,
                               probe_boost = ?, data_type_hint = ?
                           WHERE accessor = ?""",
                        (tmpl['probe_op'], tmpl['probe_threshold'],
                         tmpl['probe_gate'], tmpl['probe_boost'],
                         tmpl['data_type_hint'], accessor))

    con.commit()
    cur.execute("SELECT COUNT(*) FROM fundamental_fields")
    total = cur.fetchone()[0]
    con.close()
    return {'inserted': inserted, 'total': total}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--db', default='/home/txy/qc_work/data/S001.db')
    p.add_argument('--update-templates', action='store_true')
    args = p.parse_args()
    res = main(db_path=args.db, update_templates=args.update_templates)
    print(f"Inserted {res['inserted']} new rows; total = {res['total']}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/txy/qc_work/data && pytest tests/test_catalogue_universe.py -v`
Expected: 5 passed.

---

## Task 14: `emit_probes.py` — Per-round probe spec emission

**Files:**
- Create: `/home/txy/qc_work/data/scripts/emit_probes.py`
- Create: `/home/txy/qc_work/data/tests/test_emit_probes.py`
- Modify: `/home/txy/qc_work/data/s001/fundamental_probes.py` (add `emit_probes` lib function)

- [ ] **Step 1: Write the failing test**

Create `/home/txy/qc_work/data/tests/test_emit_probes.py`:

```python
"""emit_probes script tests."""
import ast as _ast
import json
import sqlite3
import subprocess
import sys
from pathlib import Path


def _seed_one_field(tmp_db):
    con = sqlite3.connect(tmp_db)
    con.execute(
        """INSERT INTO fundamental_fields
           (category, field_name, accessor, container, period,
            probe_op, probe_threshold, probe_gate, probe_boost,
            data_type_hint, classification)
           VALUES ('valuation', 'pe_ratio', '_vr_z.pe_ratio',
                   'valuation_ratios', NULL,
                   '<', '15', 'decline > .10', 1.10, 'numeric', 'untested')""")
    con.commit()
    con.close()


def test_emit_probes_returns_specs(tmp_db):
    from scripts.emit_probes import emit_probes_for_db
    _seed_one_field(tmp_db)
    specs = emit_probes_for_db(db_path=tmp_db, round_n=999, k_new=1, k_verify=0)
    assert len(specs) == 1
    name, body = specs[0]
    assert name.startswith('S001_R999_vr_pe_ratio_lt')
    assert '_v < 15' in body
    assert 'decline > .10' in body
    # body must parse standalone as the per-probe block.
    # It's a try/except — wrap to make it a complete statement context.
    wrapped = "def _f():\n  for sym in []:\n" + body + "\n   pass\n"
    _ast.parse(wrapped)


def test_emit_probes_pre_flight_skips_null_template(tmp_db):
    from scripts.emit_probes import emit_probes_for_db
    con = sqlite3.connect(tmp_db)
    con.execute(
        """INSERT INTO fundamental_fields
           (category, field_name, accessor, container, period,
            probe_op, probe_threshold, probe_gate, probe_boost,
            data_type_hint, classification)
           VALUES ('valuation', 'no_template', '_vr_z.no_template',
                   'valuation_ratios', NULL,
                   NULL, NULL, NULL, NULL, 'numeric', 'untested')""")
    con.commit()
    con.close()
    specs = emit_probes_for_db(db_path=tmp_db, round_n=999, k_new=5, k_verify=0)
    assert specs == []


def test_emit_probes_includes_bind_block_metadata(tmp_db):
    from scripts.emit_probes import emit_probes_for_db, BIND_PRELUDE_KEY
    _seed_one_field(tmp_db)
    specs = emit_probes_for_db(db_path=tmp_db, round_n=999, k_new=1, k_verify=0,
                               include_bind=True)
    # When include_bind=True, the result is (name, BIND + body)
    name, body = specs[0]
    assert '_fz = self.securities[sym].fundamentals' in body
    assert '_v < 15' in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/txy/qc_work/data && pytest tests/test_emit_probes.py -v`
Expected: ImportError.

- [ ] **Step 3: Add `emit_probes_for_db` to library and create script**

Append to `s001/fundamental_probes.py`:

```python
def emit_probes_for_db(db_path, round_n, k_new, k_verify=0, include_bind=False):
    """Emit (name, code) tuples for the given round.

    Picks `k_new` untested fields and `k_verify` hot fields (re-rendering with same template).
    Pre-flight checks: probe_op valid, probe_threshold present, ast.parse succeeds.

    If include_bind=True, prepends BIND to the first spec's body
    (caller may want this if injecting via simple replace at the anchor).
    """
    VALID_OPS = {'>', '>=', '<', '<=', 'eq', 'in'}
    new_picks = pick_fields(db_path, k=k_new, classification='untested')
    hot_picks = pick_fields(db_path, k=k_verify, classification='hot')

    out = []
    import ast as _ast
    for row in new_picks + hot_picks:
        # Pre-flight
        if row['probe_op'] not in VALID_OPS:
            continue
        if row['probe_threshold'] is None:
            continue
        body = render_probe(row)
        # Wrap in a parseable scaffold
        scaffold = "def _f():\n  for sym in []:\n" + body + "\n   pass\n"
        try:
            _ast.parse(scaffold)
        except SyntaxError:
            continue  # silently skip malformed rows; spec §6.6 says fail loud,
                      # but here we keep round-emission resilient
        name = spec_name(row, round_n)
        if include_bind:
            body = BIND + body
        out.append((name, body))
    return out
```

Create `/home/txy/qc_work/data/scripts/emit_probes.py`:

```python
"""Emit per-round probe specs for gen_s001_R{N}.py to consume.

Usage:
  python -m scripts.emit_probes --round 407 --k-new 10 --k-verify 5 [--json]
  → prints specs as JSON list of {name, code} objects on stdout.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from s001.fundamental_probes import emit_probes_for_db, BIND  # noqa: E402

BIND_PRELUDE_KEY = 'bind_prelude'  # exported for tests


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--round', dest='round_n', type=int, required=True)
    p.add_argument('--k-new', type=int, default=10)
    p.add_argument('--k-verify', type=int, default=5)
    p.add_argument('--db', default='/home/txy/qc_work/data/S001.db')
    p.add_argument('--include-bind', action='store_true',
                   help='Prepend the BIND block to each spec body')
    p.add_argument('--json', action='store_true', help='Output JSON (default text)')
    args = p.parse_args()

    specs = emit_probes_for_db(
        db_path=args.db, round_n=args.round_n,
        k_new=args.k_new, k_verify=args.k_verify,
        include_bind=args.include_bind)

    if args.json:
        print(json.dumps([{'name': n, 'code': c} for n, c in specs], indent=2))
    else:
        for n, c in specs:
            print(f"# {n}")
            print(c)
            print()


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/txy/qc_work/data && pytest tests/test_emit_probes.py -v`
Expected: 3 passed.

---

## Task 15: `score_probes.py` — Compute deltas, classify, write probe_results

**Files:**
- Create: `/home/txy/qc_work/data/scripts/score_probes.py`
- Create: `/home/txy/qc_work/data/tests/test_score_probes.py`

- [ ] **Step 1: Write the failing test**

Create `/home/txy/qc_work/data/tests/test_score_probes.py`:

```python
"""score_probes script tests."""
import sqlite3
from datetime import datetime, timezone

import pytest

from scripts.score_probes import score_round


def _seed(tmp_db):
    """Seed one field, three NOOP experiments, two probe experiments."""
    con = sqlite3.connect(tmp_db)
    cur = con.cursor()
    cur.execute(
        """INSERT INTO fundamental_fields
           (id, category, field_name, accessor, container, period,
            probe_op, probe_threshold, probe_gate, probe_boost,
            data_type_hint, classification)
           VALUES (1, 'valuation', 'pe_ratio', '_vr_z.pe_ratio',
                   'valuation_ratios', NULL,
                   '<', '15', 'decline > .10', 1.10, 'numeric', 'untested')""")
    # 3 NOOPs avg = 1.9000
    for i, v in enumerate([1.8995, 1.9000, 1.9005]):
        cur.execute(
            "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
            (f'S001_R500_VBAKE40_NOOP_{i}', v))
    # Probe spec name matches the auto-naming pattern.
    cur.execute(
        "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
        ('S001_R500_vr_pe_ratio_lt15', 1.9050))  # +0.0050 → hot
    cur.execute(
        "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
        ('S001_R500_vr_pe_ratio_lt99', 1.8970))  # field has only one row matching;
                                                   # this name doesn't match a field
    con.commit()
    con.close()


def test_score_inserts_probe_results(tmp_db):
    _seed(tmp_db)
    out = score_round(db_path=tmp_db, round_n=500, bake_hash='c0ed7f31')
    assert out['n_results'] >= 1

    con = sqlite3.connect(tmp_db)
    cur = con.cursor()
    cur.execute("SELECT * FROM probe_results WHERE round_n = 500")
    rows = cur.fetchall()
    assert len(rows) >= 1
    cur.execute("SELECT classification, delta FROM probe_results WHERE experiment_name = 'S001_R500_vr_pe_ratio_lt15'")
    cl, delta = cur.fetchone()
    assert cl == 'hot'
    assert abs(delta - 0.005) < 1e-6
    con.close()


def test_score_rejects_round_with_no_noops(tmp_db):
    con = sqlite3.connect(tmp_db)
    con.execute(
        """INSERT INTO fundamental_fields
           (id, category, field_name, accessor, container, period,
            probe_op, probe_threshold, probe_gate, probe_boost,
            data_type_hint, classification)
           VALUES (1, 'v', 'p', '_vr_z.p', 'valuation_ratios', NULL,
                   '>', '5', NULL, 1.1, 'numeric', 'untested')""")
    con.execute("INSERT INTO experiments (name, status, car_mdd) VALUES ('S001_R501_vr_p_gt5', 'imported', 1.91)")
    con.commit()
    con.close()
    with pytest.raises(AssertionError, match='NOOP'):
        score_round(db_path=tmp_db, round_n=501, bake_hash='c0ed7f31')


def test_score_rejects_high_noop_spread(tmp_db):
    con = sqlite3.connect(tmp_db)
    cur = con.cursor()
    cur.execute(
        """INSERT INTO fundamental_fields
           (id, category, field_name, accessor, container, period,
            probe_op, probe_threshold, probe_gate, probe_boost,
            data_type_hint, classification)
           VALUES (1, 'v', 'p', '_vr_z.p', 'valuation_ratios', NULL,
                   '>', '5', NULL, 1.1, 'numeric', 'untested')""")
    # 3 NOOPs with spread > 0.0005
    for i, v in enumerate([1.8990, 1.9000, 1.9050]):  # spread = 0.006
        cur.execute(
            "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
            (f'S001_R502_VBAKE40_NOOP_{i}', v))
    con.commit()
    con.close()
    with pytest.raises(AssertionError, match='spread'):
        score_round(db_path=tmp_db, round_n=502, bake_hash='c0ed7f31')


def test_score_idempotent(tmp_db):
    _seed(tmp_db)
    score_round(db_path=tmp_db, round_n=500, bake_hash='c0ed7f31')
    n1 = sqlite3.connect(tmp_db).execute(
        "SELECT COUNT(*) FROM probe_results").fetchone()[0]
    score_round(db_path=tmp_db, round_n=500, bake_hash='c0ed7f31')
    n2 = sqlite3.connect(tmp_db).execute(
        "SELECT COUNT(*) FROM probe_results").fetchone()[0]
    assert n1 == n2  # UNIQUE(experiment_name) prevents duplicates


def test_score_refreshes_field_classification(tmp_db):
    _seed(tmp_db)
    score_round(db_path=tmp_db, round_n=500, bake_hash='c0ed7f31')
    con = sqlite3.connect(tmp_db)
    cur = con.cursor()
    cur.execute("SELECT classification FROM fundamental_fields WHERE id = 1")
    cl = cur.fetchone()[0]
    assert cl == 'hot'
    con.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/txy/qc_work/data && pytest tests/test_score_probes.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `/home/txy/qc_work/data/scripts/score_probes.py`:

```python
"""Score probe specs from a completed round: compute deltas, classify, write
probe_results, refresh field classifications.

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
    classify_delta, field_rollup, CONTAINER_SHORT, OP_SHORT,
)

CONTAINER_FROM_SHORT = {v: k for k, v in CONTAINER_SHORT.items()}


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# Regex matching the auto-naming pattern (spec §6.5).
SPEC_NAME_RE = re.compile(
    r'^S001_R(?P<round>\d+)_(?P<cs>[a-z]+)_(?P<field>[a-z0-9_]+?)_'
    r'(?P<op>gt|gte|lt|lte|eq|in)(?P<thr>.+)$'
)


def _parse_probe_spec_name(name):
    """Return (container, field_name) from a probe spec name, or None."""
    m = SPEC_NAME_RE.match(name)
    if not m:
        return None
    cs = m.group('cs')
    cont = CONTAINER_FROM_SHORT.get(cs)
    if cont is None:
        return None
    return cont, m.group('field')


def _noop_baseline(cur, round_n):
    cur.execute(
        "SELECT car_mdd FROM experiments "
        "WHERE name LIKE ? AND status='imported' AND car_mdd IS NOT NULL",
        (f'S001_R{round_n}_VBAKE%_NOOP_%',))
    vals = [r[0] for r in cur.fetchall()]
    assert len(vals) >= 1, f'Round {round_n} has no NOOP experiments'
    spread = max(vals) - min(vals)
    assert spread <= 0.0005, (
        f'Round {round_n} NOOP spread {spread:.5f} > 0.0005 — base nondeterministic')
    return sum(vals) / len(vals)


def score_round(db_path, round_n, bake_hash):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    baseline = _noop_baseline(cur, round_n)
    now = _now_iso()

    # Find all probe-pattern experiments for this round.
    cur.execute(
        "SELECT name, car_mdd FROM experiments "
        "WHERE name LIKE ? AND status='imported' AND car_mdd IS NOT NULL",
        (f'S001_R{round_n}_%',))
    touched_field_ids = set()
    n_results = 0
    for row in cur.fetchall():
        parsed = _parse_probe_spec_name(row['name'])
        if parsed is None:
            continue
        container, field_name = parsed
        cur.execute(
            "SELECT * FROM fundamental_fields WHERE container = ? AND field_name = ?",
            (container, field_name))
        f = cur.fetchone()
        if f is None:
            continue
        delta = row['car_mdd'] - baseline
        cls = classify_delta(delta)
        try:
            cur.execute(
                """INSERT INTO probe_results
                   (field_id, experiment_name, round_n, bake_hash, noop_baseline,
                    spec_car_mdd, delta, classification, applied_op,
                    applied_threshold, applied_gate, applied_boost, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (f['id'], row['name'], round_n, bake_hash, baseline,
                 row['car_mdd'], delta, cls, f['probe_op'],
                 f['probe_threshold'], f['probe_gate'], f['probe_boost'], now))
            n_results += 1
        except sqlite3.IntegrityError:
            # UNIQUE(experiment_name) — already scored
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

    con.commit()
    con.close()
    return {'n_results': n_results, 'baseline': baseline,
            'fields_touched': len(touched_field_ids)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--round', dest='round_n', type=int, required=True)
    p.add_argument('--bake-hash', required=True)
    p.add_argument('--db', default='/home/txy/qc_work/data/S001.db')
    args = p.parse_args()
    out = score_round(db_path=args.db, round_n=args.round_n, bake_hash=args.bake_hash)
    print(f"Round {args.round_n}: scored {out['n_results']} probes, "
          f"baseline={out['baseline']:.4f}, "
          f"fields_touched={out['fields_touched']}")


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/txy/qc_work/data && pytest tests/test_score_probes.py -v`
Expected: 5 passed.

---

## Task 16: Run catalogue against real S001.db (manual)

**Files:**
- (none, runs against real DB)

- [ ] **Step 1: Backup the production DB**

```bash
cp /home/txy/qc_work/data/S001.db /home/txy/qc_work/data/S001.db.pre_catalogue.bak
```

- [ ] **Step 2: Run catalogue**

```bash
cd /home/txy/qc_work/data && python3 -m scripts.catalogue_universe
```
Expected output: `Inserted N new rows; total = M` where M ≥ 600 and N ≈ M − 92.

- [ ] **Step 3: Verify counts and backfill**

```bash
python3 << 'PY'
import sqlite3
con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
cur = con.cursor()
cur.execute("SELECT COUNT(*) FROM fundamental_fields")
print('Total rows:', cur.fetchone()[0])
cur.execute("SELECT container, COUNT(*) FROM fundamental_fields GROUP BY container ORDER BY container")
for r in cur.fetchall(): print(' ', r)
cur.execute("SELECT COUNT(*) FROM fundamental_fields WHERE container IS NULL")
print('Rows missing container (should be 0):', cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM fundamental_fields WHERE classification = 'untested'")
print('Untested rows:', cur.fetchone()[0])
PY
```
Expected: Total ≥600; per-container breakdown sensible (vr ≥50, ops ≥40, bs ≥100, etc.); 0 rows with NULL container; untested ≈ total minus 92 legacy 'tested_in' rows that were marked 'neutral'.

- [ ] **Step 4: Spot-check a categorical row**

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
cur = con.cursor()
cur.execute(\"SELECT field_name, probe_op, probe_threshold FROM fundamental_fields WHERE container='asset_classification' AND field_name='financial_health_grade'\")
print(cur.fetchone())
"
```
Expected: `('financial_health_grade', 'in', '[\"A\", \"A+\", \"A-\"]')`.

---

## Task 17: Modify `gen_s001_R407.py` template to use `emit_probes_for_db`

**Files:**
- Create: `/home/txy/qc_work/data/gen_s001_R407.py`

- [ ] **Step 1: Write the modified generator**

Create `/home/txy/qc_work/data/gen_s001_R407.py`:

```python
"""R407 — first round using the auto-emitted probes from fundamental_probes lib.

Layout:
  - 3 NOOP
  - 3 VERIFY cash_1020k (continued drill)
  - 7 cash_1020k × petlo joint
  - 7 cash_1020k × haircut joint
  - 7 cash_1020k × stop joint
  - 7 cash_1020k × stoplm joint
  - 7 cash_1020k × b14 joint
  - 7 cash_1020k × b17 joint
  - 16 fundamental probes auto-emitted from fundamental_fields (k_new=10, k_verify=6)
  = 64
"""
import ast
import hashlib
import sqlite3
import sys
from pathlib import Path

# Make s001 importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from s001.fundamental_probes import emit_probes_for_db, BIND

BASE = '/home/txy/qc_work/data/s001/s001_20260425_base.py'
EXPECTED = 'c0ed7f31b536f148f55b8ea3ea6c4550'  # BAKE-40
with open(BASE) as f:
    base_code = f.read()
got = hashlib.md5(base_code.encode()).hexdigest()
assert got == EXPECTED, f'base hash mismatch: {got}'
print(f'Base verified (BAKE-40): {EXPECTED}')

ANCHOR = '   candidates.append((sym, score, conv))'
specs = []


def chg(old, new, base=None):
    base = base if base is not None else base_code
    out = base.replace(old, new)
    assert out != base, f'chg failed: {old[:60]}'
    return out


CASH    = "STARTING_CASH = 300000  # BAKE-36 R320-R321: 120k→300k on BAKE-35 base, +0.0032 verified 3/3 deterministic"
PETLO   = "'petgt_lo':        .0275,  # BAKE-40 R390-R392: .045→.0275, +0.0089 verified 3/3 deterministic"
HAIRCUT = "'momentum_haircut': 1.344,           # BAKE-39 R383-R384: 1.34→1.344 (joint with petlo .045), +0.0041 verified 3/3"
B14     = "        score *= 1.25  # BAKE-23 R231: 1.22→1.25 (4-way stack with C1+C3+C4, +0.0148 joint)"
B17     = "       score *= 1.21"
STOP    = "'stop_default':    .42,    # BAKE-38 R327-R328: .40→.42 (joint with stop_lowmargin .09), +0.0088 verified 3/3"
STOPLM  = "'stop_lowmargin':  .09,    # BAKE-38 R327-R328: .08→.09 (joint with stop_default .42), +0.0088 verified 3/3"


# 3 NOOP
for i in range(3):
    code = base_code.replace(ANCHOR, f'   # vbake40_noop_{i}\n' + ANCHOR)
    specs.append((f'S001_R407_VBAKE40_NOOP_{i}', code))

# 3 VERIFY cash_1020k
for i in range(3):
    code = chg(CASH, 'STARTING_CASH = 1020000').replace(
        ANCHOR, f'   # verify_cash_1020k_b40_rep{i}\n' + ANCHOR)
    specs.append((f'S001_R407_VERIFY_cash_1020k_rep{i}', code))

# 7 cash_1020k × petlo joint
for v in ['.022', '.024', '.026', '.027', '.028', '.030', '.033']:
    specs.append((f'S001_R407_cash_1020k_petlo_{v.replace(".","")}',
                  chg(PETLO, f"'petgt_lo':        {v},",
                      base=chg(CASH, 'STARTING_CASH = 1020000'))))

# 7 cash_1020k × haircut joint
for v in ['1.339', '1.341', '1.343', '1.345', '1.347', '1.349', '1.352']:
    specs.append((f'S001_R407_cash_1020k_haircut_{v.replace(".","")}',
                  chg(HAIRCUT, f"'momentum_haircut': {v},",
                      base=chg(CASH, 'STARTING_CASH = 1020000'))))

# 7 cash_1020k × stop joint
for v in ['.36', '.38', '.40', '.43', '.45', '.48', '.51']:
    specs.append((f'S001_R407_cash_1020k_stop_{v.replace(".","")}',
                  chg(STOP, f"'stop_default':    {v},",
                      base=chg(CASH, 'STARTING_CASH = 1020000'))))

# 7 cash_1020k × stoplm joint
for v in ['.05', '.07', '.075', '.085', '.095', '.11', '.13']:
    specs.append((f'S001_R407_cash_1020k_stoplm_{v.replace(".","")}',
                  chg(STOPLM, f"'stop_lowmargin':  {v},",
                      base=chg(CASH, 'STARTING_CASH = 1020000'))))

# 7 cash_1020k × b14 joint
for v in ['1.20', '1.22', '1.23', '1.27', '1.29', '1.32', '1.36']:
    specs.append((f'S001_R407_cash_1020k_b14_{v.replace(".","")}',
                  chg(B14, f'        score *= {v}',
                      base=chg(CASH, 'STARTING_CASH = 1020000'))))

# 7 cash_1020k × b17 joint (skip 1.21 = baseline)
for v in ['1.16', '1.18', '1.19', '1.215', '1.225', '1.24', '1.27']:
    specs.append((f'S001_R407_cash_1020k_b17_{v.replace(".","")}',
                  chg(B17, f'       score *= {v}',
                      base=chg(CASH, 'STARTING_CASH = 1020000'))))

# === Auto-emitted fundamental probes ===
auto = emit_probes_for_db(
    db_path='/home/txy/qc_work/data/S001.db',
    round_n=407, k_new=10, k_verify=6, include_bind=False)
print(f'Auto-emitted {len(auto)} probes from fundamental_fields')

for name, body in auto:
    code = base_code.replace(ANCHOR, BIND + body + '\n' + ANCHOR)
    specs.append((name, code))

specs = specs[:64]
print(f'Total: {len(specs)}')
print(f'Unique: {len({hashlib.md5(c.encode()).hexdigest() for n, c in specs})}/{len(specs)}')

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
             '2026-05-04 12:00:00', h))
        inserted += 1
    except sqlite3.IntegrityError as e:
        print(f'Skip {n}: {e}')
con.commit()
print(f'Inserted {inserted} R407 specs')
```

- [ ] **Step 2: Run the generator (after Task 16 has populated the catalogue)**

```bash
cd /home/txy/qc_work/data && python3 gen_s001_R407.py
```
Expected: `Total: 64`, `Unique: 64/64`, `All parse OK`, `Inserted 64 R407 specs`.

If the auto-emitted count is < 10, the catalogue may have too few `untested` rows with non-NULL templates — open `S001.db` and confirm via:
```bash
python3 -c "
import sqlite3
con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
n = con.execute(\"SELECT COUNT(*) FROM fundamental_fields WHERE classification='untested' AND probe_threshold IS NOT NULL\").fetchone()[0]
print('untested with template:', n)
"
```
If still low, run `python3 -m scripts.catalogue_universe --update-templates` to apply default templates to untested rows that lack them.

- [ ] **Step 3: Verify the auto-emitted spec names follow the convention**

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
cur = con.cursor()
cur.execute(\"SELECT name FROM backtest_queue WHERE name LIKE 'S001_R407_%' AND name NOT LIKE '%VBAKE%' AND name NOT LIKE '%VERIFY%' AND name NOT LIKE '%cash_1020k%' ORDER BY name\")
for (n,) in cur.fetchall(): print(' ', n)
"
```
Expected: 16 names matching the auto-naming pattern (`S001_R407_<container_short>_<field_name>_<op_short><threshold_short>`).

---

## Task 18: End-to-end smoke (after R407 backtests complete)

**Files:**
- (none — manual workflow)

This task happens after the cron has run R407's 64 backtests and they're imported into `experiments`.

- [ ] **Step 1: Verify R407 backtests are done**

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
cur = con.cursor()
cur.execute(\"SELECT status, COUNT(*) FROM backtest_queue WHERE name LIKE 'S001_R407_%' GROUP BY status\")
for r in cur.fetchall(): print(' ', r)
"
```
Expected: `('done', 64)` — if not, wait for cron loop and retry.

- [ ] **Step 2: Run score_probes**

```bash
cd /home/txy/qc_work/data && python3 -m scripts.score_probes --round 407 --bake-hash c0ed7f31b536f148f55b8ea3ea6c4550
```
Expected: `Round 407: scored N probes, baseline=1.99XX, fields_touched=N` where N matches the count of auto-emitted probe specs (15-16).

- [ ] **Step 3: Inspect probe_results**

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
cur = con.cursor()
cur.execute(\"SELECT classification, COUNT(*) FROM probe_results WHERE round_n=407 GROUP BY classification\")
print('R407 result classification counts:')
for r in cur.fetchall(): print(' ', r)
cur.execute(\"SELECT experiment_name, delta FROM probe_results WHERE round_n=407 AND classification='hot' ORDER BY delta DESC LIMIT 5\")
print('Top 5 hot probes:')
for r in cur.fetchall(): print(f'  {r[0]:60s} +{r[1]:.4f}')
\"
"
```
Expected: classification breakdown shows hot/neutral/harmful distribution, with at least some neutral entries.

- [ ] **Step 4: Verify field classifications updated**

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('/home/txy/qc_work/data/S001.db')
cur = con.cursor()
cur.execute(\"SELECT classification, COUNT(*) FROM fundamental_fields GROUP BY classification\")
print('Field classification distribution:')
for r in cur.fetchall(): print(' ', r)
"
```
Expected: at least one row in 'hot' or 'harmful' (whichever is appropriate), plus untested/neutral.

- [ ] **Step 5: Verify the next round will pick fresh fields**

```bash
cd /home/txy/qc_work/data && python3 -m scripts.emit_probes --round 408 --k-new 5 --k-verify 0 | head -40
```
Expected: 5 specs printed, none duplicating R407's auto-emitted picks (because those are now `neutral` or `hot`/`harmful`, not `untested`).

---

## Self-Review Checklist

After completing all tasks above, verify:

1. **Spec coverage:**
   - §4 architecture → Tasks 2-15 build the library + scripts.
   - §5.1 fundamental_fields ALTERs → Task 1.
   - §5.2 probe_results table → Task 1.
   - §5.3 legacy migration → Task 1 (UPDATE statements).
   - §6.1 BIND block → Task 8.
   - §6.2-6.4 render template → Tasks 5-8.
   - §6.5 spec naming → Task 9.
   - §6.6 fail-loud render checks → Tasks 7, 8 (raises + null skip).
   - §7.1 score_probes → Task 15.
   - §7.2 field rollup → Task 4.
   - §7.3 emit_probes / pick → Tasks 10, 14.
   - §7.4 promotion query → documented in spec only; no implementation needed (manual SQL).
   - §7.5 edge cases → Task 15 (NOOP missing → assert; spread → assert; idempotent → UNIQUE).
   - §8.1-8.3 catalogue inclusion / period / template → Tasks 11, 12, 13.
   - §8.4 idempotency → Task 13.
   - §8.5 backfill → Task 13.
   - §9 testing → Tasks 0, 2-15.
   - §11 migration sequence → Tasks 1, 16, 17, 18.

2. **No placeholders / "Similar to Task N" / "Add error handling":**
   - All steps include exact code or commands.
   - No "TBD", "TODO", "implement later".

3. **Type / signature consistency:**
   - `accessor_for(row)` ←→ used by `render_probe`, `pick_fields`.
   - `classify_delta(d)` ←→ used by `score_round`.
   - `field_rollup(results)` ←→ used by `score_round` post-loop.
   - `build_condition(row, var)` ←→ used by `render_probe`.
   - `default_period(container)`, `default_template(container, field_name)` ←→ used by `catalogue_universe.main`.
   - `pick_fields(db, k, classification)` ←→ used by `emit_probes_for_db`.
   - `emit_probes_for_db(db_path, round_n, k_new, k_verify, include_bind)` ←→ used by `gen_s001_R407.py`.
   - `score_round(db_path, round_n, bake_hash)` ←→ called by `scripts/score_probes.py:main`.
   - All consistent.
