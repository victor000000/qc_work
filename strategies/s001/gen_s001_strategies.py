"""Reusable probe builders for s001 rounds.

Built on R1645-R1647 evidence. Templates here are proven to fire (i.e.
not produce orders=NOOP_orders) and follow memory-encoded rules.

Use these in gen_s001_R*.py instead of hand-rolling Probe(...) calls
for common patterns.
"""

from s001.paths import WORKSPACE_ROOT, DATA_DIR, RESEARCH_DIR
from s001.gen_s001_lib import (
    Probe, fund_gt, fund_lt, fund_rg,
    MAGS_BOOST, MAGS_DEMOTE, MAGS_WIDE, MAGS_RANK,
    PETGT_BOOST, STOP_TIGHT, ADD_VALS, ADD_VALS_PROVEN,
    WT_TILT_BOOST, WT_TILT_DEMOTE, MAGS_PROVEN_BOOST,
)


def _load_dead_cohort_signatures():
    """Load empirical 100%-silent (parent, sector, regime_pair) signatures.

    Built 2026-05-12 from R2010-R2027 audit (cohort_silent_signatures.json):
    49 cohort signatures with 100% silent at n≥6. Sector × regime pair
    never co-occurs in QQQ universe → cohort gate permanently dead.
    Rule 9 in never_fires_check blocks these at gen-time.
    """
    import json as _json, os as _os
    path = _os.path.join(str(RESEARCH_DIR),
                         'cohort_silent_signatures.json')
    try:
        with open(path) as f:
            entries = _json.load(f)
        return {(e['parent'], e['sector'], tuple(sorted(e['regimes'])))
                for e in entries}
    except Exception:
        return set()


_DEAD_COHORT_SIGNATURES = _load_dead_cohort_signatures()


def _load_productive_cohort_signatures():
    """Load empirical high-fire (rate ≥ 50%) (parent, sector, regime_pair).

    Built 2026-05-12 from R2010-R2027 audit (cohort_productive_signatures.json):
    51 cohort signatures with ≥50% fire rate. These are the SAFE cells for
    new probes; gate firing reliable in QQQ universe.
    """
    import json as _json, os as _os
    path = _os.path.join(str(RESEARCH_DIR),
                         'cohort_productive_signatures.json')
    try:
        with open(path) as f:
            entries = _json.load(f)
        return [{'parent': e['parent'], 'sector': e['sector'],
                 'regimes': tuple(sorted(e['regimes'])),
                 'rate': e.get('rate', 1.0)} for e in entries]
    except Exception:
        return []


_PRODUCTIVE_COHORT_SIGNATURES = _load_productive_cohort_signatures()


def _load_gate_sector_blocklist():
    """Load empirical (sector, ratio_field) blocklist (silent + catastrophic).

    Built 2026-05-13 from R2050-R2096 audit (gate_sector_blocklist.json):
    20 (sector, ratio_field) pairs that are either 100% silent OR ≥80%
    catastrophic with zero positive lifts (n≥8). E.g. S309 × ps_ratio:
    0/75 fired across all probe variants. Sector 309 has no QQQ stocks
    with these ratio characteristics, OR ratio-gate × this sector is a
    structural loss pattern. Rule 10 in never_fires_check blocks these.
    """
    import json as _json, os as _os
    path = _os.path.join(str(RESEARCH_DIR),
                         'gate_sector_blocklist.json')
    try:
        with open(path) as f:
            entries = _json.load(f)
        return {(e['sector'], e['ratio_field']): e for e in entries}
    except Exception:
        return {}


_GATE_SECTOR_BLOCKLIST = _load_gate_sector_blocklist()


def _load_dead_ratios():
    """Load empirical ratio-wide dead list (≥25 trials, 0 positives, all sectors).

    Built 2026-05-13 from R2050-R2098 audit (dead_ratios.json):
    11 fundamental ratios that produced ZERO positive lifts across all
    sectors tested (n≥25 each): CR, DC, EBM, EVEB, FCFY, GM, IC, PCF,
    PEG, ROE, SOLV. Average 25-60% catastrophic rate. Rule 11 in
    never_fires_check blocks ANY use of these ratios regardless of sector.
    """
    import json as _json, os as _os
    path = _os.path.join(str(RESEARCH_DIR), 'dead_ratios.json')
    try:
        with open(path) as f:
            entries = _json.load(f)
        return {e['ratio_field']: e for e in entries}
    except Exception:
        return {}


_DEAD_RATIOS = _load_dead_ratios()


def _load_silent_sec_sigs():
    """Empirical (parent, sector, regime_pair, gate_class) silent signatures.

    Built 2026-05-15 from R2200-R2268 audit (silent_sec_signatures.json):
    6 cohort patterns that produced 100% silent (orders == NOOP orders)
    across n≥5 trials each. ~30 specs/round saved when these patterns
    appear in 6-cond SEC probes.
    """
    import json as _json, os as _os
    path = _os.path.join(str(RESEARCH_DIR), 'silent_sec_signatures.json')
    try:
        with open(path) as f:
            entries = _json.load(f)
        # Build a set of frozensets for fast lookup
        return {(e['parent'], e['sector'], tuple(sorted(e['regime_pair'].split('+'))),
                 e['gate_class']) for e in entries}
    except Exception:
        return set()


_SILENT_SEC_SIGS = _load_silent_sec_sigs()


def _load_qstate_blocklist():
    """Load (qstate, sector, ratio_field) blocklist — qstate-aware extension of
    Rule 10. Built 2026-05-14 from R2050-R2106 audit. Captures cases where
    same (sector, ratio) is productive in one qstate but dead in another.
    E.g. S311 × pb_ratio: productive enough on _qzero (1 historical bake)
    but 12/15 catastrophic on _qpos. Rule 12 blocks the specific qstate match.
    """
    import json as _json, os as _os
    path = _os.path.join(str(RESEARCH_DIR),
                         'gate_qstate_sector_blocklist.json')
    try:
        with open(path) as f:
            entries = _json.load(f)
        return {(e['qstate'], e['sector'], e['ratio_field']): e for e in entries}
    except Exception:
        return {}


_QSTATE_BLOCKLIST = _load_qstate_blocklist()


def virgin_lever_combos_for_cell(parent: str, sector: str | int,
                                  regimes: tuple | list,
                                  bake_register_path: str | None = None
                                  ) -> list[tuple[str, str]]:
    """Return (lever, direction) combos NOT yet baked on the given cell.

    2026-05-12 audit: 1020 (cell × lever × direction) combinations across
    51 productive cells; only ~28 explored (~3%). Most cells have 17-20
    of 20 lever×direction combos virgin. Use this to prioritize untested
    actions instead of re-grinding already-tested ones.

    `regimes` should be sorted tuple of regime names (without `_reg_` prefix).
    Returns list of (lever, direction) tuples where direction ∈ {BOOST, DEMOTE}.
    """
    import json as _json, re as _re
    LEVERS = ['wt_tilt', 'score', 'entry_score_mtf', 'entry_score_quality',
              'entry_score_gate', 'entry_signal', 'petgt', 'stop', 'skip', 'conv']
    target_sig = (parent, str(sector), tuple(sorted(regimes))[:2])
    baked: set[tuple[str, str]] = set()
    try:
        path = bake_register_path or str(RESEARCH_DIR / 'bakes.json')
        with open(path) as f:
            bks = _json.load(f)
        for b in bks:
            c = b.get('cohort', '')
            p = next((x for x in ('_qpos', '_qzero', '_qsneg') if x in c), None)
            sm = _re.search(r'_secc\s*==\s*(\d+)', c)
            regs = tuple(sorted(set(_re.findall(r'_reg_(\w+)', c))))[:2]
            if not (p and sm and len(regs) == 2):
                continue
            sig = (p, sm.group(1), regs)
            if sig != target_sig:
                continue
            op = b.get('op', '')
            mag = b.get('mag', 0)
            is_boost = (op == '*=' and mag > 1.0) or (op == '+=' and mag > 0)
            baked.add((b['lever'], 'BOOST' if is_boost else 'DEMOTE'))
    except Exception:
        pass
    return [(lev, dir) for lev in LEVERS for dir in ('BOOST', 'DEMOTE')
            if (lev, dir) not in baked]


def productive_cells_unbaked(bake_register_path: str | None = None,
                              parent: str | None = None,
                              sector: int | None = None,
                              regime: str | None = None) -> list[dict]:
    """Return productive cohort cells (parent, sector, regime_pair) that
    haven't been baked yet. Filters by optional parent/sector/regime.

    Use to seed build_128_round() blocks with high-fire-rate cells instead
    of guessing. Each cell = dict {parent, sector, regimes, rate}.
    """
    import json as _json, re as _re
    baked_sigs: set = set()
    try:
        path = bake_register_path or str(RESEARCH_DIR / 'bakes.json')
        with open(path) as f:
            bks = _json.load(f)
        for b in bks:
            c = b.get('cohort', '')
            p = ('_qpos' if '_qpos' in c else
                 '_qzero' if '_qzero' in c else
                 '_qsneg' if '_qsneg' in c else None)
            sm = _re.search(r'_secc\s*==\s*(\d+)', c)
            regs = tuple(sorted(set(_re.findall(r'_reg_(\w+)', c))))
            if p and sm and len(regs) >= 2:
                baked_sigs.add((p, sm.group(1), regs[:2]))
    except Exception:
        pass
    out = []
    for cell in _PRODUCTIVE_COHORT_SIGNATURES:
        sig = (cell['parent'], cell['sector'], cell['regimes'])
        if sig in baked_sigs:
            continue
        if parent and cell['parent'] != parent: continue
        if sector and cell['sector'] != str(sector): continue
        if regime and regime not in cell['regimes']: continue
        out.append(cell)
    return out

# Common cohort constants (DRY out gen scripts) — informed by what's been
# productive across R1645-R1664:
#   COHORT_BAKE_ZONE  : score+= here is SATURATED after 3 bakes (memory:
#                       feedback_s001_bake_zone_saturated). Avoid further
#                       probing in this zone except for refine_bake.
#   COHORT_MEDIUM     : decline 5-10%, outside bake; wt_tilt null (cap
#                       binds at conv≥1.4) but score-additive may work
#   COHORT_DEEP       : decline 10-25%, rare entries; high-mag score probes
#   COHORT_QZERO_BZ   : flat-QQQ in bake-zone — orthogonal cohort
#   COHORT_QSNEG_BZ   : negative-QQQ in bake-zone — orthogonal cohort
#   COHORT_HYG_DN_BZ  : defensive credit regime in bake-zone
#   COHORT_HYG_UP_BZ  : risk-on credit regime in bake-zone
COHORT_BAKE_ZONE = '_qpos and decline > 0.020 and decline < 0.050'
COHORT_MEDIUM    = '_qpos and decline > 0.05 and decline < 0.10'
COHORT_DEEP      = '_qpos and decline > 0.10 and decline < 0.20'
COHORT_QZERO_BZ  = '_qzero and decline > 0.020 and decline < 0.050'
COHORT_QSNEG_BZ  = '_qsneg and decline > 0.020 and decline < 0.050'
COHORT_HYG_DN_BZ = '_qpos and _hyg_dn3 and decline > 0.020 and decline < 0.050'
COHORT_HYG_UP_BZ = '_qpos and _hyg_up3 and decline > 0.020 and decline < 0.050'


def wt_tilt_decline_band(name, decline_lo, decline_hi, mags=WT_TILT_BOOST,
                         extra_cohort='', fresh_fields=()):
    """Boost (or demote) wt_tilt for trades whose decline falls in a band.

    Position-sizing lever — fires whenever cohort fires regardless of rank.
    """
    cohort = f'decline > {decline_lo} and decline < {decline_hi}'
    if extra_cohort: cohort = f'{extra_cohort} and {cohort}'
    return Probe(name=name, lever='wt_tilt', cohort=cohort,
                 mags=mags, fresh_fields=fresh_fields)


def wt_tilt_regime(name, regime_expr, mags=WT_TILT_BOOST,
                   extra_cohort='', fresh_fields=()):
    """Boost or demote wt_tilt for trades in a specific regime."""
    cohort = regime_expr
    if extra_cohort: cohort = f'{regime_expr} and {extra_cohort}'
    return Probe(name=name, lever='wt_tilt', cohort=cohort,
                 mags=mags, fresh_fields=fresh_fields)


def wt_tilt_fund(name, accessor, op, thr, mags=WT_TILT_BOOST,
                 cohort='_qpos and decline > 0.04'):
    """Boost wt_tilt when a fundamental matches a threshold (fresh-fund position-sizer)."""
    return Probe(name=name, lever='wt_tilt', cohort=cohort,
                 fund=op(accessor, thr), mags=mags,
                 fresh_fields=(accessor,))


def score_demote_regime(name, regime_expr, mags=MAGS_DEMOTE,
                        extra_cohort='', op='*='):
    """Demote score in adverse regime. R1645/1646 evidence: only demotes
    actually shifted rank order; small mults rarely fire."""
    cohort = regime_expr
    if extra_cohort: cohort = f'{regime_expr} and {extra_cohort}'
    return Probe(name=name, lever='score', cohort=cohort, op=op, mags=mags)


def score_rank_break(name, accessor, op_fn, thr, mags=MAGS_RANK,
                     cohort='_qpos and decline > 0.04', score_op='*='):
    """Score probe with mags wide enough to break rank order on log2log2v.
    Uses MAGS_RANK = (0.70, 0.85, 1.30, 1.50) by default."""
    return Probe(name=name, lever='score', cohort=cohort,
                 fund=op_fn(accessor, thr), op=score_op, mags=mags,
                 fresh_fields=(accessor,))


def score_additive_fund(name, accessor, op_fn, thr, mags=ADD_VALS,
                        cohort='_qpos and decline > 0.04'):
    """Additive score probe. ADD on log2log2v (range ~3.5-4.5) shifts position
    meaningfully even at +=0.005."""
    return Probe(name=name, lever='score', cohort=cohort,
                 fund=op_fn(accessor, thr), op='+=', mags=mags,
                 fresh_fields=(accessor,))


# ---------- EXIT probes with fund gating (NEW dimension 2026-05-09) ----------
# EXIT scope re-derives _ops_z, _vr_z, _capec, _vsc, _fcfg1yc, _woc, etc.
# These are AVAILABLE for EXIT probe gating — was untested across all rounds.
# Memory `s001 EXIT-probe scope` only forbade _qpos/decline (entry-only).

def petgt_fund_gate(name, regime_expr, fund_expr, gain_thr,
                    mags=(1.05, 1.10, 1.15)):
    """petgt boost on winning trades with a FUND quality gate.
    Fund-expr uses EXIT-scope-available accessors: _ops_z, _vr_z, _bs_z, _inc_z,
    _cfs_z, _ers_z, _ac_z, _er_z (raw fundamentals — NOT _qpos/decline)."""
    cohort = f'{regime_expr} and pnl is not None and pnl > {gain_thr} and {fund_expr}'
    return Probe(name=name, lever='petgt', cohort=cohort, mags=mags, inject='EXIT')


def stop_fund_gate(name, regime_expr, fund_expr, loss_thr,
                   mags=(0.80, 0.90, 0.95)):
    """stop tightening on losing trades with a FUND quality gate.
    Counter-intuitive: tightening WAS catastrophic on regime-only cohorts but
    may work when paired with fund-quality discriminator."""
    cohort = f'{regime_expr} and pnl is not None and pnl < {loss_thr} and {fund_expr}'
    return Probe(name=name, lever='stop', cohort=cohort, mags=mags, inject='EXIT')


def stop_fund_loosen(name, regime_expr, fund_expr, loss_thr,
                     mags=(1.10, 1.20, 1.30)):
    """stop LOOSENING on losing trades when fund signals a quality holdout."""
    cohort = f'{regime_expr} and pnl is not None and pnl < {loss_thr} and {fund_expr}'
    return Probe(name=name, lever='stop', cohort=cohort, mags=mags, inject='EXIT')


def petgt_winner(name, regime_expr, gain_thr, mags=(1.05, 1.08, 1.10)):
    """Boost profit-target for winning trades in a regime. Use ≤1.10 only —
    R1645 PB *=1.20/1.30 was -0.04 (over-multiplied with base's existing 1.30)."""
    cohort = f'{regime_expr} and pnl is not None and pnl > {gain_thr}'
    return Probe(name=name, lever='petgt', cohort=cohort,
                 mags=mags, inject='EXIT')


def petgt_demote(name, regime_expr, gain_thr, mags=(0.85, 0.90, 0.95)):
    """Demote profit-target (exit profit faster) on adverse-trend trades."""
    cohort = f'{regime_expr} and pnl is not None and pnl > {gain_thr}'
    return Probe(name=name, lever='petgt', cohort=cohort,
                 mags=mags, inject='EXIT')


def stop_loosen(name, regime_expr, loss_thr, mags=(1.10, 1.20, 1.30)):
    """LOOSEN stop on stable regime (counter to R1645 stop-tighten which all hurt)."""
    cohort = f'{regime_expr} and pnl is not None and pnl < {loss_thr}'
    return Probe(name=name, lever='stop', cohort=cohort,
                 mags=mags, inject='EXIT')


def skip_panic(name, cohort_expr):
    """Skip trades only on extreme panic — R1645 KB/KC catastrophic at moderate gates."""
    return Probe(name=name, lever='skip', cohort=cohort_expr,
                 op='continue', mags=(0,))


def conv_fund(name, accessor, op_fn, thr, mags=(1.10, 1.20, 1.30),
              cohort='_qpos and decline > 0.05'):
    """Conv (sizing pre-tilt) with fresh-fund gate."""
    return Probe(name=name, lever='conv', cohort=cohort,
                 fund=op_fn(accessor, thr), mags=mags,
                 fresh_fields=(accessor,))


def compound_sector_fund(name, sector_code, accessor, op_fn, thr,
                         mags=MAGS_RANK, decline_thr=0.05, qpos=True):
    """Sector × fundamental compound — plateau-breaker per memory s001 compound 2-factor."""
    qgate = '_qpos and ' if qpos else '_qsneg and '
    cohort = f'{qgate}_secc == {sector_code} and decline > {decline_thr}'
    return Probe(name=name, lever='score', cohort=cohort,
                 fund=op_fn(accessor, thr), mags=mags,
                 fresh_fields=(accessor,))


# ---------- batch builders (DRY iteration patterns) ----------

def score_additive_grid(R, prefix, cohort, fresh_specs, mags=ADD_VALS):
    """Add N score-additive Probes from a list of (name, accessor, op_fn, thr) tuples.

    Saves the explicit `for tag, accessor, op, thr in fresh_specs:` loop in
    every gen script. Each probe gets fresh_fields=(accessor,) so audit counts.
    """
    for tag, accessor, op_fn, thr in fresh_specs:
        R.add(Probe(name=f'{prefix}{tag}', lever='score', cohort=cohort,
                    fund=op_fn(accessor, thr), op='+=', mags=mags,
                    fresh_fields=(accessor,)))


def wt_tilt_fund_grid(R, prefix, cohort, fresh_specs, mags=WT_TILT_BOOST):
    """Same pattern, for wt_tilt fund-gated probes."""
    for tag, accessor, op_fn, thr in fresh_specs:
        R.add(Probe(name=f'{prefix}{tag}', lever='wt_tilt', cohort=cohort,
                    fund=op_fn(accessor, thr), mags=mags,
                    fresh_fields=(accessor,)))


# Lean default for fresh `score *=` exploration. Empirical R1755-R1757
# audit: 0/47 mult axes had BOTH 1.05 and 1.10 productive — multi-mag
# never co-fires for multiplicative score on _qzero/_qsneg cohorts.
# Use single mag (1.05) for fresh accessors; promote to 1.10 verification
# only after a 1.05 candidate proves productive.
MULT_FRESH = (1.05,)
MULT_VERIFY = (1.10,)


def pick_productive_accessors(entry_only: bool = True) -> list[str]:
    """Return accessors that have produced productive bakes.

    For transfer testing on the ENTRY side (score lever), pass
    entry_only=True to filter out exit-side / large-cap-size accessors
    (current_ratio, pb_ratio, ps_ratio, total_expenses, total_revenue,
    total_assets) — these fire on the broad index population and
    catastrophically destabilize entry-side score adjustments.

    R1766 audit: 100% silent rate when pairing FRESH accessors with
    regime gates. Use known-firing entry-productive accessors instead.
    """
    import json, re
    from pathlib import Path
    EXIT_OR_LARGECAP = {
        '_ops_z.current_ratio.one_year',
        '_vr_z.pb_ratio',
        '_vr_z.ps_ratio',
        '_inc_z.total_expenses.twelve_months',
        '_inc_z.total_revenue.twelve_months',
        '_bs_z.total_assets.twelve_months',
    }
    log_path = Path(str(WORKSPACE_ROOT / 'strategies/s001/research/bakes.json'))
    with log_path.open() as f:
        bakes = json.load(f)
    accessors = []
    seen = set()
    for b in bakes:
        if b.get('reverted'): continue
        # Skip exit-side bakes when entry_only
        if entry_only and b.get('lever') == 'exit_signal': continue
        m = re.search(r'_ngt\(([^,]+),', b.get('cohort','')) or \
            re.search(r'_nlt\(([^,]+),', b.get('cohort',''))
        if not m: continue
        a = m.group(1).strip()
        if a in seen: continue
        if entry_only and a in EXIT_OR_LARGECAP: continue
        seen.add(a)
        accessors.append(a)
    return accessors


def regime_transfer_grid(R, prefix, regime_gate, parent_cohort, accessors,
                         op='*=', mags=(1.05,), allow_wide_parent: bool = False):
    """Test a set of (already-productive) accessors against a single regime
    gate on a parent cohort. Each accessor → 1 probe.

    This is the TRANSFER TEST pattern: known-firing accessors paired with
    new regime gates. R1764 found regime-gating productive when accessor
    was firing-friendly; R1766 found 0 productive when accessor was random.

    Default REJECTS wide saturated parents (_qpos/qzero × bake-zone) per
    memory feedback_s001_transfer_wide_parent_catastrophic — 14-27%
    catastrophic, 0-3% productive on those parents. Pass allow_wide_parent
    =True to override (e.g. for verification rounds).
    """
    if not allow_wide_parent:
        FORBIDDEN_WIDE = (
            '_qpos and decline > 0.020 and decline < 0.050',
            '_qzero and decline > 0.020 and decline < 0.050',
        )
        if parent_cohort in FORBIDDEN_WIDE:
            print(f'  SKIP regime_transfer_grid on wide saturated parent: '
                  f'{parent_cohort!r} (memory: 14-27% catastrophic; pass '
                  f'allow_wide_parent=True to override)')
            return
    for i, accessor in enumerate(accessors):
        R.add(Probe(name=f'{prefix}{i}', lever='score',
                    cohort=f'{parent_cohort} and {regime_gate} and _ngt({accessor},1e6)',
                    op=op, mags=mags,
                    fresh_fields=(accessor,)))


def score_mult_fresh(R, prefix, cohort_template, accessors, mag=1.05):
    """Add N score-multiplicative Probes for fresh accessor exploration.

    Single-mag default cuts spec budget in half vs (1.05, 1.10). Empirical
    audit (R1755-R1757): mult-mag co-firing rate on score *= is 0% — there
    is no information gain from running both 1.05 and 1.10 on FRESH
    accessors. Reserve 1.10 for verification of 1.05-productive axes.

    cohort_template must contain `{accessor}` placeholder (or a fixed
    cohort can be passed if all probes share the cohort).
    """
    for i, accessor in enumerate(accessors):
        cohort = cohort_template.format(accessor=accessor) if '{accessor}' in cohort_template else cohort_template
        R.add(Probe(name=f'{prefix}{i}', lever='score',
                    cohort=cohort, op='*=', mags=(mag,),
                    fresh_fields=(accessor,)))


def threshold_sweep_score(R, prefix, accessor, thresholds, cohort,
                          op_fn=None, mags=ADD_VALS):
    """Sweep threshold values for a known-productive accessor.

    Use to refine an existing BAKE: e.g., BAKE-FC used operation_margin > 0.20;
    this can test 0.10/0.15/0.25/0.30 to find the optimal threshold.

    Each spec becomes one axis × len(mags) specs. Multiple thresholds × multiple
    mags is len(thresholds) × len(mags) total specs (cap each axis at ≤4 mags
    to stay under axis_cap=20).

    The accessor is NOT marked fresh (it's a known-used field) so don't expect
    audit fresh-count credit from this.
    """
    if op_fn is None:
        op_fn = fund_gt
    for i, thr in enumerate(thresholds):
        # tag suffix encodes threshold for traceability
        thr_tag = str(thr).replace('.', 'p').replace('-', 'n')
        R.add(Probe(name=f'{prefix}T{i}', lever='score', cohort=cohort,
                    fund=op_fn(accessor, thr), op='+=', mags=mags))


# Historical-null axes to avoid re-proposing (cohort_firing_history < 5%
# fire rate over 3+ rounds). Updated 2026-05-09 from R1645-R1657 audit.
HISTORICAL_NULL_AXES = ('PA', 'KA', 'KD', 'SS')  # never fired across many rounds
HISTORICAL_NEGATIVE_AXES = ('PB', 'PE', 'PG', 'PH', 'KB', 'RA', 'SA')  # fire-and-hurt

# Patterns proven to NEVER fire (cohort doesn't match real trades, or
# cap-binding nullifies effect). Source: fund_gate_fire_history audit
# 2026-05-09 across R1645-R1666 (~2200 specs).
#
# DO NOT add probes matching these patterns — they're pure compute waste:
NEVER_FIRES_PATTERNS = {
    'wt_tilt × decline ≥ 0.05':  # cap binds when conv ≥ 1.4 (decline > 0.05)
        'wt_tilt boosts on medium/deep decline are NULL because '
        'conv*tilt*0.08 ≥ WT_CAP=0.07 regardless of tilt',
    'conv × mags ≥ 1.5':         # high conv mults hit WT_CAP via conv*tilt
        'conv boosts above 1.5 hit WT_CAP saturation in BAKE-ZONE',
    'score+= × MEDIUM':          # decline 0.05-0.10 score+= doesn't shift rank
        'MEDIUM decline cohort: score adds dont shift selection (rank stable)',
    'aux PA/PD/SS/KA/KD':        # rare cohorts by design
        'aux probes use rare cohorts (regime extremes); satisfy audit but never fire',
}


# ---------- bake-pattern-driven probe generation ----------
# Across R1645-R1660 (2071 probes), 69.5% were NULL — pure waste. Only
# productive cohort: `_qpos × decline ∈ (0.020, 0.050) × <quality-fund gate>`.
# All 3 bakes (BAKE-WH wt_tilt, BAKE-FC margin, BAKE-FG income-growth) live
# in this zone. Below helpers concentrate compute on this pattern.

def refine_bake(R, label, thresholds, mags=ADD_VALS_PROVEN, prefix=None):
    """Generate a threshold-sweep block from an applied bake.

    Looks up the bake by label in bakes.json, extracts its accessor +
    cohort minus the threshold gate, then emits Probes that test the
    same accessor at varied thresholds. The accessor is NOT marked
    fresh (it's already used) so don't expect fresh-count credit.

    Useful for refining BAKE-FC (operation_margin>0.20) → test 0.10,
    0.15, 0.25, 0.30, 0.35 to find optimal cutoff.
    """
    from s001.gen_s001_diagnostics import get_bake_log
    rec = get_bake_log(label)
    if rec is None:
        raise ValueError(f'no bake {label!r} in bakes.json')
    full_cohort = rec['cohort']
    # Strip the existing fund gate from the cohort (assume last `and _ngt(...)`
    # or `and _nlt(...)` is the threshold gate)
    import re
    cohort_no_gate = re.sub(r'\s*and\s+_n(gt|lt|rg)\([^)]+\)\s*$', '', full_cohort)
    accessor_match = re.search(r'_n(?:gt|lt)\(([^,]+),', full_cohort)
    if not accessor_match:
        raise ValueError(f'could not extract accessor from {full_cohort!r}')
    accessor = accessor_match.group(1).strip()
    op_match = re.search(r'_n(gt|lt)\(', full_cohort)
    op_fn = fund_gt if op_match.group(1) == 'gt' else fund_lt

    pfx = prefix or f'TS{rec["axis"]}'
    for i, thr in enumerate(thresholds):
        R.add(Probe(name=f'{pfx}{i}', lever=rec['lever'], cohort=cohort_no_gate,
                    fund=op_fn(accessor, thr), op=rec['op'], mags=mags))


def bake_zone_grid(R, prefix, fresh_specs, mags=ADD_VALS_PROVEN):
    """Add N score-additive Probes in the proven-productive BAKE-ZONE.

    This is the only cohort (`_qpos × decline ∈ (0.020, 0.050)`) where
    ANY session bake hit. Any new fund-gate exploration should start here.

    Default mags=ADD_VALS_PROVEN=(0.020, 0.040). DO NOT override with
    full ADD_VALS — a5 and a10 are 0% historical hit rate (138 specs,
    0 positive). Adding them just doubles compute for zero marginal hits.
    """
    for tag, accessor, op_fn, thr in fresh_specs:
        R.add(Probe(name=f'{prefix}{tag}', lever='score', cohort=COHORT_BAKE_ZONE,
                    fund=op_fn(accessor, thr), op='+=', mags=mags,
                    fresh_fields=(accessor,)))


def bake_compound_grid(R, prefix, label_existing, fresh_specs,
                       mags=ADD_VALS_PROVEN):
    """Add N probes that COMPOUND a new fund-gate ON TOP of an existing bake.

    Tests whether layering 2 quality gates on the same cohort gives more lift
    than each alone. Per memory s001 cohort saturation, expect ~20% summed lift.
    """
    from s001.gen_s001_diagnostics import get_bake_log
    rec = get_bake_log(label_existing)
    if rec is None:
        raise ValueError(f'no bake {label_existing!r}')
    base_cohort = rec['cohort']  # already includes existing fund gate
    for tag, accessor, op_fn, thr in fresh_specs:
        R.add(Probe(name=f'{prefix}{tag}', lever='score', cohort=base_cohort,
                    fund=op_fn(accessor, thr), op='+=', mags=mags,
                    fresh_fields=(accessor,)))


# ---------- default aux blocks (DRY out gen scripts) ----------

# ============================================================================
# 128-spec template (R1894/R1895 calibration 2026-05-10)
# ============================================================================
# 22 known-productive accessors from active bakes — guaranteed to pass
# cohort_var_check + never_fires_check. Pool starts here, supplemented with
# pick_fresh_fields_under_explored when available.
KNOWN_ACC_PROD_R1895 = (
    '_inc_z.other_income_expense.twelve_months',
    '_inc_z.excise_taxes.twelve_months',
    '_inc_z.total_revenue.twelve_months',
    '_inc_z.total_expenses.twelve_months',
    '_inc_z.gain_on_sale_of_security.twelve_months',
    '_inc_z.impairment_of_capital_assets.twelve_months',
    '_cfs_z.operating_gains_losses.twelve_months',
    '_cfs_z.other_non_cash_items.twelve_months',
    '_cfs_z.net_other_financing_charges.twelve_months',
    '_cfs_z.proceeds_from_stock_option_exercised.twelve_months',
    '_cfs_z.gain_loss_on_investment_securities.twelve_months',
    '_cfs_z.short_term_debt_issuance.twelve_months',
    '_cfs_z.short_term_debt_payments.twelve_months',
    '_bs_z.preferred_stock_equity.twelve_months',
    '_bs_z.total_assets.twelve_months',
    '_bs_z.raw_materials.twelve_months',
    '_bs_z.duefrom_related_parties_current.twelve_months',
    '_bs_z.dueto_related_parties_current.twelve_months',
    '_bs_z.other_payable.twelve_months',
    '_bs_z.capital_lease_obligations.twelve_months',
    '_bs_z.electric_utility_plant.twelve_months',
    '_bs_z.investmentin_financial_assets.twelve_months',
)
# Strategy references 9 sectors in base file:
STRATEGY_SECTORS = (102, 103, 205, 206, 308, 309, 310, 311, 313)


def untested_sectors_by_lever(lever: str, base_path: str | None = None) -> list[int]:
    """Return sectors NOT yet baked for a given lever (recent bakes).

    2026-05-11 audit: R1944+ score-class bakes used only S205/S310/S311.
    Sectors S102, S103, S206, S308, S309, S313 have ZERO score-class bakes.
    Helper: prioritize untested sectors when designing new rounds.
    """
    import json
    import re
    from pathlib import Path
    bakes_path = Path(base_path).parent / 'bakes.json' if base_path and (Path(base_path).parent / 'bakes.json').exists() else RESEARCH_DIR / 'bakes.json'
    try:
        bakes = json.loads(bakes_path.read_text())
    except Exception:
        return list(STRATEGY_SECTORS)
    used = set()
    for b in bakes:
        if b.get('lever') != lever:
            continue
        cohort = b.get('cohort', '')
        for s in re.findall(r'_secc\s*==\s*(\d+)', cohort):
            used.add(int(s))
    return [s for s in STRATEGY_SECTORS if s not in used]


T128_WT_MAGS = (0.50, 0.60, 0.70, 0.80, 0.90)
T128_QUALITY_MAGS = (-0.05, -0.075, -0.10, -0.15, -0.20)
T128_GATE_MAGS = (-0.025, -0.05, -0.10, -0.15, -0.20)
T128_MTF_MAGS = (-0.150, -0.250, -0.333, -0.500, -0.667)
T128_REGIME_MAGS = (-0.005, -0.010, -0.015, -0.020, -0.025)
T128_SD = 'decline > 0.020 and decline < 0.050'

# Productive pattern (2026-05-11): `_qzero × {S310,S311} × productive_regime ×
# distress-accessor × entry_score_mtf -=` consistently delivers +0.005/bake.
# Bakes so far (R1948, R1950, R1951): short_term_debt_payments, total_debt,
# impairment_of_capital_assets — all FINANCIAL DISTRESS signals.
# Hypothesis: mean-reversion candidates with distress signals underperform,
# so demoting them via entry_score_mtf -= improves selection rank.
DISTRESS_ACCESSORS = (
    '_bs_z.total_debt.twelve_months',
    '_bs_z.long_term_debt.twelve_months',
    '_bs_z.long_term_debt_capital_lease_obligation.twelve_months',
    '_bs_z.capital_lease_obligations.twelve_months',
    '_bs_z.goodwill.twelve_months',
    '_cfs_z.long_term_debt_payments.twelve_months',
    '_cfs_z.short_term_debt_payments.twelve_months',
    '_cfs_z.short_term_debt_issuance.twelve_months',
    '_inc_z.interest_expense.twelve_months',
    '_inc_z.write_off.twelve_months',
    '_inc_z.bad_debt_expense.twelve_months',
    '_inc_z.restructuring_charges.twelve_months',
    '_inc_z.asset_impairment_charge.twelve_months',
    '_inc_z.impairment_of_capital_assets.twelve_months',
    '_inc_z.goodwill_impairment_loss.twelve_months',
)


def build_128_round(rid: int, blocks: list[tuple],
                    auto_aux: bool = True) -> 'Round':
    """Build a Round targeting 128 ±10 meaningful specs post-prune.

    `blocks` is a list of (tag, lever, cohort_template, off, mags, op).
    Each block expands to 3 axes × 5 mags = 15 raw specs. P6 typically
    drops 5-10 axes → 100-115 main + 8 NOOPs + 5 productive aux ≈ 128.

    `auto_aux=True` (default) auto-attaches `add_productive_aux_blocks`
    so callers can't forget. The 5 aux specs test required levers on
    cohorts that fire regularly — they're meaningful, not padding.

    Recommended block count: 10. Quota: 6 non-score + 4 score-class.
    Accessor pool: KNOWN_ACC_PROD_R1895 + fresh; round-robin via offset.

    Returns a Round; caller wraps with pretick_or_die() before and
    `run_audit_and_queue(R)` after. P8 guard then enforces 118-138.
    """
    from s001.gen_s001_lib import Probe, Round
    from s001.gen_s001_diagnostics import (
        pick_fresh_fields_under_explored, accessor_fire_rates,
    )
    R = Round(rid=rid, noops=8, priority=1)
    fresh = pick_fresh_fields_under_explored(n=60)
    rates = accessor_fire_rates(min_trials=30)
    # Known pool: exclude truly-dead (<5% at ≥30 trials), then RANK by
    # historical fire rate (descending) so high-fire-rate accessors are
    # picked first (2026-05-12: reduces within-cell silent rate; R2028
    # was 30% silent — much of that from low-fire accessors in productive
    # cohort cells).
    known = [a for a in KNOWN_ACC_PROD_R1895
             if not (a in rates and rates[a]['rate'] < 0.05)]
    known.sort(key=lambda a: -(rates.get(a, {}).get('rate', 0.5)))
    # Fresh pool: more permissive (<2%) since fresh space is depleting and
    # audit needs ≥8 distinct fresh per round. 2-5% accessors still fire
    # 7-19 times in the backtest period — meaningful, just rare.
    fresh_pool = [a for a in fresh
                  if not (a in rates and rates[a]['rate'] < 0.02)]
    fresh_pool.sort(key=lambda a: -(rates.get(a, {}).get('rate', 0.5)))
    # Per-block accessor allocation: 1 fresh + 2 known per block. Spreads
    # fresh accessors across all 10 blocks so P6 drops don't concentrate
    # fresh-loss into a single block. Yields 10 fresh used, audit needs ≥8
    # so we tolerate up to 2 fresh-block P6 drops.
    if not fresh_pool:
        fresh_pool = list(fresh) or [known[0]]
    if not known:
        known = list(KNOWN_ACC_PROD_R1895)
    for bi, block in enumerate(blocks):
        # Block tuple: (tag, lever, template, off, mags, op[, accessor_pool])
        # Optional 7th element: list of accessors to use INSTEAD of fresh+known.
        # When provided, picks 3 sequential accessors offset by `off`.
        if len(block) == 7:
            tag, lever, template, off, mags, op, custom_pool = block
            if not custom_pool:
                custom_pool = known
            accs = [custom_pool[(off + i) % len(custom_pool)] for i in range(3)]
        else:
            tag, lever, template, off, mags, op = block
            # Axis 0 = fresh; axes 1,2 = known (round-robin via off).
            accs = [
                fresh_pool[bi % len(fresh_pool)],
                known[(off + 1) % len(known)],
                known[(off + 2) % len(known)],
            ]
        for i, acc in enumerate(accs):
            cohort = template.format(acc=acc)
            R.add(Probe(
                name=f'{tag}_{i}', lever=lever,
                cohort=cohort, op=op, mags=mags, fresh_fields=(acc,),
            ))
    if auto_aux:
        add_productive_aux_blocks(R)
    return R


SCORE_DEMOTE_MAGS = (0.80, 0.85, 0.90, 0.92, 0.95)


def score_demote_compound_blocks(parent: str, sector: int,
                                  regime_pairs: list[tuple[str, str]],
                                  tag_prefix: str = '') -> list[tuple]:
    """Generate `score *= 0.80-0.95` DEMOTE blocks on narrow compound cohorts.

    Memory feedback_s001_demote_compound_pattern (R1974-R1977 audit): this
    pattern delivers +0.001-+0.003/bake on narrow `parent × sector × regime_A
    AND regime_B × accessor` cohorts. 3 of last 4 bakes (R1974/R1976/R1977)
    used this exact structure.

    `regime_pairs` is list of (regime_A, regime_B) tuples. Each pair becomes
    one block. Tag format: `{prefix}SD_{parent_short}_S{sector}_{regA}_{regB}`.
    Each block = 3 axes × 5 mags = 15 raw specs.

    Use as part of `blocks` arg to build_128_round.
    """
    REGIME_TAGS = {
        '_reg_haccel': 'HA', '_reg_vxx_falling3': 'VF',
        '_reg_double_panic': 'DP', '_reg_qqq_up3': 'Q3',
        '_reg_hyg_dn14': 'HD14', '_reg_hyg_dn3': 'HD3', '_reg_hyg_dn5': 'HD5',
    }
    parent_short = parent[1:].upper()  # _qpos → QPOS
    blocks = []
    for i, (reg_a, reg_b) in enumerate(regime_pairs):
        tag_a = REGIME_TAGS.get(reg_a, reg_a.replace('_reg_', '').upper()[:4])
        tag_b = REGIME_TAGS.get(reg_b, reg_b.replace('_reg_', '').upper()[:4])
        blocks.append((
            f'{tag_prefix}SD_{parent_short}_S{sector}_{tag_a}_{tag_b}',
            'score',
            f'{parent} and _secc == {sector} and self.{reg_a} and self.{reg_b} and _ngt({{acc}},1e6)',
            i * 3, SCORE_DEMOTE_MAGS, '*=',
        ))
    return blocks


def distress_mtf_blocks(parent: str, sector: int, regimes: list[str],
                         tag_prefix: str = '') -> list[tuple]:
    """Generate entry_score_mtf blocks for the productive distress pattern.

    R1948+R1950+R1951 audit: `parent × _secc==sector × regime × distress_acc
    × entry_score_mtf -=` delivered +0.005/bake. This helper emits 1 block
    per regime, drawing accessors from DISTRESS_ACCESSORS via the 7-tuple
    custom_pool override (so build_128_round uses distress accessors instead
    of generic fresh+known pool).

    Each block: (tag, lever, cohort_template, off, mags, op, DISTRESS_ACCESSORS).
    Use as part of `blocks` arg to build_128_round.
    """
    REGIME_TAGS = {
        '_reg_haccel': 'HA', '_reg_vxx_falling3': 'VF',
        '_reg_double_panic': 'DP', '_reg_qqq_up3': 'Q3',
        '_reg_hyg_dn14': 'HD14', '_reg_hyg_dn3': 'HD3', '_reg_hyg_dn5': 'HD5',
    }
    blocks = []
    for i, reg in enumerate(regimes):
        reg_short = REGIME_TAGS.get(reg, reg.replace('_reg_', '').upper()[:6])
        blocks.append((
            f'{tag_prefix}EM_{parent[1:].upper()}_S{sector}_{reg_short}',
            'entry_score_mtf',
            f'{parent} and _secc == {sector} and self.{reg} and _ngt({{acc}},1e6)',
            i * 3, T128_MTF_MAGS, '+=',
            DISTRESS_ACCESSORS,
        ))
    return blocks


def build_compound_round(rid: int, probe_specs: list[tuple],
                          noops: int = 8, auto_aux: bool = True):
    """Build a round of single-axis compound probes targeting ~128 specs.

    `probe_specs` is a list of (tag, lever, cohort, mags, op, fresh_fields).
    Each becomes a single-axis Probe (1 axis × len(mags) specs).
    With 20 probes × 5 mags = 100 + 8 NOOPs + 5 aux = 113 specs.
    25 probes × 5 mags = 125 + 13 = 138 → P6 trim → ~128.

    Returns Round for run_audit_and_queue.
    """
    from s001.gen_s001_lib import Probe, Round
    R = Round(rid=rid, noops=noops, priority=1)
    for tag, lever, cohort, mags, op, fresh in probe_specs:
        R.add(Probe(name=tag, lever=lever, cohort=cohort, op=op,
                    mags=mags, fresh_fields=fresh))
    if auto_aux:
        add_productive_aux_blocks(R)
    return R


def regime_short(reg: str) -> str:
    """Short regime label for tag names."""
    M = {'haccel': 'HA', 'vxx_falling3': 'VF', 'double_panic': 'DP',
         'qqq_up3': 'Q3', 'hyg_dn14': 'HD14', 'hyg_dn3': 'HD3', 'hyg_dn5': 'HD5'}
    return M.get(reg, reg[:4].upper())


def compound_probe_spec(parent: str, sector: str | int, reg_a: str, reg_b: str,
                        pair: tuple, lever: str, mags: tuple, op: str,
                        suffix: str = '') -> tuple:
    """Build a probe_specs tuple for build_compound_round.

    Returns (tag, lever, cohort, mags, op, fresh_fields).
    """
    ra = regime_short(reg_a)
    rb = regime_short(reg_b)
    ps = parent[1:].upper()
    lev = {'entry_score_mtf': 'EM2', 'score': 'SD2',
           'entry_score_quality': 'EQ2', 'entry_score_gate': 'EG2'}.get(lever, 'X2')
    tag = f'{lev}_{ps}_S{sector}_{ra}_{rb}{suffix}'
    cohort = (f'{parent} and _secc == {sector} '
              f'and self._reg_{reg_a} and self._reg_{reg_b} '
              f'and _ngt({pair[0]},1e6) and _ngt({pair[1]},1e6)')
    return (tag, lever, cohort, mags, op, pair)


def add_productive_aux_blocks(R):
    """Aux block — adds only missing required levers (not all 5).

    2026-05-15: deep-review reduced from 5 always-added aux to demand-driven.
    R2172 audit (R2162-R2171): only CV productive (10/10 pos, avg +0.00040).
    PA inert, KA -0.37 cata, SS -0.025, RA -0.005. Always-add wasted 4 specs/round.

    New logic: scan main probes for which REQUIRED_LEVERS are missing,
    then add only those + CV (productive lever, always-add).
    """
    from s001.gen_s001_lib import REQUIRED_LEVERS
    main_levers = {p.lever for p in R.probes}
    # Score-family equivalence (must mirror audit logic in gen_s001_lib.audit)
    SCORE_FAMILY = {'score', 'wt_tilt', 'entry_signal', 'entry_score_mtf',
                    'entry_score_regime', 'entry_score_conv',
                    'entry_score_quality', 'entry_score_gate'}
    missing = set(REQUIRED_LEVERS) - main_levers
    if 'score' in missing and (main_levers & SCORE_FAMILY):
        missing.discard('score')

    # CV (productive conv) — always add unless main already has conv probes
    if 'conv' in missing or not any(p.lever == 'conv' for p in R.probes):
        R.add(Probe(name='CV', lever='conv',
                    cohort='_qpos and self._reg_haccel and decline > 0.05',
                    mags=(1.05,)))
        missing.discard('conv')

    # Add 1 minimal aux per missing required lever (rare cohorts to avoid waste)
    if 'petgt' in missing:
        R.add(petgt_winner('PA', 'self._reg_haccel', 0.05, mags=(1.05,)))
    if 'stop' in missing:
        R.add(stop_loosen('SS',
                          'self._reg_double_panic and self._reg_qqq_up3',
                          -0.04, mags=(1.10,)))
    if 'skip' in missing:
        R.add(skip_panic('KA',
                         'self._reg_double_panic and self._reg_qqq_up3 and decline > 0.40'))
    if 'score' in missing:
        R.add(score_demote_regime('RA',
                                  'self._reg_double_panic and self._reg_vxx_xhigh',
                                  mags=(0.85,),
                                  extra_cohort='_qsneg and decline > 0.40'))


def add_minimal_aux_blocks(R):
    """Absolute-minimum aux: 1 axis per required lever × 1 mag = 5 specs.
    Cohorts are ULTRA-RARE so probes almost never fire (NULL is harmless).

    Use this in efficiency-focused rounds where every spec should target
    productive exploration. Saves ~12 specs vs add_default_aux_blocks.
    Caller still needs ≥3 regime axes — these all use self._reg_* gates.
    """
    # 1 petgt EXIT (rare cohort)
    R.add(petgt_winner('PA', 'self._reg_double_panic and self._reg_vxx_xhigh', 0.20,
                       mags=(1.05,)))
    # 1 stop EXIT (rare)
    R.add(stop_loosen('SS', 'self._reg_double_panic and self._reg_vxx_xhigh', -0.30,
                      mags=(1.10,)))
    # 1 skip ENTRY (extreme panic only)
    R.add(skip_panic('KA', 'self._reg_double_panic and _hi_vol and _hi_cape and decline > 0.40'))
    # 1 score regime (audit min)
    R.add(score_demote_regime('RA', 'self._reg_double_panic and self._reg_vxx_xhigh',
                              mags=(0.85,),
                              extra_cohort='_qsneg and _hi_vol and decline > 0.40'))
    # 1 conv (audit min)
    R.add(Probe(name='CV', lever='conv',
                cohort='self._reg_double_panic and _hi_cape and decline > 0.40',
                mags=(1.05,)))


def add_default_aux_blocks(R):
    """Minimum-cost aux blocks satisfying audit's required-levers check.

    Aux-history audit (R1645-R1657): old 34-spec aux block produced 0
    positive lifts and many chronic negatives (PE 17/33 fired all neg,
    PG 16/27 fired all neg, RA 30/40 fired all neg). Replaced with
    ultra-rare cohorts that satisfy audit's `lever in levers_seen`
    requirement but rarely actually fire — ≤14 specs.

    Saves ~70 lines per gen script. Call after adding round-specific
    blocks. NOOPs still handled by Round.noops.
    """
    # 2 petgt EXIT — keep one historical-NULL (PA never fired) + one rare
    R.add(petgt_winner('PA', 'self._reg_qqq_up5', 0.03, mags=(1.05, 1.08, 1.10)))
    R.add(petgt_winner('PD', 'self._reg_qqq_up3', 0.06, mags=(1.05, 1.08, 1.10)))

    # 1 stop EXIT — loosen on stable regime (rarely fires, NULL-safe)
    R.add(stop_loosen('SS', 'self._reg_vxx_low and self._reg_qqq_up5', -0.04,
                      mags=(1.10, 1.20, 1.30)))

    # 2 skip ENTRY — historical-NULL panic gates (KA/KD never fire)
    R.add(skip_panic('KA', '_qsneg and self._reg_vxx_xhigh and self._reg_hyg_dn14 and decline > 0.30'))
    R.add(skip_panic('KD', 'self._reg_double_panic and _qsneg and _hi_vol and decline > 0.30'))

    # 1 score regime demote on ULTRA-RARE cohort (replaces RA which always hurt)
    # Cohort tightened to nearly-never-fire so the lever is registered without harm.
    R.add(score_demote_regime('RA', 'self._reg_double_panic and self._reg_vxx_xhigh',
                              mags=(0.65, 0.75, 0.85),
                              extra_cohort='_qsneg and _hi_vol and decline > 0.40'))

    # 1 conv probe on ULTRA-RARE cohort (audit min for conv lever)
    R.add(Probe(name='CV', lever='conv',
                cohort='self._reg_double_panic and _hi_cape and decline > 0.40',
                mags=(1.05, 1.10, 1.15)))


# ---------- scoreized entry/exit probes ----------
# User-requested 2026-05-09: probes that combine multiple signals into a
# weighted score for entry/exit decisions.

def entry_mtf_probe(name, mtf_cond, mag=0.020,
                    base_cohort='_qpos and decline > 0.020 and decline < 0.050',
                    mags=None):
    """Targets `entry_score_mtf` lever — multi-timeframe component.
    Pass `mags` (tuple) for multi-mag confirmation; falls back to single `mag`.
    """
    return Probe(name=name, lever='entry_score_mtf',
                 cohort=f'{base_cohort} and {mtf_cond}',
                 op='+=', mags=mags or (mag,))


def entry_regime_probe(name, regime_cond, mag=0.020,
                       base_cohort='_qpos and decline > 0.020 and decline < 0.050',
                       mags=None):
    """Targets `entry_score_regime` lever — regime component."""
    return Probe(name=name, lever='entry_score_regime',
                 cohort=f'{base_cohort} and {regime_cond}',
                 op='+=', mags=mags or (mag,))


def entry_conv_probe(name, conv_cond, mag=0.020,
                     base_cohort='_qpos and decline > 0.020 and decline < 0.050',
                     mags=None):
    """Targets `entry_score_conv` lever — conv-derived component."""
    return Probe(name=name, lever='entry_score_conv',
                 cohort=f'{base_cohort} and {conv_cond}',
                 op='+=', mags=mags or (mag,))


def entry_quality_probe(name, quality_cond, mag=0.020,
                        base_cohort='_qpos and decline > 0.020 and decline < 0.050',
                        mags=None):
    """Targets `entry_score_quality` lever — fundamental quality component
    (added 2026-05-09 to break plateau).

    quality_cond should reference high-quality fundamental gates:
      - operation_margin, net_margin, gross_margin (high)
      - roe, roic (high)
      - debt_to_equity, long_term_debt_equity_ratio (low)
      - solvency_ratio (high)
      - revenue_growth, eps_growth (positive)
    """
    return Probe(name=name, lever='entry_score_quality',
                 cohort=f'{base_cohort} and {quality_cond}',
                 op='+=', mags=mags or (mag,))


def entry_signal_probe(name, mtf_cond='', regime_cond='', conv_cond='',
                       fund_cond='', mag=0.020,
                       base_cohort='_qpos and decline > 0.020 and decline < 0.050'):
    """Targets the new `entry_signal` lever (added 2026-05-09).

    `entry_signal += mag` when ALL conditions match. Base then does
    `score += entry_signal` before ranking, so contributions feed the
    unified entry score system. Supports:
      mtf_cond:    multi-timeframe (e.g., '_r5_up and _r3_md')
      regime_cond: regime gate (e.g., 'self._reg_qqq_up5 and _hyg_up3')
      conv_cond:   conv signal (e.g., 'conv > 1.5')
      fund_cond:   fundamental gate (e.g., '_ngt(_ops_z.X.Y, 0.20)')

    Different from entry_composite_probe (which targets `score` directly):
    this targets `entry_signal` which represents the SUMMED entry-component
    contribution — multiple bakes accumulate cleanly.
    """
    parts = [base_cohort]
    if mtf_cond:    parts.append(mtf_cond)
    if regime_cond: parts.append(regime_cond)
    if conv_cond:   parts.append(conv_cond)
    if fund_cond:   parts.append(fund_cond)
    cohort = ' and '.join(parts)
    return Probe(name=name, lever='entry_signal', cohort=cohort,
                 op='+=', mags=(mag,))


def exit_signal_probe(name, regime_cond='', pnl_cond='', fund_cond='',
                      momentum_cond='', mag=1.0):
    """Targets the new `exit_signal` lever (added 2026-05-09).

    `exit_signal += mag` when conditions match. Base exits when
    `exit_signal >= EXIT_THRESHOLD (1.0)`. Each contribution is a vote
    for exit; multiple votes can compound or any single vote at mag>=1.0
    forces exit. Supports:
      regime_cond:   regime gate (EXIT scope: only self._reg_*)
      pnl_cond:      PnL gate (e.g., 'pnl > 0.05')
      fund_cond:     fundamental in EXIT scope (use _ops_z, _vr_z, _capec, etc.)
      momentum_cond: multi-bar momentum (e.g., close > N-bar high)
    """
    parts = []
    if regime_cond:   parts.append(regime_cond)
    if pnl_cond:      parts.append(pnl_cond)
    if fund_cond:     parts.append(fund_cond)
    if momentum_cond: parts.append(momentum_cond)
    cohort = ' and '.join(parts) if parts else 'True'
    return Probe(name=name, lever='exit_signal', cohort=cohort,
                 op='+=', mags=(mag,), inject='EXIT')


def entry_composite_probe(name, mtf_cond='', regime_cond='', score_cond='',
                          conv_cond='', mag=0.020,
                          base_cohort='_qpos and decline > 0.020 and decline < 0.050'):
    """Entry probe firing when ALL specified components agree.

    Each *_cond is a Python expression evaluating to bool. When all
    non-empty conditions are True (AND-gated), score += mag fires.

    Components:
      mtf_cond    : multi-timeframe signal (e.g., '_r5_up and _r3_md')
      regime_cond : regime gate (e.g., 'self._reg_qqq_up5 and _hyg_up3')
      score_cond  : prior-score signal (e.g., 'score > 4.0')
      conv_cond   : conv signal (e.g., 'conv > 1.5')

    Use to test composite-scoring hypotheses without rebuilding base.
    """
    parts = [base_cohort]
    if mtf_cond:    parts.append(mtf_cond)
    if regime_cond: parts.append(regime_cond)
    if score_cond:  parts.append(score_cond)
    if conv_cond:   parts.append(conv_cond)
    cohort = ' and '.join(parts)
    return Probe(name=name, lever='score', cohort=cohort, op='+=', mags=(mag,))


def exit_momentum_probe(name, lookback_bars, regime_cond='',
                        gain_thr=0.0, mag=1.10):
    """Exit probe firing on multi-bar close-above-high momentum.

    Already in base: `if bars[-1].close > bars[-2].high: exit` (line 409,
    1-bar lookback). This helper extends to N-bar lookbacks.

    Mechanics: probe tests `close > max(high over last N bars)` AND
    optional regime AND optional pnl > gain_thr. If all match, petgt *= mag
    (boost profit target = exit faster on momentum).

    Usage in EXIT scope (inject='EXIT'). Note: needs `bars` variable
    available in EXIT scope — it IS via `self.history[TradeBar](sym, N, _RD)`.
    """
    parts = []
    parts.append(f'len(list(self.history[TradeBar](sym, {lookback_bars}+1, _RD))) >= {lookback_bars}+1')
    parts.append(f'f_(self.securities[sym].close) > max(f_(b.high) for b in list(self.history[TradeBar](sym, {lookback_bars}+1, _RD))[:-1])')
    if regime_cond: parts.append(regime_cond)
    if gain_thr > 0: parts.append(f'pnl is not None and pnl > {gain_thr}')
    cohort = ' and '.join(parts)
    return Probe(name=name, lever='petgt', cohort=cohort,
                 op='*=', mags=(mag,), inject='EXIT')


def exit_pull_back_probe(name, lookback_bars, regime_cond='',
                         loss_thr=0.0, mag=0.85):
    """Exit probe firing on multi-bar close-below-low pull-back.

    Inverse of momentum: tighten stop when close drops below N-bar low.
    """
    parts = []
    parts.append(f'len(list(self.history[TradeBar](sym, {lookback_bars}+1, _RD))) >= {lookback_bars}+1')
    parts.append(f'f_(self.securities[sym].close) < min(f_(b.low) for b in list(self.history[TradeBar](sym, {lookback_bars}+1, _RD))[:-1])')
    if regime_cond: parts.append(regime_cond)
    if loss_thr < 0: parts.append(f'pnl is not None and pnl < {loss_thr}')
    cohort = ' and '.join(parts)
    return Probe(name=name, lever='stop', cohort=cohort,
                 op='*=', mags=(mag,), inject='EXIT')


# ---------- non-saturated parent-cohort exploration ----------

# Parent cohorts that are SATURATED (≥2 score+= bakes already):
#   `_qpos and decline > 0.020 and decline < 0.050` (BAKE-ZONE) — WH+FC+FG
#   `_qpos and decline > 0.015 and decline < 0.020` (JUST-BELOW)  — JBC+J0
# Probes there must use different lever (wt_tilt) or be skipped.
#
# UNSATURATED parent cohorts to deliberately probe:
NON_SAT_PARENTS = [
    ('VL',  '_qpos and decline > 0.005 and decline < 0.012'),    # very-low decline
    ('NB',  '_qpos and decline > 0.020 and decline < 0.025'),    # narrow bake-zone
    ('AB',  '_qpos and decline > 0.050 and decline < 0.075'),    # above-bake
    ('AB2', '_qpos and decline > 0.075 and decline < 0.100'),    # higher above-bake
    ('QZ',  '_qzero and decline > 0.020 and decline < 0.050'),   # flat-QQQ × bake-zone
    ('QS',  '_qsneg and decline > 0.020 and decline < 0.050'),   # neg-QQQ × bake-zone
    ('HD',  '_qpos and _hyg_dn3 and decline > 0.020 and decline < 0.050'),  # defensive credit
    ('HU',  '_qpos and _hyg_up3 and decline > 0.020 and decline < 0.050'),  # risk-on credit
]


def non_saturated_cohort_round(rid, n_fresh_per_parent=4, extra_blocks=None):
    """Probe NON-saturated parent cohorts with fresh fund accessors.

    Per memory feedback_s001_destructive_stacking: BAKE-ZONE and JUST-BELOW
    have 3 and 2 bakes respectively; further score+= there destructively
    stacks. This helper EXPLICITLY routes probes to 8 unsaturated parents.

    Each parent gets n_fresh_per_parent fresh accessors × 2 mags = 8 specs.
    Default 4 fresh × 8 parents × 2 mags = 64 specs + extras.

    Useful when saturation guard blocks all auto-bake candidates and you
    want to explicitly explore where new bakes CAN land.
    """
    from s001.gen_s001_lib import Round, Probe, fund_gt
    from s001.gen_s001_diagnostics import pick_fresh_fields_under_explored

    R = Round(rid=rid, noops=4, priority=1)
    fresh = pick_fresh_fields_under_explored(n=n_fresh_per_parent * len(NON_SAT_PARENTS))
    fresh_idx = 0
    for parent_tag, parent_cohort in NON_SAT_PARENTS:
        for i in range(n_fresh_per_parent):
            if fresh_idx >= len(fresh): break
            accessor = fresh[fresh_idx]; fresh_idx += 1
            R.add(Probe(name=f'{parent_tag}{i}', lever='score', cohort=parent_cohort,
                        fund=fund_gt(accessor, 1e6),
                        op='+=', mags=ADD_VALS_PROVEN,
                        fresh_fields=(accessor,)))

    if extra_blocks: extra_blocks(R)
    add_minimal_aux_blocks(R)
    return R


# ---------- domain-diversified exploration ----------

def domain_diversified_round(rid, n_per_domain=6, extra_blocks=None):
    """Build a round that probes 5+ accessor domains in parallel.

    Per memory feedback_s001_post_bake_expansion_saturates: breakthrough
    bakes come from UNRELATED domains, not theme-expansion. This helper
    deliberately rotates through 5 fund-namespaces to maximize cross-
    domain coverage per round.

    n_per_domain: # fresh accessors per namespace (×2 mags = specs/domain)

    Domains rotated:
        _cfs (cash-flow), _inc (income), _vr (valuation), _ers
        (earning ratios), _bs (balance sheet untouched)
    Plus minimal aux + 4 NOOPs.

    Total ~5*n_per_domain*2 + 9 = ~69 specs at n_per_domain=6.
    For 96-floor compliance, set n_per_domain >= 9 (90 + 9 = 99).
    """
    from s001.gen_s001_lib import Round, Probe, fund_gt
    from s001.gen_s001_diagnostics import pick_fresh_fields

    R = Round(rid=rid, noops=4, priority=1)
    domains = ['_cfs', '_inc', '_vr', '_ers', '_bs']
    bake_zone = COHORT_BAKE_ZONE
    just_below = '_qpos and decline > 0.015 and decline < 0.020'

    # 5 domains × n_per_domain accessors × 2 mags in BAKE-ZONE
    for ns_idx, ns in enumerate(domains):
        fresh = pick_fresh_fields(n=n_per_domain, namespaces=[ns])
        for i, accessor in enumerate(fresh):
            R.add(Probe(name=f'D{ns_idx}_{i}', lever='score', cohort=bake_zone,
                        fund=fund_gt(accessor, 1e6),  # selective threshold
                        op='+=', mags=ADD_VALS_PROVEN,
                        fresh_fields=(accessor,)))

    # 1 spec per domain in JUST-BELOW (sample test)
    for ns_idx, ns in enumerate(domains):
        fresh = pick_fresh_fields(n=1, namespaces=[ns])
        if fresh:
            R.add(Probe(name=f'JD{ns_idx}', lever='score', cohort=just_below,
                        fund=fund_gt(fresh[0], 1e6), op='+=', mags=ADD_VALS_PROVEN))

    if extra_blocks: extra_blocks(R)
    add_minimal_aux_blocks(R)
    return R


# ---------- diagnostic round templates ----------

def bake_stability_round(rid, n_noops=8):
    """Tiny round (4-12 specs) re-running each active bake's accessor as
    isolation probe + extra NOOPs. Use to:
      - measure NOOP variance (n_noops > standard 4)
      - re-verify each bake's lift on current base
      - fast diagnostics with minimal compute

    Round size ~16-30 specs (audit floor 96 won't pass — set enforce_audit=False).
    """
    from s001.gen_s001_lib import Round, Probe
    from s001.gen_s001_diagnostics import _load_bake_log

    R = Round(rid=rid, noops=n_noops, priority=1)
    for entry in _load_bake_log():
        if entry.get('reverted'): continue
        # Strip threshold gate from cohort to isolate parent cohort
        full_cohort = entry['cohort']
        # Add isolation probe at the bake's exact spec
        R.add(Probe(name=f'V_{entry["axis"]}',
                    lever=entry['lever'], cohort=full_cohort,
                    op=entry['op'], mags=(entry['mag'],)))
    return R


def noop_only_round(rid, n_noops=16):
    """Pure variance-measurement round. Just runs N NOOPs on current base.
    No probes. Round-size floor must be relaxed (audit will fail at 16 < 96).

    Use to:
      - measure NOOP-NOOP variance (test if same code/base produces consistent
        car_mdd, or there's variance ±0.012 per memory s001 QC backtest variance)
    """
    from s001.gen_s001_lib import Round
    return Round(rid=rid, noops=n_noops, priority=1)


# ---------- one-line round template ----------

def pure_explore_round(rid, n_fresh_bz=12, n_fresh_jb=6, namespaces=None,
                       extra_blocks=None):
    """Build a complete pure-frontier exploration round in 1 call.

    - n_fresh_bz: # fresh-fund × score+= probes in BAKE-ZONE
    - n_fresh_jb: # fresh-fund × score+= probes in JUST-BELOW-BAKE
    - namespaces: pick_fresh_fields filter
    - extra_blocks: optional callable(R) for round-specific additions

    Caller still needs pretick_or_die() + run_audit_and_queue(R).
    Returns the Round; spec count = 2*(n_fresh_bz + n_fresh_jb) + ~9 aux+noops.

    Uses ONLY proven-productive blocks per net-EV memory:
    - bake_zone_grid (5%+ hit rate)
    - just-below-bake fresh-fund (where JBC was found)
    - add_minimal_aux_blocks (5 specs, audit-min)
    """
    from s001.gen_s001_lib import Round, fund_gt
    from s001.gen_s001_diagnostics import pick_fresh_fields

    R = Round(rid=rid, noops=4, priority=1)
    fresh = pick_fresh_fields(n=n_fresh_bz + n_fresh_jb, namespaces=namespaces)
    bz_specs = [(f'B{i}', a, fund_gt, 0) for i, a in enumerate(fresh[:n_fresh_bz])]
    bake_zone_grid(R, '', bz_specs, mags=ADD_VALS_PROVEN)

    just_below = '_qpos and decline > 0.015 and decline < 0.020'
    for i, accessor in enumerate(fresh[n_fresh_bz:n_fresh_bz + n_fresh_jb]):
        R.add(Probe(name=f'J{i}', lever='score', cohort=just_below,
                    fund=fund_gt(accessor, 0), op='+=', mags=ADD_VALS_PROVEN,
                    fresh_fields=(accessor,)))

    if extra_blocks: extra_blocks(R)
    add_minimal_aux_blocks(R)
    return R


# ---------- gen script entrypoint helper ----------

# Variables defined in s001 base.py entry/exit scopes — referencing any
# OTHER local-looking name (`_x`) in a probe cohort means a NameError that
# silently no-ops via try/except wrappers. Source: grep of base.py
# 2026-05-09. Update when base accessors change.
KNOWN_BASE_VARS = frozenset({
    # MTF / momentum
    '_r3', '_r5', '_r7', '_r20', '_r60', '_r252',
    '_r3_md', '_r5_up', '_r20_dn', '_r60_dn', '_r252_up', '_r252_dn',
    '_m3', '_m5', '_m7',
    # regime aliases (locally defined; rest must use self._reg_*)
    '_hyg_dn3', '_hyg_dn5', '_hyg_dn14', '_hyg_up3', '_hyg_up5',
    '_qqq_dn3', '_qqq_dn5', '_qqq_dn7',
    # qstate
    '_qpos', '_qneg', '_qzero', '_qsneg', '_qspos',
    # core trade vars
    'decline', 'conv', 'wt_tilt', 'score', 'pnl', '_bv', '_bc',
    'sym', 'vol_climax', '_capec', '_hi_cape', '_lo_cape',
    # _t* helpers
    '_om1yc', '_fcfg1yc', '_gm1yc', '_cfog1yc', '_roe1y_c', '_rg1yc',
    '_roic1yc', '_roic3mc', '_rt1yc',
    # entry signal accumulators (for self-reference in compound probes)
    'entry_signal', 'entry_score_mtf', 'entry_score_regime', 'entry_score_conv',
    'exit_signal',
    # day flags
    '_d2_4', '_d4_12',
    # vol
    '_v', '_vol20',
})

# Variables that look like locals (`_X`) but DO NOT exist in entry/exit
# scope — referencing these silently no-ops. Memory:
# `feedback_s001_regime_aliases` documents this.
FORBIDDEN_BASE_VARS = frozenset({
    '_r60_up', '_r7_up', '_r3_up', '_r20_up',  # not defined as bool aliases
    '_hyg_up7', '_hyg_up14',                   # use self._reg_* form
    '_qqq_up3', '_qqq_up5',                    # use self._reg_qqq_up3/5
    '_vxx_low', '_vxx_high', '_vxx_xhigh',
    '_reg_qqq_up3', '_reg_qqq_up5',            # missing self.
})

# ENTRY-only locals: defined inside _scan_entries; undefined at EXIT scope.
# Probes with inject='EXIT' that reference these silently NameError → caught
# by try/except → no-op → wasted backtest. R1839 PG_W05 round wasted ~16
# specs this way (petgt_fund_gate had `_qpos` gate at EXIT scope).
ENTRY_ONLY_VARS = frozenset({
    '_qpos', '_qzero', '_qsneg',          # q-state derivatives
    '_qa', '_qs', '_hs',                  # q/h state
    'decline',                            # per-stock decline gate
    '_v', '_bc',                          # volume / bond-cap buckets
    '_d2_4', '_d4_8', '_d6_12',           # decline buckets
    '_secc',                              # sector code
    '_accel',                             # return acceleration (_r3-_r7)
    '_capec',                             # cape ratio (entry derivation)
    '_vsc',                               # volume short cap
    '_woc', '_pegr', '_fcfg1yc',          # cached fundamentals
    '_pec',                               # PE cache
    '_ic1yc',                             # income-change cache
    '_haccel_loc',                        # entry-side haccel local (haccel
                                          # is also self._reg_haccel which IS
                                          # available at exit)
})


def cohort_var_check(probe) -> list[str]:
    """Return list of FORBIDDEN var names referenced in a probe's cohort
    as BARE locals (not `self._x` or `obj._x` attributes). These would
    silently no-op via try/except → wasted backtest.

    Inject-aware: probes with inject='EXIT' additionally flag ENTRY-only
    vars (they're undefined at exit scope).
    """
    import re as _re
    text = (probe.cohort or '') + ' ' + (probe.extra or '') + ' ' + (probe.fund or '')
    bad = []
    # Match `_var` only when NOT preceded by `.` (so `self._reg_x` is excluded).
    # Also catch bare `decline` (no underscore prefix) for ENTRY-only check.
    inject = getattr(probe, 'inject', 'ENTRY') or 'ENTRY'
    forbidden = set(FORBIDDEN_BASE_VARS)
    if inject == 'EXIT':
        forbidden |= ENTRY_ONLY_VARS
    for m in _re.finditer(r'(?<![.\w])(_?[a-z][a-z0-9_]*)\b', text):
        tok = m.group(1)
        # Only check tokens that look like our state vars (start with _ or
        # are 'decline'). Skip Python keywords / builtins by token shape.
        if not (tok.startswith('_') or tok == 'decline'):
            continue
        if tok in forbidden:
            bad.append(tok)
    return bad


def never_fires_check(probe) -> list[str]:
    """Return list of NEVER-FIRES rule violations in a probe's spec.

    Rules from memory feedback_s001_never_fires_patterns:
    - wt_tilt × decline ≥ 0.05 — historically zero positive lifts (84 axes audit)
    - conv with mag ≥ 1.5 — catastrophic on small-decline cohorts (memory)
    - skip ENTRY with low-selectivity gates (e.g. `is not None` on common fields)
    - _qpos × decline > 0.075 — empirical 0/32 fire rate (audit 2026-05-09)
    - _qsneg with no decline filter — 0/9 fire rate

    Each violation as descriptive string; empty list = clean.
    """
    import re as _re
    violations = []
    cohort = (probe.cohort or '')
    fund = (probe.fund or '')
    text = cohort + ' ' + fund

    # Rule 1: wt_tilt × decline ≥ 0.05 — extract decline lower bound from
    # patterns like `decline > 0.05`, `decline > 0.06`, `decline > 0.075`.
    if probe.lever == 'wt_tilt':
        m = _re.search(r'decline\s*>\s*(\d+\.?\d*)', text)
        if m:
            try:
                lo = float(m.group(1))
                if lo >= 0.05:
                    violations.append(f'wt_tilt × decline ≥ 0.05 (lo={lo})')
            except ValueError:
                pass

    # Rule 2: conv with mag ≥ 1.5
    if probe.lever == 'conv' and probe.mags:
        bad_mags = [m for m in probe.mags if m >= 1.5]
        if bad_mags:
            violations.append(f'conv × mags ≥ 1.5: {bad_mags}')

    # Rule 3: low-selectivity gate (`is not None` on _ac/_sr fields)
    if _re.search(r'_(?:ac|sr)_z\.[a-z_]+\s+is\s+not\s+None', text):
        violations.append('low-selectivity gate (_ac/_sr is not None)')

    # Rule 4: empirical never-fire cohort patterns
    # _qpos × decline > 0.075 — 0/32 fire rate across R1690-R1705 audit.
    # All 32 probes were silent; deep declines are filtered out by the
    # broader strategy gates before reaching probe scope.
    if '_qpos' in text:
        m = _re.search(r'decline\s*>\s*(\d+\.?\d*)', text)
        if m:
            try:
                lo = float(m.group(1))
                if lo >= 0.075:
                    violations.append(
                        f'_qpos × decline ≥ 0.075 (empirical 0/32 fire rate)')
            except ValueError:
                pass

    # _qsneg without decline filter — 0/9 fire rate
    if '_qsneg' in text and not _re.search(r'decline\s*[<>]', text):
        violations.append('_qsneg with no decline filter (empirical 0/9 fire)')

    # Rule 4b: _qsneg × _secc × self._reg_* — empirically silent.
    # R1942+R1945 audit (2026-05-11): 45 WSN probes across 5 axes with
    # `_qsneg × decline_band × _secc × regime` cohort, 40 (89%) exact-NOOP
    # silent, 5 negative. 0 productive lifts. _qsneg + decline already
    # narrows population to ~9 fires; adding sector AND regime gates
    # makes the cohort effectively unreachable.
    if ('_qsneg' in text
            and _re.search(r'_secc\s*==', text)
            and _re.search(r'self\._reg_', text)):
        violations.append(
            '_qsneg × _secc × regime — empirical 89% silent, 0 productive '
            '(R1942/R1945 audit)')

    # Rule 4c: _hi_vol / _hi_cape × productive_regime × small_decline.
    # 2026-05-11 audit: 201 historical probes across 30+ rounds; max
    # delta +0.00021 (below +0.0005 bake threshold), 82% silent, 16%
    # negative, 0 bakes. The parent-novelty hypothesis (HV/HC opens new
    # cohort surface) is REFUTED empirically. Block to save backtests.
    parent_gate = _re.search(r'\b_hi_(?:vol|cape)\b', text)
    has_regime = bool(_re.search(r'self\._reg_', text))
    has_decl_band = bool(_re.search(r'decline\s*[<>]', text))
    if parent_gate and has_regime and has_decl_band:
        violations.append(
            '_hi_vol/_hi_cape × regime × decline — empirical 82% silent, '
            'max lift +0.00021, 0 bakes (201 historical probes audit)')

    # Rule 6: exit_signal mag validity (2026-05-09 v7).
    # R1745 evidence: HOLD probes (negative exit_signal mags) are
    # CATASTROPHIC for mean-reversion strategy — they prevent profit-
    # taking on close>prev_high rally days, causing peak holds and
    # ride-back losses. cm dropped to 0.77-2.49 (-0.7 to -2.4 vs NOOP).
    if probe.lever == 'exit_signal' and probe.op == '+=' and probe.mags:
        zero_mags = [m for m in probe.mags if m == 0.0]
        if zero_mags and len(zero_mags) == len(probe.mags):
            violations.append(
                f'exit_signal mag 0.0: no contribution')
        # HOLD probes (all-negative mags) — catastrophic per R1745
        all_negative = [m for m in probe.mags if m < 0.0]
        if (all_negative and len(all_negative) == len(probe.mags)):
            violations.append(
                f'exit_signal HOLD probe (all neg mags {all_negative}): '
                f'R1745 evidence — catastrophic on mean-reversion (-2.4 cm)')
        # Multi-mag duplication: 2+ mags all ≥0.6 produce identical results
        all_threshold_or_above = [m for m in probe.mags if m >= 0.6]
        if (len(all_threshold_or_above) >= 2
                and len(all_threshold_or_above) == len(probe.mags)):
            violations.append(
                f'exit_signal multi-mag ≥0.6 duplication: {probe.mags} '
                f'all fire alone past threshold; use single mag')

    # Rule 7: mag 0.04 score+= empirical catastrophic-likelihood guard.
    # Audit since R1740: 5/7 productive bakes at mag 0.02; 2/7 at 0.04 (both
    # on extreme-narrow _qzero × 0.012-0.015 only). 24+ catastrophic specs at
    # 0.04 (cm < 3.10) over the same window — net-negative EV.
    # Block 0.04 on:
    #   (a) _qzero / _qsneg outside the 0.012-0.015 safe band
    #   (b) _qpos × bake-zone × fund_gate (R1751 LG, R1754 QPS catastrophic)
    #   (c) any cohort with regime+fund double gate (R1754 QZR_HACCEL/HU5)
    if probe.lever == 'score' and probe.op == '+=' and probe.mags:
        bad_mag_04 = [m for m in probe.mags if 0.035 < m <= 0.045]
        if bad_mag_04:
            on_qzero_or_qsneg = '_qzero' in text or '_qsneg' in text
            on_safe_band = bool(_re.search(
                r'decline\s*>\s*0\.012\s+and\s+decline\s*<\s*0\.015', text))
            on_qpos = '_qpos' in text
            has_regime = bool(_re.search(r'self\._reg_', text)) or bool(
                _re.search(r'_(?:hyg|qqq|vxx)_(?:dn|up|fall|rais)', text))
            has_fund = '_ngt(' in text or '_nlt(' in text
            if on_qzero_or_qsneg and not on_safe_band:
                violations.append(
                    f'mag 0.04 score+= on _qzero/_qsneg outside 0.012-0.015 '
                    f'safe band (24% catastrophic rate)')
            elif has_regime and has_fund:
                violations.append(
                    f'mag 0.04 score+= on regime+fund cohort '
                    f'(R1754 QZR catastrophic at -0.30)')
            elif on_qpos and has_fund:
                violations.append(
                    f'mag 0.04 score+= on _qpos × fund_gate '
                    f'(R1751 LG / R1754 QPS catastrophic; 0/7 bakes since R1740)')

    # Rule 8 (2026-05-10): _qzero × _d2_4 × score *= 1.05 CATASTROPHIC.
    # R1786 evidence: 8/10 QZB_D2_4 specs cm 2.59-3.20 (vs NOOP 3.253);
    # average -0.31 regression. Cohort over-boosts mean-revert population
    # on small-decline days. Memory: feedback_s001_qzero_d2_4_catastrophic.
    if probe.lever == 'score' and probe.op == '*=' and probe.mags:
        if '_qzero' in text and '_d2_4' in text:
            high_mag = any(1.04 <= m <= 1.06 for m in probe.mags)
            if high_mag:
                violations.append(
                    f'_qzero × _d2_4 × score *= 1.05 catastrophic '
                    f'(R1786: 8/10 specs -0.31 avg regression)')

    # Rule 9 (2026-05-12): empirical 100%-silent cohort signature blocklist.
    # Deep review of R2010-R2027 (2,034 probes) found 49 cohort signatures
    # (parent × sector × regime_pair) with 100% silent rate at n≥6. Sector ×
    # regime pair never co-occurs in QQQ universe — gate is permanently dead.
    # R2027 had 38% silent waste from these signatures. Block at gen time.
    sm = _re.search(r'_secc\s*==\s*(\d+)', text)
    parent_hit = ('_qpos' if '_qpos' in text else
                  '_qzero' if '_qzero' in text else
                  '_qsneg' if '_qsneg' in text else None)
    if sm and parent_hit:
        sec = sm.group(1)
        regs = tuple(sorted(set(_re.findall(r'_reg_(\w+)', text))))
        # Only test 2-regime signatures (where overlap is rarest)
        if len(regs) >= 2:
            sig = (parent_hit, sec, regs[:2])
            if sig in _DEAD_COHORT_SIGNATURES:
                violations.append(
                    f'Rule 9: dead cohort signature {parent_hit} × S{sec} '
                    f'× {regs[:2]} — historical 100% silent (n≥6) per '
                    f'cohort_silent_signatures.json')

    # Rule 12 (2026-05-14): qstate-aware (qstate, sector, ratio) blocklist.
    # Same (sector, ratio) may be productive on _qzero but dead on _qpos
    # (e.g. S311 × pb_ratio: 1 hist bake on _qzero, 12/15 cata on _qpos).
    # Rule 12 blocks the specific qstate match without dropping the other.
    qstate_hit = ('_qpos' if '_qpos' in text else
                  '_qzero' if '_qzero' in text else
                  '_qsneg' if '_qsneg' in text else None)
    if sm and qstate_hit:
        sec = sm.group(1)
        for (q, bsec, field), entry in _QSTATE_BLOCKLIST.items():
            if q == qstate_hit and bsec == sec and field in text:
                reason = entry.get('reason', 'dead')
                trials = entry.get('total', '?')
                violations.append(
                    f'Rule 12: {q} × S{sec} × {field} {reason} '
                    f'({entry.get("fired", entry.get("cata", "?"))}/{trials})')
                break

    # Rule 11 (2026-05-13, fixed 2026-05-18): ratio-wide dead list. 11 ratios
    # with 0 positive lifts across n≥25 trials (all sectors): CR, DC, EBM,
    # EVEB, FCFY, GM, IC, PCF, PEG, ROE, SOLV. Block these ratios in ANY cohort.
    # 2026-05-18: changed substring → word-boundary match. Old `if dead in text`
    # blocked variants (e.g., `_vr_z.ev_to_ebitda_1_year_growth` matched
    # `_vr_z.ev_to_ebitda`). Variants are DIFFERENT fields with independent
    # statistical properties; should not inherit dead status. Review #24 found
    # this lost 4-5 fresh ratio variants in R2766.
    for dead_field in _DEAD_RATIOS:
        if _re.search(rf'(?<![a-zA-Z0-9_]){_re.escape(dead_field)}(?![a-zA-Z0-9_])', text):
            violations.append(
                f'Rule 11: {dead_field} ratio-wide dead — '
                f'0/{_DEAD_RATIOS[dead_field].get("evidence", "n≥25")} positive lifts')
            break

    # Rule 13 (2026-05-14): block 4F+ compound probes.
    # R2126 audit: 40/40 4F probes silent (100%) — empty cohort. Cross-
    # sectional fundamental data lacks coverage for 4+ conjunctive ratio
    # conditions on QQQ universe.
    # 2F = 1 cash-flow gate + 1 ratio gate = 2 _ngt/_nlt calls
    # 3F-multiratio = 1 cash-flow + 2 ratio gates = 3 _ngt/_nlt calls
    # 4F = 3F-multiratio + decline filter = 3 _ngt/_nlt + 'decline >'
    fund_gate_count = len(_re.findall(r'_n(?:gt|lt)\(_[a-z]+_z?\.', text))
    has_decline = bool(_re.search(r'decline\s*>', text))
    if fund_gate_count >= 3 and has_decline:
        violations.append(
            f'Rule 13: 4F+ compound ({fund_gate_count} fund gates + '
            f'decline filter) — R2126 audit: 100% silent (empty cohort)')

    # Rule 35 (2026-05-18): cohort with inline ratio + _ngt fresh-fund threshold
    # = empty cohort. R2644 evidence: 11/15 EXACT-NOOP when probe combined
    #   regime + decline + `_vr_z.X > Y` + `_ngt(_bs_z.Y > Z)`. The compound
    # fund-z ratio AND balance-sheet threshold over-restricts cohort → silent.
    # Detection: count inline comparisons `_vr_z.X op N` PLUS `_ngt(...)` calls.
    # Threshold ≥ 2 combined fund gates + decline filter = block.
    inline_fund_cmp = len(_re.findall(
        r'_vr_z\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*\s*(?:>=|<=|>|<|==)\s*[\d.eE+-]+', text))
    total_fund_gates = fund_gate_count + inline_fund_cmp
    if total_fund_gates >= 2 and fund_gate_count >= 1 and inline_fund_cmp >= 1 and has_decline:
        violations.append(
            f'Rule 35: compound cohort ({inline_fund_cmp} inline ratio cmp + '
            f'{fund_gate_count} _ngt fund gates + decline) — R2644 evidence: '
            f'11/15 EXACT-NOOP. Use SOLE fresh gate, not compound.')

    # Rule 15 (2026-05-15): block dead sectors S103/S309/S313.
    # 2026-05-15 query: S103 max CM 3.418, S313 max 3.477, S309 max 3.482 —
    # all below NOOP variance ceiling 3.487 across 870-2728 trials each.
    # Sparse QQQ population (financials/energy/discretionary absent).
    if sm:
        sec = sm.group(1)
        if sec in ('103', '309', '313'):
            violations.append(
                f'Rule 15: S{sec} STRUCTURALLY DEAD in QQQ — '
                f'sparse sector, max CM below NOOP variance across n≥800 trials. '
                f'Use S102/S205/S308/S311 only (memory s001_dead_sectors_S103_S309_S313).')

    # Rule 16 (2026-05-15): restrictive ratio-thresholds → empty cohort on QQQ.
    # R2215 evidence: 5 axes with these thresholds produced 100% NOOP-fingerprint
    # (orders=15058 identical to NOOP). QQQ universe is tech-heavy with sparse
    # support for these ratio bands.
    # Extended 2026-05-15 from R2240-R2251 fire-rate audit (13-36% fire on
    # _bs_z/_inc_z/_cfs_z with 1e9+ thresholds): big-cap absolute thresholds
    # shrink cohort × regime × decline intersection to ~5% of universe.
    _RESTRICTIVE_BANDS = [
        (r'_ngt\(_vr_z\.ps_ratio\s*,\s*(\d+\.?\d*)\)', 5.0, 'ps_ratio > 5: ~2 QQQ stocks pass'),
        (r'_ngt\(_ops_z\.quick_ratio\s*,\s*(\d+\.?\d*)\)', 1.0, 'quick_ratio > 1.0: rare in tech'),
        (r'_ngt\(_vr_z\.payout_ratio\s*,\s*(\d+\.?\d*)\)', 0.20, 'payout > 0.20: most QQQ pays <20%'),
        (r'_ngt\(_vr_z\.forward_dividend_yield\s*,\s*(\d+\.?\d*)\)', 0.02, 'fdy > 0.02: most QQQ pays <2%'),
        (r'_ngt\(_vr_z\.pe_ratio\s*,\s*(\d+\.?\d*)\)', 30.0, 'pe > 30: half of QQQ pass'),
        (r'_ngt\(_vr_z\.normalized_pe_ratio\s*,\s*(\d+\.?\d*)\)', 30.0, 'normalized_pe > 30: half QQQ'),
        (r'_ngt\(_vr_z\.pb_ratio\s*,\s*(\d+\.?\d*)\)', 5.0, 'pb_ratio > 5: ~30% QQQ pass'),
        (r'_ngt\(_ops_z\.net_margin\s*,\s*(\d+\.?\d*)\)', 0.15, 'net_margin > 0.15: ~half QQQ'),
        # 2026-05-15 fire-rate audit: big-cap absolute thresholds shrink cohort
        # severely when combined with regime + decline gates. Block 1e9+ thresholds
        # on these accessor classes when probe is already in a 6-cond cohort.
        (r'_ngt\(_bs_z\.long_term_debt\.\w+\s*,\s*([\d.]+e?\d*)\)', 1e9,
         'long_term_debt > 1e9: ~10% QQQ; 6-cond intersection silent'),
        (r'_ngt\(_bs_z\.total_debt\.\w+\s*,\s*([\d.]+e?\d*)\)', 1e9,
         'total_debt > 1e9: ~15% QQQ; 6-cond intersection silent'),
    ]
    for pat, restrictive_thr, reason in _RESTRICTIVE_BANDS:
        m = _re.search(pat, text)
        if m:
            try:
                thr = float(m.group(1))
                if thr >= restrictive_thr:
                    violations.append(
                        f'Rule 16: restrictive threshold ({reason}); '
                        f'use broader threshold or fewer cohort axes. '
                        f'Evidence: R2215 axes with such thresholds 100% NOOP-fingerprint.')
                    break
            except ValueError:
                pass

    # Rule 14 (2026-05-15, RELAXED 2026-05-15): block 7+ AND-conjunctive cohorts.
    # CORRECTION 2026-05-15: original Rule 14 blocked ≥5 conds, but base audit
    # reveals EVERY productive bake (BAKE-58 RT_S205 +0.00564, BAKE-WD2G_QPOS_
    # S102_HA_HD14_2F_QPOS_PS_FCF-R2103 +0.00862, etc.) uses 6-cond cohorts:
    # `parent + sector + 2 regimes + cash-flow anchor + ratio gate`.
    # The R2209-R2212 silent rate was due to wrong (sector, ratio) combos, NOT
    # 6-cond shape. Relax threshold from ≥5 to ≥7.
    cond_components = 0
    if _re.search(r'\b_q(?:pos|zero|sneg)\b', text):
        cond_components += 1
    if _re.search(r'_secc\s*==', text):
        cond_components += 1
    cond_components += len(set(_re.findall(r'self\._reg_(\w+)', text)))
    cond_components += fund_gate_count
    if _re.search(r'decline\s*[<>]', text):
        cond_components += 1
    if cond_components >= 7:
        violations.append(
            f'Rule 14: cohort has {cond_components} AND-conditions ≥ 7 '
            f'(very narrow; 6 is the productive bake shape). Drop sector OR '
            f'one regime OR one fund gate.')

    # Rule 10 (2026-05-13): empirical (sector, ratio_field) blocklist.
    # Deep review of R2050-R2096 (~4000 probes) found 20 (sector, ratio)
    # pairs that are either 100% silent (S309 × ps_ratio: 0/75) OR ≥80%
    # catastrophic with zero positives (S102 × peg_ratio: 10/10 cata).
    # Block at gen time to stop wasting ~30 specs/round on these.
    if sm:
        sec = sm.group(1)
        # Match any ratio field reference in cohort
        for (bsec, field), entry in _GATE_SECTOR_BLOCKLIST.items():
            if bsec == sec and field in text:
                reason = entry.get('reason', 'dead')
                trials = entry.get('total', 0)
                violations.append(
                    f'Rule 10: S{sec} × {field} {reason} '
                    f'(historical {entry.get("fired", entry.get("cata", "?"))}/{trials})')
                break

    # Rule 5: score-DEMOTE (multiplicative *= < 1.0) — broad demote dead.
    # R1690-R1707: 14 trials, 0 positive. R1709 BREAKTHROUGH: +0.00415 on
    # narrow `_qpos × decline > 0.060 × self._reg_double_panic` (BAKE-DE).
    # Refined rule: only block demotes on BROAD cohorts (no regime gate
    # AND no deep-decline gate). Narrow cohorts may be productive.
    if probe.lever == 'score' and probe.op == '*=' and probe.mags:
        bad_demotes = [m for m in probe.mags if m < 0.95]
        if bad_demotes and len(bad_demotes) == len(probe.mags):
            # 2026-05-12 refinement: cohorts with ≥2 regime gates are
            # narrow-enough that Rule 5 false-positives. R2029 was blocking
            # productive-cell cohorts (_qzero × S308 × HD14+HD3) — these
            # have regimes baked into the parent×sector×regime intersection.
            regime_count = len(set(_re.findall(r'self\._reg_(\w+)', text)))
            has_deep_decline = False
            m_dl = _re.search(r'decline\s*>\s*(\d+\.?\d*)', text)
            if m_dl:
                try:
                    has_deep_decline = float(m_dl.group(1)) >= 0.05
                except ValueError:
                    pass
            narrow_enough = regime_count >= 2 or has_deep_decline
            if not narrow_enough:
                violations.append(
                    f'score-DEMOTE on BROAD cohort (mags {bad_demotes}): '
                    f'0/14 historical lifts; need ≥2 regimes OR deep-decline')

    # Rule 14 (2026-05-14): conv lever cohort/mag guards from R2173-R2174 audit.
    # 195 conv probes: 20% pos / 0% cata / 50% silent. But specific patterns
    # systematically silent or destructive:
    #   - conv × decline < 0.04: empirically 0 pos, several destructive
    #   - conv × mag > 1.30: deep-mag CV_D005_CAP -0.00064
    #   - conv × _qpos × hyg_dn3 alone (no haccel): CV_HD3_NRW -0.00096
    if probe.lever == 'conv':
        m = _re.search(r'decline\s*>\s*(\d+\.?\d*)', text)
        if m:
            try:
                lo = float(m.group(1))
                # R2175 BAKE-CV_D02_HD14 +0.00128: low-decline productive
                # on HD14, only DEAD on haccel. Refine rule to haccel-only.
                if lo < 0.04 and '_reg_haccel' in text:
                    violations.append(
                        f'Rule 14a: conv × haccel × decline < 0.04 '
                        f'(lo={lo}) — R2173-R2175 audit: 0 pos / destructive '
                        f'(other regimes may still be productive)')
            except ValueError:
                pass
        if probe.mags:
            bad_mags = [m for m in probe.mags if m > 1.30]
            if bad_mags and len(bad_mags) == len(probe.mags):
                violations.append(
                    f'Rule 14b: conv × all mags > 1.30: {bad_mags} — '
                    f'R2174 CV_D005_CAP -0.00064 destructive')
        # _qpos × hyg_dn3 alone (no productive regime pair): destructive for conv
        # Allowed if paired with: haccel, hyg_dn14, hyg_dn5, qqq_up3, vxx_falling3
        OTHER_PROD_REGIMES = ('_reg_haccel', '_reg_hyg_dn14', '_reg_hyg_dn5',
                              '_reg_qqq_up3', '_reg_vxx_falling3')
        if ('_qpos' in text and '_reg_hyg_dn3' in text
                and not any(r in text for r in OTHER_PROD_REGIMES)):
            violations.append(
                'Rule 14c: conv × _qpos × hyg_dn3 alone (no productive regime pair) — '
                'R2173 CV_HD3_NRW -0.00096 destructive')

        # Rule 14d (2026-05-14): conv × sector × narrow regime is silent.
        # R2175/R2179 audit: CV_S206_VXXF, CV_S308_VXXF, CV_S206_Q3, CV_S308_Q3
        # all 5/5 silent (cohort fires too rarely on narrow sector + narrow regime).
        # Productive conv bakes use broad regimes (no sector OR S102/S311 only).
        sm_cv = _re.search(r'_secc\s*==\s*(\d+)', text)
        if sm_cv:
            sec = sm_cv.group(1)
            # Block sector × VXXF or sector × Q3 alone (no haccel/HD14 supplement)
            narrow_regimes = ('_reg_vxx_falling3', '_reg_qqq_up3')
            broad_regimes = ('_reg_haccel', '_reg_hyg_dn14', '_reg_hyg_dn5')
            has_narrow = any(r in text for r in narrow_regimes)
            has_broad = any(r in text for r in broad_regimes)
            # Block S{206,308,205,309,310,313} (NOT S102/S311) × narrow_alone
            dead_sectors = {'205', '206', '308', '309', '310', '313'}
            if (sec in dead_sectors and has_narrow and not has_broad):
                violations.append(
                    f'Rule 14d: conv × S{sec} × narrow regime (Q3/VXXF) alone — '
                    f'R2175/R2179 audit: 5/5 silent (cohort fires too rarely)')

    # Rule 17 (2026-05-15): score *= BOOST on S102 × haccel × HD14/HD5 cells is
    # destructive — antagonistic to existing wt_tilt DEMOTE bakes on the same
    # cohort. Evidence: SEC_NI_HAHD14_QZERO_S102 R2252 m104/m108/m110/m112 all
    # -0.00574; SEC_PS_HAHD5_QPOS_S102 R2254 m104/m108/m112 -0.02 to -0.022.
    # Score-BOOST tries to UP-RANK stocks that wt_tilt DEMOTE has DOWN-WEIGHTED
    # → destructive interference. Block at gen time.
    if (probe.lever == 'score' and probe.op == '*=' and probe.mags
            and all(m > 1.0 for m in probe.mags)):
        sm_s102 = _re.search(r'_secc\s*==\s*102\b', text)
        has_haccel = '_reg_haccel' in text
        has_hd14_or_hd5 = ('_reg_hyg_dn14' in text or '_reg_hyg_dn5' in text)
        if sm_s102 and has_haccel and has_hd14_or_hd5:
            violations.append(
                'Rule 17: score *= BOOST × S102 × haccel × (HD14|HD5) — '
                'antagonistic to existing wt_tilt DEMOTE bakes. R2252 -0.006 ×4, '
                'R2254 -0.022 ×3 catastrophic. Use wt_tilt DEMOTE direction '
                'or different sector/regime.')

    # Rule 18 (2026-05-15): regime-pair dead-zone in 6-cond decline-band cohorts.
    # R2240-R2262 audit (SEC_* axes, n≥10): regime pairs HA+Q3 (0/10), HD14+HD3
    # (0/10), HD3+Q3 (0/14) fired 0% — cohort gate × decline 2-5% intersection
    # is empty. Saves ~34 specs/round when these pairs appear with decline-band.
    if _re.search(r'_secc\s*==', text) and _re.search(r'decline\s*>\s*0\.0[12]', text):
        regimes = set(_re.findall(r'self\._reg_(\w+)', text))
        DEAD_PAIRS = [
            {'haccel', 'qqq_up3'},
            {'hyg_dn14', 'hyg_dn3'},
            {'hyg_dn3', 'qqq_up3'},
        ]
        for dp in DEAD_PAIRS:
            if dp.issubset(regimes):
                pair_str = '+'.join(sorted(dp))
                violations.append(
                    f'Rule 18: regime pair {pair_str} × decline-band 2-5% in '
                    f'6-cond SEC cohort — empirical 0% fire rate (n≥10). '
                    f'Use a different regime pair (HA+HD14, HD3+VF productive).')
                break

    # Rule 19 (2026-05-15): wt_tilt DEMOTE × _qzero × S311 × HD3+VF × PS>3 is
    # MONOTONICALLY destructive. R2265 evidence: m70=-0.0216, m80=-0.0228,
    # m85=-0.0233, m90=-0.0239 (4 mags, consistent monotonic). Cohort holds
    # productive stocks — demoting them via wt_tilt catastrophic. Try
    # score BOOST or wt_tilt BOOST direction instead.
    if (probe.lever == 'wt_tilt' and probe.op == '*=' and probe.mags
            and all(m < 1.0 for m in probe.mags)
            and _re.search(r'_qzero\b', text)
            and _re.search(r'_secc\s*==\s*311\b', text)
            and '_reg_hyg_dn3' in text and '_reg_vxx_falling3' in text
            and '_vr_z.ps_ratio' in text):
        violations.append(
            'Rule 19: wt_tilt DEMOTE × _qzero × S311 × HD3+VF × PS>3 — '
            'R2265 evidence: -0.022 to -0.024 across 4 mags MONOTONIC. '
            'Cohort holds productive stocks; use BOOST direction instead.')

    # Rule 20 (2026-05-15): empirical silent-cohort signatures.
    # R2200-R2268 audit found 6 (parent, sector, regime_pair, gate-class)
    # patterns with 0% fire rate at n≥5 trials. Loaded from
    # silent_sec_signatures.json. Saves ~30 specs/round when patterns recur.
    sm_r20 = _re.search(r'_secc\s*==\s*(\d+)', text)
    parent_m = _re.search(r'\b(_qpos|_qzero|_qsneg)\b', text)
    if sm_r20 and parent_m and _SILENT_SEC_SIGS:
        sec = sm_r20.group(1)
        parent = parent_m.group(1).upper().replace('_', '')
        regs = sorted(set(_re.findall(r'_reg_(\w+)', text)))[:2]
        # Map regimes to tags
        REGTAG = {'haccel': 'HA', 'hyg_dn14': 'HD14', 'hyg_dn3': 'HD3',
                  'hyg_dn5': 'HD5', 'qqq_up3': 'Q3', 'vxx_falling3': 'VF',
                  'double_panic': 'DP'}
        reg_tags = tuple(sorted([REGTAG.get(r, '') for r in regs if r in REGTAG]))
        # Map accessor to gate class
        gate_class = None
        if '_vr_z.ps_ratio' in text: gate_class = 'PS'
        elif '_vr_z.pe_ratio' in text: gate_class = 'PE'
        elif '_ops_z.roa' in text: gate_class = 'ROA'
        elif '_ops_z.net_margin' in text: gate_class = 'NM'
        elif '_cfs_z.free_cash_flow' in text: gate_class = 'FCF'
        elif '_cfs_z.operating_cash_flow' in text: gate_class = 'OCF'
        elif '_bs_z.cash_and_short_term' in text: gate_class = 'CSH'
        elif '_inc_z.net_income' in text: gate_class = 'NI'
        if gate_class and (parent, sec, reg_tags, gate_class) in _SILENT_SEC_SIGS:
            violations.append(
                f'Rule 20: empirical silent signature ({parent}, S{sec}, '
                f'{"+".join(reg_tags)}, {gate_class}) — 100% silent at n≥5 '
                f'(silent_sec_signatures.json).')

    # Rule 21 (2026-05-15): petgt LOOSEN (mag > 1.0) on Q3/rally regimes is
    # destructive. R2263 PEL_HD14_FCF -0.013 to -0.019, R2284 PEL_Q3_FCF
    # -0.01191 × 3 mags catastrophic. Loosening profit-target during rally
    # regimes causes premature loss when reversal hits.
    if (probe.lever == 'petgt' and probe.op == '*=' and probe.mags
            and all(m > 1.0 for m in probe.mags)):
        if ('_reg_qqq_up3' in text or '_reg_hyg_up' in text
                or '_reg_vxx_falling3' in text):
            violations.append(
                'Rule 21: petgt LOOSEN × rally-regime (Q3/HUP/VF) — '
                'R2263/R2284 evidence: -0.012 to -0.019 catastrophic. '
                'Use petgt TIGHTEN or different regime.')

    # Rule 22 (2026-05-15): stop TIGHTEN (mag < 1.0) on deep losers (pnl < -0.08)
    # is catastrophic. R2268 STT_HA_DEEP_LOSE m85 = -0.12304 (worst single
    # probe of session). Tightening stop on deep losers forces premature
    # exits, locking in catastrophic losses.
    if (probe.lever == 'stop' and probe.op == '*=' and probe.mags
            and all(m < 1.0 for m in probe.mags)):
        m_pnl = _re.search(r'pnl\s*<\s*(-\d+\.?\d*)', text)
        if m_pnl:
            try:
                pnl_thr = float(m_pnl.group(1))
                if pnl_thr < -0.06:
                    violations.append(
                        f'Rule 22: stop TIGHTEN × deep losers (pnl < {pnl_thr}) — '
                        f'R2268 evidence: -0.12 catastrophic. Use stop LOOSEN '
                        f'(let losers recover) or shallower loss threshold.')
            except ValueError:
                pass

    # Rule 23 (2026-05-15): small-sector × regime-pair × tight fund-gate goes
    # SILENT (empty cohort). R2287-R2289 evidence: 91/62/75% silent rate.
    # Small sectors: S102 (Energy ~1% of QQQ), S205 (Industrials ~5%),
    # S309 (Utilities). Combined with regime-pair AND tight fund-gate → 0
    # stocks pass. Skip these axes to avoid wasted specs.
    SMALL_SECTORS = {'102', '205', '309'}
    sm = _re.search(r'_secc\s*==\s*(\d+)', text)
    if sm and sm.group(1) in SMALL_SECTORS:
        # Count regime conditions in cohort text
        n_regimes = len(_re.findall(r'self\._reg_[a-z_0-9]+', text))
        # Tight gate detectors: 1e7+ for raw cash flows; 0.10+ for margins
        tight_gate = bool(
            _re.search(r'_ngt\([^,]+,\s*1e[78]\)', text)  # cash >= 1e7
            or _re.search(r'_ngt\([^,]+,\s*0\.[12]\d*\)', text)  # margin > 0.10+
            or _re.search(r'_ngt\([^,]+,\s*[2-9]\d?\)', text)  # ratio > 20+ etc
        )
        if n_regimes >= 2 and tight_gate:
            violations.append(
                f'Rule 23: small-sector S{sm.group(1)} × {n_regimes}-regime '
                f'× tight fund-gate — empirical 91% silent (R2287-R2289). '
                f'Use single regime OR broader gate (e.g. 1e6 instead of 1e7).')

    # Rule 24 (2026-05-15): _qzero × regime-pair × sector goes SILENT.
    # _qzero captures only neutral-momentum QQQ days (~20%). Combined with
    # 2-regime narrowing + sector + fund-gate → 0 stocks. R2290 evidence:
    # 25/25 axes silent. Use _qpos for regime-pair cohorts.
    if _re.search(r'\b_qzero\b', text):
        n_regimes_qz = len(_re.findall(r'self\._reg_[a-z_0-9]+', text))
        has_sector = bool(_re.search(r'_secc\s*==\s*\d+', text))
        has_gate = bool(_re.search(r'_ngt\(', text))
        if n_regimes_qz >= 2 and has_sector and has_gate:
            violations.append(
                f'Rule 24: _qzero × {n_regimes_qz}-regime × sector × fund-gate '
                f'— R2290 evidence: 25/25 silent. _qzero narrows by itself; '
                f'use _qpos for regime-pair cohorts.')

    # Rule 25 (2026-05-15): empirical (sector, regime-pair) dead combos.
    # R2280-R2295 audit: 6 combos have ≥5 probes 0 fired (silent cohorts).
    # Block them at gen time to avoid waste.
    _DEAD_SECTOR_REGIMES = _load_dead_sector_regime_combos()
    sec_m25 = _re.search(r'_secc\s*==\s*(\d+)', text)
    if sec_m25:
        sec25 = sec_m25.group(1)
        reg_set = set(_re.findall(r'self\._reg_(\w+)', text))
        for entry in _DEAD_SECTOR_REGIMES:
            if entry['sector'] != sec25:
                continue
            req = set(entry['regimes_full'])
            if req.issubset(reg_set):
                violations.append(
                    f'Rule 25: S{sec25} × {entry["regime_pair"]} — '
                    f'{entry["evidence"]}. Use different sector OR regime pair.')
                break

    # Rule 26 (2026-05-15): empirical (fund, regime-pair) dead combos.
    # R2200-R2307 audit: 6 (fund, regime) combos have ≥10 probes 0 fired.
    # ROA×VF (14), CSH×HA+HD14 (20), ROA×DP+HD14 (10), PB×HA+HD3 (15),
    # NM×VF (15), ROA×DP+HA (10). Block at gen time.
    _DEAD_FUND_REGIMES = _load_dead_fund_regime_combos()
    reg_set26 = set(_re.findall(r'self\._reg_(\w+)', text))
    for entry in _DEAD_FUND_REGIMES:
        fund_pat = entry.get('fund_pattern', '').replace('.', '\\.')
        if fund_pat and _re.search(fund_pat, text):
            req = set(entry['regimes_full'])
            if req.issubset(reg_set26):
                violations.append(
                    f'Rule 26: {entry["fund_code"]} × {entry["regime_pair"]} '
                    f'— {entry["evidence"]}. Use different fund or regime.')
                break

    # Rule 27 (2026-05-16): petgt/stop/skip × fund-gated cohort = SILENT.
    # R2329 + R2345 evidence: 11/11 petgt and 5/5 stop probes on (qpos +
    # regime + fund-gate) cohorts returned exact-NOOP. Exit-side levers
    # (petgt/stop/skip) only fire on trades that hit their gain/loss/skip
    # event; narrowing the entry cohort with a fund-gate produces too few
    # qualifying trades to ever reach the event. Use these levers only on
    # BROADER cohorts (regime-only, no fund-gate) or skip them entirely.
    if probe.lever in ('petgt', 'stop', 'skip'):
        has_fund_gate = bool(_re.search(
            r'_(?:cfs|inc|ops|bs|vr)_z\.', text))
        has_reg = '_reg_' in text or 'self._reg' in text
        if has_fund_gate and has_reg:
            violations.append(
                f'Rule 27: {probe.lever} × fund-gated cohort '
                '(qpos + regime + fund-z) — 16/16 silent across R2329+R2345. '
                'Use broader regime-only cohort or pick wt_tilt/score lever.')

    # Rule 28 (2026-05-16): score *= BOOST (mag > 1.0) on a panic/crash
    # regime cohort (haccel/double_panic) with deep decline (≥ 0.05) and
    # NO sector/fund/qstate-narrow gate is CATASTROPHIC.
    # R2349 evidence: SC_HA_D5_AMP at m104-m112 produced -0.020 to -0.066
    # lift across 5 mags (worst -0.066 = end_equity collapse). Score
    # amplification on the cohort that ALREADY has multiple wt_tilt and
    # conv bakes pushes position-sizing past the cap; trades that should
    # be downweighted get fully sized into a losing crash regime.
    if probe.lever == 'score' and probe.op == '*=' and probe.mags:
        if any(m > 1.0 for m in probe.mags):
            has_panic_regime = bool(_re.search(
                r'self\._reg_(?:haccel|double_panic)\b', text))
            m_dec = _re.search(r'decline\s*>\s*(\d+\.?\d*)', text)
            deep_dec = m_dec and float(m_dec.group(1)) >= 0.05
            has_sector = bool(_re.search(r'_secc\s*==\s*\d', text))
            has_fund = bool(_re.search(r'_(?:cfs|inc|ops|bs|vr)_z\.', text))
            if has_panic_regime and deep_dec and not (has_sector or has_fund):
                violations.append(
                    'Rule 28: score *= BOOST × panic-regime '
                    '(haccel/double_panic) × decline ≥ 0.05 without '
                    'sector/fund gate — catastrophic (R2349 SC_HA_D5_AMP '
                    'measured -0.020 to -0.066 across 5 mags). Add '
                    'sector/fund narrowing or pick wt_tilt/conv lever.')

    # Rule 29 (2026-05-16): entry_score_quality cohorts WITHOUT sector
    # narrowing are catastrophic on productive regimes.
    # R2358 evidence: EQB_HD3_FCF/HD5_NI/HD14_OCF/HA_HD5/DP_HD14 all
    # -0.003 to -0.032 across 5 mags. All 4 historical EQ bakes have
    # either _secc=N OR _reg_haccel.is.not.None form — regime-only
    # cohorts are dead. Sector OR explicit haccel-quality gate required.
    if probe.lever == 'entry_score_quality':
        has_sector = bool(_re.search(r'_secc\s*==\s*\d', text))
        has_haccel_quality = bool(_re.search(
            r'_reg_haccel\s+is\s+not\s+None\s+and\s+self\._reg_haccel\s*>', text))
        if not (has_sector or has_haccel_quality):
            violations.append(
                'Rule 29: entry_score_quality cohort without sector or '
                'haccel-quality gate — catastrophic (R2358 EQB_* axes '
                'measured -0.003 to -0.032 across 5 mags). All 4 historical '
                'EQ bakes have _secc=N or explicit haccel.is.not.None form. '
                'Add sector narrowing or use a different lever.')

    # Rule 30 (2026-05-16): wt_tilt/entry_score_mtf BOOST × HD14 × FCF
    # narrow-gap-decline (1-2%) is DESTRUCTIVE.
    # R2398 evidence: WB_HD14_FCF_D1015/D1520 (5 mags each) measured
    # -0.00052 to -0.00206 vs NOOP; EM_HD14_FCF_D1015 monotonic negative
    # a150/200/300 = -0.00052 to -0.00206. The 0.5-1% narrow band has
    # 4 active bakes (productive); the 1-2% adjacent gap is destructive
    # — likely the productive sub-sample sits in 0.5-1% only and adding
    # wider decline pulls in losers.
    if probe.lever in ('wt_tilt', 'entry_score_mtf'):
        has_hd14 = bool(_re.search(r'self\._reg_hyg_dn14\b', text))
        has_fcf = bool(_re.search(r'free_cash_flow', text))
        m_lo = _re.search(r'decline\s*>\s*(\d+\.\d+)', text)
        m_hi = _re.search(r'decline\s*<\s*(\d+\.\d+)', text)
        is_boost = (
            (probe.op == '*=' and any(m > 1.0 for m in (probe.mags or ())))
            or (probe.op == '+=' and any(m > 0 for m in (probe.mags or ())))
        )
        if has_hd14 and has_fcf and m_lo and m_hi and is_boost:
            lo = float(m_lo.group(1)); hi = float(m_hi.group(1))
            if lo >= 0.010 and hi <= 0.020:
                violations.append(
                    'Rule 30: wt_tilt/entry_score_mtf BOOST × HD14 × FCF × '
                    'decline 1-2% gap — destructive (R2398 measured '
                    '-0.00052 to -0.00206 across 5 mags × 3 axes). '
                    'Productive HD14+FCF zone is 0.5-1% only; the gap '
                    'band pulls in losers. Drop or use different regime.')

    # Rule 32 (2026-05-16): wt_tilt deep DEMOTE (mag <= 0.50) on fresh
    # cohorts is catastrophically destructive. R2416 measured 8 axes ×
    # 4 mags = 32 specs on broad accounting fund-gates; all monotonic
    # destructive (-0.054 worst, -0.006 best). The fund-gate alone is
    # too coarse — deep demote pulls in winners. Reserve mags 0.40-0.50
    # for VRFY on KNOWN-productive baked cohorts only.
    if probe.lever == 'wt_tilt' and probe.op == '*=' and probe.mags:
        deep_mags = [m for m in probe.mags if m <= 0.50]
        if deep_mags and len(deep_mags) == len(probe.mags):
            # Allow if probe name signals VRFY (verifying baked cohort).
            is_vrfy = '_VRFY' in (probe.name or '') or 'VRFY' in (probe.name or '')
            if not is_vrfy:
                violations.append(
                    f'Rule 32: wt_tilt *= deep DEMOTE mags <=0.50 ({deep_mags}) '
                    'on fresh cohort — catastrophic destructive (R2416 = '
                    '-0.054 worst, all 8 axes destructive). Use mags >= 0.55 '
                    'for fresh-cohort exploration; reserve <=0.50 for VRFY '
                    'on baked cohorts (probe name must contain _VRFY).')

    # Rule 31 (2026-05-16): stop/petgt × regime-only × narrow-decline cohorts
    # produce 100% silent rate. R2402 measured ST_HD14/ST_HD3 (5 mags each)
    # and PT_HD14 (5 mags) all NOOP-identical (3.19907) = 25 silent specs.
    # Exit-side levers need pnl-event triggers; regime+narrow-dec entry
    # cohorts produce too few qualifying exit trades to fire the lever.
    # Require either fund-gate (sufficient population) OR pnl-condition
    # (events-based) for stop/petgt cohorts.
    if probe.lever in ('stop', 'petgt'):
        has_pnl = bool(_re.search(r'\bpnl\b', text))
        has_fund = bool(_re.search(r'_(?:cfs|inc|ops|bs|vr|er|ers|ac)_z\.', text))
        has_sector = bool(_re.search(r'_secc\s*==\s*\d', text))
        m_dec_hi = _re.search(r'decline\s*<\s*(\d+\.\d+)', text)
        narrow_dec = m_dec_hi and float(m_dec_hi.group(1)) <= 0.015
        if narrow_dec and not (has_pnl or has_fund or has_sector):
            violations.append(
                'Rule 31: stop/petgt × regime-only × narrow-decline (<= 1.5%) '
                'is 100% silent (R2402 ST_HD14/ST_HD3/PT_HD14 = 15 NOOP-'
                'identical specs). Exit levers need pnl-event triggers; '
                'regime+narrow-dec yields too few qualifying exits. Add '
                'pnl condition, fund gate, or widen decline band.')

    # Rule 33 (2026-05-17): wt_tilt × _qpos × _reg_double_panic × _ngt(...1e6)
    # fund-gate is 100% silent. R2461-R2476 audit: 80+ specs across 16 rounds,
    # 100% NOOP-identical (0 firings). _qpos ∩ double_panic ∩ large-cap-only
    # fund threshold yields empty cohort in practice. Either drop DP regime,
    # use a different qstate (_qzero), or lower the _ngt threshold to 0.
    if (probe.lever == 'wt_tilt'
        and '_qpos' in text
        and '_reg_double_panic' in text
        and _re.search(r'_ngt\(_[a-z]+_z\.[a-z_0-9]+\.[a-z_]+\s*,\s*1[eE]?\+?6', text)):
        violations.append(
            'Rule 33: wt_tilt × _qpos × _reg_double_panic × _ngt(...1e6) '
            'fund-gate is 100% silent (R2461-R2476: 80+ specs all NOOP-'
            'identical, 0 firings across 16 rounds). _qpos ∩ double_panic '
            'rarely overlaps large-cap-fund population. Drop DP regime, '
            'switch to _qzero, or lower _ngt threshold below 1e6.')

    # Rule 34 (2026-05-17): score/wt_tilt/conv DEMOTE probes on cells where
    # entry_score_quality NEG bake (mag ≤ -0.075) already exists are SILENT.
    # R2571 evidence: 15/16 EXACT-NOOP on S205×HD14×D12×OCF cell (all 6
    # different non-EQ levers tested). R2576: 12/14 SC/WT DEMOTE specs on
    # same cell EXACT-NOOP. Mechanism: cohort's score already heavily
    # demoted (-0.10 × 1.0 entry_score_quality coefficient subtracted from
    # score sum) — further DEMOTE doesn't change rank-order of candidates.
    # BOOST is exempt (could lift rank); EQ-itself probes exempt (extending
    # the bake direction). Auto-bypass: use a different cell or BOOST mag.
    if probe.lever in ('score', 'wt_tilt', 'conv') and probe.op == '*=' and probe.mags:
        if any(m < 1.0 for m in probe.mags):
            try:
                from s001.gen_s001_diagnostics import applied_bakes, _cohort_tokens
                cand_toks = _cohort_tokens(text)
                if cand_toks:
                    for b in applied_bakes():
                        if b.get('reverted'): continue
                        if b.get('lever') != 'entry_score_quality': continue
                        if b.get('op') != '+=' or b.get('mag', 0) > -0.075: continue
                        bake_toks = _cohort_tokens(b['cohort'])
                        if not bake_toks: continue
                        inter = cand_toks & bake_toks
                        union = cand_toks | bake_toks
                        jac = len(inter) / len(union) if union else 0
                        if jac >= 0.70:
                            violations.append(
                                f'Rule 34: {probe.lever} *= DEMOTE on cell with '
                                f'EQ NEG bake (mag={b["mag"]:.3f}, {b["label"]}, '
                                f'overlap={jac:.0%}). R2571/R2576 evidence: '
                                f'15/16 and 12/14 EXACT-NOOP. Score already '
                                f'demoted; further DEMOTE silent. Try BOOST or '
                                f'different cell.')
                            break
            except Exception:
                pass

    # Rule 36 (2026-05-18): pure-fresh-field EXISTENCE cohort + wt_tilt DEMOTE
    # = catastrophic. R2644-R2657 audit: 65/66 (98%) wasted (44 catastrophic
    # avg -0.011, 21 silent). Pattern: cohort = `_qzero AND regime AND decline
    # AND _bs_z.X.twelve_months is not None` (NO value/quality ratio gate) +
    # wt_tilt *= mag<1.0. The DEMOTE on broad cohort destroys good stocks.
    # Productive WT DEMOTE bakes (BAKE-7/30/31) all had value-ratio gate
    # (ey>0.05 or evfcf<20). Pure-existence axes lack that filtering.
    # Block: cohort with `_bs_z|_inc_z|_cfs_z|_ops_z.X is not None` as SOLE
    # fund gate (no ratio op) + wt_tilt with mag < 1.0.
    if probe.lever == 'wt_tilt' and probe.op == '*=' and probe.mags:
        if any(m < 1.0 for m in probe.mags):
            # Detect: existence check on bs/inc/cfs/ops accessor
            existence_only = _re.search(
                r'\b(_bs_z|_inc_z|_cfs_z|_ops_z)\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*\s+is\s+not\s+None', text)
            # Reject if exists AND no ratio op (>, <, ==) on any fund-z accessor
            has_ratio_op = _re.search(
                r'\b(_vr_z|_bs_z|_inc_z|_cfs_z|_ops_z)\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*\s*(?:>=|<=|>|<|==)\s*[\d.eE+-]+', text)
            has_ngt = _re.search(r'_n(?:gt|lt)\(', text)
            if existence_only and not has_ratio_op and not has_ngt:
                violations.append(
                    f'Rule 36: wt_tilt *= DEMOTE on pure-fresh-existence cohort '
                    f'(no ratio/_ngt gate). R2644-R2657 audit: 65/66 (98%) wasted '
                    f'(44 catastrophic avg -0.011, 21 silent). Productive WT '
                    f'DEMOTE requires value gate (ey>0.05/evfcf<20). Add ratio '
                    f'filter or use BOOST direction.')

    # Rule 38 (2026-05-18): block SAME-LEVER direction-reversal on baked cell.
    # When (lever, cohort) has a *= DEMOTE bake (mag<1.0), same-lever *= BOOST
    # (mag>1.0) on same cell catastrophic — directly opposite signal undoes bake.
    # R2706 evidence: WT BOOST m105 on BAKE-45 (WT *= 0.78) cell → -0.005.
    # R2704 BOOST m105/m110 on adjacent band → -0.008/-0.012.
    # DIFFERENT-LEVER opposite direction is fine: CV BOOST on BAKE-45 cell
    # productive (m110=+0.00021, m112=+0.00031). Lever-specific rule.
    if probe.lever and probe.op == '*=' and probe.mags:
        boost_mags = [m for m in probe.mags if m > 1.0]
        if boost_mags:
            try:
                from pathlib import Path as _P38
                import json as _j38
                from s001.gen_s001_diagnostics import _cohort_tokens as _ct38
                _bp38 = RESEARCH_DIR / 'bakes.json'
                if _bp38.exists():
                    with open(_bp38) as _f38: _bakes38 = _j38.load(_f38)
                    cand_toks38 = _ct38(probe.cohort)
                    for b in _bakes38:
                        if b.get('reverted'): continue
                        if b.get('lever') != probe.lever: continue
                        if b.get('op') != '*=': continue
                        bake_mag38 = b.get('mag', 1.0)
                        if bake_mag38 >= 1.0: continue  # bake must be DEMOTE
                        bake_toks38 = _ct38(b.get('cohort', ''))
                        if not bake_toks38: continue
                        inter38 = cand_toks38 & bake_toks38
                        union38 = cand_toks38 | bake_toks38
                        jac38 = len(inter38) / len(union38) if union38 else 0
                        if jac38 >= 0.85:
                            violations.append(
                                f'Rule 38: {probe.lever} *= BOOST {boost_mags} '
                                f'on cell with {probe.lever} DEMOTE bake '
                                f'(mag={bake_mag38} from {b.get("label","?")}, '
                                f'overlap={jac38:.0%}). Direction-reversal '
                                f'on same lever catastrophic (R2706 -0.005). '
                                f'Use DIFFERENT lever for BOOST direction.')
                            break
            except Exception:
                pass

    # Rule 37 (2026-05-18, extended 2026-05-18): block STACKING demote that
    # brings effective_mag (bake_mag × probe_mag) below 0.85. Two failure modes:
    # (a) deeper-than-bake stack (effective << bake_mag): catastrophic compound.
    #     R2697 BAKE-45 (m=0.78) m72/74/76 stack → effective 0.56-0.59
    #     → -0.0013 to -0.0038 catastrophic.
    # (b) less-deep-but-still-stacking stack: also catastrophic when total
    #     demote exceeds tuned point. R2707 WT SHALLOW m=0.85/0.90 on BAKE-45
    #     → effective 0.663/0.702 → -0.0006 to -0.0004 catastrophic.
    # Safe stacking: effective ≥ 0.80 (BAKE-44 m=0.94 on BAKE-43 m=0.90 →
    # effective 0.846 > 0.80, productive). To stack productively,
    # use mag VERY close to 1.0 OR test BOOST direction (effective > 1.0).
    if probe.lever and probe.op == '*=' and probe.mags:
        demote_mags = [m for m in probe.mags if m < 1.0]
        if demote_mags:
            try:
                from pathlib import Path as _P
                import json as _j
                from s001.gen_s001_diagnostics import _cohort_tokens as _ct37
                _bp = RESEARCH_DIR / 'bakes.json'
                if _bp.exists():
                    with open(_bp) as _f: _bakes = _j.load(_f)
                    cand_toks = _ct37(probe.cohort)
                    for b in _bakes:
                        if b.get('reverted'): continue
                        if b.get('lever') != probe.lever: continue
                        if b.get('op') != '*=': continue
                        bake_mag = b.get('mag', 1.0)
                        if bake_mag >= 1.0: continue
                        bake_toks = _ct37(b.get('cohort', ''))
                        if not bake_toks: continue
                        inter = cand_toks & bake_toks
                        union = cand_toks | bake_toks
                        jac = len(inter) / len(union) if union else 0
                        if jac >= 0.85:
                            bad = [m for m in demote_mags
                                   if bake_mag * m < 0.80]
                            if bad:
                                violations.append(
                                    f'Rule 37: {probe.lever} *= DEMOTE stacks '
                                    f'too aggressively on baked cell '
                                    f'(bake_mag={bake_mag} × probe_mag {bad} '
                                    f'→ effective < 0.80, on {b.get("label","?")}, '
                                    f'overlap={jac:.0%}). R2697 BAKE-45 m72-76 '
                                    f'and R2707 WT SHALLOW m85-90 all '
                                    f'catastrophic -0.0006 to -0.0038. Use mag '
                                    f'close to 1.0 or BOOST direction.')
                                break
            except Exception:
                pass

    # Rule 38 (2026-05-19): VF (vxx_falling3) regime BOOST = catastrophic.
    # R2997 evidence: VF × D14T20 W/C BOOST m105/m107 all 4 specs → 3.33216-3.33247
    # = -0.00114 to -0.00145 vs NOOP 3.33361. The vxx_falling3 regime (3-day VIX
    # decreasing) is structurally bearish for QQQ mean-revert; boosting weight on
    # cohort members during VIX-decline phase is counter-productive.
    # Block ALL wt_tilt/conv BOOST (mag > 1.0) on _reg_vxx_falling3 cohorts.
    if probe.lever in ('wt_tilt', 'conv') and probe.op == '*=' and probe.mags:
        boost_mags = [m for m in probe.mags if m > 1.0]
        if boost_mags and '_reg_vxx_falling3' in text:
            violations.append(
                f'Rule 38: {probe.lever} BOOST on _reg_vxx_falling3 — '
                f'R2997 evidence: 4/4 specs -0.00114 to -0.00145 vs NOOP. '
                f'VIX-decline regime is bearish for mean-revert BOOST.')

    # Rule 39 (2026-05-19): H5/Q3 D14T20 BOOST at mag ≥ 1.10 = NEG.
    # R3001 H5 m1.12 = -0.00052 (effective 1.176 after BAKE-138 m1.05 stack);
    # R3000/R3001 Q3 m1.05-1.12 = -0.00083 (no bake on Q3, raw 1.05-1.12).
    # H5 and Q3 regimes do NOT generalize the H3 D14T20 BOOST plateau —
    # H3 specifically benefits, H5/Q3 are flat-to-NEG.
    if probe.lever == 'wt_tilt' and probe.op == '*=' and probe.mags:
        high_boost = [m for m in probe.mags if m >= 1.10]
        if high_boost:
            band_d14 = bool(_re.search(
                r'decline\s*>\s*0\.014\s+and\s+decline\s*<\s*0\.02', text))
            on_h5_or_q3 = ('_reg_hyg_up5' in text or '_reg_qqq_up3' in text)
            on_qpos = '_qpos' in text
            if band_d14 and on_h5_or_q3 and on_qpos:
                violations.append(
                    f'Rule 39: wt_tilt BOOST mag≥1.10 on _qpos × '
                    f'(H5|Q3) × D14T20 — R3001 NEG -0.00052, R3000 Q3 NEG. '
                    f'H3 plateau does not generalize to H5/Q3 regimes.')

    # Rule 40 (2026-05-19): entry_signal probes on R29xx D14T20 cohorts =
    # 100% silent. R2998 ES_H3/H5/Q3 × D14T20 → 8/8 EXACT-NOOP. The entry_signal
    # accumulator is dominated by upstream entry-condition gates; small ±= mags
    # don't shift selection ranks. Allow entry_signal only on novel cohorts.
    if probe.lever == 'entry_signal' and probe.op == '+=' and probe.mags:
        band_d14 = bool(_re.search(
            r'decline\s*>\s*0\.014\s+and\s+decline\s*<\s*0\.02', text))
        on_qpos_rally = (
            '_qpos' in text and
            ('_reg_hyg_up3' in text or '_reg_hyg_up5' in text
             or '_reg_qqq_up3' in text))
        if band_d14 and on_qpos_rally:
            violations.append(
                f'Rule 40: entry_signal += on _qpos × (H3|H5|Q3) × D14T20 — '
                f'R2998: 8/8 EXACT-NOOP. Selection rank dominated by upstream '
                f'gates; small a-mags do not shift it.')

    # Rule 42 (2026-05-19): entry_score_regime DEMOTE on uncommon decline bands = silent.
    # R3006 evidence: 16/16 ER += -0.013/-0.015 probes returned EXACTLY 3.33423
    # (NOOP) across 8 cohorts spanning decline bands D24-40 in H3/H5/DP/Q3 regimes.
    # The proven BAKE-122-129 ER bakes were on COMMON-decline bands; rare bands
    # have too few candidates to shift the score ranking meaningfully.
    # Block: entry_score_regime += DEMOTE (-0.005 to -0.030) on decline > 0.025
    # except for cohorts matching an existing baked cell.
    if probe.lever == 'entry_score_regime' and probe.op == '+=' and probe.mags:
        demote_mags = [m for m in probe.mags if -0.030 <= m <= -0.005]
        if demote_mags:
            m = _re.search(r'decline\s*>\s*(\d+\.?\d*)', text)
            if m:
                try:
                    lo = float(m.group(1))
                    if lo >= 0.025:
                        # Check if cohort matches any baked ER DEMOTE cell
                        try:
                            from pathlib import Path as _P42
                            import json as _j42
                            from s001.gen_s001_diagnostics import _cohort_tokens as _ct42
                            _bp42 = RESEARCH_DIR / 'bakes.json'
                            if _bp42.exists():
                                with open(_bp42) as _f42: _bakes42 = _j42.load(_f42)
                                cand_toks42 = _ct42(probe.cohort)
                                exempt = False
                                for b42 in _bakes42:
                                    if b42.get('reverted'): continue
                                    if b42.get('lever') != 'entry_score_regime': continue
                                    bake_toks = _ct42(b42.get('cohort', ''))
                                    if not bake_toks: continue
                                    inter = cand_toks42 & bake_toks
                                    union = cand_toks42 | bake_toks
                                    jac = len(inter) / len(union) if union else 0
                                    if jac >= 0.85:
                                        exempt = True
                                        break
                                if not exempt:
                                    violations.append(
                                        f'Rule 42: ER += DEMOTE on decline > {lo} '
                                        f'(rare band) — R3006: 16/16 EXACT-NOOP. '
                                        f'Use bands ≤ 0.025 OR match baked cells.')
                        except Exception:
                            pass
                except ValueError:
                    pass

    # Rule 43 (2026-05-19): HA-compound wt_tilt DEMOTE parallel transfer outside
    # baked cohorts is silent or catastrophic. R3008 evidence: 11 W × rally_regime ×
    # HACCEL × narrow-decline DEMOTE specs across H5/Q3/H3-wider/DP-wider cohorts:
    #   - Best: 0 positive vs NOOP (all flat or NEG)
    #   - Catastrophic: -0.00341 to -0.00382 on H5-HA D10T14 m0.90, DP-HA D40T60 m0.84
    # BAKE-139 (DP×HA×D20T40) and BAKE-140 (H3×HA×D10T14) are the only working
    # HA-compound DEMOTE bakes. Parallel transfer fails because the HACCEL gate
    # specifically discriminates DP-rally panic or H3-rally narrow events.
    if probe.lever == 'wt_tilt' and probe.op == '*=' and probe.mags:
        demote_mags = [m for m in probe.mags if m < 1.0]
        if demote_mags:
            # Check for HACCEL + rally regime + narrow-decline pattern
            has_haccel = bool(_re.search(r'self\._reg_haccel|_reg_haccel|\bHA\b', text))
            has_rally = bool(_re.search(
                r'_reg_(?:hyg_up3|hyg_up5|qqq_up3|double_panic)', text))
            if has_haccel and has_rally and '_qpos' in text:
                # Allow ONLY if cohort matches BAKE-139/140 SAME REGIME and
                # decline range is SUBSET of (or overlaps within) baked range.
                # R3010 W_DP_HA_D25T30 +0.00020 proves sub-bands within baked
                # ranges DO work; parallel regime or band-extension does NOT.
                cand_decl_m = _re.search(
                    r'decline\s*>\s*(\d+\.?\d*).*decline\s*<\s*(\d+\.?\d*)', text)
                cand_lo, cand_hi = None, None
                if cand_decl_m:
                    try:
                        cand_lo = float(cand_decl_m.group(1))
                        cand_hi = float(cand_decl_m.group(2))
                    except ValueError:
                        pass
                try:
                    from pathlib import Path as _P43
                    import json as _j43
                    _bp43 = RESEARCH_DIR / 'bakes.json'
                    if _bp43.exists():
                        with open(_bp43) as _f43: _bakes43 = _j43.load(_f43)
                        baked_match = False
                        for b43 in _bakes43:
                            if b43.get('reverted'): continue
                            lbl = b43.get('label','')
                            if 'BAKE-139' not in lbl and 'BAKE-140' not in lbl:
                                continue
                            bake_coh = b43.get('cohort', '')
                            # Same regime check
                            regime = None
                            if '_reg_double_panic' in bake_coh and '_reg_double_panic' in text:
                                regime = 'DP'
                            elif '_reg_hyg_up3' in bake_coh and '_reg_hyg_up3' in text:
                                regime = 'H3'
                            if not regime: continue
                            # Decline-range subset check
                            bake_decl_m = _re.search(
                                r'decline\s*>\s*(\d+\.?\d*).*decline\s*<\s*(\d+\.?\d*)', bake_coh)
                            if not bake_decl_m or cand_lo is None: continue
                            try:
                                bake_lo = float(bake_decl_m.group(1))
                                bake_hi = float(bake_decl_m.group(2))
                                if cand_lo >= bake_lo and cand_hi <= bake_hi:
                                    baked_match = True
                                    break
                            except ValueError:
                                pass
                        if not baked_match:
                            violations.append(
                                f'Rule 43: wt_tilt DEMOTE on _qpos × HACCEL × '
                                f'rally cohort NOT a sub-band of BAKE-139/140 — '
                                f'R3008 evidence: 11/11 NEG (-0.00021 to -0.00382). '
                                f'Sub-bands within baked range are allowed.')
                except Exception:
                    pass

    # Rule 41 (2026-05-19): score *= on heavily wt_tilt-BOOSTed cohort = catastrophic.
    # R3003 evidence: S_H3_D14T20_DEMOTE m0.95 = 3.32433 (-0.01 vs NOOP),
    # S_H3_D14T20_BOOST m1.08 = 3.31495 (-0.02 CATASTROPHIC). BAKE-136 already
    # boosts wt_tilt *= 1.22 on this cohort. Adding score *= ANY direction
    # destabilizes selection: BOOST → over-pick over-weighted candidates →
    # over-concentration; DEMOTE → under-pick the productive cohort.
    if probe.lever == 'score' and probe.op == '*=' and probe.mags:
        try:
            from pathlib import Path as _P41
            import json as _j41
            from s001.gen_s001_diagnostics import _cohort_tokens as _ct41
            _bp41 = RESEARCH_DIR / 'bakes.json'
            if _bp41.exists():
                with open(_bp41) as _f41: _bakes41 = _j41.load(_f41)
                cand_toks = _ct41(probe.cohort)
                for b41 in _bakes41:
                    if b41.get('reverted'): continue
                    if b41.get('lever') != 'wt_tilt': continue
                    if b41.get('op') != '*=': continue
                    bake_mag = b41.get('mag', 1.0)
                    if bake_mag <= 1.15: continue  # only HEAVY boosts
                    bake_toks = _ct41(b41.get('cohort', ''))
                    if not bake_toks: continue
                    inter = cand_toks & bake_toks
                    union = cand_toks | bake_toks
                    jac = len(inter) / len(union) if union else 0
                    if jac >= 0.85:
                        violations.append(
                            f'Rule 41: score *= on cohort with heavy wt_tilt '
                            f'BOOST baked ({b41.get("label","?")} mag={bake_mag}, '
                            f'overlap={jac:.0%}). R3003 evidence: -0.01 to '
                            f'-0.02 catastrophic — BOOST flips selection rank.')
                        break
        except Exception:
            pass

    # Rule 44 (2026-05-20): conv DEMOTE on cohort with W*= DEMOTE bake = waste.
    # R3043 evidence (NOOP=3.33598): 12 conv DEMOTE probes on cohorts with
    # existing W*=0.94-0.97 DEMOTE bakes (BAKE-149/150/151):
    #   8 NEG (-0.00021 to -0.00134), 4 NOOP, 0 positive.
    # Mechanism: both levers reduce effective weight. Stacking 2 DEMOTE on
    # same cohort over-suppresses signal. Score lever (Rule 41) excluded
    # only BOOST; this rule covers conv-DEMOTE stacking on W-DEMOTE bakes.
    if probe.lever == 'conv' and probe.op == '*=' and probe.mags:
        try:
            from pathlib import Path as _P44
            import json as _j44
            from s001.gen_s001_diagnostics import _cohort_tokens as _ct44
            _bp44 = RESEARCH_DIR / 'bakes.json'
            if _bp44.exists() and any(m < 1.0 for m in probe.mags):
                with open(_bp44) as _f44: _bakes44 = _j44.load(_f44)
                cand_toks = _ct44(probe.cohort)
                for b44 in _bakes44:
                    if b44.get('reverted'): continue
                    if b44.get('lever') != 'wt_tilt': continue
                    if b44.get('op') != '*=': continue
                    bake_mag = b44.get('mag', 1.0)
                    if bake_mag >= 1.0: continue  # only DEMOTE bakes (mag<1)
                    if bake_mag < 0.85: continue  # ignore aggressive demotes
                    bake_toks = _ct44(b44.get('cohort', ''))
                    if not bake_toks: continue
                    inter = cand_toks & bake_toks
                    union = cand_toks | bake_toks
                    jac = len(inter) / len(union) if union else 0
                    if jac >= 0.85:
                        violations.append(
                            f'Rule 44: conv DEMOTE on cohort with W*= DEMOTE '
                            f'baked ({b44.get("label","?")} mag={bake_mag}, '
                            f'overlap={jac:.0%}). R3043 evidence: 12/12 '
                            f'NEG/NOOP (-0.00021 to -0.00134, no positive).')
                        break
        except Exception:
            pass

    # Rule 45 (2026-05-20): W*= probe whose mag compounds with existing
    # W*= bake (same lever, sub-range decline) to effective <= 0.85 = waste.
    # R3051 evidence (NOOP=3.33629): 8 W probes on sub-bands of BAKE-152
    # (P × H3 × D020-D025 W*=0.94) at probe mags 0.90-0.96 → effective
    # 0.846-0.902 in sub-band → all NEG (-0.00114 to -0.00144).
    # The bake mag is the empirical sweet spot; sub-range compounding
    # pushes effective deeper than peak → destructive.
    if probe.lever == 'wt_tilt' and probe.op == '*=' and probe.mags:
        try:
            from pathlib import Path as _P45
            import json as _j45
            import re as _re45
            _bp45 = RESEARCH_DIR / 'bakes.json'
            if _bp45.exists():
                with open(_bp45) as _f45: _bakes45 = _j45.load(_f45)
                # Parse probe decline range
                pc = probe.cohort or ''
                pm = _re45.search(r'decline\s*>\s*([\d.]+).*decline\s*<\s*([\d.]+)', pc)
                if not pm: pm = _re45.search(r'\.(\d+)\s*<\s*d\s*<\s*\.(\d+)', pc)
                if pm:
                    p_lo = float(pm.group(1) if '.' in pm.group(1) else '.' + pm.group(1))
                    p_hi = float(pm.group(2) if '.' in pm.group(2) else '.' + pm.group(2))
                    for b45 in _bakes45:
                        if b45.get('reverted'): continue
                        if b45.get('lever') != 'wt_tilt': continue
                        if b45.get('op') != '*=': continue
                        bake_mag = b45.get('mag', 1.0)
                        if bake_mag >= 1.0: continue  # DEMOTE bakes only
                        bc = b45.get('cohort', '')
                        bm = _re45.search(r'decline\s*>\s*([\d.]+).*decline\s*<\s*([\d.]+)', bc)
                        if not bm: continue
                        b_lo = float(bm.group(1))
                        b_hi = float(bm.group(2))
                        # Probe decline must be sub-range of bake decline
                        if not (p_lo >= b_lo and p_hi <= b_hi and (p_lo > b_lo or p_hi < b_hi)):
                            continue
                        # Check cohort token overlap (same regime + qstate)
                        from s001.gen_s001_diagnostics import _cohort_tokens as _ct45
                        cand_toks = _ct45(probe.cohort)
                        bake_toks = _ct45(bc)
                        if not bake_toks: continue
                        # Strip decline tokens for regime-only overlap
                        non_decline_b = {t for t in bake_toks if 'decline' not in t}
                        non_decline_c = {t for t in cand_toks if 'decline' not in t}
                        if not non_decline_b.issubset(non_decline_c) and \
                           not non_decline_c.issubset(non_decline_b):
                            continue
                        # Probe mag <= bake mag means effective compounds deeper
                        for pmag in probe.mags:
                            effective = bake_mag * pmag
                            if effective <= 0.86:
                                violations.append(
                                    f'Rule 45: W*= probe sub-range of W bake '
                                    f'{b45.get("label","?")} (mag={bake_mag}) '
                                    f'compounds to effective={effective:.3f} <= 0.86 '
                                    f'in {p_lo:.3f}-{p_hi:.3f}. R3051 evidence: '
                                    f'8/8 NEG -0.00114 to -0.00144.')
                                break
                        if violations and violations[-1].startswith('Rule 45'):
                            break
        except Exception:
            pass

    return violations


def _load_dead_fund_regime_combos():
    import json as _json, os as _os
    path = _os.path.join(str(RESEARCH_DIR),
                         'dead_fund_regime_combos.json')
    try:
        with open(path) as f:
            return _json.load(f)
    except (OSError, _json.JSONDecodeError):
        return []


def _load_dead_sector_regime_combos():
    import json as _json, os as _os
    path = _os.path.join(str(RESEARCH_DIR),
                         'dead_sector_regime_combos.json')
    try:
        with open(path) as f:
            return _json.load(f)
    except (OSError, _json.JSONDecodeError):
        return []


# P2 — lever quota enforcer.
#   Rationale: reconstruction goal is to break score-monoculture. Every round
#   must split spec budget so non-score levers (wt_tilt/conv/stop/skip/petgt)
#   get genuine exploration time, not token presence.
NON_SCORE_LEVERS = {'wt_tilt', 'conv', 'stop', 'skip', 'petgt',
                    # entry_score_gate (P4 2026-05-10) is a multiplicative
                    # accumulator — distinct path from direct `score *=`
                    # mutation. Counts as non-score for quota since its
                    # purpose is breaking score-monoculture.
                    'entry_score_gate',
                    # 2026-05-11 update (R1967 review): entry_score_*
                    # family (mtf/quality/regime/conv/signal) all use
                    # DIFFERENT additive paths than direct `score *=`/`score +=`.
                    # They're 9 of last 9 productive bakes since R1944 while
                    # wt_tilt+conv+stop+skip+petgt yielded 0 (~420 specs).
                    # Forcing wt_tilt quota wastes 40% of round budget on
                    # dead lever space. Reclassify productive entry_score_*
                    # as non-score (they break score-monoculture by paradigm).
                    'entry_score_mtf', 'entry_score_quality',
                    'entry_score_regime', 'entry_score_conv', 'entry_signal',
                    # 2026-05-12: exit_signal is the highest-yield lever
                    # historically (8 bakes, avg +0.45 vs +0.003 score).
                    # Re-introduced post-saturation; counts as non-score
                    # for quota (different code path: EXIT accumulator).
                    'exit_signal'}
# Aux probes (NOOPs, _RA_*) bypass the quota — they're variance baseline,
# not lever experiments. Probe.lever is unset / None for those.
AUX_LEVERS = {None, '', 'noop', 'aux'}


def lever_quota_check(R, max_score_frac=0.50, min_nonscore_frac=0.30):
    """Return list of violation strings if R.probes don't meet quota.

    Counts each Probe by spec_count = len(mags or [None]). NOOP/aux probes
    (lever ∈ AUX_LEVERS) don't count toward the denominator since they're
    not lever experiments.
    """
    score_specs = nonscore_specs = other_specs = 0
    for p in R.probes:
        n = len(p.mags) if p.mags else 1
        lever = (getattr(p, 'lever', None) or '').strip()
        if lever in AUX_LEVERS:
            continue
        if lever == 'score':
            score_specs += n
        elif lever in NON_SCORE_LEVERS:
            nonscore_specs += n
        else:
            other_specs += n
    total = score_specs + nonscore_specs + other_specs
    if total == 0:
        return []
    violations = []
    score_frac = score_specs / total
    nonscore_frac = nonscore_specs / total
    if score_frac > max_score_frac:
        violations.append(
            f'lever quota: score specs {score_specs}/{total} '
            f'({score_frac:.1%}) > cap {max_score_frac:.0%}')
    if nonscore_frac < min_nonscore_frac:
        violations.append(
            f'lever quota: non-score specs {nonscore_specs}/{total} '
            f'({nonscore_frac:.1%}) < floor {min_nonscore_frac:.0%}')
    return violations


def _saturation_status(rid: int, window: int = 5) -> dict:
    """Check last `window` rounds for above-NOOP+threshold productive specs.

    Uses CURRENT-round NOOP + 0.0005 as productivity threshold (was hardcoded
    3.4830 from older base — irrelevant after 2026-05-17 base evolved to
    NOOP ~3.20). Per-round NOOP-relative threshold tracks the moving optimum.

    Returns dict with productive_count, total_specs, productive_rate per round.
    """
    import qc_storage as storage, statistics
    try:
        con = storage.connect(str(DATA_DIR / 'S001.duckdb'))
        cur = con.cursor()
        rounds_data = []
        for r in range(rid - window, rid):
            # Per-round NOOP threshold (replaces stale global 3.4830)
            cur.execute(
                "SELECT car_mdd FROM experiments WHERE name LIKE ? "
                "AND name LIKE '%NOOP%' AND car_mdd IS NOT NULL",
                (f'S001_R{r}_lp_%',))
            r_noops = [row[0] for row in cur.fetchall()]
            if not r_noops:
                continue
            r_noop = statistics.median(r_noops)
            threshold = r_noop + 0.0005  # multi-mag bake-eligible floor
            cur.execute(
                'SELECT COUNT(*) FROM experiments '
                'WHERE name LIKE ? AND name NOT LIKE ? AND car_mdd > ?',
                (f'S001_R{r}_lp_%', '%NOOP%', threshold))
            above = cur.fetchone()[0]
            cur.execute(
                'SELECT COUNT(*) FROM experiments '
                'WHERE name LIKE ? AND name NOT LIKE ? AND car_mdd IS NOT NULL',
                (f'S001_R{r}_lp_%', '%NOOP%'))
            total = cur.fetchone()[0]
            if total > 0:
                rounds_data.append((r, total, above))
        con.close()
        total_specs = sum(r[1] for r in rounds_data)
        total_above = sum(r[2] for r in rounds_data)
        return {'rounds': rounds_data,
                'productive_rate': total_above / max(total_specs, 1),
                'threshold': 'per-round NOOP + 0.0005'}
    except Exception:
        return {'rounds': [], 'productive_rate': None, 'threshold': None}


def run_audit_and_queue(R, label_prefix='=== AUDIT ==='):
    """Standard audit + queue + print. Replaces the per-script main() body."""
    from s001.gen_s001_lib import audit, queue, used_accessors
    # Saturation pre-check (2026-05-15): warn if last 5 rounds have ≤0.5%
    # productive rate (above global NOOP_high 3.4830). Doesn't block — info.
    sat = _saturation_status(R.rid)
    if sat['productive_rate'] is not None and sat['rounds']:
        rate = sat['productive_rate']
        # Recent consecutive-zero count (saturation signal)
        consec_zero = 0
        for rid_, total, above in reversed(sat['rounds']):
            if above == 0 and total >= 5:
                consec_zero += 1
            else:
                break
        if rate < 0.02 or consec_zero >= 3:
            print(f'  ⚠ SATURATION WARNING: last 5 rounds productive_rate '
                  f'{rate*100:.2f}% above threshold ({sat["threshold"]}); '
                  f'{consec_zero} consecutive zero-productive rounds.')
            for rid_, total, above in sat['rounds']:
                print(f'      R{rid_}: {above}/{total} above')
            print(f'    Consider: pause queue, base-structural exploration, '
                  f'or pivot to other strategy.')

    reg = used_accessors(exclude_round=R.rid)
    rep = audit(R, reg)

    # Cohort-var pre-check: drop probes that reference forbidden vars
    bad_probes = []
    for p in R.probes:
        bad_vars = cohort_var_check(p)
        if bad_vars:
            bad_probes.append((p.name, bad_vars))
    if bad_probes:
        print('=== COHORT-VAR PRECHECK: dropping forbidden-var probes ===')
        bad_names = {n for n, _ in bad_probes}
        for n, vs in bad_probes:
            print(f'  DROP {n}: forbidden vars {vs}')
        R.probes = [p for p in R.probes if p.name not in bad_names]
        # Re-audit after drop
        rep = audit(R, reg)

    # Never-fires precheck: drop probes (or per-mag prune) matching codified
    # bad patterns. Mag-specific rules (e.g. mag 0.04 catastrophic on _qzero)
    # only drop the offending mag; whole-probe rules drop the probe.
    nf_violations = []
    pruned_mags = []  # (probe_name, dropped_mags)
    for p in R.probes:
        viols = never_fires_check(p)
        if not viols:
            continue
        # Detect mag-specific 0.04 violations and prune those mags only.
        mag_specific = [v for v in viols if v.startswith('mag 0.04')]
        whole_probe = [v for v in viols if not v.startswith('mag 0.04')]
        if mag_specific and not whole_probe:
            kept = tuple(m for m in (p.mags or ()) if not (0.035 < m <= 0.045))
            dropped = tuple(m for m in (p.mags or ()) if 0.035 < m <= 0.045)
            if kept:
                p.mags = kept
                pruned_mags.append((p.name, dropped, mag_specific[0]))
            else:
                nf_violations.append((p.name, mag_specific))
        else:
            nf_violations.append((p.name, viols))

    if pruned_mags:
        print('=== MAG PRUNE: dropping catastrophic mags from probes ===')
        for n, dropped, why in pruned_mags:
            print(f'  PRUNE {n}: drop mags {dropped} ({why})')
    if nf_violations:
        print('=== NEVER-FIRES PRECHECK: dropping known-bad-pattern probes ===')
        bad_names = {n for n, _ in nf_violations}
        for n, vs in nf_violations:
            print(f'  DROP {n}: {", ".join(vs)}')
        R.probes = [p for p in R.probes if p.name not in bad_names]
    if pruned_mags or nf_violations:
        rep = audit(R, reg)

    print(label_prefix)
    print(f"  spec_count: {rep['spec_count']}")
    print(f"  levers: {rep['levers_seen']}")
    print(f"  fresh fields: {len(rep['fresh_fields'])}")
    for f in rep['fresh_fields']:
        print(f'    - {f}')
    print(f"  regime axes: {rep['regime_axes']}")
    # P11 (2026-05-16): hard fresh-field minimum per user constraint
    # "[s001 — 8 truly novel fundamental fields per round]". Five+ rounds
    # without fresh fields = 0 bakes (R2398-R2402 audit). Default min=5;
    # override S001_MIN_FRESH=0 only for diagnostic/structural rounds.
    import os as _os11
    min_fresh = int(_os11.environ.get('S001_MIN_FRESH', '5'))
    if min_fresh > 0 and len(rep['fresh_fields']) < min_fresh:
        raise RuntimeError(
            f'P11 fresh-field quota FAILED: round has '
            f'{len(rep["fresh_fields"])} fresh accessors, need >= {min_fresh}. '
            'User hard constraint (2026-05-07): every round must cover '
            '>=5 untouched fundamental fields. Use pick_fresh_fields_under_explored() '
            'to source virgin accessors. Bypass: S001_MIN_FRESH=0 python3 ...')
    if rep.get('warnings'):
        for w in rep['warnings']:
            print(f'  WARN: {w}')
    if rep['issues']:
        print('  ISSUES:')
        for i in rep['issues']:
            print(f'    - {i}')
    else:
        print('  AUDIT PASSED')

    # P2 lever-quota enforcement (post-prune so we count what will actually
    # queue, not what was originally drafted).
    quota_violations = lever_quota_check(R)
    if quota_violations:
        print('  LEVER QUOTA VIOLATED:')
        for v in quota_violations:
            print(f'    - {v}')
        raise RuntimeError(
            'Round rejected by lever quota (≤50% score, ≥30% non-score). '
            'Add wt_tilt/conv/stop/skip/petgt probes or reduce score probes. '
            f'Violations: {quota_violations}'
        )

    # P7 ANTI-PADDING filter (added 2026-05-10): drop probes whose
    # hypothesis is known low-EV given the saturation state. User rule:
    # "queue 128 meaningful, do not pad with nonsense, don't waste backtests."
    waste_drops = []
    for p in R.probes:
        lever = (getattr(p, 'lever', None) or '').strip()
        if lever in AUX_LEVERS:
            continue
        cohort = getattr(p, 'cohort', '') or ''
        mags = getattr(p, 'mags', None) or ()
        # Single-mag entry_score_quality on `_qpos × haccel > 0 × small_dec ×
        # FRESH × += -0.10`: this is the "fresh × proven cell" pattern that
        # has been tested ~50+ times in R1851-R1868 with 0 productive at
        # single-mag. EQ_9 + WTZM5_2 captured the productive cells; remaining
        # fresh accessors are known-silent on this exact cell+mag.
        is_fresh_proven_single = (
            lever == 'entry_score_quality'
            and len(mags) == 1
            and mags[0] == -0.10
            and '_qpos' in cohort
            and '_reg_haccel > 0' in cohort
            and 'decline > 0.020' in cohort
            and 'decline < 0.050' in cohort
        )
        if is_fresh_proven_single:
            waste_drops.append((p.name, 'fresh × proven cell × -0.10 (saturated single-mag)'))
    if waste_drops:
        print(f'  P7 ANTI-PADDING DROP: {len(waste_drops)} low-EV probes')
        for n, reason in waste_drops[:5]:
            print(f'    DROP {n}: {reason}')
        if len(waste_drops) > 5:
            print(f'    ... and {len(waste_drops) - 5} more')
        drop_names = {n for n, _ in waste_drops}
        R.probes = [p for p in R.probes if p.name not in drop_names]
        rep = audit(R, reg)

    # P6 cohort-overlap detector. Any non-aux probe whose cohort overlaps
    # any existing bake's cohort by >40% (Jaccard token similarity) is dropped.
    # Forces new probes into structurally-distinct cohort space.
    from s001.gen_s001_diagnostics import (
        capture_ratio, cohort_is_virgin, cohort_overlap_block,
        cross_lever_warning,
    )
    # P14 cross-lever warning (2026-05-17 30m reconstruct #5):
    # When candidate score-family probe (score/wt_tilt) at mag > 1.05
    # overlaps with OPPOSITE-lever bake on same cell, R2546 evidence
    # shows catastrophic interference (-0.01 to -0.015).
    cross_lever_warnings = []
    for p in R.probes:
        lever = (getattr(p, 'lever', None) or '').strip()
        if lever not in ('score', 'wt_tilt'):
            continue
        cohort = getattr(p, 'cohort', '') or ''
        mags = list(p.mags or [])
        for m in mags:
            if m is None or m <= 1.05:
                continue
            w = cross_lever_warning(cohort, lever, candidate_mag=m)
            if w:
                cross_lever_warnings.append(f"  {p.name} m{int(m*100)}: {w['msg']}")
                break  # one warning per probe is enough
    if cross_lever_warnings:
        print('  CROSS-LEVER WARNINGS:')
        for w in cross_lever_warnings:
            print(w)

    overlap_drops = []
    for p in R.probes:
        lever = (getattr(p, 'lever', None) or '').strip()
        if lever in AUX_LEVERS:
            continue
        cohort = getattr(p, 'cohort', '') or ''
        if not cohort:
            continue
        # Lever-aware overlap: only check same-lever bakes. Different
        # levers operate on different mathematical paths and can co-fire
        # on overlapping populations without destructive stacking. This
        # enables lever-transfer testing on proven cohort cells.
        # 2026-05-12: threshold raised 0.40 → 0.50. With 30+ active bakes,
        # 40% over-blocks candidates testing DIFFERENT regime pairs but
        # sharing parent/sector/one-regime tokens with a bake (e.g.
        # qzero×S206×HA+HD3 candidate shares 43% with bake qzero×S206×
        # HD3+Q3 — still meaningful exploration but was P6-dropped).
        # 2026-05-17: VRFY exemption — probes with _VRFY/_DEEP in name
        # are mag-stability tests on baked cohorts; intentional same-cohort
        # same-lever testing at adjacent mags. Skip P6 for these.
        is_vrfy = '_VRFY' in (p.name or '') or '_DEEP' in (p.name or '')
        if is_vrfy:
            continue
        blocked, msg = cohort_overlap_block(cohort, threshold=0.50,
                                              candidate_lever=lever)
        if blocked:
            overlap_drops.append((p.name, msg))
    if overlap_drops:
        print(f'  P6 OVERLAP-DROP: {len(overlap_drops)} probes >50% overlap')
        for n, m in overlap_drops[:8]:
            print(f'    DROP {n}: {m}')
        if len(overlap_drops) > 8:
            print(f'    ... and {len(overlap_drops) - 8} more')
        drop_names = {n for n, _ in overlap_drops}
        R.probes = [p for p in R.probes if p.name not in drop_names]
        rep = audit(R, reg)

    # P5 capture-ratio guard. If recent capture <50% (relaxed from 60% on
    # 2026-05-17 30m deep-review #2), force virgin-only mode.
    cap = capture_ratio()
    if cap.get('force_virgin'):
        print(f"  CAPTURE-RATIO {cap['ratio']:.1%} < 50% — VIRGIN MODE FORCED")
        non_virgin = []
        # 2026-05-16: short-name aux probes (CV/RA/PA/SS/KA from
        # add_productive_aux_blocks) are 1-mag productive-aux entries,
        # not exploration axes. Exempt from virgin check.
        AUX_PROBE_NAMES = {'CV', 'RA', 'PA', 'SS', 'KA'}
        for p in R.probes:
            lever = (getattr(p, 'lever', None) or '').strip()
            if lever in AUX_LEVERS:
                continue
            if getattr(p, 'name', '') in AUX_PROBE_NAMES:
                continue
            cohort = getattr(p, 'cohort', '') or ''
            # Lever-aware virgin check: only block when SAME-LEVER bake
            # subsumes (consistent with P6 lever-aware overlap).
            if not cohort_is_virgin(cohort, candidate_lever=lever):
                non_virgin.append((p.name, cohort))
        if non_virgin:
            print('  FOUND NON-VIRGIN PROBES (rejected):')
            for n, c in non_virgin[:8]:
                print(f'    - {n}: {c}')
            if len(non_virgin) > 8:
                print(f'    - ... and {len(non_virgin) - 8} more')
            raise RuntimeError(
                f'Capture-ratio guard ({cap["ratio"]:.1%}<60%) requires '
                f'virgin-only round. {len(non_virgin)} probes reuse '
                f'already-baked cohorts. Pivot to under-explored cohorts '
                f'or run a diagnostic round (e.g. R1833 decay audit).'
            )
        print('  ✓ all main-line probes are virgin — quota guard passed')
    else:
        ratio = cap.get('ratio')
        if ratio is not None:
            print(f"  capture-ratio: {ratio:.1%} (≥50% — no virgin lock)")

    # P10 — productive-regime guard (user 2026-05-10: R1894/R1895 measured
    # 0% meaningful yield because their cohorts used VIRGIN regimes that
    # genuinely don't fire. Rule: each non-aux probe's cohort MUST reference
    # ≥1 productive regime (one with ≥2 active bakes). Bypass: S001_BYPASS_REGIME_GUARD=1.
    import os as _os10
    PRODUCTIVE_REGIMES = {
        '_reg_haccel', '_reg_vxx_falling3', '_reg_double_panic',
        '_reg_qqq_up3', '_reg_hyg_dn14',
        # Minor regimes confirmed productive R1939-R1940 (2026-05-11):
        '_reg_hyg_dn3', '_reg_hyg_dn5',
        # 2026-05-18 candidates: qqq_up3 productive via BAKE-37/38 (+0.00093,
        # +0.00423). hyg_up3 BAKE-40, hyg_up5 BAKE-39/41/42 ALL confirmed productive.
        '_reg_qqq_up5', '_reg_hyg_up3', '_reg_hyg_up5',
        # 2026-05-18 review #8: post-BAKE-42 drought. Expanding to QQQ
        # negative regimes (untested in session) for exploration coverage.
        '_reg_qqq_dn3', '_reg_qqq_dn5', '_reg_qqq_dn7',
    }
    if _os10.environ.get('S001_BYPASS_REGIME_GUARD') != '1':
        regime_drops = []
        for p in R.probes:
            lever = (getattr(p, 'lever', None) or '').strip()
            if lever in AUX_LEVERS:
                continue
            # 2026-05-12: exit_signal probes are pnl-conditional partial-vote
            # gates (no parent/sector/regime structure). Exempt from regime
            # guard; productive direction validated by exit_signal lever
            # avg lift +0.453 (150x other levers).
            if lever == 'exit_signal':
                continue
            cohort = getattr(p, 'cohort', '') or ''
            if not any(r in cohort for r in PRODUCTIVE_REGIMES):
                regime_drops.append(p.name)
        if regime_drops:
            print(f'  P10 REGIME-GUARD DROP: {len(regime_drops)} probes lack productive regime')
            for n in regime_drops[:5]:
                print(f'    DROP {n}: cohort needs ≥1 of {sorted(PRODUCTIVE_REGIMES)}')
            if len(regime_drops) > 5:
                print(f'    ... and {len(regime_drops) - 5} more')
            R.probes = [p for p in R.probes if p.name not in regime_drops]

    # P9 — fire-rate guard (user 2026-05-10 hard constraint: meaningful specs
    # only). Drops probes whose accessor is empirically DEAD: <5% fire rate at
    # ≥30 trials (significant sample of consistent silence). Soft threshold —
    # 5-10% fire rate is meaningful (unusual but real signal); only <5% with
    # large sample is truly wasted. Bypass: S001_BYPASS_FIRE_GUARD=1.
    import os as _os
    if _os.environ.get('S001_BYPASS_FIRE_GUARD') != '1':
        from s001.gen_s001_diagnostics import accessor_fire_rates
        rates = accessor_fire_rates(min_trials=30)
        fire_drops = []
        for p in R.probes:
            lever = (getattr(p, 'lever', None) or '').strip()
            if lever in AUX_LEVERS:
                continue
            for fld in (getattr(p, 'fresh_fields', None) or ()):
                stat = rates.get(fld)
                if stat and stat['rate'] < 0.05:
                    fire_drops.append((p.name, fld,
                                       f"{stat['rate']:.0%}@{stat['total']}"))
                    break
        if fire_drops:
            print(f'  P9 FIRE-RATE DROP: {len(fire_drops)} probes <5%@≥30 trials')
            for n, fld, why in fire_drops[:5]:
                print(f'    DROP {n}: {fld} {why}')
            if len(fire_drops) > 5:
                print(f'    ... and {len(fire_drops) - 5} more')
            drop_names = {n for n, _, _ in fire_drops}
            R.probes = [p for p in R.probes if p.name not in drop_names]

    # P8 — 16-spec guard (user 2026-05-19 updated: 8→16):
    # Every round MUST queue 16 ±2 meaningful specs (14-18 band).
    # Hard constraint — design meaningful 16-spec rounds.
    # Bypass: S001_BYPASS_128_GUARD=1 (forbidden by user).
    import os as _os
    _bypass = _os.environ.get('S001_BYPASS_128_GUARD') == '1'
    if not _bypass:
        def _est():
            return (sum(len(p.mags) if p.mags else 1 for p in R.probes)
                    + R.noops)
        AUX_NAMES = {'PA', 'SS', 'KA', 'RA', 'CV'}
        trimmed = 0
        while _est() > 18:
            for i in range(len(R.probes) - 1, -1, -1):
                if R.probes[i].name not in AUX_NAMES:
                    R.probes.pop(i)
                    trimmed += 1
                    break
            else:
                break
        if trimmed:
            print(f'  AUTO-TRIM: dropped {trimmed} probes to fit ≤18')
            rep = audit(R, reg)
        est = _est()
        if est < 14 or est > 18:
            raise RuntimeError(
                f'16-spec guard FAILED PRE-QUEUE: would insert {est} specs, '
                f'outside band 14-18.\n'
                f'  User hard constraint (2026-05-19): every round = 16 '
                f'MEANINGFUL specs (±2, prefer exactly 16).\n'
                f'  Adjust block count: 7 axes × 2 mags + 1 CV + 1 NOOP ≈ 16. '
                f'Add/remove axes to land in 14-18 band.\n'
                f'  Bypass for diagnostics: S001_BYPASS_128_GUARD=1 python3 ...'
            )

    res = queue(R, rep, enforce_audit=True)
    print()
    print(f"=== QUEUED ===\ninserted={res['inserted']} skipped={res['skipped']} total={res['total_specs']}")
    return res


def pretick_or_die(rid_completed=None):
    """Run before queueing. If bakes are pending, raise so caller halts.

    Pass rid_completed=None (default) to auto-pick latest completed round.
    Use as the FIRST line of every gen script's main().
    """
    # Base-corruption check: previous revert operations have left the
    # base in a state where `except: pass<spaces>#` joins onto one line,
    # causing all subsequent specs to fail with SyntaxError. Detect and
    # die loudly. R1773, R1785 base corruption history.
    import re as _re
    from pathlib import Path as _Path
    from s001.gen_s001_diagnostics import BASE_PATH, pretick_guard
    base_src = _Path(BASE_PATH).read_text()
    # Only match horizontal whitespace (tabs/spaces) between `pass` and `#`,
    # NOT newlines — `except: pass\n   #` is the legitimate inter-bake gap.
    bad = _re.findall(r'except:[ \t]*pass[ \t]+#', base_src)
    if bad:
        raise RuntimeError(
            f'BASE CORRUPTION: {len(bad)} `except: pass<spaces>#` join-lines '
            f'detected. Fix base before queueing. Sample: {bad[0][:80]!r}')
    clear, msg = pretick_guard(rid_completed)
    print(msg)
    if not clear:
        raise RuntimeError(
            f'BLOCK: bake-eligible probes pending. '
            f'Apply bake to base, commit, then re-run.\n{msg}')

    # 2026-05-16: post-bake NOOP-shift verification. R2347 conv bakes
    # showed +0.00206 predicted vs +0.00000 actual NOOP shift — null
    # bakes that clutter base + waste compute. Audit last applied
    # bake's predicted vs actual NOOP shift; warn if < 30% delivered.
    try:
        from s001.gen_s001_diagnostics import verify_recent_bake_lift
        verify_recent_bake_lift()
    except ImportError:
        pass
    except Exception as _e:
        print(f'  [verify_recent_bake_lift skipped: {_e}]')
