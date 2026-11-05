# S001 Fundamental Data v3: Full-Grid Coarse Sweep + Adaptive Prune + Refine

**Date:** 2026-04-27
**Status:** Design — extends `2026-04-27-s001-fundamental-data-auto-sweep-design.md` (v2)
**Scope:** Single implementation plan. First sub-project of a v3 roadmap; subsequent sub-projects (composite probes, time-series probes, relative-rank probes) get their own specs.

---

## 1. Problem

After 27 rounds of v2 auto-sweep on BAKE-45 (R465–R491), 75 fields completed Phase 2 (15-variant mag/gate sweep). Sign distribution: **0 positive / 1 zero / 74 negative**. Top non-sweep delta: +0.00019. Top sweep winner: 0.0. Zero candidates qualify for the +0.002 bake threshold.

**Hypothesis:** v2's narrow grid (5 mags × 3 gates × 1 fixed threshold × 1 op direction = 15 cells) is missing signal because:
1. **Direction may be wrong.** Default-template hard-codes the `>` operator. If the field's true predictive direction is `<`, no v2 cell can ever score positive.
2. **Threshold is wrong.** Default-template picks one threshold per `data_type_hint`. If the field's actual signal sits at p25 or p75 of the universe distribution, the default is far off.
3. **Mag is too narrow.** v2 spans 1.04–1.13. Stronger penalties (mag<1) or larger boosts (mag>1.15) untested.

The pattern of all-non-positive sweep winners across 75 fields suggests at least one of these is systematically wrong.

## 2. Goals

1. **Full-grid sweep**: per-field coarse pass exercises 4 dimensions — `op` (`>`/`<`), `mag` (4 values), `gate` (3 values), `threshold` (3 percentile-based values from universe stats) → 72 cells per numeric field.
2. **Adaptive prune**: between coarse and refine, dimension-level prune drops bottom-half values per dimension; refine emits only ±neighbors of the coarse winner within survivors (~26 cells).
3. **Universe-aware thresholds**: an offline scanner records `{p10, p25, p50, p75, p90}` of each field's universe values per bake; coarse uses `{p25, p50, p75}`.
4. **Bake-hash scoping** preserved from v2.
5. **Migration-clean**: existing v2 sealed fields stay sealed (one-time `sweep_version=2`); future fields go through v3.

## 3. Non-goals

- **Composite probes** (multi-field AND/OR) — separate v3.2 sub-project.
- **Relative-rank probes** (cross-stock percentile gates at trade time) — separate v3.3 sub-project.
- **Time-series probes** (latest-vs-3yr-avg, growth-style) — separate v3.1 sub-project.
- **Re-sweeping v2-completed fields** — sealed at `sweep_version=2`; manual override path documented but not auto-triggered.
- **Auto-promotion to bake** — promotion query surfaces winners with `delta ≥ +0.002`; baking remains manual with 3x VERIFY.
- **Auto-rerun of universe scanner within a bake** — manual one-shot per bake.

## 4. Architecture

```
                                    Round N
                                    emit_probes_for_db(
                                      k_new, k_coarse_fields, k_refine_fields)
                                          │
                ┌─────────────────────────┼─────────────────────────┐
                ▼                         ▼                         ▼
        pick_fields(             pick_v3_coarse_candidates(  pick_v3_refine_candidates(
          'untested',              bake=current,              bake=current,
          bake=current)            phase=1, |Δ|≥.0001,        phase=2, all coarse scored)
                │                  has field_universe_stats)         │
                ▼                         │                          ▼
        K_new fields                      ▼                  Run dimension_prune,
        (Phase 1, default                K_coarse fields     persist refine_*_set,
         template)                        × 72 = ~144 specs   build refine grid:
                │                         (coarse pass)        coarse_winner ± neighbors
                │                                              within survivors
                │                                                    │
                │                                                    ▼
                │                                            K_refine fields
                │                                            × ~26 = ~52 specs
                │                                            (refine pass)
                │                         │                          │
                └─────────────────────────┴──────────────────────────┘
                                          │
                                          ▼
                                 score_round(round=N)
                                          │
                                  INSERT probe_results
                                  (sweep_stage = NULL | 'coarse' | 'refine')
                                          │
                          ┌───────────────┴───────────────┐
                          ▼                               ▼
                   For coarse-complete:            For refine-complete:
                     run dimension_prune,            update_v3_winner →
                     persist refine_*_set,           sweep_winner_*,
                     bump sweep_phase=3              sweep_phase=4, sweep_version=3
```

### 4.1 Phase machine

| Phase | Meaning |
|-------|---------|
| 0 | Untested |
| 1 | Phase 1 default-template probe complete; awaits coarse decision |
| 2 | v3 coarse sweep in flight |
| 3 | v3 refine sweep in flight (post-prune) |
| 4 | Sealed (sweep_winner_* set, sweep_version=2 or 3) |

**Old v2 phase=2 fields** (sweep complete) get one-time renumbered to phase=4 with `sweep_version=2`.

## 5. Schema changes

### 5.1 `fundamental_fields` additions

```sql
-- Which sweep version sealed the field
ALTER TABLE fundamental_fields ADD COLUMN sweep_version INTEGER DEFAULT 1;
-- 1 = v1 single-shot, 2 = v2 mag/gate sweep, 3 = v3 full-grid + adaptive

-- Coarse-best snapshot (set after coarse, before refine)
ALTER TABLE fundamental_fields ADD COLUMN coarse_winner_op TEXT;
ALTER TABLE fundamental_fields ADD COLUMN coarse_winner_threshold TEXT;
ALTER TABLE fundamental_fields ADD COLUMN coarse_winner_gate TEXT;
ALTER TABLE fundamental_fields ADD COLUMN coarse_winner_mag REAL;
ALTER TABLE fundamental_fields ADD COLUMN coarse_winner_delta REAL;

-- Surviving subspace after dimension prune (JSON arrays)
ALTER TABLE fundamental_fields ADD COLUMN refine_op_set TEXT;
ALTER TABLE fundamental_fields ADD COLUMN refine_mag_set TEXT;
ALTER TABLE fundamental_fields ADD COLUMN refine_gate_set TEXT;
ALTER TABLE fundamental_fields ADD COLUMN refine_threshold_set TEXT;
```

`sweep_winner_*` columns from v2 are reused — they hold the post-refine final winner.

### 5.2 New `field_universe_stats` table

```sql
CREATE TABLE field_universe_stats (
    field_id INTEGER NOT NULL,
    bake_hash TEXT NOT NULL,
    p10 REAL, p25 REAL, p50 REAL, p75 REAL, p90 REAL,
    sample_size INTEGER NOT NULL,
    scanned_at TEXT NOT NULL,
    PRIMARY KEY (field_id, bake_hash),
    FOREIGN KEY (field_id) REFERENCES fundamental_fields(id)
);
CREATE INDEX idx_fus_bake ON field_universe_stats(bake_hash);
```

### 5.3 `probe_results` addition

```sql
ALTER TABLE probe_results ADD COLUMN sweep_stage TEXT;
-- NULL  = v1 default or v2 sweep variant (legacy)
-- 'coarse' = v3 Phase 2 coarse variant
-- 'refine' = v3 Phase 3 refine variant
```

### 5.4 Migration script

`scripts/migrate_v3_schema.py` is idempotent and runs all of the above via `PRAGMA table_info` checks. Final step:
```sql
UPDATE fundamental_fields
SET sweep_version = 2, sweep_phase = 4
WHERE sweep_phase = 2 AND sweep_winner_delta IS NOT NULL;
```

## 6. Search strategy

### 6.1 Coarse grid (Phase 2)

| Dimension | Values | Count |
|-----------|--------|-------|
| `op` | `{>, <}` | 2 |
| `mag` | `{1.04, 1.08, 1.13, 1.20}` (penalty handled via inverse op) | 4 |
| `gate` | `{.05, .10, .15}` | 3 |
| `threshold` | `{p25, p50, p75}` from `field_universe_stats` | 3 |

**Per-field coarse cell count: 2 × 4 × 3 × 3 = 72.**

For categorical fields (`op in {eq, in}`): skip threshold sweep, fall back to v2-style 5 mags × 3 gates = 15 cells (no inversion).

### 6.2 Dimension prune

After all coarse cells score, for each dimension `d`:
1. Group `coarse_results` by `d`'s value.
2. Compute median delta per group → `medians[d]`.
3. Compute `t = median(medians[d].values())`.
4. **Survivors:** values whose median ≥ `t`.

**Special case** for 2-value dimensions (e.g., `op`): drop the loser only if its median is `≥ 0.001` worse than the winner. Otherwise keep both. Avoids killing the optimum when one side has a single strong cell amid weak cells.

Survivors persisted as JSON in `refine_*_set` columns.

### 6.3 Refine grid (Phase 3)

```python
def refine_grid(coarse_winner, refine_sets):
    op_choices = [coarse_winner.op]
    mag_choices = neighbors(coarse_winner.mag, refine_sets['mag'], k=1)
    gate_choices = neighbors(coarse_winner.gate, refine_sets['gate'], k=1)
    threshold_choices = neighbors(coarse_winner.threshold, refine_sets['threshold'], k=1)
    cells = cartesian(op_choices, mag_choices, gate_choices, threshold_choices)
    return cells - {coarse_winner}  # don't re-emit
```

`neighbors(v, allowed_set, k)` returns up to `2k+1` values around `v` from the allowed set (sorted by allowed_set's natural ordering): includes `v` itself plus the `k` nearest values above and the `k` nearest values below `v` within `allowed_set`. If fewer than `k` exist on either side (e.g., `v` is at the boundary), returns however many exist.

**Typical refine cell count:** 1 × 3 × 3 × 3 − 1 = **26**. Worst case: 26.

### 6.4 Round budget

```python
auto = emit_probes_for_db(
    db_path, round_n=N,
    k_new=20, k_verify=0,
    k_coarse_fields=2, k_refine_fields=2)
```
- 20 Phase 1
- 2 × 72 = 144 coarse
- 2 × 26 = 52 refine
- 6 NOOP/VERIFY (manual)

**Total: ~222 specs/round.** Roughly 2× v2's typical round.

## 7. Offline universe scanner

### 7.1 `scripts/gen_scan_spec.py`

Generates a single backtest spec `S001_SCAN_FUNDAMENTALS_BAKE45` (one per bake) that:
1. Runs against current `s001_*_base.py`.
2. On the first trading day after warmup, iterates every QQQ symbol.
3. For each non-categorical `fundamental_fields` row, reads the field via the standard accessor.
4. Calls `self.log(json.dumps([symbol, field_id, value]))` per non-null read.
5. Exits early after one snapshot (no holding).

Queued at `priority=0` (priority 0 jumps the queue ahead of normal sweeps).

### 7.2 `scripts/parse_scan_log.py`

After scan completes:
1. Read `backtest_queue.result_json` for the scan spec.
2. Parse the log payload into `(symbol, field_id, value)` triples.
3. For each `field_id`, compute `{p10, p25, p50, p75, p90}` across symbols (numpy.percentile, sample_size = count of non-null reads).
4. `INSERT OR REPLACE INTO field_universe_stats (...)`.

**Sample size threshold:** persist only if `sample_size >= 50`. Below threshold, the field is skipped from coarse picks for this bake until the next scan covers it.

### 7.3 Threshold formatting

```python
def _format_threshold(value, hint):
    """Round to 2 sig figs; scientific notation for |value| outside [1e-3, 1e6)."""
    if value == 0:
        return '0'
    abs_v = abs(value)
    if abs_v >= 1e6 or abs_v < 1e-3:
        return f'{value:.1e}'   # e.g. '1.5e+09'
    return f'{value:.2g}'        # e.g. '0.10', '120'
```

### 7.4 Trigger order

After a new bake:
1. Operator runs `python3 scripts/gen_scan_spec.py` (queues scan spec).
2. Backtest worker drains the priority-0 spec.
3. Operator runs `python3 scripts/parse_scan_log.py` (populates `field_universe_stats`).
4. Subsequent v3 rounds find populated stats and pick coarse candidates.

Until step 3 completes, `pick_v3_coarse_candidates` returns empty (all candidates skipped on missing stats). The cron-driven loop continues advancing Phase 1 fields and refining any in-flight Phase 3 fields.

## 8. Library API

### 8.1 New module-level constants

```python
COARSE_OPS = ['>', '<']
COARSE_MAGS = [1.04, 1.08, 1.13, 1.20]
COARSE_GATES = ['.05', '.10', '.15']
COARSE_THRESHOLD_PERCENTILES = ['p25', 'p50', 'p75']

PRUNE_DOMINANCE_THRESHOLD = 0.001
COARSE_TRIGGER_DELTA = 0.0001  # same as v2

V3_COARSE_PREFIX = 'v3c'
V3_REFINE_PREFIX = 'v3r'
```

### 8.2 New functions in `s001/fundamental_probes.py`

| Function | Purpose |
|----------|---------|
| `coarse_grid(field_row, bake_hash, db_path)` | Build coarse Cartesian grid; returns None if no `field_universe_stats`. |
| `dimension_prune(coarse_results)` | Run prune algorithm; return survivors dict. |
| `refine_grid(coarse_winner, refine_sets)` | Build refine cells around coarse winner. |
| `emit_v3_coarse(field_row, round_n, bake_hash, db_path)` | Render coarse specs `[(name, body), ...]`. |
| `emit_v3_refine(field_row, round_n)` | Render refine specs using saved coarse_winner_* + refine_*_set. |
| `pick_v3_coarse_candidates(db_path, k, bake_hash)` | Pick fields ready for coarse; bump phase to 2. |
| `pick_v3_refine_candidates(db_path, k, bake_hash)` | Pick fields with all coarse scored; run prune; bump phase to 3. |
| `update_v3_winner(con, field_id, bake_hash)` | After refine complete, write final winner; phase=4, version=3. |

### 8.3 Modified function

```python
def emit_probes_for_db(
    db_path, round_n,
    k_new, k_verify=0,
    k_coarse_fields=0, k_refine_fields=0,
    k_sweep_fields=None,  # deprecated; aliased to k_coarse_fields with warning
    include_bind=False,
):
    """Returns list[(spec_name, body)] containing:
      - K_new Phase 1 default-template specs (via pick_fields)
      - K_coarse_fields × 72 v3 coarse specs (via pick_v3_coarse_candidates + emit_v3_coarse)
      - K_refine_fields × ~26 v3 refine specs (via pick_v3_refine_candidates + emit_v3_refine)

    Side effects:
      - pick_v3_coarse_candidates bumps each picked field's sweep_phase to 2.
      - pick_v3_refine_candidates runs dimension_prune, persists refine_*_set,
        and bumps each picked field's sweep_phase to 3.
    """
```

`k_sweep_fields` alias logs a `DeprecationWarning`; existing R465–R491 generators keep working until their cron firings end.

### 8.4 Spec naming

```
S001_R{round}_v3c_{cs}_{field}_o{op_short}_m{mag_int}_g{gate_int}_t{thr_idx}
S001_R{round}_v3r_{cs}_{field}_o{op_short}_m{mag_int}_g{gate_int}_t{thr_idx}
```

| Token | Encoding |
|-------|----------|
| `op_short` | `gt` for `>`, `lt` for `<` |
| `mag_int` | `int(mag * 100)`, e.g. `1.08` → `108` |
| `gate_int` | `int(gate.lstrip('.') )`, e.g. `.05` → `05` |
| `thr_idx` | percentile index: `25`, `50`, `75` (coarse), `25`/`50`/`75` (refine inherits) |

Truncated to 100 chars.

## 9. Score-routing changes (`scripts/score_probes.py`)

```python
V3_COARSE_NAME_RE = re.compile(
    r'^S001_R(?P<round>\d+)_v3c_(?P<cs>[a-z]+)_(?P<field>[a-z0-9_]+?)'
    r'_o(?P<op>gt|lt)_m(?P<mag>\d+)_g(?P<gate>\d+)_t(?P<thr>\d+)$')

V3_REFINE_NAME_RE = re.compile(
    r'^S001_R(?P<round>\d+)_v3r_(?P<cs>[a-z]+)_(?P<field>[a-z0-9_]+?)'
    r'_o(?P<op>gt|lt)_m(?P<mag>\d+)_g(?P<gate>\d+)_t(?P<thr>\d+)$')
```

**Dispatch order in `score_round`:** V3_COARSE → V3_REFINE → SWEEP_NAME_RE (v2) → default.

Insert into `probe_results` with `sweep_stage = 'coarse' | 'refine' | NULL`.

After scoring pass:
1. **Coarse-complete detection:**
```sql
SELECT field_id, COUNT(*) AS n FROM probe_results
WHERE bake_hash = ? AND sweep_stage = 'coarse'
GROUP BY field_id HAVING n = 72;
```
For each, run `dimension_prune` + persist `refine_*_set`. Bump `sweep_phase = 3`.

2. **Refine-complete detection:**
```sql
SELECT f.id FROM fundamental_fields f
WHERE f.sweep_phase = 3
  AND (SELECT COUNT(*) FROM probe_results p
       WHERE p.field_id = f.id AND p.bake_hash = ? AND p.sweep_stage = 'refine')
      >= expected_refine_count(f);
```
For each, run `update_v3_winner`. Bump `sweep_phase = 4`, `sweep_version = 3`.

`expected_refine_count(f)` reads `refine_*_set` and `coarse_winner_*`, computes `len(refine_grid(...))`.

## 10. Promotion query

```sql
SELECT f.field_name, f.sweep_winner_op, f.sweep_winner_threshold,
       f.sweep_winner_gate, f.sweep_winner_boost, f.sweep_winner_delta
FROM fundamental_fields f
WHERE f.sweep_phase = 4 AND f.sweep_version = 3 AND f.sweep_winner_delta >= 0.002
ORDER BY f.sweep_winner_delta DESC;
```

Bake decision still manual; 3x VERIFY rule unchanged from v2.

## 11. Testing strategy

### 11.1 Unit tests (`tests/test_fundamental_probes.py`)

- `coarse_grid` cell count = 72 for numeric, 15 for categorical.
- `coarse_grid` returns `None` when `field_universe_stats` is missing.
- `dimension_prune` correctly drops bottom-half values for 3+-value dims.
- `dimension_prune` 2-value dim respects 0.001 dominance rule (drops only when worse by ≥0.001).
- `refine_grid` returns expected `±1` neighbors and excludes the coarse winner.
- `pick_v3_coarse_candidates` filters by bake_hash + Phase 1 delta + universe_stats presence.
- `pick_v3_refine_candidates` filters by phase=2 + all 72 coarse scored.
- `update_v3_winner` only fires when refine count matches `expected_refine_count`.

### 11.2 Score-routing tests (`tests/test_score_probes.py`)

- v3 coarse spec name → matched by V3_COARSE_NAME_RE → inserted with `sweep_stage='coarse'`.
- v3 refine spec name → matched by V3_REFINE_NAME_RE → inserted with `sweep_stage='refine'`.
- v2 spec name (`_sw_`) still matches SWEEP_NAME_RE; `sweep_stage` stays NULL.
- After 72 coarse rows for a field, `score_round` triggers `dimension_prune` + bumps phase=3.
- After expected refine rows, `score_round` triggers `update_v3_winner` + bumps phase=4 + version=3.

### 11.3 Migration tests (`tests/test_migrate_v3_schema.py`)

- All ALTER TABLE statements idempotent.
- `field_universe_stats` table created idempotently.
- v2 sealed fields renumbered to `phase=4, version=2` (one-time).
- v2 in-flight fields (phase=1 with sweep_winner_delta NULL) untouched.

### 11.4 End-to-end test

Synthetic minimal DB with 1 field, 100 fake symbols, populated `field_universe_stats`. Walk through:
1. Phase 0 → Phase 1 (single default probe, fake delta = 0.0005).
2. Phase 1 → coarse pick → emit 72 specs.
3. Insert 72 fake `probe_results` with deltas designed to test prune (one dimension clearly dominant).
4. `dimension_prune` produces expected `refine_*_set`.
5. `coarse_winner_*` set correctly to argmax.
6. Phase 2 → refine pick → emit ≤26 specs.
7. Insert refine `probe_results`.
8. `update_v3_winner` runs; `sweep_winner_*` set to refine argmax; phase=4, version=3.

## 12. Operational notes

- **Cron loop unchanged.** Per-round generator (`gen_s001_R{N}.py`) just swaps `k_sweep_fields=...` for `k_coarse_fields=2, k_refine_fields=2`. Existing `/loop 10m queue 64 ...` keeps firing.
- **Backlog tolerance.** ~222 specs/round vs v2's ~131; throughput in current cluster handles this when `running` floor is ≥30. If backlog spikes >300 active, drop `k_coarse_fields` to 1.
- **Universe scanner failure mode.** If scan spec fails or log parse fails, `field_universe_stats` stays empty; v3 coarse picks return empty; loop falls back to Phase 1-only rounds (still progress, just no sweeps until scan succeeds).
- **Rollback.** `sweep_version` allows rollback by reverting `pick_v3_coarse_candidates` to a no-op; existing Phase 1 + v2 path still works for fresh fields.

## 13. Out-of-scope future enhancements

- **Auto-rescan** when fundamental_fields catalogue grows: detect new field IDs and emit per-field scan rather than full universe re-scan.
- **Hot-zone refinement**: when refine winner has `delta ≥ +0.0015`, queue a third "ultra-fine" pass with mag step 0.01.
- **Cross-field correlation analysis**: feeds into v3.2 composite probe selection.
- **Multi-bake comparison view**: track which fields had different optimal cells across bake versions.
