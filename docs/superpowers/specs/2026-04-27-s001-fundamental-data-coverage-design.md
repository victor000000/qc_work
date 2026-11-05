# S001 Fundamental Data: Full Coverage + Learning Loop

**Date:** 2026-04-27
**Author:** brainstorming session (cron-driven autonomous S001 round work)
**Scope:** Single implementation plan — replaceable per future bake/strategy.

---

## 1. Problem

The S001 strategy probes fundamental fields to discover scoring boosts that improve CAR/MDD. Today the workflow is:

- The DB tracks 92 fields in `fundamental_fields`; LEAN exposes ~900+ numeric fields plus ~17 categorical.
- Each round (~5-min cron) hand-codes 10–50 probes via `gen_s001_R{N}.py`.
- After 405 rounds, the 92-field DB is fully exhausted. No further untested fields exist.
- We don't systematically know **which** fundamentals helped/hurt CAR/MDD — only which were "tested somewhere."
- Categorical fields (sector codes, financial_health_grade, style_box) are not used at all.

The strategy's edge comes from richer fundamental discrimination, not finer numeric tuning of existing axes (per project memory rule). To continue making progress, we need (a) more fields to probe and (b) a feedback loop that tells us which probes are actually valuable.

## 2. Goals

1. **Catalogue** the full LEAN fundamental universe (~900 numeric + ~17 categorical) into `fundamental_fields`.
2. **Render** probe code from declarative DB rows instead of hand-typing per round.
3. **Classify** each probe outcome (hot / neutral / harmful) by comparing CAR/MDD to the round's NOOP baseline.
4. **Pick** the next round's probes from the classified DB — re-verify hot ones (3-rep rule), explore untested ones in container-cycle order.
5. **Augment, don't replace** the existing per-round generator workflow.

## 3. Non-goals

- Replacing the per-round generator with a full automation framework (sweeps and VERIFYs stay hand-written).
- Promoting hot probes into the baseline strategy automatically (always manual, gated by user review).
- Building cross-bake comparison tooling (each bake's results are scoped by `bake_hash`; trends across bakes are out of scope for v1).
- Multi-probe specs (each spec injects exactly one fundamental probe).
- Threshold-sweep automation per field (one default template per field; the user can edit templates manually).

## 4. Architecture

```
                ┌──────────────────────────────────────────────────────────┐
                │          s001/fundamental_probes.py  (library)           │
                │  catalogue_lean()   render_probe()   classify_results()  │
                │                     pick_fields()                        │
                └──────────────┬───────────────┬───────────────┬───────────┘
                               │               │               │
                  ┌────────────▼──┐    ┌───────▼─────┐  ┌──────▼────────┐
                  │ catalogue_    │    │ emit_       │  │ score_        │
                  │  universe.py  │    │  probes.py  │  │  probes.py    │
                  │  (one-time)   │    │ (per-round) │  │ (after-round) │
                  └───────┬───────┘    └──────┬──────┘  └──────┬────────┘
                          │                   │                │
                          ▼                   ▼                ▼
                 ┌──────────────────────────────────────────────────┐
                 │                     S001.db                      │
                 │  fundamental_fields (extended)                   │
                 │  probe_results (new)                             │
                 │  experiments (existing, unchanged)               │
                 └──────────────────────────────────────────────────┘
                          ▲
                          │ imports + appends specs
                          │
                  ┌───────┴────────────┐
                  │ gen_s001_R{N}.py   │
                  │ (per-round, hand)  │
                  └────────────────────┘
```

**Three stages**, each in its own thin script, sharing a pure-functional library:

1. **Catalogue** — one-time bootstrap. Reflects over `QuantConnect/Data/Fundamental/__init__.pyi`, populates `fundamental_fields`. Idempotent; re-runnable on LEAN updates.
2. **Emit** — per-round. Picks K untested + M hot fields; renders probe code; emits `(name, code)` tuples that `gen_s001_R{N}.py` appends to its specs list.
3. **Score** — after a round. Reads `experiments`, computes per-probe delta vs round-NOOP baseline, writes `probe_results`, refreshes field classifications.

**Per-round generator integration:**
```python
from s001.fundamental_probes import emit_probes
specs.extend(emit_probes(round_n=406, k_new=10, k_verify=5))
```

The generator still owns NOOP/VERIFY/sweep specs; the library only emits fundamental probes (~15 per round).

## 5. Schema changes

### 5.1 Extend `fundamental_fields`

```sql
ALTER TABLE fundamental_fields ADD COLUMN period TEXT;
  -- 'twelve_months' | 'one_year' | 'three_months' | NULL (direct float)
ALTER TABLE fundamental_fields ADD COLUMN container TEXT;
  -- 'balance_sheet' | 'cash_flow_statement' | 'income_statement'
  -- | 'operation_ratios' | 'valuation_ratios' | 'earning_ratios'
  -- | 'earning_reports' | 'asset_classification' | 'security_reference'
ALTER TABLE fundamental_fields ADD COLUMN probe_op TEXT;
  -- '>' | '<' | '>=' | '<=' | 'eq' | 'in'
ALTER TABLE fundamental_fields ADD COLUMN probe_threshold TEXT;
  -- Numeric: '15', '0.10', '-0.05'
  -- Categorical: JSON array '["A","B+"]' or '[205,206,207]'
ALTER TABLE fundamental_fields ADD COLUMN probe_gate TEXT;
  -- Python expr fragment: 'decline > .10' | NULL = always-on
ALTER TABLE fundamental_fields ADD COLUMN probe_boost REAL;
  -- 1.05–1.15 typical positive; 0.85–0.95 typical penalty
ALTER TABLE fundamental_fields ADD COLUMN classification TEXT DEFAULT 'untested';
  -- 'untested' | 'hot' | 'neutral' | 'harmful'
ALTER TABLE fundamental_fields ADD COLUMN last_classified_at TEXT;
  -- ISO timestamp of most recent classification update
ALTER TABLE fundamental_fields ADD COLUMN data_type_hint TEXT;
  -- 'numeric' | 'absolute_amount' | 'absolute_amount_signed'
  -- | 'signed_ratio' | 'categorical'
  -- drives auto-guards in renderer (see §6)
CREATE INDEX idx_ff_classification ON fundamental_fields(classification);
CREATE INDEX idx_ff_container ON fundamental_fields(container);
```

### 5.2 New table `probe_results`

```sql
CREATE TABLE probe_results (
  id INTEGER PRIMARY KEY,
  field_id INTEGER NOT NULL REFERENCES fundamental_fields(id),
  experiment_name TEXT NOT NULL,
  round_n INTEGER NOT NULL,
  bake_hash TEXT NOT NULL,
  noop_baseline REAL NOT NULL,
  spec_car_mdd REAL NOT NULL,
  delta REAL NOT NULL,
  classification TEXT NOT NULL,
  -- snapshot of template at score time (decoupled from current field row)
  applied_op TEXT NOT NULL,
  applied_threshold TEXT NOT NULL,
  applied_gate TEXT,
  applied_boost REAL NOT NULL,
  recorded_at TEXT NOT NULL,
  UNIQUE(experiment_name)
);
CREATE INDEX idx_pr_field ON probe_results(field_id);
CREATE INDEX idx_pr_classification ON probe_results(classification);
CREATE INDEX idx_pr_bake_hash ON probe_results(bake_hash);
```

`bake_hash` scopes results to a base version; once the base changes, picking filters to the new bake_hash. Old results stay queryable for audit. The applied_* columns capture template state at the moment of probing so re-classification with different templates can be detected.

### 5.3 Migration of existing 92 rows

```sql
UPDATE fundamental_fields SET classification = 'untested'
  WHERE status = 'untested';
UPDATE fundamental_fields SET classification = 'neutral'
  WHERE status = 'tested_in';
-- Legacy 'tested_in' rows lack delta data — they're 'neutral' by default
-- and will be reclassified on next probe.
-- New columns (period, container, probe_*, data_type_hint) populated by
-- catalogue_universe.py via accessor parsing on the legacy 92 rows.
```

The existing `status` and `tested_in` columns are kept read-only for audit; new code reads `classification`.

## 6. Probe-render template

### 6.1 Bind block (shared per spec)

Pre-fetched once per `for sym in equities` iteration:

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
```

Suffix `_z` is unique to library-emitted probes and does not collide with the existing hand-written `_f3`/`_f4`/`_f5` suffixes.

### 6.2 Per-row render

```python
def render_probe(row):
    accessor = accessor_for(row)        # e.g. _vr_z.book_value_per_share
    cond = build_condition(row, accessor)
    gate = f" and ({row['probe_gate']})" if row['probe_gate'] else ""
    return f"""   try:
    _v = {coerce_or_raw(row, accessor)}
    if {cond}{gate}: score *= {row['probe_boost']}
   except: pass"""
```

### 6.3 Operator dispatch

| `probe_op` | Rendered condition                                 | data_type_hint        |
|------------|----------------------------------------------------|-----------------------|
| `>`        | `_v is not None and _v > {threshold}`              | numeric/signed_ratio  |
| `<`        | `_v is not None and 0 < _v < {threshold}`          | absolute_amount       |
| `<`        | `_v is not None and _v < {threshold}`              | signed_ratio          |
| `<`        | `_v is not None and abs(_v) < {threshold}`         | absolute_amount_signed (BS/CFS sign-tolerant flavor) |
| `>=`/`<=`  | inclusive variants                                 | rare                  |
| `eq`       | `_v == {threshold_parsed}`                         | categorical           |
| `in`       | `_v in {tuple_from_json}`                          | categorical           |

Numeric-coerce wrap (`f_(...)`) applies for numeric/signed_ratio/absolute_amount paths; categorical paths use raw access.

### 6.4 Accessor construction

```python
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
    base = f"{CONTAINER_ALIAS[row['container']]}.{row['field_name']}"
    return f"{base}.{row['period']}" if row['period'] else base
```

### 6.5 Spec naming

`f"S001_R{round_n}_{container_short}_{field_name}_{op_short}_{threshold_short}"` — e.g.
- `S001_R406_vr_book_value_per_share_gt15`
- `S001_R406_ac_finhealth_in_AB`
- `S001_R406_inc_interest_expense_lt5e7`

Truncated to 100 chars; `UNIQUE(name)` on `backtest_queue` is the safety net.

### 6.6 Render-time fail-loud checks

- Bad operator for `data_type_hint`: raises (not silent) — e.g. `op='in'` on a numeric field.
- NULL `probe_threshold`: skip with logged warning (field surfaced as "needs template" in picker).
- Categorical with non-JSON threshold: raises.
- Generated code's `ast.parse(...)` is part of `emit_probes.py` pre-flight (§9.5).

## 7. Classify & Pick

### 7.1 `score_probes.py --round N`

```
1. Identify probe specs in round N: query backtest_queue for spec names
   matching the auto-naming pattern from §6.5
   ('S001_R{N}_{container_short}_{field_name}_{op_short}_{threshold_short}').
   Parse container_short + field_name from the name, join to
   fundamental_fields to get field_id and template snapshot at score time.
2. Compute noop_baseline:
     SELECT AVG(car_mdd) FROM experiments
       WHERE name LIKE 'S001_R{N}_VBAKE%_NOOP_%'.
   Reject the round if NOOP count < 1, or if NOOP spread > 0.0005.
3. For each probe spec with status='done':
     delta = experiments.car_mdd − noop_baseline
     classification = 'hot'      if delta > +0.0015
                    = 'harmful'  if delta < −0.0015
                    = 'neutral'  otherwise
     INSERT INTO probe_results (...) — UNIQUE(experiment_name) makes idempotent.
4. For each touched field, recompute field-row classification (§7.2).
```

### 7.2 Field-level rollup

Filter `probe_results` to `bake_hash = current_bake`:
```
no results       → 'untested'
any 'harmful'    → 'harmful'   (one harmful poisons the field)
any 'hot'        → 'hot'
all 'neutral'    → 'neutral'
```

When base changes (BAKE-41), all fields revert to 'untested' for picking purposes; old results remain queryable.

### 7.3 `emit_probes.py --round N --k_new K --k_verify M`

Returns `K + M` `(name, code)` tuples.

```
verify slots (M):
  fields where classification='hot' on current bake_hash AND
    n_results_on_current_bake < 3.
  Sort by avg(delta) DESC. Take top M. Re-render with same template.
  Spec name suffix: '_VERIFY_repN' (where N counts existing verifies).

new slots (K):
  fields where classification='untested' AND probe_threshold IS NOT NULL.
  Container-cycle order:
    valuation_ratios → operation_ratios → asset_classification →
    balance_sheet → cash_flow_statement → income_statement →
    earning_ratios → earning_reports → security_reference
  Within container, ORDER BY id. Take K.
```

Container-cycle spreads coverage across categories per round. Deterministic; repeatable.

### 7.4 Promotion candidates (manual, query-only)

```sql
SELECT f.id, f.field_name, f.container, AVG(p.delta) avg_delta, COUNT(*) n_hot
FROM fundamental_fields f
JOIN probe_results p ON p.field_id = f.id
WHERE p.bake_hash = :current_bake AND p.classification = 'hot'
GROUP BY f.id
HAVING n_hot >= 3 AND avg_delta > 0.003
ORDER BY avg_delta DESC;
```

Bake threshold ≥+0.003 + 3 reps matches existing memory rule. The user reviews and edits `s001_20260425_base.py` manually; no auto-promotion.

### 7.5 Edge cases

| Case                                            | Behavior                                                  |
|-------------------------------------------------|-----------------------------------------------------------|
| Probe spec failed (status='error')              | Skipped — no result row written. Re-tried next round.     |
| Round has no NOOP specs                         | `score_probes.py` errors out. Generator must emit ≥1 NOOP.|
| NOOP spread > 0.0005                            | Warn + abort scoring. Indicates base nondeterminism.      |
| Field's template changed mid-history            | Classify uses results matching current template only.     |
| New fields catalogued mid-experiment            | Additive — existing results untouched; new fields untested.|

## 8. Catalogue script

`catalogue_universe.py` reads `QuantConnect/Data/Fundamental/__init__.pyi` and emits `fundamental_fields` rows.

### 8.1 Inclusion rules

- Include fields on: BalanceSheet, CashFlowStatement, IncomeStatement, OperationRatios, ValuationRatios, EarningRatios, EarningReports, AssetClassification, SecurityReference.
- Exclude metadata: `*_file_date`, `accession_number`, `form_type`, `period_type`, `period_ending_date`, `*_period_*`, `*_currency_id`.
- Exclude CompanyProfile entirely (address fields, not signal).
- Exclude CompanyReference except for `country_id` (categorical) and `industry_template_code`.

### 8.2 Period assignment

Per container's class definition:
- BalanceSheet/CashFlowStatement/IncomeStatement/EarningReports: each property is a `XxxStatement` class with `.twelve_months/.three_months/.one_month` — default `period='twelve_months'`.
- OperationRatios/EarningRatios: properties are `XxxRatio` classes with `.one_year/.three_months/etc` — default `period='one_year'`.
- ValuationRatios/AssetClassification/SecurityReference: properties are direct floats/strings — `period=NULL`.

### 8.3 Default template heuristics

| Container                          | data_type_hint     | probe_op | probe_threshold      | probe_gate         | probe_boost |
|------------------------------------|--------------------|----------|----------------------|--------------------|-------------|
| valuation_ratios (most)            | numeric            | `>`      | category-specific    | `decline > .10`    | 1.10        |
| valuation_ratios (PE/PEG/EV ratios)| numeric            | `<`      | 15 / 1.5 / 10        | `decline > .10`    | 1.10        |
| operation_ratios (margins, ROE)    | numeric            | `>`      | 0.10–0.20            | `decline > .12`    | 1.10        |
| operation_ratios (debt/leverage)   | numeric            | `<`      | 1.5–2.0              | `decline > .15`    | 1.08        |
| earning_ratios (growth)            | signed_ratio       | `>`      | 0.10                 | `decline > .15`    | 1.15        |
| balance_sheet (assets, equity)     | absolute_amount    | `>`      | 1e9–1e10             | `decline > .12`    | 1.08        |
| balance_sheet (debt items)         | absolute_amount    | `<`      | 5e8                  | `decline > .10`    | 1.06        |
| cash_flow (free cash, operating)   | absolute_amount    | `>`      | 1e9                  | `decline > .10`    | 1.08        |
| income (net income, operating)     | absolute_amount    | `>`      | 1e9                  | `decline > .12`    | 1.10        |
| asset_classification (grades)      | categorical        | `in`     | `'["A","B+","B"]'`   | `decline > .10`    | 1.06        |
| asset_classification (sector codes)| categorical        | `in`     | defensive set        | `decline > .10`    | 1.08        |

These are first-pass heuristics; the user can edit any row's template manually. Hot/harmful results inform threshold tuning over time.

### 8.4 Idempotency

`UNIQUE(accessor)` on `fundamental_fields` prevents duplicate inserts. Re-runs:
- Insert new rows for newly-added LEAN fields.
- Skip existing rows (existing template is preserved, never overwritten).
- Optionally: `--update-templates` flag rewrites templates per current heuristics (off by default).

### 8.5 Backfill of legacy 92 rows

Existing rows have `accessor` like `_vr.book_value_per_share` or `_bs.long_term_debt.twelve_months`. Backfill populates `container` and `period` by parsing the accessor; `data_type_hint` from the container; `probe_*` columns left NULL (the user authors them on first re-test).

## 9. Testing

### 9.1 Library tests (`test_fundamental_probes.py`)

| Function                | Test                                                          |
|-------------------------|---------------------------------------------------------------|
| `accessor_for(row)`     | All 9 containers + period combinations produce expected accessor strings |
| `render_probe(row)`     | Each `probe_op` renders expected Python; rendered code passes `ast.parse` |
| `render_probe(row)`     | Categorical row → tuple; `<` on absolute_amount adds `0 < _v` guard; signed_ratio path skips guard |
| `classify_delta(d)`     | +0.002 → 'hot'; −0.002 → 'harmful'; 0.0005 → 'neutral'; exact +0.0015 → 'neutral' (strict `>`); exact −0.0015 → 'neutral' (strict `<`) |
| `field_rollup(results)` | Empty → 'untested'; mixed hot+harmful → 'harmful'; all-neutral → 'neutral'; ≥1 hot only → 'hot' |
| `pick_fields(...)`      | Deterministic; container-cycle works; respects classification filters |

### 9.2 Catalogue test

```python
def test_catalogue_idempotent(tmp_db):
    catalogue_universe.main(db_path=tmp_db)
    n1 = count_rows(tmp_db, 'fundamental_fields')
    catalogue_universe.main(db_path=tmp_db)
    n2 = count_rows(tmp_db, 'fundamental_fields')
    assert n1 == n2
    assert n1 >= 800
    assert categorical_rows_present(tmp_db)
```

Runs against installed LEAN — no fixtures.

### 9.3 End-to-end smoke (manual, one-time after implementation)

```bash
python scripts/catalogue_universe.py
python scripts/emit_probes.py --round 999 --k-new 5 --k-verify 0 --dry-run > /tmp/smoke.json
python -c "import ast, json; [ast.parse(s['code']) for s in json.load(open('/tmp/smoke.json'))]"
```

Then queue real round R406 with `k_new=10, k_verify=3`, run cron, run `score_probes.py --round 406`, inspect.

### 9.4 Pre-flight checks (in scripts, fail loud)

`emit_probes.py`:
```python
# Idempotency comes from UNIQUE(name) on backtest_queue; no need to
# track already-emitted rounds separately. Picker is deterministic, so
# re-running on same DB state produces same specs.
for field in picked_fields:
    assert field['probe_op'] in VALID_OPS
    assert field['probe_threshold'] is not None
    rendered = render_probe(field)
    ast.parse(rendered)
```

`score_probes.py`:
```python
assert len(noops) >= 1, f"Round {round_n} has no NOOP specs"
spread = max(n.car_mdd) - min(n.car_mdd)
assert spread <= 0.0005, f"NOOP spread {spread} > 0.0005 — base nondeterministic"
```

### 9.5 What's not tested

- Probe correctness against LEAN runtime (rely on existing convention, validated by R401–R405).
- Threshold defaults producing useful boosts (the learning loop tests this over many rounds).
- Multi-bake delta validity (`bake_hash` scoping is the safety; failure is visible to the user).

## 10. File layout

```
/home/txy/qc_work/data/
├── s001/
│   ├── fundamental_probes.py          # NEW — library (catalogue / render / classify / pick)
│   └── s001_20260425_base.py          # existing — unchanged
├── scripts/                           # NEW directory
│   ├── catalogue_universe.py          # NEW — bootstrap (one-time)
│   ├── emit_probes.py                 # NEW — per-round
│   └── score_probes.py                # NEW — after-round
├── tests/                             # NEW directory
│   └── test_fundamental_probes.py     # NEW — library tests
├── gen_s001_R{N}.py                   # existing — adds 1 import + 1 call
└── docs/superpowers/specs/2026-04-27-s001-fundamental-data-coverage-design.md  # this file
```

## 11. Migration sequence

1. Apply schema changes (8 ALTERs + 1 new table + 3 indexes). One-shot SQL; the existing 92 rows survive.
2. Implement library + tests; verify all green.
3. Run `catalogue_universe.py` once. It (a) inserts ~800+ new rows for never-tracked fields, (b) backfills `container`/`period`/`data_type_hint` on the legacy 92 rows by parsing their existing `accessor`. Confirm total row count ≈900.
4. Modify `gen_s001_R406.py` template to import `emit_probes` and append output.
5. Run smoke round R406; run `score_probes.py --round 406`; inspect `probe_results`.
6. Subsequent rounds: each `gen_s001_R{N}.py` follows the same template. Eventually the library emits all probe specs and the user authors only NOOPs/VERIFYs/sweeps.

## 12. Risks & mitigations

| Risk                                            | Mitigation                                                       |
|-------------------------------------------------|------------------------------------------------------------------|
| Catalogued field doesn't exist at runtime       | `try/except` swallows; renderer's `ast.parse` catches static errors; runtime errors stay in the spec's outer try. |
| Default templates produce many no-op probes     | Acceptable; classification quickly tags them 'neutral' and the picker moves on. |
| Conservative "any-harmful poisons" rule misses good fields | Manual override available — user can run `UPDATE fundamental_fields SET classification='untested' WHERE id=...` to retry. |
| Schema change breaks existing per-round generators | ALTERs are additive (new columns nullable); legacy code paths continue to work unchanged. |
| Bake change invalidates classifications         | `bake_hash` scoping in queries; promotion query filters to current bake. |
| Categorical sector codes drift                  | Catalogue heuristic stores defaults as JSON; user can edit per-row when LEAN updates classification taxonomy. |

## 13. Out-of-scope future work

- Auto-discovery of working probe combinations (interaction effects across hot probes).
- Cross-bake trend analysis (does a probe's delta survive a base change?).
- Multi-strategy reuse (S002 etc. importing the same library for its own DB).
- Threshold sweep automation (per-field grid search for optimal probe_threshold).
- Pruning rule for fields that stay 'neutral' for N rounds (currently they keep getting re-emitted via container-cycle but never re-verified).

These are deferrable to follow-up specs. v1 is bounded to the catalogue + render + classify + pick loop on a single-strategy DB.
