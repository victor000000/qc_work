# S001 — Improve car/mdd subject to dd < 10

**Date:** 2026-04-28
**Status:** Design approved
**Owner:** S001 strategy line

---

## Problem

Current S001 champion `S001_LIVE` (bake hash `7d340db8…`) sits at car_mdd ≈ 2.003, dd ≈ 10.4%, CAGR ≈ 20.8%. The user's objective is to **increase car/mdd while keeping dd strictly below 10%**.

Empirical state of the search (S001.db, ~23,194 successful experiments):

- 14,711 specs cluster at dd ∈ [10.0, 10.5%].
- 8,483 specs at dd ≥ 10.5%.
- **Only 4 specs** ever cleared dd < 10. Only one is non-trivial: `S001_R306_glow_50_grad_022_haircut_off` (car_mdd = 1.857, dd = 9.6%) — found via structural knob sweep, not fundamentals.

Conclusion: the strategy's drawdown is structurally floored near 10.4%. Fundamental probes (recent rounds R465–R553) shift score weighting but cannot move dd, because they don't change *when* the strategy holds risk — only *what* it weights. To break the floor, a new risk-timing/sizing component is required.

The base file already has `_dynamic_gross()` (`data/s001/s001_20260425_base.py:70`) which scales gross between `GROSS_LOW=0.55` and `GROSS_HIGH=1.0` using QQQ/HYG ratio vs an MA. That signal is insufficient — it does not capture realized-volatility regimes (2008 spillover, 2020 COVID, 2022).

A second issue compounds the stagnation: `score_probes.SPEC_NAME_RE` mis-parses field names containing `_in_`, `_gt_`, `_lt_` substrings, silently dropping ~17/20 specs in affected rounds. R493 was confirmed affected (memory `project_s001_score_parse_bug`).

## Goal

Land three deliverables, in order, that together unlock dd < 10 while preserving accumulated edge:

1. **C₁** — fix `score_probes` parser (unblocks fundamental discovery).
2. **C₂** — gate bake promotions on `(car_mdd ≥ baseline + Δ) AND (dd < 10.0)` (prevents drift toward dd = 10.4 wall).
3. **B** — add `_vol_scale()` overlay (realized-volatility regime sizing) on top of existing `_dynamic_gross()`.

Success = a baked champion with car_mdd > 2.008 AND dd < 10.0, 3x deterministically verified.

## Architecture

```
                         ┌─────────────────────┐
                         │  _dynamic_gross()   │   existing — QQQ/HYG vs MA
                         │  → base_gross       │   ∈ [0.55, 1.0]
                         └──────────┬──────────┘
                                    │
              NEW                   ▼
        ┌─────────────────┐   ┌─────────────────┐
        │  _vol_scale()   │──▶│   combine:      │── final gross_target
        │  → vol_scale    │   │ base * vol_scale│   ∈ [VOL_FLOOR · GROSS_LOW, GROSS_HIGH]
        │ ∈ [VOL_FLOOR,1] │   └─────────────────┘
        └─────────────────┘
```

**Key decisions (locked):**

- Augment, do not replace, `_dynamic_gross()`. Preserves baked edge.
- Combination is multiplicative (`base * vol_scale`), so the new signal can only ever reduce gross, not raise it.
- Sequencing is strictly serial: C₁ → C₂ → B. No phase overlaps.
- Champion grandfathered through C₂ — gate prevents new high-dd promotions but does not retroactively demote `S001_LIVE`.

## Components

### B — `_vol_scale()` overlay

**Signal:** realized-volatility percentile (RVP) on QQQ daily log returns.

```python
returns = [log(qqq_bars[i].close / qqq_bars[i-1].close) for i in range(-RV_WIN, 0)]
rv_now  = stdev(returns) * sqrt(252)
rv_hist = rolling annualized rv over RV_HIST days
pct     = rank(rv_now, rv_hist) / RV_HIST                 # 0.0 calm … 1.0 panic
vol_scale = max(VOL_FLOOR, 1.0 - VOL_SLOPE * max(0, pct - VOL_DEADZONE))
```

**Why RVP and not raw RV / VIX-ATR / trailing-DD-pct:**
- Raw vol levels drift over a 17-year backtest. Percentile is regime-stationary.
- VIX is not cleanly available inside QC `before_market_open` for the QQQ universe.
- ATR conflates trend and volatility; RV from log returns is a cleaner volatility-only signal.

**Why deadzone + linear ramp (vs. step):** stepping at a threshold whipsaws on the boundary. Linear past a deadzone keeps the system smooth in normal regimes (≤ 60th pct), trims gross above that, hits the floor at extreme percentiles.

**Parameter surface (sweep targets, lives in `self.tune`):**

| Param | Default | Search range | Role |
|---|---|---|---|
| `RV_WIN` | 20 | {10, 15, 20, 30} | Realized-vol lookback (days) |
| `RV_HIST` | 504 | {252, 504, 1008} | Percentile reference window |
| `VOL_DEADZONE` | 0.60 | {0.40, 0.50, 0.60, 0.70} | Below this percentile, no trim |
| `VOL_SLOPE` | 1.5 | {1.0, 1.5, 2.0, 2.5} | Aggressiveness past deadzone |
| `VOL_FLOOR` | 0.40 | {0.25, 0.30, 0.40, 0.55} | Minimum `vol_scale` |

Cross product 4 × 3 × 4 × 4 × 4 = 768 cells; sweep takes a 128-point Latin-hypercube sample.

**Plug-in point** — single-line edit at `data/s001/s001_20260425_base.py:118`:

```python
gross_target = self._dynamic_gross() * self._vol_scale()
```

`_vol_scale()` follows the same `try/except → return 1.0` pattern as `_dynamic_gross()`, so insufficient history produces a no-op (identity multiplier).

**Cold-start window:** ~`RV_HIST + RV_WIN` ≈ 524 trading days before the overlay produces non-1.0 output. With start_date 2009-08-01, first non-identity output ~2011-09. Acceptable; nothing baked depends on early-period dd.

**Hard caps preserved:** `WT_CAP ≤ 0.07`, `GROSS_HIGH ≤ 1.0`, QQQ-only, daily, 5h pre-market — all unchanged. The overlay only ever shrinks effective gross.

**Risks:**
- *CAR compression* — too-low `VOL_FLOOR` flattens 2008/2020 returns. Mitigated by floor ≥ 0.25 in search and 3x deterministic verify on any winner.
- *Look-ahead* — RV is computed on closed bars only, runs in `before_market_open`. Confirmed safe.

### C₁ — `score_probes` parser fix

**Bug** (`data/scripts/score_probes.py:30-33`):

```python
SPEC_NAME_RE = re.compile(
    r'^S001_R(?P<round>\d+)_(?P<cs>[a-z]+)_(?P<field>[a-z0-9_]+?)_'
    r'(?P<op>gt|gte|lt|lte|eq|in)(?P<thr>.+)$'
)
```

On `S001_R553_inc_non_interest_income_gt1e9`: non-greedy `field` consumes minimally; `op=in` matches the `_in_` inside `interest`; lookup `(income, non)` fails; spec silently dropped.

**Fix — registry-aware longest-prefix match:**

```python
def _parse_probe_spec_name(name, conn):
    m = re.match(r'^S001_R(?P<round>\d+)_(?P<cs>[a-z]+)_(?P<rest>.+)$', name)
    if not m:
        return None
    cs = m.group('cs')
    cont = CONTAINER_FROM_SHORT.get(cs)
    if cont is None:
        return None
    rest = m.group('rest')

    OPS = ('gte', 'lte', 'gt', 'lt', 'eq', 'in')   # longest-first
    candidates = []
    for op in OPS:
        token = f'_{op}'
        for i in range(len(rest) - len(token) + 1):
            if rest[i:i+len(token)] == token:
                field = rest[:i]
                thr = rest[i+len(token):]
                if field and thr:
                    candidates.append((field, op, thr, len(field)))

    if not candidates:
        return None

    candidates.sort(key=lambda c: -c[3])
    cur = conn.cursor()
    for field, op, thr, _ in candidates:
        row = cur.execute(
            "SELECT 1 FROM fundamental_fields WHERE container=? AND field_name=? LIMIT 1",
            (cont, field)
        ).fetchone()
        if row:
            return cont, field, op, thr
    return None
```

Caller threads the existing sqlite connection to `_parse_probe_spec_name`.

**Tests** (`tests/test_score_probes_parser.py`, new):
- 20 R493 spec names from memory, expected `(container, field, op, thr)` tuples drawn from the live `fundamental_fields` registry.
- Negative case: `S001_R553_inc_garbage_gt1e9` → `None`.
- Backwards-compat: 5 R200-era names without `_in_/_gt_/_lt_` substrings → identical result to old regex.

**Historical rescore** (`data/scripts/rescore_historical.py`, new, one-shot): re-parses spec names across R465–R553. Backfills `probe_results` rows for previously-masked specs. Read-only with respect to bake state. Expected outcome: ~17 specs/round become visible; some may surface fundamentals that should have been baked but weren't.

### C₂ — constrained bake policy

**Promotion gate** (new helpers in `data/s001/fundamental_probes.py`):

```python
PROMOTE_THRESHOLDS = {'tune': 0.002, 'structural': 0.005}
DD_CEILING = 10.0  # candidate dd must be strictly < this

def is_promotable(row, baseline_row, kind='tune'):
    if row.get('dd') is None or row['dd'] >= DD_CEILING:
        return False, f"dd {row.get('dd')} not < {DD_CEILING}"
    delta = row['car_mdd'] - baseline_row['car_mdd']
    thr = PROMOTE_THRESHOLDS[kind]
    if delta < thr:
        return False, f"car_mdd lift {delta:+.4f} < +{thr}"
    return True, f"lift={delta:+.4f}, dd={row['dd']:.2f}"
```

`classify_delta` is left unchanged — it's a probe-triage classifier, not a bake gate; tightening it would invalidate `field_rollup` history across 23k experiments.

**Promotion wrapper** (`data/scripts/promote_candidate.py`, new):

1. Look up candidate by name in `experiments`.
2. Look up current baseline via `settings.current_bake_hash` → matching `experiments` row.
3. Call `is_promotable(candidate, baseline, kind)`.
4. On pass: write new `current_bake_hash` to `settings`, snapshot base.py to `.bak_pre_bake_<N>`, append row to `bakes` table.
5. On fail: print reason, exit 1, no writes.

This codifies the manual checklist into a guarded transition.

**Audit table** (schema migration):

```sql
CREATE TABLE bakes (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    prev_bake_hash TEXT,
    new_bake_hash TEXT NOT NULL,
    candidate_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    baseline_car_mdd REAL,
    candidate_car_mdd REAL,
    candidate_dd REAL,
    delta REAL
);
```

**Tests** (`tests/test_promote_gate.py`, new): 6 cases covering boundaries — dd=10.0 (reject), dd=9.99/lift=+0.0019 tune (reject), dd=9.99/lift=+0.0021 tune (accept), dd=9.99/lift=+0.0040 structural (reject), dd=9.99/lift=+0.0051 structural (accept), dd=11.0/lift=+0.05 (reject).

**Champion grandfathering:** current `S001_LIVE` has dd = 10.4 and **fails** the new gate. The gate is in force from day 1 but does not retroactively demote — it only blocks future promotions. The natural transition: phase B's structural sweep produces a dd < 10 winner, which becomes the first gate-conformant champion. From then on, all promotions are gated.

## Search & rollout plan

### Phase C₁ — parser fix (~1 day)

- **Files:** `data/scripts/score_probes.py`, `tests/test_score_probes_parser.py` (new), `data/scripts/rescore_historical.py` (new).
- **Verification:** unit tests + live regression (R493 `n_results` jumps 3 → ~20).
- **Rescore:** R465–R553 backfill, read-only with respect to bakes.
- **Commit per task** (memory: auto-commit authorized for qc_work).

### Phase C₂ — bake gate (~½ day)

- **Files:** `data/s001/fundamental_probes.py` (constants + helper), `data/scripts/promote_candidate.py` (new), schema migration adding `bakes` table, `tests/test_promote_gate.py` (new).
- **Verification:** 6 unit cases + dry-run on `S001_LIVE` (must reject because dd=10.4 ≥ 10.0).
- No backtests run.

### Phase B — vol overlay (≈3–5 days incl. backtests)

**Round B₁ — coarse Latin-hypercube sweep, 128 specs:**

- Spec naming: `S001_R{N}_volscale_w{RV_WIN}_h{RV_HIST}_dz{DZ}_sl{SL}_fl{FL}` — explicit underscore-anchored tokens, no `_in_/_gt_/_lt_` substring traps.
- LHS over the 5-d space; 128 cells.
- Plus ≥5 untested fundamental probes layered on top of the vol overlay (memory rule: every round must include ≥5 untouched fundamentals from `fundamental_fields` where `status='untested'`).
- All specs run with grandfathered `current_bake_hash`. No bakes during sweep.

**Scoring B₁:**
- Apply `is_promotable(kind='structural')` → require `dd < 10` AND `Δcar_mdd ≥ +0.005`.
- ≥1 pass: pick top by car_mdd (tie-break: lowest dd).
- 0 pass but a dd<10 frontier exists: compute `(car_mdd, dd)` Pareto over all dd<10 specs; top quartile seeds B₂.
- 0 pass and no dd<10 anywhere: stop. RVP signal cannot break the floor with this strategy. Escalate to a follow-up design that explores ATR-pct, trailing-DD-pct, or position-level vol-scaling.

**Round B₂ — refinement (64–96 specs):**
- B₁ found a winner: refine each param to its immediate neighbors in the discrete search set (e.g. winner `RV_WIN=20` → also try `15` and `30`); stack 5 untouched fundamentals.
- B₁ found Pareto-only: explore neighborhood; accept +0.002 lift over best dd<10 spec from B₁ as soft anchor.

**3x deterministic verify:** for any candidate clearing the gate, queue 3 identical reruns (random seeds locked in QC). Promotion only on 3 identical metric tuples.

**Rollback:**
- Each phase commits `.bak_pre_bake_*` snapshot of base.py (existing convention).
- C₁/C₂ infra reverts via standard `git revert`.
- B's overlay disables to identity by setting `VOL_DEADZONE=1.0` and `VOL_FLOOR=1.0` — no code revert needed.

**Wall-clock:** ~5–7 days end-to-end. Dominated by QC backtest queue throughput at `rate_limit_delay_ms=8237` (~18 min/spec); B₁ would be ~38h sequential but parallelizes across QC runners.

## Hard constraints honored

From memory `feedback_s001_hard_constraints` and `feedback_s001_cash_locked_70k`:

- `WT_CAP ≤ 0.07` — unchanged.
- `GROSS_HIGH ≤ 1.0` — unchanged; overlay only multiplies down.
- QQQ-only universe — unchanged.
- `Resolution.DAILY` — unchanged.
- `before_market_open("QQQ", 300)` — unchanged.
- Calendar regime signals forbidden — RVP uses realized vol on closed bars, an operational/market-status signal, permitted.
- `STARTING_CASH = 70000` — unchanged.
- Bake threshold ≥ +0.005 for structural changes (overlay), ≥ +0.002 for tune — both with 3x deterministic verify.
- Each round includes ≥5 untested fundamental probes — encoded in B₁ and B₂ spec generation.

## Success criteria

- **C₁:** R493 rescore yields ~20 parsed specs (up from ~3).
- **C₂:** gate rejects `S001_LIVE` (proves enforcement); accepts a synthetic dd=9.5/lift=+0.006 input.
- **B:** baked champion with car_mdd > 2.008 AND dd < 10.0, 3x verified.

## Out of scope

- Replacing `_dynamic_gross()` (augmentation only).
- Changing `WT_CAP`, `GROSS_HIGH`, or universe (hard caps).
- Per-position volatility scaling (could be a future component if RVP-overlay alone is insufficient).
- Migrating away from current spec naming convention (the parser fix is registry-aware, no rename needed).
