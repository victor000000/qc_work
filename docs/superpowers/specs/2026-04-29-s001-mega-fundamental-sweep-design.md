# S001 Mega Fundamental-Field Sweep — Design

**Date:** 2026-04-29
**Strategy:** S001 (QQQ daily mean-reversion)
**Goal:** Coarsely test every templatable fundamental field (891 across 8 containers) against four mechanism categories — entry / exit / score / conv (six cells per field) — in a single mega-round, then phase down to leaders.

## 1. Motivation

Today's S001 probe pipeline (Phase 1 / v2 sweep / v3 coarse / v3 refine) tests fundamentals only as a `score *= boost` lever inside `_scan_entries`. Of 979 fundamental fields in `S001.db.fundamental_fields`, 891 have a stored probe template (`probe_threshold IS NOT NULL`); 927 are still `status='untested'`, and the 52 already touched were tested only on the score axis. A field that's harmful for score selection might still help as an entry filter, an exit modulator, or a sizing (conv) lever — those mechanisms have never been swept. Per user direction (2026-04-29): treat ALL templatable fields as untested, sweep all four mechanism categories in one mega-round, then narrow.

The 88 fields missing templates are out of scope for this design — they need catalogue templates seeded via the existing emit/catalogue scripts before they can be probed in any mechanism.

## 2. Scope and constraints

**In-scope (Phase A — this design):**
- One mega-round emitting ~5349 specs covering 891 templatable fields × 6 mechanism cells.
- A regime-context refactor of `base.py` to expose clean injection anchors for entry-side and exit-side probes.
- Schema and parser additions so the existing scoring pipeline can route mega specs.

**Out-of-scope (Phase B/C — separate plans):**
- Mag/gate/threshold percentile sweep on Phase A leaders (Phase B).
- Refine grid on Phase B winners (Phase C).
- Automated bake decisions. Bakes remain manual per existing convention.

**Hard constraints carried from S001 memory:**
- `WT_CAP ≤ 0.07`, `GROSS_HIGH ≤ 1.0`, QQQ-only, `Resolution.DAILY`, `before_market_open("QQQ", 300)` (5h pre-market). Calendar regime conditionals forbidden.
- `STARTING_CASH = 70000`. Locked.
- Pure-fundamental hard skips spike DD (8.6→13-20%) — entry-skip mechanism MUST be regime-gated. Default gate for skip cells: `decline > .10`.
- Bake threshold = ≥+0.001 over baseline, no verify required. **At sweep size ~5349 the false-positive count at +0.001 is non-trivial; this design raises the mega-cell promotion threshold to +0.0015 (matches the existing `HOT_THRESHOLD`). Manual bake review unchanged.**

## 3. Mechanism enumeration

Six cells per field, dispatched by `mech` key:

| # | mech    | side                        | action template     | default mag | regime gate (entry-side) | location |
|---|---------|-----------------------------|---------------------|-------------|--------------------------|----------|
| 1 | `score` | good (probe_op as-defined)  | `score *= {mag}`    | 1.10        | `decline > .05`          | entry    |
| 2 | `skip`  | bad (probe_op flipped)      | `continue`          | n/a         | `decline > .10`          | entry    |
| 3 | `stop`  | bad (probe_op flipped)      | `stop *= {mag}`     | 0.85        | none (per-position)      | exit     |
| 4 | `petgt` | good (probe_op as-defined)  | `petgt *= {mag}`    | 1.15        | none (per-position)      | exit     |
| 5 | `convg` | good (probe_op as-defined)  | `conv *= {mag}`     | 1.15        | `decline > .05`          | entry    |
| 6 | `convb` | bad (probe_op flipped)      | `conv *= {mag}`     | 0.70        | `decline > .05`          | entry    |

`flip_op`: `>`↔`<`, `>=`↔`<=`, `in`→`notin`, `eq`→`neq`. The current DB has 758 `>` / 130 `<` / 3 `in` / 0 `eq` templated fields, so all 891 fields produce a meaningful inverse. `render_cell` returning `None` is preserved as a safety valve for future categorical fields whose inverse would be ambiguous (e.g. `in [...]` arrays covering >50% of the universe), but no current field triggers it.

**Cell-count audit (concrete, 891 templated fields):**

| mech    | count | notes |
|---------|-------|-------|
| score   | 891   | all templated fields |
| skip    | 891   | inverse exists for all current ops |
| stop    | 891   | same  |
| petgt   | 891   | all templated fields |
| convg   | 891   | all templated fields |
| convb   | 891   | inverse exists for all current ops |
| **total** | **5346** | + 3 NOOPs = **5349 specs** |

## 4. base.py refactor

### 4.1 Regime dict computed once per `on_data` tick

```python
def on_data(self, data):
    if not self._initialized: ... self._initialized = True
    equities = [s for s in data.bars.keys()
                if s.security_type == SecurityType.EQUITY
                and s not in self._hedge_syms]
    self._regime = self._compute_regime()        # NEW
    self._scan_exits(data, equities)
    if self.time.weekday() == 0:
        self._scan_entries(data, equities)

def _compute_regime(self):
    try: qa = list(self.history[TradeBar](self._qqq_sym, 30, _RD))
    except (AttributeError, KeyError, ValueError): qa = []
    try: ha = list(self.history[TradeBar](self._bond_sym, 30, _RD))
    except (AttributeError, KeyError, ValueError): ha = []
    def _r(bars, n):
        if len(bars) <= n or f_(bars[-n].close) <= 0: return None
        return (f_(bars[-1].close) - f_(bars[-n].close)) / f_(bars[-n].close)
    self._qa_scan = qa     # alias for baked probes (BAKE-8/16/29-AB/53-58/62)
    self._ha_scan = ha
    return {
        'qa': qa, 'ha': ha,
        'qd5': _r(qa, 5), 'qd10': _r(qa, 10), 'qd20': _r(qa, 20),
        'bd5': _r(ha, 5), 'bd10': _r(ha, 10), 'bd20': _r(ha, 20),
    }
```

`_scan_entries` and `_scan_exits` read `self._regime[...]` instead of recomputing.
`self._qa_scan` / `self._ha_scan` retained as aliases (set inside `_compute_regime` to `self._regime['qa']` / `self._regime['ha']`) so existing baked probes (BAKE-8/16/29-AB/53-58/62) keep working without touch-ups. The current PERFOPT cache block at lines 121-124 of `_scan_entries` (`try: self._ha_scan = list(...)`) is removed — `_compute_regime` is now the single owner of those caches.

### 4.2 Two explicit injection anchors

```python
# inside _scan_entries, after conv computation, before existing baked probes:
   # --- ENTRY INJECT POINT ---

# inside _scan_exits, after the nm/qr→stop/petgt block, before the
# `if pnl < -stop or pnl > petgt:` check:
   # --- EXIT INJECT POINT ---
```

Existing baked probes (R166→R602) sit between the ENTRY anchor and `candidates.append`. Mega-round entry-side cells splice AT the anchor, so they fire BEFORE the baked stack — meaning their `continue` skips/conv mults reach the baked probes and downstream selection naturally. Baked probes' execution order doesn't change.

The EXIT anchor is new. It mutates `stop` and `petgt` locals before the comparison. Mega exit cells inject here.

## 5. fundamental_probes.py rewrite

### 5.1 Public API

```python
MECHANISMS = ('score', 'skip', 'stop', 'petgt', 'convg', 'convb')
# ENTRY_BIND: existing BIND constant from fundamental_probes.py (the
# `_ops_z`/`_vr_z`/`_ers_z`/... attribute prelude that Phase 1 already uses,
# fundamental_probes.py:119-132). Reused verbatim — no behavior change.
ENTRY_BIND = BIND       # alias for clarity at call sites
# EXIT_BIND: same attribute prelude, but indented one level deeper to sit
# inside `_scan_exits`'s `for sym in equities:` loop. Generated by
# re-indenting BIND, not maintained as a separate string.
EXIT_BIND  = _reindent(BIND, extra_spaces=1)

def render_cell(field_row, mech, round_n, mag=None, gate_override=None):
    """Return (spec_name, body, location) or None.
    location ∈ {'entry', 'exit'} — generator splices at matching anchor."""

def emit_mega_round(db_path, round_n, mechanisms=MECHANISMS, force_all=True):
    """Yield (spec_name, body, location) for every (field, mech) cell."""

def pick_fields(db_path, k, classification='untested', bake_hash=None,
                force_all=False):
    """Existing API + force_all flag bypassing NOT EXISTS / classification scoping."""
```

### 5.2 Spec-name format

```
S001_R{N}_mg_{mech}_{cs}_{field}

Examples:
  S001_R603_mg_score_ops_revenue_growth
  S001_R603_mg_skip_ers_diluted_eps_growth
  S001_R603_mg_petgt_vr_pe_ratio
  S001_R603_mg_convb_bs_long_term_debt
```

No threshold or op suffix in the name — mech + field-row's stored template fully determine the cell. The `_mg_<mech>_<cs>_` prefix is fully anchored by regex, so the trailing field name can contain `_in_`, `_gt_`, etc. without triggering the v1 parsing bug.

### 5.3 `flip_op` and inverse-condition rendering

```python
def flip_op(op):
    return {'>': '<', '<': '>', '>=': '<=', '<=': '>=',
            'eq': 'neq', 'in': 'notin'}[op]

# build_condition gains two branches:
#   op='neq'   : f"{var} != {parsed!r}"   for categorical scalar
#   op='notin' : f"{var} not in {tup_repr}"
```

`render_cell` returns `None` for `mech ∈ {skip, stop, convb}` only when the inverse is provably ambiguous — concrete rule: `op == 'in'` AND the threshold array covers more than half of the universe of distinct observed values. With 3 templated `in` fields today and small thresholds, this guard fires zero times in practice; it exists as a safety valve.

### 5.4 Cell body templates

**Entry-side (score/skip/convg/convb):**
```python
"""   try:
    _v = f_({accessor})
    if {cond} and ({gate}): {action}
   except: pass"""
```

**Exit-side (stop/petgt):**
```python
"""    try:
     _v = f_({accessor})
     if {cond}: {action}
    except: pass"""
```
(One indent level deeper — sits inside the per-position `for sym in equities` loop in `_scan_exits`.)

## 6. score_probes.py routing

### 6.1 New regex (anchored, no substring trap)

```python
MEGA_NAME_RE = re.compile(
    r'^S001_R(?P<round>\d+)_mg_'
    r'(?P<mech>score|skip|stop|petgt|convg|convb)_'
    r'(?P<cs>[a-z]+)_(?P<field>.+)$'
)
```

### 6.2 Routing branch

Add the mega branch first in `score_round`'s match-cascade (mega → v3 coarse → v3 refine → v2 sweep → v1 default). The `_mg_` infix is unique to mega specs, so order matters only for code clarity:

```python
mega = MEGA_NAME_RE.match(row['name'])
if mega:
    mech = mega.group('mech')
    cs   = mega.group('cs')
    field_name = mega.group('field')
    container = CONTAINER_FROM_SHORT.get(cs)
    cur.execute("SELECT * FROM fundamental_fields WHERE container=? AND field_name=?",
                (container, field_name))
    f = cur.fetchone()
    if f is None: continue
    delta = row['car_mdd'] - baseline
    cls = classify_delta(delta)
    op_used = f['probe_op'] if MECH_DEFAULTS[mech]['side'] == 'good' \
              else flip_op(f['probe_op'])
    cur.execute("""INSERT INTO probe_results
        (field_id, experiment_name, round_n, bake_hash, noop_baseline,
         spec_car_mdd, delta, classification, applied_op, applied_threshold,
         applied_gate, applied_boost, recorded_at, is_sweep_variant,
         sweep_stage, mechanism)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)""",
        (f['id'], row['name'], round_n, bake_hash, baseline,
         row['car_mdd'], delta, cls, op_used, f['probe_threshold'],
         MECH_DEFAULTS[mech]['gate'], MECH_DEFAULTS[mech]['mag'], now, mech))
    n_results += 1
    touched_field_ids.add(f['id'])
    continue
```

Mega rows do NOT trigger sweep-winner promotion. `sweep_phase` stays untouched.

### 6.3 `field_rollup` scoping

Update the rollup read to ignore non-score mechanism rows:
```sql
SELECT classification FROM probe_results
WHERE field_id = ? AND bake_hash = ?
  AND (mechanism IS NULL OR mechanism = 'score')
```
Otherwise a "skip is hot" cell would mark the field globally `hot` and disrupt v3 pickup. Mega leaders for `skip`/`stop`/`petgt`/`convg`/`convb` surface only via direct `probe_results` queries (Phase B picker).

## 7. DB schema change

```sql
ALTER TABLE probe_results ADD COLUMN mechanism TEXT;
CREATE INDEX IF NOT EXISTS idx_probe_results_mechanism
    ON probe_results(field_id, mechanism, bake_hash);
```

Existing v1/v2/v3 rows: `mechanism = NULL`.
Mega rows: `mechanism ∈ MECHANISMS`.

## 8. Generator — `data/gen_s001_R603_mega.py`

Single-purpose script. Layout:

```python
"""R603 mega-round: 6 mechanisms × ~979 fields ≈ 5580 specs."""
import ast, hashlib, sqlite3, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from s001.fundamental_probes import (
    emit_mega_round, ENTRY_BIND, EXIT_BIND, current_bake_hash,
)

BASE = '/home/txy/qc_work/data/s001/s001_20260425_base.py'
DB   = '/home/txy/qc_work/data/S001.db'
ROUND = 603

with open(BASE) as f: BASE_CODE = f.read()
got = hashlib.md5(BASE_CODE.encode()).hexdigest()
expected = current_bake_hash(DB)
assert got == expected, f'Hash mismatch {got} vs {expected}'

ENTRY_ANCHOR = '   # --- ENTRY INJECT POINT ---'
EXIT_ANCHOR  = '   # --- EXIT INJECT POINT ---'
assert ENTRY_ANCHOR in BASE_CODE and EXIT_ANCHOR in BASE_CODE

specs = []
# 3 NOOPs (entry-side, harmless comment splice — establishes baseline)
for i in range(3):
    code = BASE_CODE.replace(ENTRY_ANCHOR, f'   # mega_noop_{i}\n' + ENTRY_ANCHOR)
    specs.append((f'S001_R{ROUND}_VBAKEMG_NOOP_{i}', code, 1))

for name, body, loc in emit_mega_round(DB, ROUND, force_all=True):
    if loc == 'entry':
        code = BASE_CODE.replace(ENTRY_ANCHOR, ENTRY_BIND + body + '\n' + ENTRY_ANCHOR)
    else:
        code = BASE_CODE.replace(EXIT_ANCHOR,  EXIT_BIND  + body + '\n' + EXIT_ANCHOR)
    specs.append((name, code, 5))

# Pre-flight: AST-parse every spec
for name, code, _ in specs:
    try: ast.parse(code)
    except SyntaxError as e: sys.exit(f'SYNTAX ERROR in {name}: {e}')

# Coverage matrix: assert each (mech, container) cell count matches the
# Section 3 audit. Concretely, for each mech in MECHANISMS, sum over all
# containers; expected total = 891 (or fewer if any field's inverse drops).
# Print one line per mechanism so anomalies are visible before commit.
from collections import Counter
ctr = Counter()
for n, _, _ in specs:
    if n.startswith(f'S001_R{ROUND}_VBAKEMG_NOOP_'): continue
    parts = n.split('_'); ctr[parts[3]] += 1     # parts[3] is the mech token
for m in MECHANISMS:
    assert 800 <= ctr[m] <= 891, f'{m}: {ctr[m]} out of expected band'
print('Mechanism counts:', dict(ctr))

# Bulk insert into backtest_queue
con = sqlite3.connect(DB); cur = con.cursor()
for n, c, pri in specs:
    h = hashlib.md5(c.encode()).hexdigest()
    cur.execute(
        "INSERT INTO backtest_queue (name, code, status, priority, "
        "submitted_at, code_hash, project_id) "
        "VALUES (?, ?, 'queued', ?, datetime('now'), ?, NULL)",
        (n, c, pri, h))
con.commit()
print(f'Inserted {len(specs)} R{ROUND} specs')
```

**Pre-flight checks the generator runs:**
1. Hash-verify base.py matches `settings.current_bake_hash`.
2. Both ENTRY/EXIT anchors present in BASE_CODE.
3. AST-parse every generated spec body.
4. Coverage matrix: assert each (mech, container) cell count matches expected (within drop budget for categorical inverses).
5. Print histogram of spec counts per mechanism before commit.

## 9. Run sequence

| Round | Purpose | Spec count |
|-------|---------|------------|
| **R603 (mega)** | All 891 templated fields × 6 mechanisms, breadth | ~5349 |
| R604 (Phase B) | Top 50 leaders × percentile-threshold sweep (3 thresholds × 4 mags = 12 cells/leader) | ~600 |
| R605 (Phase C) | Top 10 confirmed leaders × refine grid (~26 cells each) | ~260 |
| R606+ | Bake winners; back to existing v3 plumbing for compounding | normal |

**Phase B picker query (after R603 scoring):**
```sql
SELECT field_id, mechanism, MAX(delta) AS best_delta
FROM probe_results
WHERE bake_hash = ? AND mechanism IS NOT NULL
  AND delta > 0.0015
GROUP BY field_id, mechanism
ORDER BY best_delta DESC
LIMIT 50
```

## 10. Testing

- **Unit tests** for `flip_op`, `render_cell` per mechanism, `MEGA_NAME_RE` parse round-trip.
- **Generator dry-run**: emit specs to a tmp DB; verify cell counts match Section 3's audit (±10% for categorical inversions).
- **Smoke test**: pick 5 specs at random from R603 output, run them locally, confirm they execute without error and produce a `car_mdd` value.
- **Score-pipeline test**: insert 3 fake R603 results into `experiments` table, run `score_probes --round 603 --bake-hash <hash>`, verify `probe_results` rows have correct `mechanism` value.

## 11. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Pure-fundamental skip spikes DD | Default gate `decline > .10`; matches existing baked C1/C3 pattern. |
| Exit-side templates break invested-position iteration | EXIT body is wrapped in `try/except: pass`; can't crash the position loop. |
| 5349 specs × backtest cost | Cron handles queue; +0.0015 promotion threshold filters statistical FPs. |
| `field_rollup` poisoned by non-score mechanisms | Rollup query scoped to `mechanism IS NULL OR mechanism = 'score'`. |
| Categorical fields with no meaningful inverse | `render_cell` returns `None`; generator drops the cell. Documented drop count in Section 3. |
| Base hash drift mid-generation | Hash-verify at top of generator; settings table is source of truth. |
| New regex collides with existing v1 specs | `_mg_` infix is unique; v1 specs lack it. Scored test confirms. |

## 12. Out-of-scope reminders

- No automated bake. Bakes remain manual.
- No mechanism-specific magnitude/gate sweep in R603. That's Phase B.
- No new CLI/UI surface.
- No backwards-compat shims; v1/v2/v3 specs continue working unchanged.
- No verification across multiple NOOP runs beyond the existing 3-NOOP requirement.
