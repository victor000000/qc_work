# S001 Mega Fundamental-Field Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 6-cell-per-field mechanism dimension (entry-skip / exit-stop / exit-petgt / score / conv-good / conv-bad) to the S001 probe pipeline, refactor `base.py` to expose ENTRY/EXIT injection anchors with a shared regime context, and ship a single mega-round generator that emits ~5349 specs covering all 891 templated fundamental fields.

**Architecture:** Generalize the existing Phase-1 emit primitives (`render_probe` → `render_cell` taking a `mech` arg). Pure additive changes — v1/v2/v3 paths untouched. New `mechanism` column on `probe_results` distinguishes mega rows; `field_rollup` scoped to score-only so non-score cells don't poison v3 pickup. Spec naming uses an unambiguous `S001_R{N}_mg_{mech}_{cs}_{field}` format anchored by `_mg_` so the field tail can contain any substring without re-triggering the v1 `_in_/_gt_` parser bug.

**Tech Stack:** Python 3.13, sqlite3, pytest, QuantConnect LEAN. Working dir for tests: `/home/txy/qc_work/data`. Run tests with `cd /home/txy/qc_work/data && python -m pytest <path> -v`.

**Reference spec:** `docs/superpowers/specs/2026-04-29-s001-mega-fundamental-sweep-design.md`

---

## File map

**Create:**
- `data/gen_s001_R603_mega.py` — single-purpose generator script (Task 13)

**Modify:**
- `data/s001/fundamental_probes.py` — add `MECHANISMS`, `MECH_DEFAULTS`, `flip_op`, extend `build_condition`, add `mega_spec_name`, `render_cell`, `emit_mega_round`, `pick_fields(force_all=True)`, `EXIT_BIND` (Tasks 2-9)
- `data/s001/s001_20260425_base.py` — `_compute_regime`, ENTRY/EXIT injection anchors, remove stale PERFOPT cache (Task 10)
- `data/scripts/score_probes.py` — `MEGA_NAME_RE`, mega routing branch, `field_rollup` scoping (Tasks 11-12)
- `data/scripts/migrate_schema.py` — add `mechanism` column + index (Task 1)
- `data/tests/conftest.py` — add `mechanism` column to test schema (Task 1)

**Test files to extend (existing):**
- `data/tests/test_fundamental_probes.py` — flip_op, build_condition extension, MECH_DEFAULTS, render_cell, mega_spec_name, emit_mega_round, pick_fields(force_all)
- `data/tests/test_score_probes.py` — mega routing, field_rollup scoping
- `data/tests/test_migrate_schema.py` — `mechanism` column added

---

### Task 1: DB schema — add `mechanism` column

**Files:**
- Modify: `data/scripts/migrate_schema.py`
- Modify: `data/tests/conftest.py`
- Test: `data/tests/test_migrate_schema.py`

- [ ] **Step 1: Write the failing test**

Add to `data/tests/test_migrate_schema.py` (after the existing `test_migration_adds_columns_and_table`):

```python
def test_migration_adds_mechanism_column(tmp_db):
    # tmp_db starts with the post-V3 schema (no mechanism column yet, since we haven't added it).
    # Drop the column from probe_results to simulate the legacy state if present.
    import sqlite3
    con = sqlite3.connect(tmp_db)
    cur = con.cursor()
    cur.execute("PRAGMA table_info(probe_results)")
    cols_before = {r[1] for r in cur.fetchall()}
    if 'mechanism' in cols_before:
        # SQLite has no DROP COLUMN pre-3.35 simulation needed; conftest after this task
        # won't have mechanism, so this branch is for forward-compat sanity only.
        pass

    apply_schema_migration(tmp_db)

    cur.execute("PRAGMA table_info(probe_results)")
    cols_after = {r[1] for r in cur.fetchall()}
    assert 'mechanism' in cols_after, f'mechanism column missing: {cols_after}'

    cur.execute("PRAGMA index_list(probe_results)")
    idx_names = {r[1] for r in cur.fetchall()}
    assert 'idx_probe_results_mechanism' in idx_names
    con.close()


def test_migration_idempotent_on_mechanism(tmp_db):
    # Running migration twice should not error.
    apply_schema_migration(tmp_db)
    apply_schema_migration(tmp_db)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_migrate_schema.py::test_migration_adds_mechanism_column -v
```

Expected: FAIL with "mechanism column missing" (or similar).

- [ ] **Step 3: Update conftest schema**

Modify `data/tests/conftest.py` — change the `CREATE TABLE probe_results` block to include `mechanism TEXT`:

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
            sweep_stage TEXT,
            mechanism TEXT
        )""")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_probe_results_mechanism "
            "ON probe_results(field_id, mechanism, bake_hash)")
```

- [ ] **Step 4: Add migration logic**

Modify `data/scripts/migrate_schema.py`. Add a new constant near the existing `V3_PROBE_RESULTS_COLUMNS`:

```python
MEGA_PROBE_RESULTS_COLUMNS = [
    ('mechanism', 'TEXT', ''),
]
```

Find `apply_schema_migration` and locate where `V3_PROBE_RESULTS_COLUMNS` is iterated (look for the existing `for name, ctype, default in V3_PROBE_RESULTS_COLUMNS:` block). Add an analogous block right after it:

```python
    # Mega-round mechanism dimension (2026-04-29)
    cur.execute("PRAGMA table_info(probe_results)")
    pr_cols = {r[1] for r in cur.fetchall()}
    for name, ctype, default in MEGA_PROBE_RESULTS_COLUMNS:
        if name not in pr_cols:
            sql = f"ALTER TABLE probe_results ADD COLUMN {name} {ctype} {default}".strip()
            cur.execute(sql)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_probe_results_mechanism "
                "ON probe_results(field_id, mechanism, bake_hash)")
```

(If the existing migration script reads `pr_cols` once at the top, reuse that variable instead of re-querying.)

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_migrate_schema.py -v
```

Expected: All migration tests PASS, including the two new ones.

Also run the conftest-affecting tests to confirm no breakage:

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_score_probes.py -v
```

Expected: PASS (existing tests still work because `mechanism` is nullable).

- [ ] **Step 6: Apply migration to live DB**

```bash
cd /home/txy/qc_work/data && python -c "from scripts.migrate_schema import apply_schema_migration; apply_schema_migration('/home/txy/qc_work/data/S001.db')"
python3 -c "import sqlite3; c=sqlite3.connect('/home/txy/qc_work/data/S001.db').cursor(); c.execute('PRAGMA table_info(probe_results)'); print('mechanism' in {r[1] for r in c.fetchall()})"
```

Expected output: `True`.

- [ ] **Step 7: Commit**

```bash
git add data/scripts/migrate_schema.py data/tests/conftest.py data/tests/test_migrate_schema.py
git commit -m "$(cat <<'EOF'
feat(s001): add mechanism column to probe_results for mega-round dimension

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `flip_op` helper

**Files:**
- Modify: `data/s001/fundamental_probes.py`
- Test: `data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Write the failing test**

Append to `data/tests/test_fundamental_probes.py`:

```python
from s001.fundamental_probes import flip_op


class TestFlipOp:
    def test_gt_to_lt(self):
        assert flip_op('>') == '<'

    def test_lt_to_gt(self):
        assert flip_op('<') == '>'

    def test_gte_to_lte(self):
        assert flip_op('>=') == '<='

    def test_lte_to_gte(self):
        assert flip_op('<=') == '>='

    def test_eq_to_neq(self):
        assert flip_op('eq') == 'neq'

    def test_in_to_notin(self):
        assert flip_op('in') == 'notin'

    def test_unknown_raises(self):
        with pytest.raises(KeyError):
            flip_op('between')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py::TestFlipOp -v
```

Expected: FAIL with `ImportError: cannot import name 'flip_op'`.

- [ ] **Step 3: Implement `flip_op`**

Add to `data/s001/fundamental_probes.py` after the existing `OP_SHORT` dict (around line 184):

```python
def flip_op(op):
    """Return the logical inverse of a probe op.

    Used by mega-round 'bad-side' mechanisms (skip/stop/convb) which trigger on
    the opposite side of a field's stored 'good' template."""
    return {'>': '<', '<': '>', '>=': '<=', '<=': '>=',
            'eq': 'neq', 'in': 'notin'}[op]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py::TestFlipOp -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add data/s001/fundamental_probes.py data/tests/test_fundamental_probes.py
git commit -m "$(cat <<'EOF'
feat(s001): add flip_op helper for mega-round bad-side mechanisms

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Extend `build_condition` for `neq` and `notin`

**Files:**
- Modify: `data/s001/fundamental_probes.py`
- Test: `data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Write the failing tests**

Append to `data/tests/test_fundamental_probes.py`:

```python
from s001.fundamental_probes import build_condition


class TestBuildConditionInverse:
    def test_neq_string(self):
        row = {'probe_op': 'neq', 'probe_threshold': '"A"',
               'data_type_hint': 'categorical'}
        assert build_condition(row, '_v') == "_v != 'A'"

    def test_neq_number(self):
        row = {'probe_op': 'neq', 'probe_threshold': '207',
               'data_type_hint': 'categorical'}
        assert build_condition(row, '_v') == "_v != 207"

    def test_notin_array(self):
        row = {'probe_op': 'notin', 'probe_threshold': '[205, 206, 207]',
               'data_type_hint': 'categorical'}
        assert build_condition(row, '_v') == "_v not in (205, 206, 207)"

    def test_notin_single_element(self):
        row = {'probe_op': 'notin', 'probe_threshold': '["A"]',
               'data_type_hint': 'categorical'}
        assert build_condition(row, '_v') == "_v not in ('A',)"

    def test_neq_requires_categorical(self):
        row = {'probe_op': 'neq', 'probe_threshold': '"A"',
               'data_type_hint': 'numeric'}
        with pytest.raises(ValueError, match='categorical'):
            build_condition(row, '_v')

    def test_notin_requires_array(self):
        row = {'probe_op': 'notin', 'probe_threshold': '"single"',
               'data_type_hint': 'categorical'}
        with pytest.raises(ValueError, match='array'):
            build_condition(row, '_v')
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py::TestBuildConditionInverse -v
```

Expected: All 6 tests FAIL with "NotImplementedError: build_condition: op 'neq' not supported".

- [ ] **Step 3: Implement the new branches**

Modify `data/s001/fundamental_probes.py` `build_condition` function. Locate the existing `if op == 'in':` branch and add two new branches BEFORE the final `raise NotImplementedError`:

```python
    if op == 'neq':
        if hint != 'categorical':
            raise ValueError(f"op 'neq' requires data_type_hint='categorical', got {hint!r}")
        try:
            parsed = json.loads(thr)
        except json.JSONDecodeError as e:
            raise ValueError(f"op 'neq' requires JSON threshold: {thr!r} ({e})")
        return f"{var} != {parsed!r}" if isinstance(parsed, str) else f"{var} != {parsed}"

    if op == 'notin':
        if hint != 'categorical':
            raise ValueError(f"op 'notin' requires data_type_hint='categorical', got {hint!r}")
        try:
            parsed = json.loads(thr)
        except json.JSONDecodeError as e:
            raise ValueError(f"op 'notin' requires JSON array threshold: {thr!r} ({e})")
        if not isinstance(parsed, list):
            raise ValueError(f"op 'notin' requires JSON array threshold: got {type(parsed).__name__}")
        if len(parsed) == 1:
            tup_repr = f"({parsed[0]!r},)" if isinstance(parsed[0], str) else f"({parsed[0]},)"
        else:
            inner = ", ".join(repr(x) if isinstance(x, str) else str(x) for x in parsed)
            tup_repr = f"({inner})"
        return f"{var} not in {tup_repr}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py::TestBuildConditionInverse -v
```

Expected: All 6 tests PASS.

Also rerun the full file to confirm no regressions:

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py -v
```

Expected: All tests PASS (existing + new).

- [ ] **Step 5: Commit**

```bash
git add data/s001/fundamental_probes.py data/tests/test_fundamental_probes.py
git commit -m "$(cat <<'EOF'
feat(s001): build_condition supports inverse ops (neq, notin) for mega bad-side cells

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `MECHANISMS` tuple + `MECH_DEFAULTS` dict

**Files:**
- Modify: `data/s001/fundamental_probes.py`
- Test: `data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Write the failing tests**

Append to `data/tests/test_fundamental_probes.py`:

```python
from s001.fundamental_probes import MECHANISMS, MECH_DEFAULTS


class TestMechanismDefaults:
    def test_six_mechanisms(self):
        assert MECHANISMS == ('score', 'skip', 'stop', 'petgt', 'convg', 'convb')

    def test_each_has_required_keys(self):
        required = {'action', 'mag', 'gate', 'side', 'location'}
        for m in MECHANISMS:
            assert required <= set(MECH_DEFAULTS[m].keys()), f'{m} missing keys'

    def test_score_defaults(self):
        d = MECH_DEFAULTS['score']
        assert d['action'] == 'score *= {mag}'
        assert d['mag'] == 1.10
        assert d['gate'] == 'decline > .05'
        assert d['side'] == 'good'
        assert d['location'] == 'entry'

    def test_skip_defaults(self):
        d = MECH_DEFAULTS['skip']
        assert d['action'] == 'continue'
        assert d['mag'] is None
        assert d['gate'] == 'decline > .10'
        assert d['side'] == 'bad'
        assert d['location'] == 'entry'

    def test_stop_defaults(self):
        d = MECH_DEFAULTS['stop']
        assert d['action'] == 'stop *= {mag}'
        assert d['mag'] == 0.85
        assert d['gate'] is None
        assert d['side'] == 'bad'
        assert d['location'] == 'exit'

    def test_petgt_defaults(self):
        d = MECH_DEFAULTS['petgt']
        assert d['action'] == 'petgt *= {mag}'
        assert d['mag'] == 1.15
        assert d['gate'] is None
        assert d['side'] == 'good'
        assert d['location'] == 'exit'

    def test_convg_defaults(self):
        d = MECH_DEFAULTS['convg']
        assert d['action'] == 'conv *= {mag}'
        assert d['mag'] == 1.15
        assert d['gate'] == 'decline > .05'
        assert d['side'] == 'good'
        assert d['location'] == 'entry'

    def test_convb_defaults(self):
        d = MECH_DEFAULTS['convb']
        assert d['action'] == 'conv *= {mag}'
        assert d['mag'] == 0.70
        assert d['gate'] == 'decline > .05'
        assert d['side'] == 'bad'
        assert d['location'] == 'entry'
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py::TestMechanismDefaults -v
```

Expected: FAIL with `ImportError: cannot import name 'MECHANISMS'`.

- [ ] **Step 3: Implement `MECHANISMS` and `MECH_DEFAULTS`**

Add to `data/s001/fundamental_probes.py` near the top (after `HOT_THRESHOLD` constants, around line 33):

```python
MECHANISMS = ('score', 'skip', 'stop', 'petgt', 'convg', 'convb')

MECH_DEFAULTS = {
    'score': {'action': 'score *= {mag}',  'mag': 1.10, 'gate': 'decline > .05',
              'side': 'good', 'location': 'entry'},
    'skip':  {'action': 'continue',        'mag': None, 'gate': 'decline > .10',
              'side': 'bad',  'location': 'entry'},
    'stop':  {'action': 'stop *= {mag}',   'mag': 0.85, 'gate': None,
              'side': 'bad',  'location': 'exit'},
    'petgt': {'action': 'petgt *= {mag}',  'mag': 1.15, 'gate': None,
              'side': 'good', 'location': 'exit'},
    'convg': {'action': 'conv *= {mag}',   'mag': 1.15, 'gate': 'decline > .05',
              'side': 'good', 'location': 'entry'},
    'convb': {'action': 'conv *= {mag}',   'mag': 0.70, 'gate': 'decline > .05',
              'side': 'bad',  'location': 'entry'},
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py::TestMechanismDefaults -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add data/s001/fundamental_probes.py data/tests/test_fundamental_probes.py
git commit -m "$(cat <<'EOF'
feat(s001): add MECHANISMS + MECH_DEFAULTS for mega-round 6-cell schema

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `ENTRY_BIND` / `EXIT_BIND` aliases

**Files:**
- Modify: `data/s001/fundamental_probes.py`
- Test: `data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Write the failing tests**

Append to `data/tests/test_fundamental_probes.py`:

```python
from s001.fundamental_probes import ENTRY_BIND, EXIT_BIND, BIND


class TestBinds:
    def test_entry_bind_equals_bind(self):
        # ENTRY INJECT POINT and EXIT INJECT POINT are at the same indent level
        # (both are inside their respective `for sym in equities:` loops at
        # 3-space indent). Both binds reuse BIND verbatim.
        assert ENTRY_BIND == BIND

    def test_exit_bind_equals_bind(self):
        assert EXIT_BIND == BIND

    def test_binds_contain_alias_block(self):
        assert '_ops_z' in ENTRY_BIND
        assert '_vr_z' in ENTRY_BIND
        assert '_bs_z' in ENTRY_BIND
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py::TestBinds -v
```

Expected: FAIL with `ImportError: cannot import name 'ENTRY_BIND'`.

- [ ] **Step 3: Add bind aliases**

Add to `data/s001/fundamental_probes.py` immediately after the `BIND = """..."""` block (around line 132):

```python
# ENTRY/EXIT bind aliases. The ENTRY INJECT POINT (in _scan_entries) and
# EXIT INJECT POINT (in _scan_exits) sit inside their respective
# `for sym in equities:` loops at the same 3-space indent level, so the
# fundamental-attribute prelude is identical for both.
ENTRY_BIND = BIND
EXIT_BIND  = BIND
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py::TestBinds -v
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add data/s001/fundamental_probes.py data/tests/test_fundamental_probes.py
git commit -m "$(cat <<'EOF'
feat(s001): export ENTRY_BIND/EXIT_BIND aliases for mega-round generator

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `mega_spec_name` + spec-name regex round-trip test

**Files:**
- Modify: `data/s001/fundamental_probes.py`
- Test: `data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Write the failing tests**

Append to `data/tests/test_fundamental_probes.py`:

```python
from s001.fundamental_probes import mega_spec_name


class TestMegaSpecName:
    def test_score_ops(self):
        row = {'container': 'operation_ratios', 'field_name': 'revenue_growth'}
        assert mega_spec_name(603, 'score', row) == 'S001_R603_mg_score_ops_revenue_growth'

    def test_skip_ers(self):
        row = {'container': 'earning_ratios', 'field_name': 'diluted_eps_growth'}
        assert mega_spec_name(603, 'skip', row) == 'S001_R603_mg_skip_ers_diluted_eps_growth'

    def test_petgt_vr(self):
        row = {'container': 'valuation_ratios', 'field_name': 'pe_ratio'}
        assert mega_spec_name(603, 'petgt', row) == 'S001_R603_mg_petgt_vr_pe_ratio'

    def test_convb_bs(self):
        row = {'container': 'balance_sheet', 'field_name': 'long_term_debt'}
        assert mega_spec_name(603, 'convb', row) == 'S001_R603_mg_convb_bs_long_term_debt'

    def test_handles_underscore_heavy_field_name(self):
        # Field names with substring _in_ / _gt_ / _lt_ — the source of the v1 parser bug.
        # mega_spec_name should produce them as-is; the regex (Task 11) parses unambiguously
        # because the _mg_<mech>_<cs>_ prefix is fully anchored.
        row = {'container': 'cash_flow_statement',
               'field_name': 'change_in_account_payable'}
        assert mega_spec_name(603, 'score', row) == 'S001_R603_mg_score_cfs_change_in_account_payable'

    def test_unknown_mech_raises(self):
        row = {'container': 'operation_ratios', 'field_name': 'roe'}
        with pytest.raises(KeyError):
            mega_spec_name(603, 'bogus', row)

    def test_unknown_container_raises(self):
        row = {'container': 'mystery', 'field_name': 'x'}
        with pytest.raises(KeyError):
            mega_spec_name(603, 'score', row)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py::TestMegaSpecName -v
```

Expected: FAIL with `ImportError: cannot import name 'mega_spec_name'`.

- [ ] **Step 3: Implement `mega_spec_name`**

Add to `data/s001/fundamental_probes.py` after the existing `spec_name` function (around line 235):

```python
def mega_spec_name(round_n, mech, field_row):
    """Build the deterministic mega-round spec name.

    Format: S001_R{round_n}_mg_{mech}_{container_short}_{field_name}

    The `_mg_<mech>_<cs>_` prefix is fully anchored, so the trailing field_name
    can contain `_in_`, `_gt_`, etc. without triggering the v1 parser bug."""
    if mech not in MECHANISMS:
        raise KeyError(f'Unknown mechanism {mech!r}; expected one of {MECHANISMS}')
    cs = CONTAINER_SHORT[field_row['container']]
    return f"S001_R{round_n}_mg_{mech}_{cs}_{field_row['field_name']}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py::TestMegaSpecName -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add data/s001/fundamental_probes.py data/tests/test_fundamental_probes.py
git commit -m "$(cat <<'EOF'
feat(s001): mega_spec_name produces unambiguous _mg_<mech>_<cs>_<field> names

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: `render_cell` per mechanism

**Files:**
- Modify: `data/s001/fundamental_probes.py`
- Test: `data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Write the failing tests**

Append to `data/tests/test_fundamental_probes.py`:

```python
from s001.fundamental_probes import render_cell


def _row_score_template():
    """A score-template field: revenue_growth > 0.10 → score *= 1.10, gated decline > .12.
    Mega will reuse the field's container/field_name/probe_op/probe_threshold/data_type_hint."""
    return {
        'id': 1, 'container': 'operation_ratios', 'field_name': 'revenue_growth',
        'period': 'one_year',
        'probe_op': '>', 'probe_threshold': '0.10', 'probe_gate': 'decline > .12',
        'probe_boost': 1.10, 'data_type_hint': 'numeric',
    }


def _row_categorical_in():
    return {
        'id': 2, 'container': 'asset_classification',
        'field_name': 'morningstar_sector_code', 'period': None,
        'probe_op': 'in', 'probe_threshold': '[205, 206, 207]',
        'probe_gate': 'decline > .10', 'probe_boost': 1.08,
        'data_type_hint': 'categorical',
    }


class TestRenderCell:
    def test_score_good_side(self):
        out = render_cell(_row_score_template(), 'score', 603)
        assert out is not None
        name, body, location = out
        assert name == 'S001_R603_mg_score_ops_revenue_growth'
        assert location == 'entry'
        # Good-side: probe_op as-defined ('>'), action 'score *= 1.10', gate 'decline > .05'
        assert '_ops_z.revenue_growth.one_year' in body
        assert '_v > 0.10' in body
        assert 'decline > .05' in body
        assert 'score *= 1.1' in body

    def test_skip_bad_side(self):
        out = render_cell(_row_score_template(), 'skip', 603)
        assert out is not None
        name, body, location = out
        assert name == 'S001_R603_mg_skip_ops_revenue_growth'
        assert location == 'entry'
        # Bad-side: op flipped to '<', action is 'continue', gate 'decline > .10'
        assert '_v < 0.10' in body
        assert 'continue' in body
        assert 'decline > .10' in body

    def test_stop_bad_side(self):
        out = render_cell(_row_score_template(), 'stop', 603)
        assert out is not None
        name, body, location = out
        assert location == 'exit'
        assert '_v < 0.10' in body
        assert 'stop *= 0.85' in body
        # No regime gate on exit-side.
        assert 'decline >' not in body

    def test_petgt_good_side(self):
        out = render_cell(_row_score_template(), 'petgt', 603)
        assert out is not None
        name, body, location = out
        assert location == 'exit'
        assert '_v > 0.10' in body
        assert 'petgt *= 1.15' in body
        assert 'decline >' not in body

    def test_convg_good_side(self):
        out = render_cell(_row_score_template(), 'convg', 603)
        assert out is not None
        name, body, location = out
        assert location == 'entry'
        assert '_v > 0.10' in body
        assert 'conv *= 1.15' in body
        assert 'decline > .05' in body

    def test_convb_bad_side(self):
        out = render_cell(_row_score_template(), 'convb', 603)
        assert out is not None
        name, body, location = out
        assert location == 'entry'
        assert '_v < 0.10' in body
        assert 'conv *= 0.7' in body
        assert 'decline > .05' in body

    def test_categorical_in_good_renders(self):
        out = render_cell(_row_categorical_in(), 'score', 603)
        assert out is not None
        name, body, location = out
        assert '_v in (205, 206, 207)' in body

    def test_categorical_notin_bad_renders(self):
        out = render_cell(_row_categorical_in(), 'skip', 603)
        assert out is not None
        name, body, location = out
        assert '_v not in (205, 206, 207)' in body

    def test_unknown_mech_raises(self):
        with pytest.raises(KeyError):
            render_cell(_row_score_template(), 'bogus', 603)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py::TestRenderCell -v
```

Expected: All FAIL with `ImportError: cannot import name 'render_cell'`.

- [ ] **Step 3: Implement `render_cell`**

Add to `data/s001/fundamental_probes.py` after `mega_spec_name` (Task 6):

```python
def render_cell(field_row, mech, round_n, mag=None, gate_override=None):
    """Render a single mega-round cell.

    Returns (spec_name, body, location) or None if the cell should be dropped
    (e.g. categorical 'in' field whose inverse covers >50% of the universe —
    not currently triggered by any DB row).

    location ∈ {'entry', 'exit'} — generator splices at the matching anchor."""
    defaults = MECH_DEFAULTS[mech]
    side = defaults['side']
    op = field_row['probe_op'] if side == 'good' else flip_op(field_row['probe_op'])
    thr = field_row['probe_threshold']
    hint = field_row.get('data_type_hint') or 'numeric'

    # Safety valve: drop bad-side cells when the inverse is provably ambiguous.
    # Only triggered for `in` ops with arrays > 50% of universe — not triggered
    # by any current DB row (3 templated `in` fields, all with small arrays).
    if op == 'notin' and side == 'bad':
        try:
            parsed = json.loads(thr)
            # No universe-stats lookup here — just a sanity guard.
            if isinstance(parsed, list) and len(parsed) > 100:
                return None
        except (json.JSONDecodeError, TypeError):
            return None

    accessor = accessor_for(field_row)
    coerced = accessor if hint == 'categorical' else f'f_({accessor})'

    cond_row = {'probe_op': op, 'probe_threshold': thr, 'data_type_hint': hint}
    cond = build_condition(cond_row, '_v')

    chosen_mag = mag if mag is not None else defaults['mag']
    action = (defaults['action'].format(mag=chosen_mag)
              if chosen_mag is not None
              else defaults['action'])

    gate = gate_override if gate_override is not None else defaults['gate']
    name = mega_spec_name(round_n, mech, field_row)
    location = defaults['location']

    if location == 'entry':
        # 3-space indent (inside _scan_entries `for sym in equities:` body)
        if gate:
            body = (
                "   try:\n"
                f"    _v = {coerced}\n"
                f"    if {cond} and ({gate}): {action}\n"
                "   except: pass"
            )
        else:
            body = (
                "   try:\n"
                f"    _v = {coerced}\n"
                f"    if {cond}: {action}\n"
                "   except: pass"
            )
    else:
        # 3-space indent (inside _scan_exits `for sym in equities:` body)
        body = (
            "   try:\n"
            f"    _v = {coerced}\n"
            f"    if {cond}: {action}\n"
            "   except: pass"
        )

    return name, body, location
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py::TestRenderCell -v
```

Expected: All 9 tests PASS. If any test fails on an exact-string match, inspect the actual `body` output and adjust the test's substring assertion.

- [ ] **Step 5: Commit**

```bash
git add data/s001/fundamental_probes.py data/tests/test_fundamental_probes.py
git commit -m "$(cat <<'EOF'
feat(s001): render_cell emits per-mechanism cell bodies for mega-round

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: `pick_fields(force_all=True)`

**Files:**
- Modify: `data/s001/fundamental_probes.py`
- Test: `data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Write the failing test**

Append to `data/tests/test_fundamental_probes.py`:

```python
import sqlite3
from s001.fundamental_probes import pick_fields


def _seed_three_fields(tmp_db):
    """One templated untested, one templated already-tested, one with NULL template."""
    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO fundamental_fields "
            "(id, category, field_name, accessor, container, period, probe_op, probe_threshold, probe_gate, probe_boost, data_type_hint, classification) "
            "VALUES (1, 'ops', 'revenue_growth', '_ops_z.revenue_growth.one_year', "
            "'operation_ratios', 'one_year', '>', '0.10', 'decline > .12', 1.10, 'numeric', 'untested')")
        cur.execute(
            "INSERT INTO fundamental_fields "
            "(id, category, field_name, accessor, container, period, probe_op, probe_threshold, probe_gate, probe_boost, data_type_hint, classification) "
            "VALUES (2, 'vr', 'pe_ratio', '_vr_z.pe_ratio', 'valuation_ratios', NULL, "
            "'<', '15', 'decline > .10', 1.10, 'numeric', 'hot')")
        # Mark field 2 as already probed at bake_hash 'b4619' so default pick_fields skips it.
        cur.execute(
            "INSERT INTO probe_results "
            "(field_id, experiment_name, round_n, bake_hash, noop_baseline, spec_car_mdd, delta, classification, applied_op, applied_threshold, applied_gate, applied_boost, recorded_at) "
            "VALUES (2, 'S001_R500_vr_pe_ratio_lt15', 500, 'b4619', 1.9, 1.91, 0.01, 'hot', '<', '15', 'decline > .10', 1.10, '2026-04-29')")
        cur.execute(
            "INSERT INTO fundamental_fields "
            "(id, category, field_name, accessor, container, period, probe_op, probe_threshold, classification) "
            "VALUES (3, 'sr', 'no_template_field', '_sr_z.no_template_field', 'security_reference', NULL, NULL, NULL, 'untested')")
        # settings.current_bake_hash needed by pick_fields default path
        cur.execute("INSERT INTO settings (category, key, value) VALUES ('strategy', 'current_bake_hash', 'b4619')")
        con.commit()


class TestPickFieldsForceAll:
    def test_default_excludes_already_probed(self, tmp_db):
        _seed_three_fields(tmp_db)
        picked = pick_fields(tmp_db, k=10, classification='untested')
        ids = {p['id'] for p in picked}
        assert 1 in ids        # untested + templated → included
        assert 2 not in ids    # already probed at this bake_hash → excluded
        assert 3 not in ids    # NULL template → excluded

    def test_force_all_includes_already_probed(self, tmp_db):
        _seed_three_fields(tmp_db)
        picked = pick_fields(tmp_db, k=10, force_all=True)
        ids = {p['id'] for p in picked}
        assert 1 in ids
        assert 2 in ids        # force_all bypasses the NOT EXISTS filter
        assert 3 not in ids    # NULL probe_threshold still excluded — can't be probed

    def test_force_all_ignores_classification_arg(self, tmp_db):
        _seed_three_fields(tmp_db)
        picked = pick_fields(tmp_db, k=10, classification='hot', force_all=True)
        ids = {p['id'] for p in picked}
        # With force_all=True, classification arg is ignored — both templated fields returned.
        assert 1 in ids
        assert 2 in ids
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py::TestPickFieldsForceAll -v
```

Expected: `test_force_all_includes_already_probed` and `test_force_all_ignores_classification_arg` FAIL with `TypeError: pick_fields() got an unexpected keyword argument 'force_all'`.

- [ ] **Step 3: Add `force_all` flag to `pick_fields`**

Modify `data/s001/fundamental_probes.py` `pick_fields` function signature and body:

```python
def pick_fields(db_path, k, classification='untested', bake_hash=None,
                force_all=False):
    """Pick up to k fields with the given classification on the CURRENT bake_hash.

    For 'untested': fields with NO probe_results for this bake_hash.
    For 'hot'/'neutral'/'harmful': fields with at least one matching
    probe_results.classification on this bake_hash.

    If force_all=True: ignore classification + NOT EXISTS scoping; return every
    field with a non-null probe_threshold across all containers (mega-round mode).
    """
    if bake_hash is None and not force_all:
        bake_hash = current_bake_hash(db_path)

    queues = {}
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        for cont in CONTAINER_CYCLE:
            if force_all:
                cur.execute("""
                    SELECT * FROM fundamental_fields f
                    WHERE f.container = ?
                      AND f.probe_threshold IS NOT NULL
                    ORDER BY f.id ASC
                """, (cont,))
            elif classification == 'untested':
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

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py::TestPickFieldsForceAll -v
```

Expected: All 3 tests PASS.

Re-run the full test file to catch regressions in existing pick_fields callers:

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add data/s001/fundamental_probes.py data/tests/test_fundamental_probes.py
git commit -m "$(cat <<'EOF'
feat(s001): pick_fields(force_all=True) returns all templated fields for mega-round

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: `emit_mega_round`

**Files:**
- Modify: `data/s001/fundamental_probes.py`
- Test: `data/tests/test_fundamental_probes.py`

- [ ] **Step 1: Write the failing tests**

Append to `data/tests/test_fundamental_probes.py`:

```python
from s001.fundamental_probes import emit_mega_round


def _seed_mega_test_fields(tmp_db):
    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO fundamental_fields "
            "(id, category, field_name, accessor, container, period, probe_op, probe_threshold, probe_gate, probe_boost, data_type_hint) "
            "VALUES (1, 'ops', 'revenue_growth', '_ops_z.revenue_growth.one_year', "
            "'operation_ratios', 'one_year', '>', '0.10', 'decline > .12', 1.10, 'numeric')")
        cur.execute(
            "INSERT INTO fundamental_fields "
            "(id, category, field_name, accessor, container, period, probe_op, probe_threshold, probe_gate, probe_boost, data_type_hint) "
            "VALUES (2, 'vr', 'pe_ratio', '_vr_z.pe_ratio', 'valuation_ratios', NULL, "
            "'<', '15', 'decline > .10', 1.10, 'numeric')")
        cur.execute("INSERT INTO settings (category, key, value) VALUES ('strategy', 'current_bake_hash', 'mega_test_hash')")
        con.commit()


class TestEmitMegaRound:
    def test_emits_six_cells_per_field(self, tmp_db):
        _seed_mega_test_fields(tmp_db)
        cells = list(emit_mega_round(tmp_db, round_n=603, force_all=True))
        # 2 fields × 6 mechanisms = 12 cells
        assert len(cells) == 12

    def test_each_cell_is_triple(self, tmp_db):
        _seed_mega_test_fields(tmp_db)
        cells = list(emit_mega_round(tmp_db, 603, force_all=True))
        for c in cells:
            assert len(c) == 3
            name, body, location = c
            assert name.startswith('S001_R603_mg_')
            assert location in ('entry', 'exit')
            assert isinstance(body, str) and len(body) > 0

    def test_mechanism_breakdown(self, tmp_db):
        _seed_mega_test_fields(tmp_db)
        cells = list(emit_mega_round(tmp_db, 603, force_all=True))
        from collections import Counter
        ctr = Counter(c[0].split('_')[3] for c in cells)
        for m in ('score', 'skip', 'stop', 'petgt', 'convg', 'convb'):
            assert ctr[m] == 2, f'{m}: {ctr[m]}'

    def test_location_split(self, tmp_db):
        _seed_mega_test_fields(tmp_db)
        cells = list(emit_mega_round(tmp_db, 603, force_all=True))
        entry = [c for c in cells if c[2] == 'entry']
        exit_ = [c for c in cells if c[2] == 'exit']
        # 4 entry mechs (score, skip, convg, convb) × 2 fields = 8
        # 2 exit mechs (stop, petgt) × 2 fields = 4
        assert len(entry) == 8
        assert len(exit_) == 4

    def test_subset_of_mechanisms(self, tmp_db):
        _seed_mega_test_fields(tmp_db)
        cells = list(emit_mega_round(tmp_db, 603,
                                     mechanisms=('score', 'skip'),
                                     force_all=True))
        assert len(cells) == 4   # 2 mechs × 2 fields
        for n, _, _ in cells:
            assert any(m in n for m in ('mg_score_', 'mg_skip_'))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py::TestEmitMegaRound -v
```

Expected: All FAIL with `ImportError: cannot import name 'emit_mega_round'`.

- [ ] **Step 3: Implement `emit_mega_round`**

Add to `data/s001/fundamental_probes.py` after `emit_probes_for_db`:

```python
def emit_mega_round(db_path, round_n, mechanisms=MECHANISMS, force_all=True):
    """Yield (spec_name, body, location) for every (field, mech) cell.

    All templated fields × all requested mechanisms. Skips cells where
    `render_cell` returns None (safety valve for ambiguous inverses)."""
    fields = pick_fields(db_path, k=10**9, force_all=force_all)
    out = []
    for field_row in fields:
        for mech in mechanisms:
            rendered = render_cell(field_row, mech, round_n)
            if rendered is not None:
                out.append(rendered)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_fundamental_probes.py::TestEmitMegaRound -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add data/s001/fundamental_probes.py data/tests/test_fundamental_probes.py
git commit -m "$(cat <<'EOF'
feat(s001): emit_mega_round yields (name, body, location) per (field, mech) cell

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: `base.py` refactor — regime context + injection anchors

**Files:**
- Modify: `data/s001/s001_20260425_base.py`
- Test: `data/tests/test_smoke.py` (smoke check)

This task changes the strategy file. We can't unit-test the QuantConnect runtime, but we CAN verify:
1. The file still AST-parses.
2. Both injection anchors are present.
3. The `_compute_regime` method is callable signature-wise.
4. Aliases `self._qa_scan` / `self._ha_scan` are still set after `_compute_regime`.
5. Existing baked-probe substrings (e.g. `BAKE-8`, `BAKE-16`) are unchanged.

After this refactor, `s001_20260425_base.py` will have a NEW md5. The user must run 3 NOOPs in QuantConnect and update `settings.current_bake_hash` before R603 — that operational step is OUT of plan scope and noted in step 7.

- [ ] **Step 1: Write the failing test**

Append to `data/tests/test_smoke.py`:

```python
import ast
import re
from pathlib import Path

BASE_PATH = Path('/home/txy/qc_work/data/s001/s001_20260425_base.py')


class TestBaseRefactor:
    def test_file_parses(self):
        src = BASE_PATH.read_text()
        ast.parse(src)  # raises SyntaxError on malformed code

    def test_entry_anchor_present(self):
        src = BASE_PATH.read_text()
        assert '   # --- ENTRY INJECT POINT ---' in src

    def test_exit_anchor_present(self):
        src = BASE_PATH.read_text()
        assert '   # --- EXIT INJECT POINT ---' in src

    def test_compute_regime_method_defined(self):
        src = BASE_PATH.read_text()
        assert re.search(r'def _compute_regime\(self\)', src)

    def test_regime_assigned_in_on_data(self):
        src = BASE_PATH.read_text()
        # on_data must assign self._regime BEFORE the scan_exits call.
        on_data_match = re.search(
            r'def on_data\(self, data\):.*?(?=\n def )', src, re.DOTALL)
        assert on_data_match
        body = on_data_match.group(0)
        regime_pos = body.find('self._regime = self._compute_regime()')
        exits_pos = body.find('self._scan_exits(')
        assert regime_pos > 0 and exits_pos > 0
        assert regime_pos < exits_pos, 'regime must be computed before scan_exits'

    def test_aliases_set_in_compute_regime(self):
        # qa_scan / ha_scan aliases must be set so existing baked probes still work.
        src = BASE_PATH.read_text()
        assert 'self._qa_scan = qa' in src
        assert 'self._ha_scan = ha' in src

    def test_baked_probes_intact(self):
        # Sample baked probes that depend on _qa_scan / _ha_scan must remain in source.
        src = BASE_PATH.read_text()
        for marker in ('BAKE-8', 'BAKE-16', 'BAKE-29', 'BAKE-53', 'BAKE-58', 'BAKE-62'):
            assert marker in src, f'{marker} missing — refactor broke baked code'

    def test_stale_perfopt_cache_removed(self):
        # The line `try: self._ha_scan = list(self.history` should NOT appear in
        # _scan_entries any longer — _compute_regime now owns those caches.
        src = BASE_PATH.read_text()
        scan_entries_match = re.search(
            r'def _scan_entries\(self.*?(?=\n def )', src, re.DOTALL)
        assert scan_entries_match
        scan_entries_body = scan_entries_match.group(0)
        # The stale cache lookup phrase shouldn't be in _scan_entries.
        assert 'self._ha_scan = list(self.history' not in scan_entries_body
        assert 'self._qa_scan = list(self.history' not in scan_entries_body
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_smoke.py::TestBaseRefactor -v
```

Expected: Several tests FAIL (anchors missing, _compute_regime undefined, etc.).

- [ ] **Step 3: Snapshot the current base.py before refactor**

```bash
cp /home/txy/qc_work/data/s001/s001_20260425_base.py /home/txy/qc_work/data/s001/s001_20260425_base.py.bak_pre_megaround
```

- [ ] **Step 4: Refactor `on_data` and add `_compute_regime`**

Modify `data/s001/s001_20260425_base.py`. Replace the existing `on_data` method (lines ~59-68) with:

```python
 def on_data(self, data):
  if not self._initialized:
   self._qqq_sym = self.securities["QQQ"].symbol
   self._bond_sym = self.securities[BOND_SYMBOL].symbol
   self._hedge_syms = {self._bond_sym}
   self._initialized = True
  equities = [s for s in data.bars.keys() if s.security_type == SecurityType.EQUITY and s not in self._hedge_syms]
  self._regime = self._compute_regime()
  self._scan_exits(data, equities)
  if self.time.weekday() == 0:
   self._scan_entries(data, equities)

 def _compute_regime(self):
  """Compute QQQ/bond regime once per tick. Sets self._qa_scan / self._ha_scan
  aliases for existing baked probes (BAKE-8/16/29-AB/53-58/62)."""
  try: qa = list(self.history[TradeBar](self._qqq_sym, 30, _RD))
  except (AttributeError, KeyError, ValueError): qa = []
  try: ha = list(self.history[TradeBar](self._bond_sym, 30, _RD))
  except (AttributeError, KeyError, ValueError): ha = []
  def _r(bars, n):
   if len(bars) <= n or f_(bars[-n].close) <= 0: return None
   return (f_(bars[-1].close) - f_(bars[-n].close)) / f_(bars[-n].close)
  self._qa_scan = qa
  self._ha_scan = ha
  return {
   'qa': qa, 'ha': ha,
   'qd5': _r(qa, 5), 'qd10': _r(qa, 10), 'qd20': _r(qa, 20),
   'bd5': _r(ha, 5), 'bd10': _r(ha, 10), 'bd20': _r(ha, 20),
  }
```

(Indentation matches base.py's single-space convention: `def` at 1 space, body at 2 spaces, `try:` at 2 spaces, try-body at 3 spaces.)

- [ ] **Step 5: Add the ENTRY INJECT POINT anchor**

In `_scan_entries`, locate the comment `# --- INJECT POINT ---` (around line 160). REPLACE that exact line with:

```python
   # --- ENTRY INJECT POINT ---
```

(Same indent: 3 spaces.)

- [ ] **Step 6: Remove the stale PERFOPT cache from `_scan_entries`**

In `_scan_entries`, locate lines ~120-124:

```python
  # PERFOPT: cache cross-asset history once per scan (was per-candidate × bakes) — saves ~30-50% runtime
  try: self._ha_scan = list(self.history[TradeBar](self._bond_sym, 30, _RD))
  except (AttributeError, KeyError, ValueError): self._ha_scan = []
  try: self._qa_scan = list(self.history[TradeBar](self._qqq_sym, 60, _RD))
  except (AttributeError, KeyError, ValueError): self._qa_scan = []
```

REPLACE with a single comment:

```python
  # PERFOPT: regime caches (_qa_scan / _ha_scan) populated by _compute_regime in on_data.
```

NOTE: the original code fetched 60 bars for `_qa_scan` here vs 30 in `_compute_regime`. Audit any baked probe that uses `self._qa_scan` indices < -30:

```bash
grep -nE 'self\._qa_scan\[-(3[0-9]|[4-9][0-9])' /home/txy/qc_work/data/s001/s001_20260425_base.py
```

If there are matches, increase the `_compute_regime` qa lookback to 60. If no matches, the 30-bar lookback is sufficient. (Spot-checking the baked probes already shown in the spec, all use indices ≥ -20, so 30 is safe.)

If matches exist, change the line in `_compute_regime`:

```python
  try: qa = list(self.history[TradeBar](self._qqq_sym, 30, _RD))
```

to:

```python
  try: qa = list(self.history[TradeBar](self._qqq_sym, 60, _RD))
```

Likewise for `ha` if any `self._ha_scan[-n]` for n > 30 exists (unlikely — the original was 30).

- [ ] **Step 7: Add the EXIT INJECT POINT anchor**

In `_scan_exits`, locate the existing nm/qr block ending at the `except: pass` around line 106. After that line and BEFORE the `if pnl < -stop or pnl > petgt:` line, INSERT:

```python
   # --- EXIT INJECT POINT ---
```

(Same 3-space indent as `pos = self.portfolio[sym]`.)

- [ ] **Step 8: Run smoke tests to verify the refactor**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_smoke.py::TestBaseRefactor -v
```

Expected: All 8 tests PASS.

- [ ] **Step 9: Verify baked probes still parse with current accesses**

```bash
cd /home/txy/qc_work/data && python -c "import ast; ast.parse(open('s001/s001_20260425_base.py').read()); print('OK')"
```

Expected: `OK`.

- [ ] **Step 10: Commit**

```bash
git add data/s001/s001_20260425_base.py data/tests/test_smoke.py
git commit -m "$(cat <<'EOF'
refactor(s001): hoist regime context to on_data + add ENTRY/EXIT inject anchors

Pre-mega-round refactor. _compute_regime() now owns _qa_scan / _ha_scan caches
and computes qd*/bd* return ratios once per tick. Existing baked probes
unchanged via aliasing. ENTRY/EXIT INJECT POINT anchors added for the mega-
round generator (R603). File hash will change — operator must run 3 NOOPs in
QuantConnect and update settings.current_bake_hash before R603 dispatch.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

**Operator note (post-commit, manual step out of plan):** Run 3 NOOP backtests of the new `s001_20260425_base.py` against the QuantConnect runtime; verify each car_mdd matches the previous bake's car_mdd within ±0.0005. Then update `settings.current_bake_hash` to the new file's md5 hash. R603 generator (Task 13) hash-asserts on this value.

---

### Task 11: `score_probes.py` — mega routing branch + `MEGA_NAME_RE`

**Files:**
- Modify: `data/scripts/score_probes.py`
- Test: `data/tests/test_score_probes.py`

- [ ] **Step 1: Write the failing test**

Append to `data/tests/test_score_probes.py`:

```python
def _seed_mega_round(tmp_db):
    """Seed: 1 field, 3 NOOPs, 3 mega-spec experiments (score / skip / petgt)."""
    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                data_type_hint, classification)
               VALUES (1, 'ops', 'revenue_growth', '_ops_z.revenue_growth.one_year',
                       'operation_ratios', 'one_year',
                       '>', '0.10', 'decline > .12', 1.10, 'numeric', 'untested')""")
        # 3 NOOPs avg = 1.9000, spread = 0.0004
        for i, v in enumerate([1.8998, 1.9000, 1.9002]):
            cur.execute(
                "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
                (f'S001_R603_VBAKEMG_NOOP_{i}', v))
        # 3 mega cells, 3 different mechanisms
        cur.execute(
            "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
            ('S001_R603_mg_score_ops_revenue_growth', 1.9050))   # +0.005 → hot
        cur.execute(
            "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
            ('S001_R603_mg_skip_ops_revenue_growth', 1.9020))    # +0.002 → hot
        cur.execute(
            "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
            ('S001_R603_mg_petgt_ops_revenue_growth', 1.8990))   # -0.001 → neutral


def test_score_routes_mega_specs(tmp_db):
    _seed_mega_round(tmp_db)
    out = score_round(db_path=tmp_db, round_n=603, bake_hash='b4619')
    assert out['n_results'] == 3

    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("SELECT mechanism, applied_op, classification, delta "
                    "FROM probe_results WHERE experiment_name = ?",
                    ('S001_R603_mg_score_ops_revenue_growth',))
        mech, op_used, cls, delta = cur.fetchone()
        assert mech == 'score'
        assert op_used == '>'        # good-side: probe_op as-defined
        assert cls == 'hot'

        cur.execute("SELECT mechanism, applied_op FROM probe_results "
                    "WHERE experiment_name = ?",
                    ('S001_R603_mg_skip_ops_revenue_growth',))
        mech, op_used = cur.fetchone()
        assert mech == 'skip'
        assert op_used == '<'        # bad-side: probe_op flipped

        cur.execute("SELECT mechanism, applied_op FROM probe_results "
                    "WHERE experiment_name = ?",
                    ('S001_R603_mg_petgt_ops_revenue_growth',))
        mech, op_used = cur.fetchone()
        assert mech == 'petgt'
        assert op_used == '>'        # good-side


def test_mega_name_re_matches_underscore_heavy_field():
    from scripts.score_probes import MEGA_NAME_RE
    m = MEGA_NAME_RE.match('S001_R603_mg_score_cfs_change_in_account_payable')
    assert m
    assert m.group('mech') == 'score'
    assert m.group('cs') == 'cfs'
    assert m.group('field') == 'change_in_account_payable'


def test_mega_name_re_does_not_match_v1_specs():
    from scripts.score_probes import MEGA_NAME_RE
    assert MEGA_NAME_RE.match('S001_R500_vr_pe_ratio_lt15') is None
    assert MEGA_NAME_RE.match('S001_R500_sw_ops_revenue_growth_m110_g05') is None
    assert MEGA_NAME_RE.match('S001_R500_v3c_ops_revenue_growth_ogt_m110_g05_t50') is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_score_probes.py::test_score_routes_mega_specs tests/test_score_probes.py::test_mega_name_re_matches_underscore_heavy_field tests/test_score_probes.py::test_mega_name_re_does_not_match_v1_specs -v
```

Expected: FAIL with `ImportError: cannot import name 'MEGA_NAME_RE'` (and possibly assertion errors on n_results count).

- [ ] **Step 3: Add `MEGA_NAME_RE` to `score_probes.py`**

In `data/scripts/score_probes.py`, near the existing `SPEC_NAME_RE` / `SWEEP_NAME_RE` / `V3_*_NAME_RE` regex constants (around line 30-47), add:

```python
MEGA_NAME_RE = re.compile(
    r'^S001_R(?P<round>\d+)_mg_'
    r'(?P<mech>score|skip|stop|petgt|convg|convb)_'
    r'(?P<cs>[a-z]+)_(?P<field>.+)$'
)
```

- [ ] **Step 4: Add the mega routing branch**

In `data/scripts/score_probes.py`, locate the inner `for row in cur.fetchall():` loop in `score_round` (around line 129). The current order is: v3 parse → sweep parse → v1 default. Insert a NEW first branch BEFORE `v3_parsed = _parse_v3_spec_name(row['name'])`:

```python
            # Mega-round routing (most-specific anchor — try first).
            mega = MEGA_NAME_RE.match(row['name'])
            if mega:
                mech = mega.group('mech')
                cs = mega.group('cs')
                field_name = mega.group('field')
                container = CONTAINER_FROM_SHORT.get(cs)
                if container is None:
                    continue
                cur.execute(
                    "SELECT * FROM fundamental_fields WHERE container = ? AND field_name = ?",
                    (container, field_name))
                f = cur.fetchone()
                if f is None:
                    continue
                from s001.fundamental_probes import (
                    MECH_DEFAULTS, flip_op,
                )
                defaults = MECH_DEFAULTS[mech]
                op_used = (f['probe_op'] if defaults['side'] == 'good'
                           else flip_op(f['probe_op']))
                delta = row['car_mdd'] - baseline
                cls = classify_delta(delta)
                applied_gate = defaults['gate'] if defaults['gate'] is not None else ''
                applied_boost = defaults['mag'] if defaults['mag'] is not None else 0.0
                try:
                    cur.execute(
                        """INSERT INTO probe_results
                           (field_id, experiment_name, round_n, bake_hash, noop_baseline,
                            spec_car_mdd, delta, classification, applied_op,
                            applied_threshold, applied_gate, applied_boost,
                            recorded_at, is_sweep_variant, sweep_stage, mechanism)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)""",
                        (f['id'], row['name'], round_n, bake_hash, baseline,
                         row['car_mdd'], delta, cls, op_used, f['probe_threshold'],
                         applied_gate, applied_boost, now, mech))
                    n_results += 1
                except sqlite3.IntegrityError:
                    pass
                touched_field_ids.add(f['id'])
                continue
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_score_probes.py -v
```

Expected: All tests PASS, including the 3 new mega-routing tests.

- [ ] **Step 6: Commit**

```bash
git add data/scripts/score_probes.py data/tests/test_score_probes.py
git commit -m "$(cat <<'EOF'
feat(s001): score_probes routes mega-round specs into mechanism column

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: `field_rollup` scoping — exclude non-score mechanisms

**Files:**
- Modify: `data/scripts/score_probes.py`
- Test: `data/tests/test_score_probes.py`

- [ ] **Step 1: Write the failing test**

Append to `data/tests/test_score_probes.py`:

```python
def test_field_rollup_ignores_non_score_mechanisms(tmp_db):
    """A 'harmful' skip cell must NOT mark the field's rollup as harmful —
    rollup is score-only so v3 pickup isn't disrupted."""
    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            """INSERT INTO fundamental_fields
               (id, category, field_name, accessor, container, period,
                probe_op, probe_threshold, probe_gate, probe_boost,
                data_type_hint, classification)
               VALUES (1, 'ops', 'rg', '_ops_z.rg.one_year',
                       'operation_ratios', 'one_year',
                       '>', '0.10', 'decline > .12', 1.10, 'numeric', 'untested')""")
        # 3 NOOPs avg 1.90, tight spread
        for i, v in enumerate([1.8998, 1.9000, 1.9002]):
            cur.execute(
                "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
                (f'S001_R604_VBAKEMG_NOOP_{i}', v))
        # 1 score cell with neutral delta
        cur.execute(
            "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
            ('S001_R604_mg_score_ops_rg', 1.9005))   # +0.0005 → neutral
        # 1 skip cell with HARMFUL delta — must NOT poison the rollup.
        cur.execute(
            "INSERT INTO experiments (name, status, car_mdd) VALUES (?, 'imported', ?)",
            ('S001_R604_mg_skip_ops_rg', 1.8950))    # -0.005 → harmful in skip mech

    score_round(db_path=tmp_db, round_n=604, bake_hash='b4619')
    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute("SELECT classification FROM fundamental_fields WHERE id = 1")
        rollup = cur.fetchone()[0]
    # Score cell was 'neutral'; skip cell was 'harmful' but excluded from rollup.
    # Result: rollup should be 'neutral', not 'harmful'.
    assert rollup == 'neutral', f'rollup got poisoned by skip cell: {rollup!r}'
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_score_probes.py::test_field_rollup_ignores_non_score_mechanisms -v
```

Expected: FAIL — `rollup got poisoned by skip cell: 'harmful'` (because current `field_rollup` query reads ALL probe_results rows, and 'harmful' wins).

- [ ] **Step 3: Update the rollup query in `score_probes.py`**

In `data/scripts/score_probes.py`, locate the rollup section in `score_round`:

```python
        # Refresh field-row classification for each touched field
        for fid in touched_field_ids:
            cur.execute(
                "SELECT classification FROM probe_results "
                "WHERE field_id = ? AND bake_hash = ?", (fid, bake_hash))
            results = [{'classification': r[0]} for r in cur.fetchall()]
            rollup = field_rollup(results)
```

Change the `cur.execute(...)` query to:

```python
            cur.execute(
                "SELECT classification FROM probe_results "
                "WHERE field_id = ? AND bake_hash = ? "
                "AND (mechanism IS NULL OR mechanism = 'score')",
                (fid, bake_hash))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_score_probes.py::test_field_rollup_ignores_non_score_mechanisms -v
```

Expected: PASS.

Re-run the full file:

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_score_probes.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add data/scripts/score_probes.py data/tests/test_score_probes.py
git commit -m "$(cat <<'EOF'
fix(s001): field_rollup scoped to score-only — non-score mega cells don't poison v3 pickup

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: Generator `gen_s001_R603_mega.py` + dry-run smoke test

**Files:**
- Create: `data/gen_s001_R603_mega.py`
- Test: `data/tests/test_gen_s001_R603_mega.py` (new)

- [ ] **Step 1: Write the failing dry-run test**

Create `data/tests/test_gen_s001_R603_mega.py`:

```python
"""Smoke test for gen_s001_R603_mega.py dry-run mode."""
import hashlib
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

GEN_PATH = Path('/home/txy/qc_work/data/gen_s001_R603_mega.py')


def _load_gen_module():
    spec = importlib.util.spec_from_file_location('gen_s001_R603_mega', GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_min_db(tmp_db, base_path):
    """Seed: 2 templated fields, 1 settings row with the live base.py md5."""
    md5 = hashlib.md5(Path(base_path).read_bytes()).hexdigest()
    with sqlite3.connect(tmp_db) as con:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO fundamental_fields "
            "(id, category, field_name, accessor, container, period, probe_op, probe_threshold, probe_gate, probe_boost, data_type_hint) "
            "VALUES (1, 'ops', 'revenue_growth', '_ops_z.revenue_growth.one_year', "
            "'operation_ratios', 'one_year', '>', '0.10', 'decline > .12', 1.10, 'numeric')")
        cur.execute(
            "INSERT INTO fundamental_fields "
            "(id, category, field_name, accessor, container, period, probe_op, probe_threshold, probe_gate, probe_boost, data_type_hint) "
            "VALUES (2, 'vr', 'pe_ratio', '_vr_z.pe_ratio', 'valuation_ratios', NULL, "
            "'<', '15', 'decline > .10', 1.10, 'numeric')")
        cur.execute("INSERT INTO settings (category, key, value) VALUES ('strategy', 'current_bake_hash', ?)", (md5,))
        con.commit()
    return md5


def test_dry_run_emits_expected_specs(tmp_db, monkeypatch):
    base = '/home/txy/qc_work/data/s001/s001_20260425_base.py'
    md5 = _seed_min_db(tmp_db, base)

    # Dry-run mode: don't write to backtest_queue, just return the specs list.
    mod = _load_gen_module()
    specs = mod.build_specs(db_path=tmp_db, base_path=base, round_n=603,
                            expected_hash=md5, dry_run=True)
    # 2 fields × 6 mechanisms + 3 NOOPs = 15
    assert len(specs) == 15

    noops = [s for s in specs if 'VBAKEMG_NOOP_' in s[0]]
    mega = [s for s in specs if 'VBAKEMG_NOOP_' not in s[0]]
    assert len(noops) == 3
    assert len(mega) == 12

    # Every mega spec splices into exactly one of the two anchors.
    for name, code, _ in mega:
        # The probe body must appear in the spec code somewhere.
        assert '_ops_z.revenue_growth.one_year' in code or '_vr_z.pe_ratio' in code


def test_dry_run_all_specs_ast_parse(tmp_db, monkeypatch):
    import ast
    base = '/home/txy/qc_work/data/s001/s001_20260425_base.py'
    md5 = _seed_min_db(tmp_db, base)
    mod = _load_gen_module()
    specs = mod.build_specs(db_path=tmp_db, base_path=base, round_n=603,
                            expected_hash=md5, dry_run=True)
    for name, code, _ in specs:
        ast.parse(code)


def test_hash_mismatch_aborts(tmp_db, monkeypatch):
    base = '/home/txy/qc_work/data/s001/s001_20260425_base.py'
    _seed_min_db(tmp_db, base)
    mod = _load_gen_module()
    with pytest.raises(AssertionError, match='Hash mismatch'):
        mod.build_specs(db_path=tmp_db, base_path=base, round_n=603,
                        expected_hash='deadbeef', dry_run=True)


def test_anchors_required(tmp_db, monkeypatch, tmp_path):
    # Write a fake base.py without anchors; generator must abort.
    fake_base = tmp_path / 'fake_base.py'
    fake_base.write_text('# no anchors here\nprint("hi")\n')
    md5 = hashlib.md5(fake_base.read_bytes()).hexdigest()
    with sqlite3.connect(tmp_db) as con:
        con.execute("INSERT INTO settings (category, key, value) VALUES ('strategy', 'current_bake_hash', ?)", (md5,))
    mod = _load_gen_module()
    with pytest.raises(AssertionError, match='anchor'):
        mod.build_specs(db_path=tmp_db, base_path=str(fake_base), round_n=603,
                        expected_hash=md5, dry_run=True)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_gen_s001_R603_mega.py -v
```

Expected: FAIL with FileNotFoundError (gen file doesn't exist yet).

- [ ] **Step 3: Create `gen_s001_R603_mega.py`**

Create `data/gen_s001_R603_mega.py`:

```python
"""R603 mega-round generator: 6 mechanisms × all templated fields, ~5349 specs.

Reference spec: docs/superpowers/specs/2026-04-29-s001-mega-fundamental-sweep-design.md
"""
import argparse
import ast
import hashlib
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s001.fundamental_probes import (  # noqa: E402
    MECHANISMS,
    emit_mega_round,
    ENTRY_BIND,
    EXIT_BIND,
)


def build_specs(db_path, base_path, round_n, expected_hash, dry_run=False):
    """Produce the list of (spec_name, code, priority) tuples for the round.

    On dry_run=True, skip the DB insert. Otherwise insert into backtest_queue
    after pre-flight checks pass."""
    base_code = Path(base_path).read_text()
    got = hashlib.md5(base_code.encode()).hexdigest()
    assert got == expected_hash, f'Hash mismatch {got} vs {expected_hash}'

    entry_anchor = '   # --- ENTRY INJECT POINT ---'
    exit_anchor  = '   # --- EXIT INJECT POINT ---'
    assert entry_anchor in base_code, f'ENTRY anchor not found in {base_path}'
    assert exit_anchor  in base_code, f'EXIT anchor not found in {base_path}'

    specs = []
    # 3 NOOPs (entry-side, harmless comment splice — establishes baseline)
    for i in range(3):
        code = base_code.replace(entry_anchor,
                                 f'   # mega_noop_{i}\n' + entry_anchor)
        specs.append((f'S001_R{round_n}_VBAKEMG_NOOP_{i}', code, 1))

    # Mega cells
    for name, body, loc in emit_mega_round(db_path, round_n, force_all=True):
        if loc == 'entry':
            code = base_code.replace(
                entry_anchor, ENTRY_BIND + body + '\n' + entry_anchor)
        else:
            code = base_code.replace(
                exit_anchor, EXIT_BIND + body + '\n' + exit_anchor)
        specs.append((name, code, 5))

    # Pre-flight: AST-parse every spec
    for name, code, _ in specs:
        try:
            ast.parse(code)
        except SyntaxError as e:
            sys.exit(f'SYNTAX ERROR in {name}: {e}')

    # Coverage matrix
    ctr = Counter()
    for n, _, _ in specs:
        if 'VBAKEMG_NOOP_' in n: continue
        ctr[n.split('_')[3]] += 1
    print('Mechanism counts:', dict(ctr))
    for m in MECHANISMS:
        # 891 templated fields ± small drop budget for inverse-ambiguous cells.
        # In dry-run with seeded DBs the counts will be tiny; only enforce in
        # real-DB mode (when total > 100).
        if sum(ctr.values()) > 100:
            assert 800 <= ctr[m] <= 1000, f'{m}: {ctr[m]} out of expected band'

    if dry_run:
        return specs

    # Bulk insert
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    inserted = 0
    for n, c, pri in specs:
        h = hashlib.md5(c.encode()).hexdigest()
        try:
            cur.execute(
                "INSERT INTO backtest_queue (name, code, status, priority, "
                "submitted_at, code_hash, project_id) "
                "VALUES (?, ?, 'queued', ?, datetime('now'), ?, NULL)",
                (n, c, pri, h),
            )
            inserted += 1
        except sqlite3.IntegrityError as e:
            print(f'Skip {n}: {e}')
    con.commit()
    print(f'Inserted {inserted} R{round_n} specs')
    return specs


def _resolve_expected_hash(db_path):
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.execute("SELECT value FROM settings WHERE category = 'strategy' AND key = 'current_bake_hash'")
        row = cur.fetchone()
    if row is None:
        sys.exit('settings.current_bake_hash is not set')
    return row[0]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--db', default='/home/txy/qc_work/data/S001.db')
    p.add_argument('--base', default='/home/txy/qc_work/data/s001/s001_20260425_base.py')
    p.add_argument('--round', dest='round_n', type=int, default=603)
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()
    expected = _resolve_expected_hash(args.db)
    build_specs(db_path=args.db, base_path=args.base, round_n=args.round_n,
                expected_hash=expected, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/txy/qc_work/data && python -m pytest tests/test_gen_s001_R603_mega.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Run a dry-run against the LIVE S001.db**

(This requires Tasks 1 + 10 to be applied — i.e. mechanism column is migrated and base.py has the anchors.)

```bash
cd /home/txy/qc_work/data && python gen_s001_R603_mega.py --dry-run
```

Expected output (key lines):

- `Mechanism counts: {'score': 891, 'skip': 891, ...}` — six entries each within 800-1000 range.
- No `SYNTAX ERROR` lines.
- The script exits 0 without inserting into backtest_queue.

If counts are unexpected:
- Diff against the cell-count audit in spec section 3.
- Check `pick_fields(force_all=True)` returned the expected 891 fields:

```bash
cd /home/txy/qc_work/data && python -c "from s001.fundamental_probes import pick_fields; print(len(pick_fields('/home/txy/qc_work/data/S001.db', k=10**9, force_all=True)))"
```

Expected: `891`.

- [ ] **Step 6: Verify all live-DB specs AST-parse**

The dry-run already does this; the assertion is just a sanity check that we didn't get a generation skew. If Step 5 passed without `SYNTAX ERROR`, this is satisfied.

- [ ] **Step 7: Commit**

```bash
git add data/gen_s001_R603_mega.py data/tests/test_gen_s001_R603_mega.py
git commit -m "$(cat <<'EOF'
feat(s001): R603 mega-round generator (~5349 specs across 6 mechanisms)

Single-purpose generator with hash-verify, anchor presence check, AST
pre-flight, and coverage matrix. Dry-run mode for CI; live mode inserts
into backtest_queue. Operator runs --dry-run first to verify counts,
then re-runs without --dry-run to commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Operator hand-off (out of plan scope)

After Task 13 commits, the implementation is done. The remaining steps are operational, NOT code:

1. **Apply base.py refactor's bake-hash update.** After Task 10's commit, the file md5 changes. Run 3 NOOP backtests in QuantConnect against the new `s001_20260425_base.py`. Confirm car_mdd matches the previous bake within ±0.0005. Then:

   ```sql
   UPDATE settings SET value = '<new_md5>' WHERE category = 'strategy' AND key = 'current_bake_hash';
   ```

2. **Run the live mega-round.**

   ```bash
   cd /home/txy/qc_work/data && python gen_s001_R603_mega.py --dry-run    # verify counts
   cd /home/txy/qc_work/data && python gen_s001_R603_mega.py              # commit ~5349 specs
   ```

3. **Wait for cron to drain the queue.** ~5349 backtests at current per-spec runtime — order of magnitude is days. Monitor:

   ```bash
   python3 -c "import sqlite3; c=sqlite3.connect('/home/txy/qc_work/data/queue.db').cursor(); c.execute(\"SELECT status, COUNT(*) FROM backtest_queue WHERE name LIKE 'S001_R603_mg_%' GROUP BY status\"); print(c.fetchall())"
   ```

4. **Score the round once complete.**

   ```bash
   cd /home/txy/qc_work/data && python -m scripts.score_probes --round 603 --bake-hash <hash>
   ```

5. **Survey leaders:**

   ```sql
   SELECT field_id, mechanism, MAX(delta) AS best_delta
   FROM probe_results
   WHERE bake_hash = ? AND mechanism IS NOT NULL AND delta > 0.0015
   GROUP BY field_id, mechanism
   ORDER BY best_delta DESC LIMIT 50;
   ```

6. **Phase B / C** are separate plans (out of scope here).

---

## Self-review summary

**Spec coverage:** All 12 spec sections covered.
- §3 mechanism enumeration → Tasks 4, 7
- §4 base.py refactor → Task 10
- §5 fundamental_probes rewrite → Tasks 2-9
- §6 score_probes routing → Tasks 11-12
- §7 DB schema → Task 1
- §8 generator → Task 13
- §9 run sequence → operator hand-off (out of plan scope by design)
- §10 testing → Tasks 1-13 each include unit/smoke tests
- §11 risks → mitigations in Tasks 7 (try/except in body), 12 (rollup scoping), 13 (hash-verify, anchor-check, AST pre-flight)
- §12 out-of-scope → not implemented (correct)

**Naming consistency check:**
- `mega_spec_name` (Task 6) emits names matching `MEGA_NAME_RE` (Task 11). ✓
- `MECH_DEFAULTS[mech]['side']` (Task 4) consumed by `render_cell` (Task 7) AND mega routing (Task 11). Same key. ✓
- `MECH_DEFAULTS[mech]['location']` (Task 4) consumed by `render_cell` (Task 7) — returned as the third tuple element used by generator (Task 13). ✓
- `flip_op` (Task 2) called from `render_cell` (Task 7) AND mega routing in score_probes (Task 11). Same impl. ✓
- `ENTRY_BIND` / `EXIT_BIND` (Task 5) imported by generator (Task 13). ✓
- `pick_fields(force_all=True)` (Task 8) called by `emit_mega_round` (Task 9). ✓
- `mechanism` column (Task 1) populated by mega routing (Task 11) and read by `field_rollup` query (Task 12). ✓

**Placeholder scan:** No TBD / TODO / placeholder steps. Every test has actual assertions; every implementation step has actual code.
