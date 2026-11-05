# S001 Lambda-Base Design

**Date:** 2026-05-04
**Status:** Approved (user said yes to hybrid B+C, lambda table)
**Goal:** Compress `s001_20260504_dsl2_base.py` (1470 lines, 167 active bakes) to ~500 lines via central lambda table while preserving NOOP=2.42218 bit-identical.

## Why the current base is "too large"

Each bake is a 4-7 line `try/except` block. After 200+ bakes, the file balloons. Prior compression already eliminated alias re-fetching (-365 lines pass-1) and migrated 31 simple bakes to a single-helper call (-77 lines DSL2). But ~136 bakes remain in original style at ~6 lines each = ~800 lines of bake scaffolding.

The deeper problem is **per-bake overhead**: every new bake adds 4-7 lines and one try/except. There's no central registry. Auditing "what fires for vs<15 cohort?" requires grepping. Future-proof solution requires a table.

## User goals (A+C+D from brainstorm)

| Goal | Target |
|---|---|
| **A — Pure size** | 1470 → ~500 lines (-66%) |
| **C — Performance** | Same or faster per-tick CPU |
| **D — Auditability** | All bakes in one scannable table |

## Architecture

### Core abstraction: lambda-per-bake table

```python
BAKES_ENTRY = [
    # (id, action_str, gate_lambda)
    ('B71', 'score*1.30', lambda c: _gt(c.opm_1y, 0.30) and c.decline > 0.05),
    ('B72', 'score*1.40', lambda c: _gt(c.opm_1y, 0.30) and _gt(c.fcfg_1y, 0.10) and c.decline > 0.07),
    # ...
    # Multi-step bakes use def function:
    ('B22', 'skip', _b22_zombie),  # see _b22_zombie defined separately
]
```

### Components

**1. `_BakeCtx` class** — per-symbol context with pre-extracted fields
```python
class _BakeCtx:
    __slots__ = ('decline', 'qaccel', 'opm_1y', 'gm_1y', 'rg_1y', 'roe_1y', 'peg', 'pe',
                 'vs', 'fhg', 'pg', 'sector_code', 'fcfy', ...)  # all fields used by any bake
```

**2. Safe accessors**
```python
def _safe(obj, *attrs):
    """Walk attribute path; return None on any None or AttributeError."""
    try:
        for a in attrs:
            if obj is None: return None
            obj = getattr(obj, a, None)
        return float(obj) if obj is not None else None
    except (TypeError, ValueError): return None

def _gt(v, x): return v is not None and v > x
def _lt(v, x): return v is not None and v < x
```

**3. Runner**
```python
def _run_bakes(ctx, bakes, score, conv, wt_tilt, alt_score, alt_blend, stop, petgt):
    skip = False
    for bid, action, gate in bakes:
        try:
            if not gate(ctx): continue
            # action like 'score*1.30', 'score+0.50', 'skip', 'conv*0.50', 'stop*0.85', 'petgt*1.50'
            if action == 'skip': skip = True; break
            kind, _, val = action.partition('*' if '*' in action else '+')
            v = float(val)
            op = '+' if '+' in action else '*'
            if kind == 'score':
                score = score * v if op == '*' else score + v
            elif kind == 'conv': conv *= v
            elif kind == 'wt_tilt': wt_tilt *= v
            elif kind == 'stop': stop *= v
            elif kind == 'petgt': petgt *= v
        except: pass
    return skip, score, conv, wt_tilt, alt_score, alt_blend, stop, petgt
```

(Action parsing happens once per call, ~167 string-splits per symbol — negligible. Could be optimized to pre-parse at module load if needed.)

**4. Hybrid B+C for heterogeneous bakes**
- Pre-extract reusable derived values (cum_ret_7d, v_recent_3, etc.) into `_BakeCtx` once per symbol.
- For one-off complex bakes (~10-15), define `def _bXX(c): ...` returning bool, reference in BAKES list.

### File layout (`s001_20260505_lambda_base.py`)

| Section | Lines |
|---|---|
| Imports + constants | ~25 |
| Helpers (`_safe`, `_gt`, `_lt`, `_run_bakes`) | ~40 |
| `_BakeCtx` class with `__slots__` | ~30 |
| `_compute_ctx_for_entry(self, sym, ...)` — populates ctx fields | ~80 |
| `_compute_ctx_for_exit(self, sym, ...)` | ~20 |
| `BAKES_ENTRY` table (~140 simple lambdas + ~30 complex) | ~200 |
| `BAKES_EXIT` table (~14 exit bakes) | ~25 |
| Complex `def _bXX` helpers (~10-15 of them) | ~80 |
| `MeanReversionAlgorithm` class (init, on_data, regime, dynamic_gross, scan_exits, scan_entries) | ~200 |
| `execute_pending_orders` + helpers | ~15 |
| **Total** | **~715** |

Conservative estimate ~715 lines; aggressive (less commenting, tighter ctx) could hit ~500.

## Data flow

```
on_data → _compute_regime → for sym in equities:
  _scan_exits / _scan_entries:
    1. Pre-filter (price, volume, decline, vol_climax)
    2. ctx = _compute_ctx_for_entry(sym, ...)  // populates _BakeCtx fields
    3. skip, score, conv, ... = _run_bakes(ctx, BAKES_ENTRY, score, conv, ...)
    4. if skip: continue
    5. candidates.append((sym, score, conv, wt_tilt, ...))
```

## Migration plan

**Phase 0:** Create `s001_20260505_lambda_base.py` (NEW file, dsl2_base unchanged).
**Phase 1:** Copy verbatim — header/constants/`_compute_regime`/`_dynamic_gross`/`execute_pending_orders`.
**Phase 2:** Build helpers + runner + `_BakeCtx` skeleton + ctx populator stubs.
**Phase 3:** Migrate 31 simple bakes that DSL2 already handled (re-derive into BAKES_ENTRY table). Smoke test → NOOP=2.42218.
**Phase 4:** Migrate next 30 simple bakes. Smoke test.
**Phase 5:** Migrate next 30. Smoke test.
**Phase 6:** Migrate next 30. Smoke test.
**Phase 7:** Migrate remaining ~50, including complex bakes via def functions. Smoke test.
**Phase 8:** Migrate exit bakes (~14). Smoke test.
**Phase 9:** If NOOP matches, switch memory pointer to lambda_base.

Each smoke test = queue one NOOP_DSL3_phaseN spec, verify NOOP=2.42218 before continuing.

## Risk & mitigation

| Risk | Mitigation |
|---|---|
| Translation error in lambda gate | Per-batch smoke tests catch regressions |
| Order-dependent additive bakes (BAKE-127, BAKE-130) misordered | Preserve list order; `_run_bakes` iterates in order |
| Performance regression from lambda overhead | Pre-extract fields in ctx → no getattr in hot path |
| Action string parsing per-call cost | Pre-parse to `(kind, op, val)` tuple at module load if perf matters |
| Heterogeneous bake breaks lambda mold | Use `def _bXX` for ~10-15 complex ones |
| `__slots__` doesn't cover field used by some bake | First migration phase populates ctx; missing field = AttributeError caught by try/except |

## Acceptance criteria

1. `s001_20260505_lambda_base.py` < 800 lines
2. NOOP smoke test returns `2.422178217821782` (bit-identical to dsl2_base NOOP)
3. All 167 bakes preserved (no logic dropped)
4. File parses (no SyntaxError)
5. Memory pointer updated; future bakes added to `BAKES_ENTRY` list (1 line each)

## Out of scope

- Cleaning up rolled-back/dead bakes
- Architectural changes to score/conv/wt_tilt mechanism
- Performance benchmarking (only correctness tested)
- Migration of `s001_20260504_dsl_base.py` (working dsl2 stays as fallback)

## Future bake density

Once lambda_base lands, every new bake adds ONE LINE to `BAKES_ENTRY`:
```python
('B243', 'score*1.15', lambda c: _gt(c.vs, 25) and _lt(c.vs, 35) and c.decline > 0.10),
```
Compared to current ~6 lines. Sustainable for next 100+ bakes.
