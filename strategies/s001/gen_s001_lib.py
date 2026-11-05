"""S001 generator library: declarative axes + audit gate + queue.

Replaces the per-round boilerplate (R1XXX hand-coded probe loops). Callers
declare a `Round` of `Probe`s; library builds spec codes, runs the audit
checks (fresh-field count, axis-cap, lever coverage, dedup), and queues.

Memory rules enforced:
  - >=8 truly fresh fundamental accessors per round (vs registry of all
    historical gen scripts)
  - axis-size cap ~20 unless probe targets fresh field
  - 128-spec minimum per round
  - same priority across all specs of a round
  - full lever coverage (score/petgt/stop/skip/conv must each appear)
  - md5 dedup (avoid IntegrityError noise)
  - bake-in-time: gen scripts always read latest base
"""

from __future__ import annotations

from s001.paths import WORKSPACE_ROOT, DATA_DIR
import re, glob, hashlib, qc_storage as storage
from dataclasses import dataclass, field
from pathlib import Path

# Paths
DB_PATH   = str(DATA_DIR / 'S001.duckdb')
BASE_PATH = str(WORKSPACE_ROOT / 'strategies/s001/s001_20260628_base.py')
GEN_GLOB  = str(WORKSPACE_ROOT / 'strategies/s001/**/gen_s001_R*.py')

ENTRY_MARKER = '   # --- ENTRY INJECT POINT ---'
EXIT_MARKER  = '   # --- EXIT INJECT POINT ---'
# Post-2026-05-09 score-system marker — for entry_signal lever probes
# and bakes that should live AFTER the multiplicative tail-chain.
SIGNAL_MARKER = '   # --- ENTRY SIGNAL BAKE INSERT ---'

# Mutation levers — every round MUST exercise each at least once.
# wt_tilt added 2026-05-09 after R1645/R1646 diagnostic showed score *= 1.05-1.25
# is too compressed to shift log2(log2(v)) rank order; wt_tilt is read at line ~1606
# of base, multiplied directly into position weight, so guaranteed to alter trade size.
LEVERS = ('score', 'petgt', 'stop', 'skip', 'conv', 'wt_tilt',
          'entry_signal', 'exit_signal',
          'entry_score_mtf', 'entry_score_regime', 'entry_score_conv')
# Relaxed 2026-05-17 — R2520-R2527 aux-waste audit: PA (petgt) 0/4,
# SS (stop) 0/4, RA (score-regime) 0/6 = 100% silent across 8 rounds.
# KA (skip) 1/5 with one catastrophic. Only score and conv showed any
# measurable Δ. Aux specs satisfying the dropped levers were pure waste
# (~4 specs/round → ~240 wasted backtests/day).
REQUIRED_LEVERS = ('score', 'conv')
# Regime gates that a probe's cohort can reference (regime-coverage check is separate)
REGIME_TOKENS = ('self._reg_', '_hyg_', '_qqq_', '_vxx_', '_dpanic')

# Default magnitude bands (probes pick one)
MAGS_BOOST  = (1.05, 1.10, 1.15, 1.25)
MAGS_DEMOTE = (0.70, 0.80, 0.85, 0.90)
MAGS_WIDE   = (0.85, 1.15, 1.30, 1.50)
MAGS_RANK   = (0.70, 0.85, 1.30, 1.50)  # guaranteed rank-shifters on log2log2v
PETGT_BOOST = (1.10, 1.20, 1.30)
STOP_TIGHT  = (0.70, 0.85, 0.95)
ADD_VALS    = (0.005, 0.010, 0.020, 0.040)
WT_TILT_BOOST  = (1.10, 1.25, 1.40, 1.60)
WT_TILT_DEMOTE = (0.60, 0.70, 0.80, 0.90)

# Mag bands proven productive across R1645-R1660 (~1100 probes audited).
# Use these in NEW gen scripts to avoid testing mags with 0% historical
# positive-hit rate.
#   *= mults: (1.05–1.13) = 0% across 518 specs (mostly cap-bound)
#             (1.40)      = 0% across 50 specs + 18 negative (poison, repeatable)
#             demote      = 0% across 277 specs (m40–m95)
#             (1.60)      = 10% positive hit rate (best)
#             (1.70/2.00) = 12-25% (small samples; treat as exploratory)
#             (1.25)      = 2.3% (moderate, useful for control)
#   += additive: a5/a10  = 0% across 138 specs
#                a20     = 4.8% (best)
#                a40     = 2.4%
#                a80+    = 0% across 100+ specs
ADD_VALS_PROVEN  = (0.020, 0.040)            # 2× more efficient than ADD_VALS
MAGS_PROVEN_BOOST = (1.25, 1.60, 1.70)        # avoids 0%-hit zones


@dataclass
class Probe:
    name: str                       # axis label (must be unique within round)
    lever: str                      # one of LEVERS
    cohort: str = ''                # cohort gate (e.g. '_qpos and _hyg_up5')
    fund: str = ''                  # optional fundamental check (e.g. '_ngt(_ey_c,0.08)')
    extra: str = ''                 # extra inline conds joined with ' and '
    op: str = '*='                  # '*=' | '+=' | 'continue'
    mags: tuple = MAGS_WIDE         # magnitudes; ignored for op='continue'
    inject: str = 'ENTRY'           # 'ENTRY' or 'EXIT'
    wrap_try: bool = True           # wrap in try:/except: pass for safety
    fresh_fields: tuple = ()        # accessor strings (e.g. '_vr_z.peg_ratio') marked fresh

    def expand(self) -> list[tuple[str, str]]:
        """Return list of (label_suffix, probe_text)."""
        body_parts = []
        if self.cohort: body_parts.append(self.cohort)
        if self.fund:   body_parts.append(self.fund)
        if self.extra:  body_parts.append(self.extra)
        body = ' and '.join(body_parts) if body_parts else 'True'

        out = []
        for m in (self.mags or (1.0,)):
            if self.op == 'continue':
                stmt = f'if {body}: continue'
                tag = self.name
            elif self.op == '+=':
                stmt = f'if {body}: {self.lever} += {m}'
                tag = f'{self.name}_a{int(m*1000)}'
            else:
                stmt = f'if {body}: {self.lever} *= {m}'
                tag = f'{self.name}_m{int(m*100)}'
            if self.wrap_try:
                probe_txt = f'   try:\n    {stmt}\n   except: pass\n'
            else:
                probe_txt = f'   {stmt}\n'
            out.append((tag, probe_txt))
        return out


@dataclass
class Round:
    rid: int                        # round number (e.g. 1645)
    probes: list[Probe] = field(default_factory=list)
    noops: int = 1  # 2026-05-17 user-reduced 3→2→1 for 16-spec budget; cross-round NOOP comparison detects drift
    priority: int = 1
    base_path: str = BASE_PATH

    def add(self, *probes):
        for p in probes:
            self.probes.append(p)
        return self

    def find_probe(self, name: str):
        """Look up a Probe by its axis name. Returns None if not found."""
        for p in self.probes:
            if p.name == name:
                return p
        return None


# ---------- registry ----------

_ACCESSOR_RE = re.compile(
    r'(_(?:vr|ops|ers|ac|er|sr|fs|bs|inc|cfs)_z)\.([a-z_][a-z_0-9]*)(?:\.([a-z_][a-z_0-9]*))?'
)

def used_accessors(exclude_round: int | None = None) -> dict[str, int]:
    """Scan all gen_s001_R*.py and return {accessor_string: occurrence_count}.

    `exclude_round` skips files like gen_s001_R{N}.py — useful when the
    current round being built shouldn't count itself in the registry.
    """
    counts: dict[str, int] = {}
    skip_token = f'gen_s001_R{exclude_round}.py' if exclude_round is not None else None
    for path in glob.glob(GEN_GLOB, recursive=True):
        if path.endswith('gen_s001_lib.py'): continue
        if skip_token and path.endswith(skip_token): continue
        try:
            src = open(path).read()
        except OSError:
            continue
        for m in _ACCESSOR_RE.finditer(src):
            obj, fld, sub = m.group(1), m.group(2), m.group(3)
            key = f'{obj}.{fld}' + (f'.{sub}' if sub else '')
            counts[key] = counts.get(key, 0) + 1
    return counts


def is_fresh(accessor: str, registry: dict[str, int] | None = None) -> bool:
    if registry is None:
        registry = used_accessors()
    return registry.get(accessor, 0) == 0


# ---------- audit ----------

class AuditFailed(Exception): pass


def audit(rnd: Round, registry: dict[str, int] | None = None) -> dict:
    if registry is None:
        registry = used_accessors(exclude_round=rnd.rid)

    spec_count = sum(len(p.expand()) for p in rnd.probes) + rnd.noops
    levers_seen = {p.lever for p in rnd.probes}
    fresh_seen = set()
    axis_sizes = {}
    duplicate_names = []
    name_seen = set()
    regime_axes = 0

    for p in rnd.probes:
        if p.name in name_seen: duplicate_names.append(p.name)
        name_seen.add(p.name)
        axis_sizes[p.name] = len(p.expand())
        for f in p.fresh_fields:
            if is_fresh(f, registry):
                fresh_seen.add(f)
        # Does cohort/extra reference a regime token?
        whole = (p.cohort or '') + ' ' + (p.extra or '')
        if any(tok in whole for tok in REGIME_TOKENS):
            regime_axes += 1

    issues = []
    warnings = []
    # Round-size floor 2026-05-17 (user updated): lowered 28 → 14.
    # User reduced /loop cadence 12m→6m and target 32→16 specs/round.
    # Allow 16 ±2 spec band (14-20). Multi-mag confirmation preserved (≥3 mags
    # per axis × 4-5 axes = 12-15 specs main + ~4 aux/NOOP = 16-19 total).
    if spec_count < 14:
        issues.append(f'spec_count={spec_count} < 14 (round-size floor — user 2026-05-19)')
    # fresh_fields requirement disabled 2026-05-11: investing-theme rounds
    # reuse registered accessors that have produced bakes. Novelty floor
    # superseded by theme-targeted exploration.
    pass
    # Score-family equivalence (2026-05-17 30m deep-review #2 fix):
    # R2529-R2531 SC absorber pattern wasted 6 specs, ALL destructive
    # (worst -0.20629 on R2531 SC_NOQ score *=). The SC absorber was
    # added only to satisfy 'score' in REQUIRED_LEVERS even when main
    # already had a score-family lever (wt_tilt/entry_signal/entry_score_*).
    # ALL score-family levers feed `score` per base.py:
    #   score += entry_signal + entry_score_mtf + entry_score_regime
    #          + entry_score_conv [+ wt_tilt indirectly via weight_score]
    # Any of these in main satisfies the score-coverage intent.
    SCORE_FAMILY = {'score', 'wt_tilt', 'entry_signal', 'entry_score_mtf',
                    'entry_score_regime', 'entry_score_conv',
                    'entry_score_quality', 'entry_score_gate'}
    missing_levers = set(REQUIRED_LEVERS) - levers_seen
    if 'score' in missing_levers and (levers_seen & SCORE_FAMILY):
        missing_levers.discard('score')
    if missing_levers:
        issues.append(f'missing required levers: {sorted(missing_levers)} (memory: full lever coverage)')
    if regime_axes < 3:
        issues.append(f'regime-gated axes={regime_axes} < 3 (memory: probe regime QQQ/HYG every round)')
    for axis, sz in axis_sizes.items():
        probe = next(p for p in rnd.probes if p.name == axis)
        is_fresh_axis = any(is_fresh(f, registry) for f in probe.fresh_fields)
        if sz > 20 and not is_fresh_axis:
            issues.append(f'axis {axis!r} size={sz} > 20 without fresh-field justification')
        # warn on score-multiplicative axes whose entire mag range is in rank-stable zone
        if probe.lever == 'score' and probe.op == '*=' and probe.mags:
            if all(0.95 <= m <= 1.10 for m in probe.mags):
                warnings.append(f'axis {axis!r} score *= {probe.mags} likely null-effect (compressed mag range)')
            # 2026-05-17 30m reconstruct #4: high-mag score *= on _qpos × HA-regime
            # × narrow-band sector cohorts = CATASTROPHIC interaction with
            # existing bakes. R2541 evidence: SC_QP_S308_HA_D12 m1.12 = -0.01258,
            # SC_QP_S205_HA_D12 m1.12 = -0.00557, SC_QP_S102_HA_D12 m1.07 = -0.00206.
            # Warn when probe combines high mag + this cohort shape.
            cohort_str = (probe.cohort or '')
            high_mags = [m for m in probe.mags if m > 1.10]
            if (high_mags and probe.op == '*=' and probe.lever == 'score'
                    and '_qpos' in cohort_str and '_reg_haccel' in cohort_str
                    and 'decline < 0.020' in cohort_str):
                warnings.append(
                    f'axis {axis!r} score *= {high_mags} > 1.10 × _qpos × HA × narrow-band '
                    f'risks catastrophic interaction (R2541: -0.005 to -0.013). '
                    f'Consider mag ≤ 1.08 or use _DEEP/_VRFY suffix to bypass.')
    # 2026-05-17 30m reconstruct #6: wt_tilt × deep-decline concentration risk.
    # R2551 evidence: 3 catastrophic outliers (-1.86 to -2.15 Δ) all on
    # wt_tilt × HA × decline > 0.04 × mag 1.07-1.10. Pattern: BOOSTing
    # already-down-8%+ stocks concentrates losses across cohort during
    # correlated drawdown periods.
    import re as _re_dd
    for axis, sz in axis_sizes.items():
        probe = next(p for p in rnd.probes if p.name == axis)
        if probe.lever != 'wt_tilt' or probe.op != '*=' or not probe.mags:
            continue
        cohort_str = (probe.cohort or '')
        # Detect deep-decline cohort (decline lo > 0.04)
        m = _re_dd.search(r'decline\s*>\s*(0\.\d+)', cohort_str)
        if not m:
            continue
        decline_lo = float(m.group(1))
        if decline_lo < 0.04:
            continue
        high_mags = [m for m in probe.mags if m >= 1.07]
        if high_mags:
            warnings.append(
                f'axis {axis!r} wt_tilt *= {high_mags} ≥ 1.07 × decline ≥ {decline_lo} '
                f'concentration risk (R2551: 3 cata -1.86 to -2.15 from this pattern). '
                f'Consider mag ≤ 1.06 or narrower decline band.')

    if duplicate_names:
        issues.append(f'duplicate axis names: {duplicate_names}')

    return {
        'spec_count': spec_count,
        'levers_seen': sorted(levers_seen),
        'fresh_fields': sorted(fresh_seen),
        'regime_axes': regime_axes,
        'axis_sizes': axis_sizes,
        'issues': issues,
        'warnings': warnings,
    }


# ---------- post-run diagnostics ----------

def round_effect_signature(rid: int, db_path: str = DB_PATH) -> dict:
    """Aggregate per-axis effect of a completed round.

    Returns {axis_name: {'specs': N, 'null': N, 'fired': N, 'pos_001': N, 'best_delta': ±}}.
    Used to flag axes that systematically null-effect or hurt across multiple rounds.
    """
    con = storage.connect(db_path)
    cur = con.cursor()
    cur.execute("""SELECT name, car_mdd, total_orders FROM experiments
                   WHERE name LIKE ? AND name LIKE '%NOOP%' AND car_mdd IS NOT NULL""",
                (f'S001_R{rid}_lp_%',))
    noops = cur.fetchall()
    if not noops:
        con.close()
        return {}
    noop_cm = sum(n[1] for n in noops) / len(noops)
    noop_orders = noops[0][2]
    cur.execute("""SELECT name, car_mdd, total_orders FROM experiments
                   WHERE name LIKE ? AND name NOT LIKE '%NOOP%' AND car_mdd IS NOT NULL""",
                (f'S001_R{rid}_lp_%',))
    rows = cur.fetchall()
    con.close()
    by_axis: dict[str, dict] = {}
    for name, cm, to in rows:
        # name = S001_R{rid}_lp_{axis}_{tag} or S001_R{rid}_lp_{axis}
        bare = name.replace(f'S001_R{rid}_lp_', '')
        axis = bare.split('_')[0]
        slot = by_axis.setdefault(axis, {'specs': 0, 'null': 0, 'fired': 0,
                                        'pos_001': 0, 'neg_005': 0, 'best_delta': 0.0})
        slot['specs'] += 1
        delta = cm - noop_cm
        if to == noop_orders and abs(delta) < 1e-6:
            slot['null'] += 1
        else:
            slot['fired'] += 1
            if delta > 0.001: slot['pos_001'] += 1
            if delta < -0.005: slot['neg_005'] += 1
            if abs(delta) > abs(slot['best_delta']): slot['best_delta'] = delta
    return by_axis


def null_effect_axes(rids: list[int], min_rounds: int = 1, db_path: str = DB_PATH) -> set[str]:
    """Return set of axis names whose entire family was null-effect across `rids`.

    Use as a soft hint when designing a new round: don't re-test these axis NAMES
    (the names tend to repeat — FA, FB, etc.). Caller can rename probes accordingly.
    """
    aggregate: dict[str, list[dict]] = {}
    for rid in rids:
        for axis, sig in round_effect_signature(rid, db_path).items():
            aggregate.setdefault(axis, []).append(sig)
    null_axes = set()
    for axis, sigs in aggregate.items():
        if len(sigs) < min_rounds: continue
        if all(s['fired'] == 0 for s in sigs):
            null_axes.add(axis)
    return null_axes


# ---------- emit + queue ----------

def emit(rnd: Round) -> list[tuple[str, str, int]]:
    """Build spec codes. Returns list of (spec_name, code, priority)."""
    base_src = Path(rnd.base_path).read_text()
    out: list[tuple[str, str, int]] = []
    spec_idx = 0

    # All 5 entry-signal accumulators sum together at the SIGNAL_MARKER.
    # Probes targeting any of them belong at that position for consistent
    # post-chain semantics. (entry_score_quality added 2026-05-09 to break
    # plateau via fundamental-quality signal class.)
    SIGNAL_LEVERS = {'entry_signal', 'entry_score_mtf', 'entry_score_regime',
                     'entry_score_conv', 'entry_score_quality',
                     'entry_score_gate'}  # P4 2026-05-10 — multiplicative
    for p in rnd.probes:
        # Route by inject + lever:
        # - inject='SIGNAL' OR lever ∈ SIGNAL_LEVERS → SIGNAL_MARKER (post-chain)
        # - inject='EXIT' → EXIT_MARKER
        # - default → ENTRY_MARKER (mid-chain, legacy)
        if p.inject == 'EXIT':
            anchor = EXIT_MARKER
        elif p.inject == 'SIGNAL' or p.lever in SIGNAL_LEVERS:
            anchor = SIGNAL_MARKER
        else:
            anchor = ENTRY_MARKER
        for tag, probe_txt in p.expand():
            salt = f'   # loop_salt_{rnd.rid}_{spec_idx}\n'
            code = base_src.replace(anchor, probe_txt + anchor, 1).replace(anchor, salt + anchor, 1)
            name = f'S001_R{rnd.rid}_lp_{tag}'
            out.append((name[:60], code, rnd.priority))
            spec_idx += 1

    # NOOPs (4+ for variance estimation)
    for k in range(rnd.noops):
        salt = f'   # noop_R{rnd.rid}_s{k}\n'
        code = base_src.replace(ENTRY_MARKER, salt + ENTRY_MARKER, 1)
        out.append((f'S001_R{rnd.rid}_lp_NOOP_{k}', code, rnd.priority))

    return out


def queue(rnd: Round, audit_result: dict | None = None,
          enforce_audit: bool = True, db_path: str = DB_PATH) -> dict:
    """Audit (optional) + queue specs. Returns summary."""
    if audit_result is None:
        audit_result = audit(rnd)
    if enforce_audit and audit_result['issues']:
        raise AuditFailed('\n'.join(audit_result['issues']))

    specs = emit(rnd)
    con = storage.connect(db_path)
    cur = con.cursor()
    inserted = skipped = 0
    for name, code, pri in specs:
        h = hashlib.md5(code.encode()).hexdigest()
        try:
            cur.execute(
                "INSERT INTO backtest_queue (name, code, status, priority, "
                "submitted_at, code_hash, project_id) VALUES (?, ?, 'queued', ?, datetime('now'), ?, NULL)",
                (name, code, pri, h)
            )
            inserted += 1
        except storage.IntegrityError:
            skipped += 1
    con.commit()
    con.close()
    return {'inserted': inserted, 'skipped': skipped, 'total_specs': len(specs)}


# ---------- short builders ----------

def fund_gt(accessor: str, thr: float) -> str:
    """Build a None-safe '> thr' check using base helper _ngt."""
    # accessor is e.g. '_vr_z.peg_ratio' or '_ops_z.fcf_growth.one_year'
    return f'_ngt({accessor},{thr})'

def fund_lt(accessor: str, thr: float) -> str:
    return f'_nlt({accessor},{thr})'

def fund_rg(accessor: str, lo: float, hi: float) -> str:
    return f'_nrg({accessor},{lo},{hi})'

def fund_inline_gt(local_name: str, accessor: str, thr: float) -> str:
    """When base doesn't yet bind a local, fetch via _g1 inline.
    Produces an expression that's a valid `if` body fragment using a walrus.
    Note: simpler pattern is to wrap probe with `try:` and use direct attribute.
    """
    # accessor like '_ops_z.field' or '_ops_z.field.timeframe'
    parts = accessor.split('.')
    obj = parts[0]
    args = ','.join(f"'{p}'" for p in parts[1:])
    return f'(({local_name}:=_g1({obj},{args})) is not None and {local_name}>{thr})'
