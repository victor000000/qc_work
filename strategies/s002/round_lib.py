"""s002 round generator library — single source of truth for mutation, axes,
probe groups, NOOP-hash dedupe, and DB queueing.

Replaces:
  - boilerplate in data/gen_afql3b_div25XX.py
  - data/diversity_generator.py (round_template_v2, cold_etf_probes)

Use via strategies/s002/queue_round.py CLI.
"""
from __future__ import annotations
import re
import os
import qc_storage as storage
import hashlib
import shutil
import datetime as _dt
from dataclasses import dataclass, field
from typing import Iterable, Sequence

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(os.environ.get('QC_DATA_DIR', os.path.join(ROOT, 'data')), 'S002.duckdb')

# ─── Hard constraints (single source of truth) ─────────────────────────────
WT_BAN = frozenset({'gdx', 'dbb', 'vde', 'iyr'})
TF_T_BAN = frozenset({'mgv', 'sptm', 'exi', 'pey'})
TP_LARGE_BAN = frozenset({'pjp', 'iak', 'aok', 'usig', 'pgx'})
WT_RANGE = (0.020, 0.0699)
SL_FLOOR = 0.012  # sl > this
TF_T_FLOOR = 0.95
SP_CEILING = 280


def _validate(etf: str, changes: dict) -> None:
    if 'sl' in changes and changes['sl'] <= SL_FLOOR:
        raise ValueError(f'sl<={SL_FLOOR}')
    if 'wt' in changes:
        w = changes['wt']
        if not (WT_RANGE[0] <= w <= WT_RANGE[1]):
            raise ValueError('wt range')
        if etf in WT_BAN:
            raise ValueError(f'wt ban: {etf}')
    if 'tf_t' in changes:
        if changes['tf_t'] < TF_T_FLOOR:
            raise ValueError('tf_t floor')
        if etf in TF_T_BAN:
            raise ValueError(f'tf_t ban: {etf}')
    if 'tp' in changes and etf in TP_LARGE_BAN:
        raise ValueError(f'tp ban: {etf}')
    if 'sp' in changes and changes['sp'] > SP_CEILING:
        raise ValueError('sp cap')
    if 'sf' in changes and changes['sf'] == 0:
        raise ValueError('sf=0')


# ─── Mutation ──────────────────────────────────────────────────────────────
_ETF_BLOCK = re.compile(r"(\s+'(?P<etf>[a-z]{2,5})':\s*\{)(?P<body>[^}]+)(\})", re.M)


def mut_etf(changes: dict, etf: str, code: str) -> str | None:
    """Apply changes to ETF cfg in code. Returns new code, or None if etf missing.
    Raises ValueError if changes violate hard constraints."""
    _validate(etf, changes)
    pat = re.compile(r"(\s+'" + re.escape(etf) + r"':\s*\{)([^}]+)(\})", re.M)
    m = pat.search(code)
    if not m:
        return None
    body = m.group(2)
    for k, v in changes.items():
        kp = re.compile(r"'" + re.escape(k) + r"'\s*:\s*[^,}]+")
        if kp.search(body):
            body = kp.sub(f"'{k}':{repr(v)}", body, count=1)
        else:
            body = body.rstrip().rstrip(',') + f",'{k}':{repr(v)}"
    return code[:m.start()] + m.group(1) + body + m.group(3) + code[m.end():]


def make_spec(etf: str, changes: dict, salt: int, base: str) -> str | None:
    code = mut_etf(changes, etf, base)
    if code is None:
        return None
    return mut_etf({'_rvtag': salt}, 'vti', code)


def codehash(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


# ─── ETF parsing ───────────────────────────────────────────────────────────
def parse_all_etfs(base: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for m in _ETF_BLOCK.finditer(base):
        etf = m.group('etf')
        if etf == 'vti':
            continue
        cfg = {km.group(1): km.group(2).strip()
               for km in re.finditer(r"'(\w+)'\s*:\s*([^,}]+)", m.group('body'))}
        out[etf] = cfg
    return out


def cohort_index(base: str) -> dict[str, list[tuple[str, int]]]:
    """{indicator: [(etf, n_keys)] sorted ascending by key count}."""
    cohorts: dict[str, list[tuple[str, int]]] = {}
    for etf, cfg in parse_all_etfs(base).items():
        ind = cfg.get('i', '').strip("'")
        if not ind:
            continue
        cohorts.setdefault(ind, []).append((etf, len(cfg)))
    for k in cohorts:
        cohorts[k].sort(key=lambda t: t[1])
    return cohorts


def _f(cfg: dict, key: str) -> float | None:
    v = cfg.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None


# ─── Axes ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Axis:
    name: str
    key: str
    mode: str  # 'value' or 'add'
    values: tuple[tuple[str, callable], ...]

    def apply(self, cur, value_idx=0):
        if value_idx >= len(self.values):
            return None, None
        vname, vfn = self.values[value_idx]
        return vname, vfn(cur)


def _ax_value(name, key, *vals):
    return Axis(name, key, 'value', tuple(vals))


def _ax_add(name, key, *vals):
    return Axis(name, key, 'add', tuple(vals))


AXES: dict[str, Axis] = {
    a.name: a for a in [
        _ax_value('tp_shrink', 'tp',
            ('60pct', lambda c: round(c*0.6, 3) if c and c > 0.05 else None),
            ('50pct', lambda c: round(c*0.5, 3) if c and c > 0.05 else None),
            ('70pct', lambda c: round(c*0.7, 3) if c and c > 0.05 else None)),
        _ax_value('tp_grow', 'tp',
            ('150pct', lambda c: round(c*1.5, 3) if c and c < 0.15 else None),
            ('120pct', lambda c: round(c*1.2, 3) if c and c < 0.20 else None),
            ('180pct', lambda c: round(c*1.8, 3) if c and c < 0.12 else None)),
        _ax_value('tp_pivot_low', 'tp',
            ('060', lambda c: 0.060 if c and abs(c-0.060) > 0.010 and c > 0.030 else None),
            ('080', lambda c: 0.080 if c and abs(c-0.080) > 0.012 and c > 0.040 else None)),
        _ax_value('tp_pivot_high', 'tp',
            ('120', lambda c: 0.120 if c and abs(c-0.120) > 0.015 and c > 0.060 else None),
            ('150', lambda c: 0.150 if c and abs(c-0.150) > 0.020 and c > 0.075 else None)),
        _ax_add('sl_add', 'sl',
            ('025', lambda c: 0.025 if c is None else None),
            ('032', lambda c: 0.032 if c is None else None)),
        _ax_value('sl_tighten', 'sl',
            ('025', lambda c: 0.025 if c and c > 0.026 else None),
            ('018', lambda c: 0.018 if c and c > 0.019 else None)),
        _ax_value('wt_lower', 'wt',
            ('035', lambda c: 0.035 if c and abs(c-0.035) > 0.005 else None),
            ('045', lambda c: 0.045 if c and abs(c-0.045) > 0.005 else None)),
        _ax_value('ef_norm', 'ef',
            ('095', lambda c: 0.95 if c and abs(c-0.95) > 0.02 else None),
            ('088', lambda c: 0.88 if c and abs(c-0.88) > 0.02 else None)),
        _ax_value('xf_norm', 'xf',
            ('105', lambda c: 1.05 if c and abs(c-1.05) > 0.03 else None),
            ('095', lambda c: 0.95 if c and abs(c-0.95) > 0.03 else None)),
        _ax_value('cf_norm', 'cf',
            ('092', lambda c: 0.92 if c and abs(c-0.92) > 0.03 else None),
            ('088', lambda c: 0.88 if c and abs(c-0.88) > 0.03 else None)),
        _ax_value('sp_shrink', 'sp',
            ('60pct', lambda c: max(15, int(c*0.6)) if c and c > 25 else None),
            ('50pct', lambda c: max(15, int(c*0.5)) if c and c > 30 else None)),
        _ax_value('e_widen', 'e',
            ('plus3', lambda c: round(c+3, 3) if c is not None and abs(c) < 25 and c != 0 else None),
            ('plus5', lambda c: round(c+5, 3) if c is not None and abs(c) < 25 and c != 0 else None)),
        _ax_value('x_tighten', 'x',
            ('minus3', lambda c: round(c-3, 3) if c is not None and abs(c) > 5 else None),
            ('minus5', lambda c: round(c-5, 3) if c is not None and abs(c) > 8 else None)),
        # New for Pass 8 — untouched live levers
        _ax_value('p_shrink', 'p',
            ('half', lambda c: max(2, int(c * 0.5)) if c and c >= 8 else None),
            ('two_thirds', lambda c: max(2, int(c * 0.67)) if c and c >= 6 else None)),
        _ax_value('p_grow', 'p',
            ('1_5x', lambda c: int(c * 1.5) if c and 4 <= c <= 30 else None),
            ('2x', lambda c: int(c * 2) if c and 4 <= c <= 25 else None)),
        # tf_t — memory says <0.95 catastrophic. Probe within [0.95, 1.10].
        # Loosened: any nonzero current value with target ≥ 0.95 qualifies.
        _ax_value('tf_t_raise', 'tf_t',
            ('100', lambda c: 1.00 if c is not None and 0.95 <= c <= 1.10 and abs(c - 1.00) > 0.005 else None),
            ('105', lambda c: 1.05 if c is not None and 0.95 <= c <= 1.10 and abs(c - 1.05) > 0.005 else None)),
        _ax_value('tf_t_lower', 'tf_t',
            ('097', lambda c: 0.97 if c is not None and 0.97 < c <= 1.10 else None),
            ('095', lambda c: 0.95 if c is not None and 0.96 < c <= 1.10 else None)),
        # tr_p (trade-pattern period) — 12 ETFs configured
        _ax_value('tr_p_shrink', 'tr_p',
            ('two_thirds', lambda c: max(5, int(c * 0.67)) if c and c >= 8 else None),
            ('half', lambda c: max(5, int(c * 0.5)) if c and c >= 10 else None)),
    ]
}

# Round-rotated axis sets (set_idx = round_num % len).
# Pass 12 prune: only tp axes produce signal in current saturation regime.
# Productivity data over R2519-R2528:
#   tp_shrink: 313 specs, 1.0% positive (max +0.00143)
#   tp_grow:   319 specs, 7.5% positive (max +0.00071)
#   ALL OTHER AXES: 0/458 positive (ef_norm, sl_add, xf_norm, cf_norm,
#     sp_shrink, wt_lower, tp_pivot_high, tp_pivot_low, e_widen, x_tighten,
#     p_shrink, p_grow, tr_p_shrink, tf_t_*).
# Removed dead axes from rotation. tf_t_raise/lower kept for one slot since
# never had broad testing (only 5 probes).
# Productivity-dead axes (2026-05-09 audit, ≥50 historical samples each,
# 0 positive lifts at +0.0007 threshold). Filtered out of AXIS_SETS, cold
# probes, and untouched-lever rotation.
DEAD_AXES: frozenset[str] = frozenset({
    'atr_p', 'cf_norm', 'ef_norm', 'sl_add', 'wt_lower',
    'tp_pivot_high', 'sp_shrink', 'xf_norm', 'p_shrink',
    'p_grow', 'e_widen', 'x_tighten',
})

AXIS_SETS: tuple[tuple[str, ...], ...] = (
    ('tp_shrink', 'tp_grow'),
    ('tp_grow', 'tp_shrink'),
    ('tp_shrink', 'tp_pivot_low', 'tp_grow'),
    ('tp_grow', 'tp_shrink'),  # was tp_pivot_high — DEAD, replaced
    ('tp_grow', 'tp_shrink', 'tf_t_raise', 'tf_t_lower'),  # tf_t still under-tested
)


# ETFs whose indicator requires special handling (e.g., frama needs even p)
FRAMA_INDICATORS = frozenset({'frama'})


def _is_frama_etf(cfg: dict) -> bool:
    return cfg.get('i', '').strip("'") in FRAMA_INDICATORS


# ─── Probe generation ──────────────────────────────────────────────────────
@dataclass
class Probe:
    etf: str
    changes: dict
    kind: str  # 'DIV', 'COLD', 'C2D', 'DV2', 'VRFY'
    axis: str
    val: str


def _safe_for_etf(etf: str, cfg: dict, lever: str, new_val) -> bool:
    """Per-(etf, lever, value) safety. frama needs even p. Other rules added here."""
    if lever == 'p' and _is_frama_etf(cfg):
        try:
            return int(new_val) % 2 == 0
        except (TypeError, ValueError):
            return False
    return True


def axis_probes(round_num: int, base: str, axis_subset: Sequence[str],
                value_idx: int = 0, etf_per_cohort: int = 1,
                exclude: set[str] | None = None,
                prefer: set[str] | None = None,
                exclude_axis_pair: set[tuple[str, str]] | None = None) -> list[Probe]:
    """exclude_axis_pair blocks (etf, axis_name) pairs known-destructive,
    while still allowing untested pairs (medium-EV exploration).
    2026-05-10 added per user directive: every backtest must be meaningful."""
    exclude = exclude or set()
    prefer = prefer or set()
    exclude_axis_pair = exclude_axis_pair or set()
    cohorts = cohort_index(base)
    cfgs = parse_all_etfs(base)
    rotation = round_num // max(len(axis_subset), 1)
    out: list[Probe] = []
    for ax_name in axis_subset:
        ax = AXES.get(ax_name)
        if ax is None:
            continue
        for ind in sorted(cohorts):
            cohort = cohorts[ind]
            if not cohort:
                continue
            # Bias: productive ETFs first within cohort
            if prefer:
                cohort = sorted(cohort, key=lambda x: x[0] not in prefer)
            for k in range(etf_per_cohort):
                etf, _ = cohort[(rotation + k) % len(cohort)]
                if etf in exclude:
                    continue
                if prefer and etf not in prefer and len([p for p in cohort if p[0] in prefer]) > 0:
                    continue  # skip non-productive when productive available in cohort
                cfg = cfgs.get(etf, {})
                cur = _f(cfg, ax.key)
                if ax.mode == 'add' and ax.key in cfg:
                    continue
                if ax.mode == 'value' and cur is None:
                    continue
                vname, new = ax.apply(cur, value_idx)
                if new is None:
                    continue
                if not _safe_for_etf(etf, cfg, ax.key, new):
                    continue
                # Block known-destructive (etf, axis) pairs while allowing
                # untested pairs (2026-05-10 — meaningful spec directive).
                if (etf, ax_name) in exclude_axis_pair:
                    continue
                out.append(Probe(etf, {ax.key: new}, 'DIV', ax_name, vname))
    return out


def cold_probes(base: str, recent_etfs: set[str],
                axes: Sequence[str] = ('tp_grow', 'tp_shrink'),
                max_probes: int = 32, value_idx: int = 0,
                multi_axis_per_etf: bool = False) -> list[Probe]:
    """Probe ETFs absent from recent_etfs.

    multi_axis_per_etf=True: cycle through ETFs first, axes second — so each
    cold ETF gets probed across multiple axes (better hit rate against
    indicator-gated levers). Default False keeps backward compat.
    """
    cfgs = parse_all_etfs(base)
    cold = sorted(set(cfgs) - set(recent_etfs))
    out: list[Probe] = []
    axes = tuple(a for a in axes if a not in DEAD_AXES)
    if multi_axis_per_etf:
        # ETF outer, axis inner: each ETF gets ≤len(axes) probes
        for etf in cold:
            if len(out) >= max_probes:
                break
            cfg = cfgs[etf]
            for ax_name in axes:
                if len(out) >= max_probes:
                    break
                ax = AXES.get(ax_name)
                if ax is None:
                    continue
                cur = _f(cfg, ax.key)
                if ax.mode == 'add' and ax.key in cfg:
                    continue
                if ax.mode == 'value' and cur is None:
                    continue
                vname, new = ax.apply(cur, value_idx)
                if new is None:
                    continue
                out.append(Probe(etf, {ax.key: new}, 'COLD', ax_name, vname))
    else:
        for ax_name in axes:
            if len(out) >= max_probes:
                break
            ax = AXES.get(ax_name)
            if ax is None:
                continue
            for etf in cold:
                if len(out) >= max_probes:
                    break
                cfg = cfgs[etf]
                cur = _f(cfg, ax.key)
                if ax.mode == 'add' and ax.key in cfg:
                    continue
                if ax.mode == 'value' and cur is None:
                    continue
                vname, new = ax.apply(cur, value_idx)
                if new is None:
                    continue
                out.append(Probe(etf, {ax.key: new}, 'COLD', ax_name, vname))
    return out


def cold_probes_directed(base: str, recent_etfs: set[str],
                         best_lever_per_indicator: dict[str, str],
                         lever_to_axes: dict[str, list[str]] | None = None,
                         max_probes: int = 24, value_idx: int = 0,
                         fallback_axis: str = 'tp_grow') -> list[Probe]:
    """Probe cold ETFs on the most productive axis for their indicator cohort.

    For each cold ETF, look up its indicator → preferred lever from
    best_lever_per_indicator (built from cohort_productivity.best_axis_per_indicator).
    If known: probe that lever's primary axis at value_idx.
    If unknown: probe fallback_axis at value_idx (default tp_grow).

    Returns a list of Probes. Higher hit-rate than uniform single-axis cold
    probing because each ETF gets the axis its cohort has historically
    responded to.
    """
    cfgs = parse_all_etfs(base)
    cold = sorted(set(cfgs) - set(recent_etfs))
    if lever_to_axes is None:
        lever_to_axes = {}
        for ax_name, ax in AXES.items():
            lever_to_axes.setdefault(ax.key, []).append(ax_name)
    # Prioritize cold ETFs whose indicator-cohort has known productive lever
    def _has_known_lever(etf: str) -> int:
        ind = cfgs[etf].get('i', '').strip("'")
        return 1 if ind in best_lever_per_indicator else 0
    cold.sort(key=lambda e: -_has_known_lever(e))
    out: list[Probe] = []
    for etf in cold:
        if len(out) >= max_probes:
            break
        cfg = cfgs[etf]
        ind = cfg.get('i', '').strip("'")
        # Pick axis: prefer cohort-best lever, else fallback
        preferred_lever = best_lever_per_indicator.get(ind)
        if preferred_lever and preferred_lever in lever_to_axes:
            ax_name = lever_to_axes[preferred_lever][0]
        else:
            ax_name = fallback_axis
        ax = AXES.get(ax_name)
        if ax is None:
            continue
        cur = _f(cfg, ax.key)
        if ax.mode == 'add' and ax.key in cfg:
            continue
        if ax.mode == 'value' and cur is None:
            continue
        vname, new = ax.apply(cur, value_idx)
        if new is None:
            continue
        out.append(Probe(etf, {ax.key: new}, 'COLD', ax_name, vname))
    return out


def untouched_lever_probes(base: str,
                           untouched: list[tuple[str, float, int]],
                           max_probes: int = 30,
                           etf_filter: set[str] | None = None,
                           excluded_pairs: set | None = None,
                           baked_etfs: set[str] | None = None,
                           saturated_combos: set | None = None,
                           inert_etfs: set[str] | None = None) -> list[Probe]:
    """For each (lever, value, etfs_to_test) in `untouched`, generate ADD probes.

    These keys exist in strategy code (cfg.get('lever', default)) but absent
    from current ETF cfgs — adding activates dormant code paths.

    untouched: list of (lever_name, target_value, n_etfs_to_test).
       n_etfs_to_test lets productive levers get broader coverage.
    excluded_pairs: skip (etf, lever) in this set (dead/toxic from history).
    """
    excluded_pairs = excluded_pairs or set()
    baked_etfs = baked_etfs or set()
    saturated_combos = saturated_combos or set()
    inert_etfs = inert_etfs or set()
    cohorts = cohort_index(base)
    cfgs = parse_all_etfs(base)
    out: list[Probe] = []
    # Build diverse ETF order including ALL ETFs (not just first 3 per cohort).
    # Pass 22: 134/310 ETFs never probed; widen pool for full diversification.
    ordered_etfs: list[str] = []
    for ind in sorted(cohorts):
        # All ETFs in cohort, sorted by key count (sparse first for less-tuned)
        for etf, _ in cohorts[ind]:
            ordered_etfs.append(etf)
    seen = set()
    ordered_etfs = [e for e in ordered_etfs if not (e in seen or seen.add(e))]
    if etf_filter:
        ordered_etfs = [e for e in ordered_etfs if e in etf_filter]
    # Pass 34 (2026-05-09): drop structurally-inert ETFs entirely. These have
    # ≥30 historical probes, ≥80% exact-NOOP, 0 positive lifts. Probes on
    # them are pure compute waste regardless of lever.
    ordered_etfs = [e for e in ordered_etfs if e not in inert_etfs]
    # Pass 22: untouched-priority — sort unprobed ETFs first.
    try:
        previously_probed = db_untouched_etfs()
        unprobed = [e for e in ordered_etfs if e not in previously_probed]
        already = [e for e in ordered_etfs if e in previously_probed]
        ordered_etfs = unprobed + already
    except Exception:
        previously_probed = set()
        unprobed = []
        already = ordered_etfs

    # Pass 23: for FRESH (unprobed) ETFs, test ALL untouched lever-value
    # combos on each ETF before moving to next ETF. Maximizes per-ETF
    # coverage and surfaces multi-lever bakes faster (e.g., kxi got
    # atr_sl + dd_haircut bakes; pjp dd_haircut. Each fresh ETF should
    # get all chances).
    # Pass 35 (2026-05-09): WITHIN a round, only ONE value per (etf, lever)
    # pair. Without this, a fresh ETF gets dd_haircut at 0.3/0.4/0.5/0.7
    # all in one round = 4 specs × 3 salts = 12 wasted backtests if the
    # first value confirms inert. After 1 round of data, the cross-round
    # dead-pair filter takes over for that ETF.
    seen_pairs_this_round: set[tuple[str, str]] = set()
    if unprobed:
        fresh_set = set(unprobed)
        # Generate fresh-ETF probes (etf-outer, lever-inner)
        fresh_probes: list[Probe] = []
        for etf in unprobed:
            if len(fresh_probes) + len(out) >= max_probes:
                break
            cfg = cfgs.get(etf, {})
            for lever, value, _n in untouched:
                if len(fresh_probes) + len(out) >= max_probes:
                    break
                if lever in cfg:
                    continue
                if (etf, lever) in excluded_pairs:
                    continue
                if (etf, lever) in seen_pairs_this_round:
                    continue
                if (etf, lever, value) in saturated_combos:
                    continue
                if lever in TRADE_GATE_LEVERS and etf in baked_etfs:
                    continue
                val_label = str(value).replace('.', '_').replace('-', 'n')[:8]
                fresh_probes.append(Probe(etf, {lever: value}, 'NEWAX',
                                          lever, val_label))
                seen_pairs_this_round.add((etf, lever))
        out.extend(fresh_probes)

    for lever, value, n_etfs in untouched:
        if len(out) >= max_probes:
            break
        # TRADE_GATE_LEVERS skip baked ETFs entirely (gate-style mutations
        # damage tuned ETFs). RISK_MGMT_LEVERS are safe to add on baked ETFs.
        if lever in TRADE_GATE_LEVERS:
            etf_pool = [e for e in ordered_etfs if e not in baked_etfs]
        else:
            etf_pool = ordered_etfs  # risk-mgmt — allow on baked ETFs too
        candidates = [e for e in etf_pool
                      if lever not in cfgs.get(e, {})
                      and (e, lever) not in excluded_pairs
                      and (e, lever) not in seen_pairs_this_round
                      and (e, lever, value) not in saturated_combos]
        for etf in candidates[:n_etfs]:
            if len(out) >= max_probes:
                break
            val_label = str(value).replace('.', '_').replace('-', 'n')[:8]
            # Don't truncate lever — analysis tools look for full name
            out.append(Probe(etf, {lever: value}, 'NEWAX',
                             lever, val_label))
            seen_pairs_this_round.add((etf, lever))
    return out


# Lever taxonomy:
#   TRADE_GATE_LEVERS skip baked ETFs — they gate WHEN/WHETHER to trade,
#     adding them to a baked (already-tuned) ETF damages frequency.
#     Evidence: bb_width_max on itot/piz/kre = -0.018 / -0.026 / -0.046.
#   RISK_MGMT_LEVERS may apply to baked ETFs — they add safety layers
#     that compose with existing config without changing trade gating.
#     Evidence: piz + atr_sl=2.5 = +0.00167 (BAKE-166) on already-baked piz.
TRADE_GATE_LEVERS = frozenset({
    'bb_width_max', 'adx_min', 'rsi_gate', 'mom_min',
})
RISK_MGMT_LEVERS = frozenset({
    'atr_sl', 'atr_p', 'vol_max', 'dd_haircut',
})


# Curated dormant-lever activations.
# Each entry: (lever_name, target_value, n_etfs_to_test).
# adx_min/rsi_gate REMOVED after R2530 evidence (xlu adx_min=20 → -0.69;
# xlu rsi_gate=30 → -0.93 catastrophic).
# bb_width_max value variants added after R2530 success: xlu bb_width_max=0.10
# = +0.00119. Test wider value range and on more ETFs.
UNTOUCHED_LEVERS_CURATED: list[tuple[str, float, int]] = [
    # Pass 21 rebalance: vol_max widely tested (88 combos, only spxs productive
    # at +0.0098). Saturated. Pivot to truly under-tested: dd_haircut/mom_min/
    # atr_p which have ≤30 specs total.
    #
    # dd_haircut — drawdown haircut (1st priority — sparse data)
    ('dd_haircut', 0.5, 10),
    ('dd_haircut', 0.3, 8),
    ('dd_haircut', 0.7, 6),
    ('dd_haircut', 0.4, 4),
    # mom_min — momentum filter (2nd priority — sparse data)
    ('mom_min', 0.0, 8),
    ('mom_min', 0.005, 6),
    ('mom_min', 0.01, 4),
    # atr_p REMOVED 2026-05-09: 394 historical samples, 0 positive lifts at
    # +0.0007 threshold. ATR-period mutation never crosses a productive
    # decision boundary on this base. Behavior was exact-NOOP across all
    # tested ETFs. Memory called this "sparse" but data is now dense and
    # uniformly dead — class-level prune.
    # vol_max — saturated; opportunistic only
    ('vol_max', 0.05, 4),
    ('vol_max', 0.20, 3),
    ('vol_max', 0.10, 2),
    # atr_sl — saturated
    ('atr_sl', 2.5, 3),
    ('atr_sl', 1.5, 2),
    # adx_min/rsi_gate/bb_width_max REMOVED — broadly toxic
]


# Leveraged ETFs in universe — high-volatility candidates for atr_sl bakes.
# spxs (3x inverse SP) showed +0.01690 with atr_sl=3.0; pattern may extend.
LEVERAGED_ETFS = frozenset({
    'agq',   # 2x silver
    'ddm',   # 2x Dow
    'erx',   # 3x energy
    'fas',   # 3x financials
    'qid',   # 2x inverse QQQ
    'qld',   # 2x QQQ (baked tp)
    'sds',   # 2x inverse S&P
    'spxl',  # 3x S&P
    'spxs',  # 3x inverse S&P (baked atr_sl)
    'sso',   # 2x S&P
    'tlh',   # 10-20y treasury
    'tlt',   # 20+ year treasury
    'tna',   # 3x Russell 2000
})


def leveraged_atr_sl_probes(base: str,
                            baked_etfs: set[str],
                            atr_sl_values: tuple = (3.0, 2.5, 2.0, 1.5),
                            max_probes: int = 24,
                            excluded_pairs: set | None = None) -> list[Probe]:
    """Pass 19: probe atr_sl on un-baked leveraged ETFs.

    Hypothesis from R2539 evidence: spxs (3x inv S&P) + atr_sl=3.0 produced
    +0.01690 — leveraged ETFs benefit disproportionately from ATR stops
    (their volatility makes ATR-aware risk management high-leverage).

    Tests each un-baked leveraged ETF at multiple atr_sl values.
    """
    excluded_pairs = excluded_pairs or set()
    cfgs = parse_all_etfs(base)
    candidates = sorted(LEVERAGED_ETFS - baked_etfs)
    out: list[Probe] = []
    # Round-robin: value-outer, etf-inner
    for value in atr_sl_values:
        if len(out) >= max_probes:
            break
        for etf in candidates:
            if len(out) >= max_probes:
                break
            if etf not in cfgs:
                continue
            cfg = cfgs[etf]
            if 'atr_sl' in cfg:
                continue
            if (etf, 'atr_sl') in excluded_pairs:
                continue
            val_label = str(value).replace('.', '_')[:6]
            out.append(Probe(etf, {'atr_sl': value}, 'LEVAX',
                             'atr_sl', val_label))
    return out


def short_alias_value_probes(base: str,
                              alias_value_specs: list[tuple[str, str, list[float]]] | None = None,
                              max_probes: int = 30,
                              excluded_pairs: set | None = None,
                              baked_etfs: set[str] | None = None) -> list[Probe]:
    """Pass 29: probe SHORT-ALIAS keys as VALUE CHANGES on ETFs that use them.

    KEY INSIGHT: _KM map at base line 413 expands short aliases at runtime.
    ETFs use 'bw'/'dh'/'mm'/'rg'/'am' etc which become bb_width_max/dd_haircut/
    month_mask/rsi_gate/adx_min. NEWAX tested LONG names but most ETFs use
    SHORT forms — so probes were really value-changing, not activating.

    Untested territory:
      mm (month_mask): 24 ETFs — variants 1365/3087/4095/etc untested
      rg (rsi_gate): 68 ETFs — variants 40/45/50/55/60/65 untested
      am (adx_min): 53 ETFs — variants 10/15/20/25/30 untested
      bw (bb_width_max): 51 ETFs — value variants beyond xlu untested

    alias_value_specs: list of (short_alias, long_name, [values_to_test])
    """
    if alias_value_specs is None:
        alias_value_specs = [
            # Pass 32 — added newly-discovered untested short-alias levers:
            ('sp', 'sma_p', [10, 20, 30, 50, 80, 120]),
            ('cb', 'cdd_boost', [1.10, 1.20, 1.30, 1.50, 1.70]),
            ('cm', 'cdd_min', [1, 2, 3, 5]),
            ('ub', 'cup_boost', [1.10, 1.20, 1.30]),
            ('um', 'cup_min', [1, 2, 3]),
            ('cd', 'conv_depth', [5.0, 10.0, 20.0, 30.0]),
            ('dm', 'conv_deep_mult', [1.20, 1.40, 1.70, 2.00]),
            ('ed', 'e_deep', [0.05, 0.08, 0.15, 0.25]),
            # Original Pass 29 set:
            ('mm', 'month_mask', [1365, 2767, 3079, 3087, 4095]),
            ('rg', 'rsi_gate', [40, 45, 50, 55, 60, 65]),
            ('am', 'adx_min', [10, 15, 20, 25, 30]),
            ('bw', 'bb_width_max', [0.05, 0.08, 0.12, 0.15, 0.20]),
            ('dh', 'dd_haircut', [0.10, 0.15, 0.20, 0.30, 0.50]),
        ]
    excluded_pairs = excluded_pairs or set()
    baked_etfs = baked_etfs or set()
    cfgs = parse_all_etfs(base)
    out: list[Probe] = []

    # Cap per-lever to ensure variety — avoid one big-population lever
    # (sma_p with 282 ETFs) eating the entire budget.
    n_levers = len(alias_value_specs)
    max_per_lever = max(8, max_probes // max(n_levers, 1))

    # Round-robin: alias-outer, etf-inner
    for short, long_name, values in alias_value_specs:
        if len(out) >= max_probes:
            break
        per_lever_count = 0
        # ETFs using this short alias
        users = sorted([e for e in cfgs if short in cfgs[e]])
        for etf in users:
            if len(out) >= max_probes or per_lever_count >= max_per_lever:
                break
            if etf in baked_etfs and long_name not in {'atr_sl', 'dd_haircut', 'vol_max', 'atr_p'}:
                # Trade-gate levers: skip baked ETFs
                continue
            if (etf, long_name) in excluded_pairs:
                continue
            try:
                cur = float(cfgs[etf][short])
            except (ValueError, TypeError):
                continue
            for value in values:
                if len(out) >= max_probes or per_lever_count >= max_per_lever:
                    break
                if abs(value - cur) < 0.001 if isinstance(value, float) else value == cur:
                    continue
                val_label = str(value).replace('.', '_').replace('-', 'n')[:8]
                out.append(Probe(etf, {long_name: value}, 'SHRTAX',
                                 long_name, val_label))
                per_lever_count += 1
    return out


def breadth_first_sweep_probes(base: str,
                                previously_probed: set[str],
                                baked_etfs: set[str],
                                lever_value: tuple[str, float] = ('dd_haircut', 0.5),
                                max_probes: int = 32,
                                excluded_pairs: set | None = None,
                                inert_etfs: set[str] | None = None,
                                round_offset: int = 0,
                                noop_sigs: set | None = None,
                                destructive_cells: set | None = None,
                                dead_pairs: set | None = None,
                                recent_bfsw_axes: set[tuple[str, str]] | None = None,
                                inert_etf_axes: set[tuple[str, str]] | None = None,
                                noop_etf_axes: set[tuple[str, str]] | None = None,
                                prioritize_etfs: set[str] | None = None) -> list[Probe]:
    """Pass 27: 1 probe per untouched ETF, single (lever, value).

    2026-05-14: also pre-filters noop_sigs / destructive_cells / dead_pairs so
    candidates aren't generated only to be rejected at add_probes time (which
    leaves BFSW with 0 specs when filters saturate the alphabetical-first pool).
    2026-05-15: also accepts inert_etf_axes / noop_etf_axes — axis-class
    aggregate filters (R3115 30m review found 80% BFSW silent rate because
    per-value filters fire too late for alphabetical-rotation block).
    """
    excluded_pairs = excluded_pairs or set()
    inert_etfs = inert_etfs or set()
    noop_sigs = noop_sigs or set()
    destructive_cells = destructive_cells or set()
    dead_pairs = dead_pairs or set()
    recent_bfsw_axes = recent_bfsw_axes or set()
    inert_etf_axes = inert_etf_axes or set()
    noop_etf_axes = noop_etf_axes or set()
    prioritize_etfs = prioritize_etfs or set()
    cfgs = parse_all_etfs(base)
    cohorts = cohort_index(base)
    candidates: list[str] = []
    for ind in sorted(cohorts):
        for etf, _ in cohorts[ind]:
            candidates.append(etf)
    seen = set()
    candidates = [e for e in candidates if not (e in seen or seen.add(e))]
    lever, value = lever_value
    fresh = [e for e in candidates
             if e not in baked_etfs and e not in previously_probed
             and e not in inert_etfs
             and (e, lever) not in recent_bfsw_axes]
    # 2026-05-13: rotate by round to ensure later-alphabetical ETFs get tested
    # (e.g., aoa/ezu/fez/uco/voe were starved by first-15 alphabetical priority)
    if round_offset and fresh:
        start = round_offset % len(fresh)
        fresh = fresh[start:] + fresh[:start]
    # 2026-05-15: prioritize specific ETFs (e.g., cat-ETFs on safe axes for
    # cross-axis recovery — break-stuck mechanism). Maintains rotation but
    # puts prioritized ETFs at the front.
    if prioritize_etfs:
        priority = [e for e in fresh if e in prioritize_etfs]
        rest = [e for e in fresh if e not in prioritize_etfs]
        fresh = priority + rest

    val_label = str(value).replace('.', '_').replace('-', 'n')[:8]
    out: list[Probe] = []
    for etf in fresh:
        if len(out) >= max_probes:
            break
        cfg = cfgs.get(etf, {})
        if lever in cfg:
            continue
        if (etf, lever) in excluded_pairs:
            continue
        if (etf, lever) in dead_pairs:
            continue
        if (etf, lever) in inert_etf_axes:
            continue
        if (etf, lever) in noop_etf_axes:
            continue
        if (etf, lever, val_label) in noop_sigs:
            continue
        if (etf, lever, val_label) in destructive_cells:
            continue
        out.append(Probe(etf, {lever: value}, 'BFSW', lever, val_label))
    return out


def compound_risk_mgmt_probes(base: str,
                              previously_probed: set[str],
                              baked_etfs: set[str],
                              combos: list[tuple[tuple[str, float], tuple[str, float]]] | None = None,
                              max_probes: int = 18,
                              excluded_pairs: set | None = None,
                              inert_etfs: set[str] | None = None) -> list[Probe]:
    """Pass 26: probe COMPOUND risk_mgmt 2-key on un-baked, never-probed ETFs.

    Hypothesis: spxs got 2 risk_mgmt bakes (atr_sl + vol_max). kxi got
    atr_sl + dd_haircut. piz got tp + atr_sl. ETFs that respond to one
    risk_mgmt lever often respond to another. Testing 2 simultaneously
    on a fresh ETF may surface bigger lift (additive risk-mgmt layers)
    OR test 2 chances at once.

    combos: list of ((lever1, value1), (lever2, value2)) pairs.
    Targets: ETFs not in baked_etfs and not in previously_probed.
    """
    excluded_pairs = excluded_pairs or set()
    if combos is None:
        # Updated 2026-05-11: refocused around productive single-key axes
        # month_mask (4.3% pos), atr_sl=1.5 (2.4% pos), dd_haircut=0.3 (new)
        combos = [
            (('month_mask', 3583), ('atr_sl', 1.5)),
            (('month_mask', 2767), ('atr_sl', 1.5)),
            (('month_mask', 3583), ('dd_haircut', 0.3)),
            (('atr_sl', 1.5), ('dd_haircut', 0.3)),
            (('month_mask', 3583), ('dd_haircut', 0.5)),  # 0.5 for ETFs without dd_haircut
        ]
    cfgs = parse_all_etfs(base)
    cohorts = cohort_index(base)
    # Ordered by cohort, sparse-first
    candidates: list[str] = []
    for ind in sorted(cohorts):
        for etf, _ in cohorts[ind]:
            candidates.append(etf)
    seen = set()
    candidates = [e for e in candidates if not (e in seen or seen.add(e))]
    # Filter to truly fresh (also exclude inert/catastrophic per caller's set)
    inert_etfs = inert_etfs or set()
    fresh = [e for e in candidates
             if e not in baked_etfs and e not in previously_probed
             and e not in inert_etfs]

    out: list[Probe] = []
    # Round-robin: combo-outer, etf-inner
    for combo in combos:
        if len(out) >= max_probes:
            break
        (l1, v1), (l2, v2) = combo
        for etf in fresh:
            if len(out) >= max_probes:
                break
            cfg = cfgs.get(etf, {})
            if l1 in cfg or l2 in cfg:
                continue
            if (etf, l1) in excluded_pairs or (etf, l2) in excluded_pairs:
                continue
            label = f'{l1[:4]}{l2[:4]}'
            val_label = (str(v1) + 'p' + str(v2)).replace('.', '_').replace('-', 'n')[:12]
            out.append(Probe(etf, {l1: v1, l2: v2}, 'CRMX',
                             label, val_label))
    return out


def baked_untested_risk_probes(base: str,
                                baked_levers: dict[str, list[str]],
                                tested_per_etf: dict[str, set] | None = None,
                                risk_lever_values: list[tuple[str, float]] | None = None,
                                max_probes: int = 12,
                                excluded_pairs: set | None = None) -> list[Probe]:
    """Pass 25: probe each baked ETF with risk_mgmt levers it has NEVER seen.

    Pass 22 untouched-priority pushes baked ETFs to end of NEWAX pool. With
    60-probe budget mostly exhausted on fresh ETFs, baked ETFs miss probes
    on untested risk_mgmt levers. ~50 (baked_etf × untested_risk_lever)
    combos sit unprobed. Some might be productive (piz, kxi, spxs all
    had 2nd bakes on different risk_mgmt levers).

    Strategy: round-robin baked ETFs, test 1 untested risk lever each,
    bounded by max_probes. Conservative single-probe-per-ETF approach
    avoids BAKERX-style shotgun toxicity.
    """
    excluded_pairs = excluded_pairs or set()
    tested_per_etf = tested_per_etf or {}
    if risk_lever_values is None:
        risk_lever_values = [
            ('dd_haircut', 0.5), ('dd_haircut', 0.3),
            ('vol_max', 0.10), ('vol_max', 0.05),
            ('atr_sl', 2.5), ('atr_sl', 3.0),
            ('atr_p', 14), ('mom_min', 0.0),
        ]
    cfgs = parse_all_etfs(base)
    out: list[Probe] = []
    # Round-robin: cycle through baked ETFs, picking first untested risk lever
    etfs = sorted(baked_levers.keys())
    # Build per-ETF queue of untested (lever, value) pairs
    queues: dict[str, list[tuple[str, float]]] = {}
    for etf in etfs:
        baked_set = set(baked_levers[etf])
        tested_set = tested_per_etf.get(etf, set())
        skip_set = baked_set | tested_set
        cfg = cfgs.get(etf, {})
        q = []
        for lever, value in risk_lever_values:
            if lever in skip_set:
                continue
            if lever in cfg:
                continue
            if (etf, lever) in excluded_pairs:
                continue
            q.append((lever, value))
        queues[etf] = q

    # Round-robin draw
    while len(out) < max_probes:
        any_added = False
        for etf in etfs:
            if len(out) >= max_probes:
                break
            if not queues[etf]:
                continue
            lever, value = queues[etf].pop(0)
            val_label = str(value).replace('.', '_').replace('-', 'n')[:8]
            out.append(Probe(etf, {lever: value}, 'BURX',
                             lever, val_label))
            any_added = True
        if not any_added:
            break
    return out


def baked_risk_mgmt_probes(base: str,
                           baked_levers: dict[str, list[str]],
                           risk_levers: list[tuple[str, float, int]] | None = None,
                           max_probes: int = 30) -> list[Probe]:
    """Pass 16: probe each baked ETF with each risk_mgmt lever × value combo.

    Validated by piz + atr_sl=2.5 = +0.00167 (BAKE-166). Risk-mgmt levers
    add safety layers without changing trade gating, so they compose with
    existing tuning. Each baked ETF gets a chance at every (lever, value).
    """
    if risk_levers is None:
        risk_levers = [
            ('atr_sl', 2.5, None), ('atr_sl', 1.5, None),
            ('atr_sl', 3.0, None), ('atr_sl', 2.0, None),
            ('vol_max', 0.10, None), ('vol_max', 0.05, None),
            ('dd_haircut', 0.5, None), ('dd_haircut', 0.3, None),
        ]
    cfgs = parse_all_etfs(base)
    out: list[Probe] = []
    # Round-robin: outer loop is lever, inner is etf — distributes coverage
    for lever, value, _ in risk_levers:
        if len(out) >= max_probes:
            break
        for etf in sorted(baked_levers):
            if len(out) >= max_probes:
                break
            cfg = cfgs.get(etf, {})
            if lever in cfg:
                continue
            already = set(baked_levers[etf])
            if lever in already:
                continue
            val_label = str(value).replace('.', '_')[:8]
            out.append(Probe(etf, {lever: value}, 'BAKERX',
                             lever[:8], val_label))
    return out


def bake_stack_probes(base: str,
                      baked_levers: dict[str, list[str]],
                      stack_axes: Sequence[str] = (
                          'sl_add', 'ef_norm', 'xf_norm', 'cf_norm',
                          'sp_shrink', 'e_widen', 'x_tighten', 'wt_lower',
                      ),
                      max_probes: int = 24,
                      max_per_etf: int = 3,
                      value_idx: int = 0) -> list[Probe]:
    """Probe already-baked ETFs on UNTOUCHED levers.

    After single-lever bakes saturate (e.g., 9 tp bakes), additional lift may
    live in compound mutations on the same ETF. For each baked ETF, try axes
    NOT in baked_levers[etf]. Returns probes ready for queue.

    baked_levers: {etf: [lever_already_baked, ...]} e.g. {'ewg': ['tp']}
    """
    cfgs = parse_all_etfs(base)
    out: list[Probe] = []
    etfs = sorted(baked_levers)
    per_etf_count: dict[str, int] = {}
    # Round-robin across (axis, etf), cap at max_per_etf so dense-config ETFs
    # don't monopolize the budget at the expense of sparse-config ETFs.
    for ax_name in stack_axes:
        ax = AXES.get(ax_name)
        if ax is None:
            continue
        for etf in etfs:
            if len(out) >= max_probes:
                return out
            if per_etf_count.get(etf, 0) >= max_per_etf:
                continue
            if etf not in cfgs:
                continue
            cfg = cfgs[etf]
            already = set(baked_levers[etf])
            if ax.key in already:
                continue
            cur = _f(cfg, ax.key)
            if ax.mode == 'add' and ax.key in cfg:
                continue
            if ax.mode == 'value' and cur is None:
                continue
            vname, new = ax.apply(cur, value_idx)
            if new is None:
                continue
            if not _safe_for_etf(etf, cfg, ax.key, new):
                continue
            out.append(Probe(etf, {ax.key: new}, 'STACK', ax_name, vname))
            per_etf_count[etf] = per_etf_count.get(etf, 0) + 1
    return out


def borderline_reverify_probes(base: str,
                               borderline_pairs: set[tuple[str, str]],
                               max_probes: int = 16) -> list[Probe]:
    """Re-probe (etf, lever) pairs whose lift was 0.0001–0.001 at adjacent
    value_idx (1 and 2) to push them out of the borderline zone."""
    cfgs = parse_all_etfs(base)
    out: list[Probe] = []
    # Map lever name → axis names that mutate that lever
    lever_to_axes: dict[str, list[str]] = {}
    for ax_name, ax in AXES.items():
        lever_to_axes.setdefault(ax.key, []).append(ax_name)
    for etf, lever in sorted(borderline_pairs):
        if len(out) >= max_probes:
            break
        if etf not in cfgs:
            continue
        cur = _f(cfgs[etf], lever)
        for ax_name in lever_to_axes.get(lever, []):
            if len(out) >= max_probes:
                break
            ax = AXES[ax_name]
            for vi in (1, 2):
                if len(out) >= max_probes:
                    break
                if vi >= len(ax.values):
                    continue
                if ax.mode == 'add' and lever in cfgs[etf]:
                    continue
                if ax.mode == 'value' and cur is None:
                    continue
                vname, new = ax.apply(cur, vi)
                if new is None:
                    continue
                out.append(Probe(etf, {lever: new}, 'BORD', ax_name, vname))
    return out


def compound_2key_probes(round_num: int, base: str,
                         etf_per_cohort: int = 1) -> list[Probe]:
    """Compound 2-key: sl=0.025 + tp 60% on no-sl ETFs with tp>0.10."""
    cohorts = cohort_index(base)
    cfgs = parse_all_etfs(base)
    rotation = round_num // 8
    out: list[Probe] = []
    for ind in sorted(cohorts):
        cohort = cohorts[ind]
        for k in range(etf_per_cohort):
            etf, _ = cohort[(rotation + k) % len(cohort)]
            cfg = cfgs.get(etf, {})
            if 'sl' in cfg:
                continue
            cur_tp = _f(cfg, 'tp')
            if cur_tp is None or cur_tp <= 0.10:
                continue
            new_tp = round(cur_tp * 0.6, 3)
            out.append(Probe(etf, {'sl': 0.025, 'tp': new_tp},
                             'C2D', 'C2_sl25tp60', '60pct'))
    return out


# Compound 2-key combinations beyond the original sl+tp shrink. Each entry:
# (label, predicate(cfg)→bool, mutation(cfg)→dict|None).
# Predicate gates which ETFs the combo applies to.
def _c2_tp_ef_shrink(cfg):
    """tp×0.6 + ef→0.95 (push exit weaker, take profits sooner)."""
    cur_tp = _f(cfg, 'tp')
    cur_ef = _f(cfg, 'ef')
    if cur_tp is None or cur_tp <= 0.05:
        return None
    if cur_ef is None or abs(cur_ef - 0.95) < 0.02:
        return None
    return {'tp': round(cur_tp * 0.6, 3), 'ef': 0.95}


def _c2_tp_grow_xf(cfg):
    """tp×1.5 + xf→1.05. Skip if xf change >20% (matches the wt-drop
    cautionary lesson from R2522)."""
    cur_tp = _f(cfg, 'tp')
    cur_xf = _f(cfg, 'xf')
    if cur_tp is None or cur_tp >= 0.15:
        return None
    if cur_xf is None or abs(cur_xf - 1.05) < 0.03:
        return None
    if abs(cur_xf - 1.05) / max(cur_xf, 0.01) > 0.20:
        return None
    return {'tp': round(cur_tp * 1.5, 3), 'xf': 1.05}


def _c2_wt_lower_tp_shrink(cfg):
    """wt→0.045 + tp×0.6 (only mild wt drops; large drops were catastrophic
    in R2522/R2523 — xlu -0.475, sso -0.263). Restricted to ETFs with wt
    already near 0.045 so change is ≤25%."""
    cur_wt = _f(cfg, 'wt')
    cur_tp = _f(cfg, 'tp')
    if cur_wt is None or not (0.040 <= cur_wt <= 0.055):
        return None
    if cur_tp is None or cur_tp <= 0.05:
        return None
    return {'wt': 0.045, 'tp': round(cur_tp * 0.6, 3)}


def _c2_sl_add_ef_norm(cfg):
    """sl=0.025 added (where absent) + ef→0.95."""
    if 'sl' in cfg:
        return None
    cur_ef = _f(cfg, 'ef')
    if cur_ef is None or abs(cur_ef - 0.95) < 0.02:
        return None
    return {'sl': 0.025, 'ef': 0.95}


C2_COMBOS = [
    ('C2tpef', _c2_tp_ef_shrink),
    ('C2tpxf', _c2_tp_grow_xf),
    ('C2wttp', _c2_wt_lower_tp_shrink),
    ('C2slef', _c2_sl_add_ef_norm),
]


def compound_2key_probes_v2(round_num: int, base: str,
                            etf_per_cohort: int = 1,
                            combos: list = C2_COMBOS,
                            excluded_pairs: set | None = None) -> list[Probe]:
    """Broader compound 2-key: rotate through multiple combinations
    (tp+ef shrink, tp+xf grow, wt+tp, sl+ef) — one combo per round_num group.

    Skips ETFs where ANY component lever is in excluded_pairs (dead/toxic).
    Compound combos amplify single-lever toxicity — if (etf, wt) is toxic,
    a wt+tp combo will be even more toxic.
    """
    excluded_pairs = excluded_pairs or set()
    cohorts = cohort_index(base)
    cfgs = parse_all_etfs(base)
    combo_idx = (round_num // 4) % len(combos)
    label, mut_fn = combos[combo_idx]
    rotation = round_num // 8
    out: list[Probe] = []
    for ind in sorted(cohorts):
        cohort = cohorts[ind]
        for k in range(etf_per_cohort):
            etf, _ = cohort[(rotation + k) % len(cohort)]
            cfg = cfgs.get(etf, {})
            changes = mut_fn(cfg)
            if changes is None:
                continue
            # Skip if any component lever is excluded
            if any((etf, lever) in excluded_pairs for lever in changes):
                continue
            out.append(Probe(etf, changes, 'C2D', label, 'mix'))
    return out


# ─── DB helpers ────────────────────────────────────────────────────────────
def db_dead_etf_axis_pairs(min_salts: int = 6,
                           eps: float = 0.0001,
                           recent_window: int = 20) -> set[tuple[str, str]]:
    """Returns set of (etf, axis) pairs where ALL historical samples on that
    pair (across all values of the axis) produced exact NOOP across ≥min_salts.

    2026-05-14: recency-windowed (default 50 rounds). Base evolves with each
    bake; pairs that were inert pre-bake may respond to new exits/regimes.
    Was unwindowed, contributed to R2993 459-skip over-blocking.

    Audit 2026-05-09: R2582 90.7% waste was driven by such patterns —
    pwb/ivw/agg/blv/biv etc. each had multiple values of dd_haircut tested
    after the first value confirmed NOOP.
    """
    import re, collections
    db = storage.connect(DB_PATH)
    noop_per_batch: dict[str, float] = {}
    for b, v in db.execute(
            "SELECT batch, AVG(car_mdd) FROM experiments "
            "WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL GROUP BY batch"
            ).fetchall():
        if v is not None:
            noop_per_batch[b] = v
    max_round = 0
    for (b,) in db.execute("SELECT DISTINCT batch FROM experiments WHERE batch LIKE 'gen_afql3b_div%'").fetchall():
        m_b = re.search(r'div(\d+)', b)
        if m_b:
            max_round = max(max_round, int(m_b.group(1)))
    cutoff_round = max_round - recent_window if max_round > 0 else 0
    # 2026-05-16: added UTNT/UTNTW/BTI/WTX/STX/CFX/SFX/NEWLEV
    name_re = re.compile(
        r's002_(?:NEWAX|LEVAX|BAKERX|COLD|DIV|DV2|DV3|BORD|VRFY|STACK|FILL|'
        r'C2D|AT|RT|BFSW|SHRTAX|BURX|CRMX|UTNT|UTNTW|BTI|WTX|STX|CFX|SFX|NEWLEV)_'
        r'([a-z]{2,5})_(.+?)_rv\d+_')
    by_pair: dict[tuple, list[float]] = collections.defaultdict(list)
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE car_mdd IS NOT NULL AND name LIKE 's002_%' "
            "AND name NOT LIKE '%NOOP%'").fetchall():
        m = name_re.match(name)
        if not m:
            continue
        m_b = re.search(r'div(\d+)', batch)
        if not m_b: continue
        if int(m_b.group(1)) < cutoff_round: continue
        noop = noop_per_batch.get(batch)
        if noop is None:
            continue
        etf, lever_value = m.group(1), m.group(2)
        # Strip trailing _<value> tokens to recover axis.
        # Heuristic: strip up to 2 trailing tokens that are short or numeric.
        parts = lever_value.split('_')
        # axis = all but last 1-2 tokens (heuristic — matches sig parsing)
        if len(parts) >= 2:
            axis = '_'.join(parts[:-1])
        else:
            axis = lever_value
        by_pair[(etf, axis)].append(cm - noop)
    db.close()
    out = set()
    for pair, lifts in by_pair.items():
        if len(lifts) >= min_salts and max(abs(l) for l in lifts) < eps:
            out.add(pair)
    return out


def db_inert_etfs(min_probes_strict: int = 30, min_noop_frac: float = 0.75,
                  min_probes_loose: int = 35,
                  pos_threshold: float = 0.0007) -> set[str]:
    """Returns set of ETFs that are structurally inert. Two qualifying paths:
       - STRICT: ≥min_probes_strict probes AND ≥min_noop_frac exact-NOOP AND 0 pos
       - LOOSE:  ≥min_probes_loose probes AND 0 pos (regardless of NOOP frac)

    The loose path catches "responsive but never-positive" ETFs (e.g. ijh:
    32 probes, 0 positives, 53% NOOP — strict threshold misses it). The
    "0 positives across ≥20 trials" criterion is sufficient evidence of
    no-positive-EV class regardless of negative variance.

    Such ETFs absorb compute without producing signal. Blacklist them
    entirely from NEWAX/COLD/BFSW.
    """
    import re, collections
    db = storage.connect(DB_PATH)
    noop_per_batch: dict[str, float] = {}
    for b, v in db.execute(
            "SELECT batch, AVG(car_mdd) FROM experiments "
            "WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL GROUP BY batch"
            ).fetchall():
        if v is not None:
            noop_per_batch[b] = v
    # 2026-05-14: REMOVED UTNT|UTNTW|BTI from regex (was added 2026-05-14 then reverted).
    # Including them caused db_inert_etfs to flag 219 ETFs as inert, killing UTNT pool
    # (down from 70+ to 7). UTNT block has its own db_utnt_inert_etfs for filter logic.
    name_re = re.compile(
        r's002_(?:NEWAX|LEVAX|BAKERX|COLD|DIV|DV2|DV3|BORD|VRFY|STACK|FILL|'
        r'C2D|AT|RT|BFSW|SHRTAX|BURX|CRMX|LV|ASP|EH|HV)_'
        r'([a-z]{2,5})_')
    stats: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0, 0])
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE car_mdd IS NOT NULL AND name LIKE 's002_%' "
            "AND name NOT LIKE '%NOOP%'").fetchall():
        m = name_re.match(name)
        if not m:
            continue
        noop = noop_per_batch.get(batch)
        if noop is None:
            continue
        s = stats[m.group(1)]
        s[0] += 1
        if abs(cm - noop) < 0.0001:
            s[1] += 1
        if cm - noop > pos_threshold:
            s[2] += 1
    db.close()
    out: set[str] = set()
    for etf, (n, noop, pos) in stats.items():
        if pos > 0:
            continue
        # STRICT: high NOOP frac at the ≥30-probe threshold
        if n >= min_probes_strict and noop / n >= min_noop_frac:
            out.add(etf)
        # LOOSE: many trials, no positives — "no-EV" class
        elif n >= min_probes_loose:
            out.add(etf)
    return out


def db_utnt_inert_etfs(min_probes: int = 6,
                       pos_threshold: float = 0.0005,
                       neg_threshold: float = -0.0005,
                       min_neg_for_destructive: int = 3) -> set[str]:
    """ETFs disqualified from UTNT block. Two paths:
       1. INERT: ≥min_probes with 0 above-thresh
       2. DESTRUCTIVE: ≥min_neg_for_destructive specs below neg_threshold

    Path 2 added 2026-05-10: dfj/cwi were producing catastrophic NEG
    (-0.23) but had been tested too few times to qualify as inert.
    Pre-emptive filter on ETFs with multi-spec destructive signal.
    """
    import re, collections
    db = storage.connect(DB_PATH)
    noop_per_batch: dict[str, float] = {}
    for b, v in db.execute(
            "SELECT batch, AVG(car_mdd) FROM experiments "
            "WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL GROUP BY batch"
            ).fetchall():
        if v is not None:
            noop_per_batch[b] = v
    name_re = re.compile(r's002_UTNT_([a-z]{2,5})_')
    stats: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0, 0])
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE car_mdd IS NOT NULL AND name LIKE 's002_UTNT_%'").fetchall():
        m = name_re.match(name)
        if not m:
            continue
        noop = noop_per_batch.get(batch)
        if noop is None:
            continue
        s = stats[m.group(1)]
        s[0] += 1
        if cm - noop > pos_threshold:
            s[1] += 1
        if cm - noop < neg_threshold:
            s[2] += 1
    # Catastrophic-spec tracking (lift < -0.05) — disqualifies even if past pos
    catastrophic: set[str] = set()
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE car_mdd IS NOT NULL AND name LIKE 's002_UTNT_%'").fetchall():
        m = name_re.match(name)
        if not m: continue
        noop = noop_per_batch.get(batch)
        if noop is None: continue
        if cm - noop < -0.05:
            catastrophic.add(m.group(1))
    db.close()
    out: set[str] = set()
    for etf, (n, pos, neg) in stats.items():
        if n >= min_probes and pos == 0:
            out.add(etf)  # INERT
        elif neg >= min_neg_for_destructive and pos == 0:
            out.add(etf)  # DESTRUCTIVE (no past pos)
        elif etf in catastrophic and neg >= min_neg_for_destructive:
            out.add(etf)  # DESTRUCTIVE (catastrophic at extreme mags)
    return out


def db_lever_inert_etf_axes(min_specs: int = 4,
                             min_zero_frac: float = 0.65,
                             recent_window: int = 1000) -> set[tuple[str, str]]:
    """Returns (etf, axis_class) pairs where the lever appears inert: ≥min_specs
    historical samples with ≥min_zero_frac exact-NOOP and ZERO positive lifts.

    Stronger than db_behavioral_noop_etf_axes (which requires 2 distinct values):
    if a single value of an (etf, axis_class) is mostly-NOOP across ≥4 historical
    samples AND no salt ever produced a positive lift, the axis is effectively
    inert for this ETF — keep iterating means burning compute on a deterministic-
    zero outcome.

    Use case: fvd × tp had 61 historical specs, 57 exact-zero, 0 positive.
    BTI was about to queue 4 more. Pure waste.
    """
    import re, collections
    db = storage.connect(DB_PATH)
    noop_per_batch: dict[str, float] = {}
    for b, v in db.execute(
            "SELECT batch, AVG(car_mdd) FROM experiments "
            "WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL GROUP BY batch"
            ).fetchall():
        if v is not None: noop_per_batch[b] = v
    max_round = 0
    for (b,) in db.execute("SELECT DISTINCT batch FROM experiments WHERE batch LIKE 'gen_afql3b_div%'").fetchall():
        m_b = re.search(r'div(\d+)', b)
        if m_b: max_round = max(max_round, int(m_b.group(1)))
    cutoff_round = max_round - recent_window if max_round > 0 else 0
    name_re = re.compile(
        r's002_(?:BFSW|UTNT|UTNTW|BTI|WTX|CFX|STX|SFX|BORD|NEWAX|LEVAX|COLD|DIV|CRMX)_'
        r'([a-z]{2,5})_(.+?)_rv\d+_')

    def axis_class(raw: str) -> str:
        for p in ('tp_grow_','tp_shrink_','tp_'):
            if raw.startswith(p): return 'tp'
        for p in ('sl_grow_','sl_shrink_','sl_'):
            if raw.startswith(p): return 'sl'
        for p in ('wt_grow_','wt_shrink_','wt_'):
            if raw.startswith(p): return 'wt'
        for p in ('cf_grow_','cf_shrink_','cf_'):
            if raw.startswith(p): return 'cf'
        for p in ('sf_grow_','sf_shrink_','sf_'):
            if raw.startswith(p): return 'sf'
        if raw.startswith('atr_sl'): return 'atr_sl'
        if raw.startswith('month_mask'): return 'month_mask'
        if raw.startswith('dd_haircut'): return 'dd_haircut'
        return raw.rsplit('_',1)[0]

    by_pair: dict[tuple[str,str], list[float]] = collections.defaultdict(list)
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE car_mdd IS NOT NULL AND name LIKE 's002_%' AND name NOT LIKE '%NOOP%'"
            ).fetchall():
        m = name_re.match(name)
        if not m: continue
        m_b = re.search(r'div(\d+)', batch)
        if not m_b: continue
        if int(m_b.group(1)) < cutoff_round: continue
        noop = noop_per_batch.get(batch)
        if noop is None: continue
        etf, raw = m.group(1), m.group(2)
        ac = axis_class(raw)
        by_pair[(etf, ac)].append(cm - noop)

    out = set()
    # 2026-05-15 (post-cleanup): broadened silent_eps from 0.0001 to 0.001 to
    # handle NOOP salt drift. When 1 of 4 NOOP salts produces a trade-win
    # (+0.00262), NOOP_avg drifts to 9.98566 and silent probes show lift=-0.00065
    # — looks destructive but is actually behavioral-NOOP. The tight 0.0001 band
    # missed these. Real signals (lift ≥ +0.001) still excluded from zero count.
    for pair, deltas in by_pair.items():
        if len(deltas) < min_specs: continue
        n_zero = sum(1 for d in deltas if abs(d) < 0.001)
        n_pos = sum(1 for d in deltas if d > 0.001)
        zero_frac = n_zero / len(deltas)
        if zero_frac >= min_zero_frac and n_pos == 0:
            out.add(pair)
    db.close()
    return out


def db_recent_failed_vrfy_etf_levers(n_rounds: int = 8,
                                      max_lift: float = 0.0002) -> set[tuple[str, str]]:
    """Returns (etf, lever_class) pairs whose VRFY failed in last N rounds.

    2026-05-17 architecture gap fix: _failed_vrfy_keys only blocks the
    VRFY queue. Discovery blocks (NEWLEV/BTI/UTNT/BFSW/WTX/STX/CFX/SFX)
    don't consult it. Example: dem cd VRFY failed in R3385 (-0.00024 ×
    4), but R3387 NEWLEV re-queued dem cd_grow_1 because NEWLEV block
    didn't see the failure.

    Returns axis_class (tp/sl/wt/cf/cd/etc) not specific value, since
    failed VRFY at one value usually indicates the lever is unproductive
    for that ETF.

    Drift-aware: skips drift rounds (NOOP within-round range > 0.005
    OR cross-round NOOP delta > 0.005).
    """
    import re, collections
    db = storage.connect(DB_PATH)
    # Detect drift batches
    drift_batches: set[str] = set()
    for b, mn, mx, n_ in db.execute(
            "SELECT batch, MIN(car_mdd), MAX(car_mdd), COUNT(*) FROM experiments "
            "WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL GROUP BY batch"
            ).fetchall():
        if n_ is not None and n_ >= 2 and mx - mn > 0.005:
            drift_batches.add(b)
    _batch_noop: dict[str, float] = {b: v for b, v in db.execute(
        "SELECT batch, AVG(car_mdd) FROM experiments WHERE name LIKE '%NOOP%' "
        "AND car_mdd IS NOT NULL GROUP BY batch").fetchall()}
    _sorted = sorted(_batch_noop.keys())
    for i, b in enumerate(_sorted):
        if b in drift_batches: continue
        prior = [_batch_noop[_sorted[j]] for j in range(max(0, i-3), i)]
        if prior and abs(_batch_noop[b] - sum(prior)/len(prior)) > 0.005:
            drift_batches.add(b)
    # Find max round_num
    max_round = 0
    for (b,) in db.execute(
            "SELECT DISTINCT batch FROM experiments WHERE batch LIKE 'gen_afql3b_div%'"
            ).fetchall():
        m_b = re.search(r'div(\d+)', b)
        if m_b: max_round = max(max_round, int(m_b.group(1)))
    cutoff = max_round - n_rounds if max_round > 0 else 0
    out: set[tuple[str, str]] = set()
    vrfy_re = re.compile(r's002_VRFY_([a-z0-9]+)_([a-z]+)([0-9_]*)_verify')
    # 2026-05-17 fix: group by (base + batch) so each VRFY ROUND is evaluated
    # independently. Previously aggregated R3387 vbr (1 lift, avg +0.0073) +
    # R3388 vbr (0 lifts, avg 0) → combined avg +0.0037 > 0.0002 = passed filter.
    # But R3388 alone was clearly failed. Per-batch check correctly captures.
    vrfy_groups: dict[tuple, list[float]] = collections.defaultdict(list)
    vrfy_meta: dict[tuple, tuple[str, str, str]] = {}
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE name LIKE 's002_VRFY_%' AND car_mdd IS NOT NULL"
            ).fetchall():
        if batch in drift_batches: continue
        m_b = re.search(r'div(\d+)', batch)
        if not m_b: continue
        if int(m_b.group(1)) < cutoff: continue
        m = vrfy_re.match(name)
        if not m: continue
        etf, lever_prefix, val = m.group(1), m.group(2), m.group(3)
        noop = _batch_noop.get(batch)
        if noop is None: continue
        base = name[:name.index('_rv')] if '_rv' in name else name
        key = (base, batch)  # per-batch grouping
        vrfy_groups[key].append(cm - noop)
        vrfy_meta[key] = (etf, lever_prefix, batch)
    for key, deltas in vrfy_groups.items():
        if len(deltas) < 3: continue
        avg = sum(deltas) / len(deltas)
        if avg < max_lift:
            etf, lever, _ = vrfy_meta[key]
            out.add((etf, lever))
    db.close()
    return out


def db_destructive_etf_axes(min_neg_specs: int = 3,
                             neg_avg_threshold: float = -0.0003,
                             recent_window: int = 200) -> set[tuple[str, str]]:
    """Returns (etf, axis_class) pairs where the AGGREGATE history of all
    values within the same axis_class shows net-destructive performance:
    avg lift ≤ neg_avg_threshold across ≥min_neg_specs total NEG specs.

    Stronger evidence than per-value db_destructive_cells: rgi × tp had 59
    historical probes with avg -0.0377, but spread across 8+ distinct tp
    values so no SINGLE (rgi, tp_grow, 105pct) triplet had ≥3 NEG. Aggregate
    catches the broader signal.

    Use case: prevent BTI/STX/WTX/CFX from iterating around a bake on an
    axis that's net-destructive even though the original bake was productive.
    Once a productive value exists in base, iterating ±5% should also be
    productive; if aggregate history says no, skip.
    """
    import re, collections
    db = storage.connect(DB_PATH)
    noop_per_batch: dict[str, float] = {}
    for b, v in db.execute(
            "SELECT batch, AVG(car_mdd) FROM experiments "
            "WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL GROUP BY batch"
            ).fetchall():
        if v is not None:
            noop_per_batch[b] = v
    max_round = 0
    for (b,) in db.execute("SELECT DISTINCT batch FROM experiments WHERE batch LIKE 'gen_afql3b_div%'").fetchall():
        m_b = re.search(r'div(\d+)', b)
        if m_b:
            max_round = max(max_round, int(m_b.group(1)))
    cutoff_round = max_round - recent_window if max_round > 0 else 0
    name_re = re.compile(
        r's002_(?:BFSW|UTNT|UTNTW|BTI|WTX|CFX|STX|SFX|BORD|NEWAX|LEVAX|COLD|DIV|CRMX)_'
        r'([a-z]{2,5})_(.+?)_rv\d+_')

    def axis_class(raw: str) -> str:
        for p in ('tp_grow_','tp_shrink_','tp_'):
            if raw.startswith(p): return 'tp'
        for p in ('sl_grow_','sl_shrink_','sl_'):
            if raw.startswith(p): return 'sl'
        for p in ('wt_grow_','wt_shrink_','wt_'):
            if raw.startswith(p): return 'wt'
        for p in ('cf_grow_','cf_shrink_','cf_'):
            if raw.startswith(p): return 'cf'
        for p in ('sf_grow_','sf_shrink_','sf_'):
            if raw.startswith(p): return 'sf'
        if raw.startswith('atr_sl'): return 'atr_sl'
        if raw.startswith('month_mask'): return 'month_mask'
        if raw.startswith('dd_haircut'): return 'dd_haircut'
        return raw.rsplit('_',1)[0]

    by_pair: dict[tuple[str,str], list[float]] = collections.defaultdict(list)
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE car_mdd IS NOT NULL AND name LIKE 's002_%' AND name NOT LIKE '%NOOP%'"
            ).fetchall():
        m = name_re.match(name)
        if not m: continue
        m_b = re.search(r'div(\d+)', batch)
        if not m_b: continue
        if int(m_b.group(1)) < cutoff_round: continue
        noop = noop_per_batch.get(batch)
        if noop is None: continue
        etf, raw = m.group(1), m.group(2)
        ac = axis_class(raw)
        by_pair[(etf, ac)].append(cm - noop)

    out = set()
    for pair, deltas in by_pair.items():
        n_neg = sum(1 for d in deltas if d < neg_avg_threshold)
        avg = sum(deltas) / len(deltas) if deltas else 0
        if n_neg >= min_neg_specs and avg <= neg_avg_threshold:
            out.add(pair)
        # 2026-05-17 R3477 30m fix: also qualify on ANY catastrophic spec
        # (lift < -0.05). Single-spec catastrophic = clear ETF/axis
        # incompatibility, shouldn't wait for 3 NEG specs. Examples: cwi
        # sl_grow_110pct -0.248 × 1 (R3463), cwi um_grow_105pct -0.240 × 1
        # (R3463), ewd wt_grow_105pct -0.240 × 2 (R3476) all bypass the
        # standard 3-spec threshold.
        elif any(d < -0.05 for d in deltas):
            out.add(pair)
    db.close()
    return out


def db_behavioral_noop_etf_axes(min_distinct_vals: int = 2,
                                 min_salts_per_val: int = 2,
                                 eps: float = 0.0001,
                                 recent_window: int = 20) -> set[tuple[str, str]]:
    """Return (etf, axis_class) pairs where ≥min_distinct_vals different values
    of the SAME axis class were all behavioral-NOOP across ≥min_salts_per_val
    salts each. Stronger evidence of axis-inertness than single-value banning.

    Axis class is the lever family (tp, sl, wt, cf, sf, ef, xf, atr_sl, month_mask,
    dd_haircut). Direction suffixes (grow_/shrink_) are stripped.

    Use case: ewm with tp_grow_110 + tp_shrink_95 BOTH all-zero across 3 salts each
    → (ewm, tp) banned axis-wide; tp_grow_120 next round won't be queued.

    Audit R3066: BFSW/BTI/STX produced 19/19 behavioral-NOOPs (100% waste).
    Single-value filter is too granular — by the time it catches one value the
    same ETF×axis cycles to a different value and wastes another round.
    """
    import re
    db = storage.connect(DB_PATH)
    noop_per_batch: dict[str, float] = {}
    for b, v in db.execute(
            "SELECT batch, AVG(car_mdd) FROM experiments "
            "WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL GROUP BY batch"
            ).fetchall():
        if v is not None:
            noop_per_batch[b] = v
    max_round = 0
    for (b,) in db.execute("SELECT DISTINCT batch FROM experiments WHERE batch LIKE 'gen_afql3b_div%'").fetchall():
        m_b = re.search(r'div(\d+)', b)
        if m_b:
            max_round = max(max_round, int(m_b.group(1)))
    cutoff_round = max_round - recent_window if max_round > 0 else 0
    name_re = re.compile(
        r's002_(?:BFSW|UTNT|UTNTW|BTI|WTX|CFX|STX|SFX|BORD|NEWAX|LEVAX|COLD|DIV|CRMX)_'
        r'([a-z]{2,5})_(.+?)_rv\d+_')
    # Map raw axis prefix → canonical axis class
    def axis_class(raw: str) -> str:
        for prefix in ('tp_grow_', 'tp_shrink_', 'tp_'):
            if raw.startswith(prefix): return 'tp'
        for prefix in ('sl_grow_', 'sl_shrink_', 'sl_'):
            if raw.startswith(prefix): return 'sl'
        for prefix in ('wt_grow_', 'wt_shrink_', 'wt_'):
            if raw.startswith(prefix): return 'wt'
        for prefix in ('cf_grow_', 'cf_shrink_', 'cf_'):
            if raw.startswith(prefix): return 'cf'
        for prefix in ('sf_grow_', 'sf_shrink_', 'sf_'):
            if raw.startswith(prefix): return 'sf'
        for prefix in ('ef_grow_', 'ef_shrink_', 'ef_'):
            if raw.startswith(prefix): return 'ef'
        for prefix in ('xf_grow_', 'xf_shrink_', 'xf_'):
            if raw.startswith(prefix): return 'xf'
        if raw.startswith('atr_sl'): return 'atr_sl'
        if raw.startswith('month_mask'): return 'month_mask'
        if raw.startswith('dd_haircut'): return 'dd_haircut'
        if raw.startswith('vol_max'): return 'vol_max'
        # fallback: strip trailing _Nval
        return raw.rsplit('_', 1)[0]

    # (etf, axis_class, full_val_string) → list of deltas
    by_etf_axis_val: dict[tuple[str,str,str], list[float]] = {}
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE car_mdd IS NOT NULL AND name LIKE 's002_%' AND name NOT LIKE '%NOOP%'"
            ).fetchall():
        m = name_re.match(name)
        if not m: continue
        m_b = re.search(r'div(\d+)', batch)
        if not m_b: continue
        if int(m_b.group(1)) < cutoff_round: continue
        etf, raw = m.group(1), m.group(2)
        ac = axis_class(raw)
        noop = noop_per_batch.get(batch)
        if noop is None: continue
        by_etf_axis_val.setdefault((etf, ac, raw), []).append(cm - noop)

    # Aggregate per (etf, axis_class): which distinct vals are NOOP?
    noop_vals_per_pair: dict[tuple[str,str], set[str]] = {}
    for (etf, ac, raw), deltas in by_etf_axis_val.items():
        if len(deltas) < min_salts_per_val: continue
        if max(abs(d) for d in deltas) < eps:
            noop_vals_per_pair.setdefault((etf, ac), set()).add(raw)

    out = {pair for pair, vals in noop_vals_per_pair.items()
           if len(vals) >= min_distinct_vals}
    db.close()
    return out


def db_behavioral_noop_signatures(min_salts: int = 3,
                                  eps: float = 0.0001,
                                  recent_window: int = 30) -> set[tuple[str, str, str]]:
    """Returns set of (etf, axis_name, val_label) signatures where ≥min_salts
    historical samples ALL matched their batch's NOOP exactly.

    This is the most general waste-prevention filter: any probe (regardless
    of KIND — NEWAX/COLD/BFSW/SHRTAX/etc.) whose (etf, axis, val) has been
    confirmed inert across multiple salts is a behavioral no-op and must
    not be re-queued.

    Audit (R2566+): 75-95% of queued specs were producing exact NOOP.
    Probable causes: indicator-gated levers on ETFs whose indicator never
    fires, value changes that don't cross any decision boundary, etc.
    """
    import re
    db = storage.connect(DB_PATH)
    # Cache NOOP per batch.
    noop_per_batch: dict[str, float] = {}
    for b, v in db.execute(
            "SELECT batch, AVG(car_mdd) FROM experiments "
            "WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL GROUP BY batch"
            ).fetchall():
        if v is not None:
            noop_per_batch[b] = v
    # 2026-05-13 CRITICAL FIX: previously excluded UTNT|UTNTW|BTI from regex,
    # so 85-90% of those blocks' exact-NOOP results never populated this filter.
    # User hard-constraint: every spec must be MEANINGFUL — exact-NOOP is waste.
    # 2026-05-13 recency-window: bake events evolve the base; old NOOP-equiv may
    # no longer apply. Only include sigs from last `recent_window` rounds.
    max_round = 0
    for (b,) in db.execute("SELECT DISTINCT batch FROM experiments WHERE batch LIKE 'gen_afql3b_div%'").fetchall():
        m_b = re.search(r'div(\d+)', b)
        if m_b:
            max_round = max(max_round, int(m_b.group(1)))
    cutoff_round = max_round - recent_window if max_round > 0 else 0
    name_re = re.compile(
        r's002_(?:NEWAX|LEVAX|BAKERX|COLD|DIV|DV2|DV3|BORD|VRFY|STACK|FILL|'
        r'C2D|AT|RT|BFSW|SHRTAX|BURX|CRMX|UTNT|UTNTW|BTI|WTX|STX|CFX|SFX|NEWLEV)_'
        r'([a-z]{2,5})_(.+?)_rv\d+_')
    by_sig: dict[tuple, list[float]] = {}
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE car_mdd IS NOT NULL AND name LIKE 's002_%'").fetchall():
        m = name_re.match(name)
        if not m:
            continue
        m_b = re.search(r'div(\d+)', batch)
        if not m_b: continue
        if int(m_b.group(1)) < cutoff_round: continue
        etf, lever_value = m.group(1), m.group(2)
        noop = noop_per_batch.get(batch)
        if noop is None:
            continue
        axis_name, val_label = _split_lever_value(lever_value)
        by_sig.setdefault((etf, axis_name, val_label), []).append(cm - noop)
    db.close()
    out = set()
    for sig, lifts in by_sig.items():
        if len(lifts) >= min_salts and max(abs(l) for l in lifts) < eps:
            out.add(sig)
    return out


def productive_axis_probes(base: str, productive_pairs: set[tuple[str, str]],
                            value_indices: tuple[int, ...] = (0, 1, 2),
                            exclude: set[str] | None = None,
                            noop_sigs: set | None = None,
                            destructive_cells: set | None = None,
                            catastrophic_cells: set | None = None) -> list[Probe]:
    """Generate probes by iterating historically-productive (etf, axis_name)
    pairs directly. Each pair × multiple value_idx = many candidates per pair.

    More efficient than cohort-rotation axis_probes() at saturation: ensures
    every spec targets a known-responsive (etf, axis) cell.

    2026-05-10: added per user directive — must 128 meaningful specs/round.
    2026-05-18: filter against noop_sigs/destructive/catastrophic so re-tests
    of already-known dead cells are skipped (R3618 audit: PROD 22 specs / 20
    rounds = 100% silent because filters not consulted).
    """
    exclude = exclude or set()
    noop_sigs = noop_sigs or set()
    destructive_cells = destructive_cells or set()
    catastrophic_cells = catastrophic_cells or set()
    cfgs = parse_all_etfs(base)
    out: list[Probe] = []
    for etf, ax_name in productive_pairs:
        if etf in exclude:
            continue
        ax = AXES.get(ax_name)
        if ax is None:
            continue
        cfg = cfgs.get(etf, {})
        cur = _f(cfg, ax.key)
        if ax.mode == 'add' and ax.key in cfg:
            continue
        if ax.mode == 'value' and cur is None:
            continue
        for vi in value_indices:
            vname, new = ax.apply(cur, vi)
            if new is None:
                continue
            if not _safe_for_etf(etf, cfg, ax.key, new):
                continue
            if (etf, ax_name, vname) in noop_sigs:
                continue
            if (etf, ax_name, vname) in destructive_cells:
                continue
            if (etf, ax_name, vname) in catastrophic_cells:
                continue
            out.append(Probe(etf, {ax.key: new}, 'PROD', ax_name, vname))
    return out


def db_destructive_etf_axis(neg_threshold: float = -0.0001,
                             min_neg: int = 3,
                             ratio: int = 5) -> set[tuple[str, str]]:
    """(etf, axis_name) pairs where neg specs ≥ min_neg AND neg ≥ ratio*pos.
    Used to BLOCK destructive axis-pairs while allowing untested ones."""
    import re, collections
    db = storage.connect(DB_PATH)
    noop_per_batch: dict[str, float] = {}
    for b, v in db.execute(
            "SELECT batch, AVG(car_mdd) FROM experiments "
            "WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL GROUP BY batch"
            ).fetchall():
        if v is not None:
            noop_per_batch[b] = v
    name_re = re.compile(r's002_\w+?_([a-z]{2,5})_(\w+?)_\d')
    stats: dict[tuple, list[int]] = collections.defaultdict(lambda: [0, 0])
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE car_mdd IS NOT NULL AND name LIKE 's002_%' AND name NOT LIKE '%NOOP%'").fetchall():
        m = name_re.match(name)
        if not m: continue
        noop = noop_per_batch.get(batch)
        if noop is None: continue
        lift = cm - noop
        sig = (m.group(1), m.group(2))
        if lift < neg_threshold: stats[sig][0] += 1
        elif lift > 0.0005: stats[sig][1] += 1
    db.close()
    return {sig for sig, (neg, pos) in stats.items()
            if neg >= min_neg and (pos == 0 or neg >= ratio * pos)}


def db_productive_etf_axis(pos_threshold: float = 0.0005,
                            recent_destr_window: int = 30,
                            recent_destr_count: int = 6) -> set[tuple[str, str]]:
    """(etf, axis_name) pairs with ≥1 historical positive lift, MINUS pairs
    that have ≥`recent_destr_count` recent destructive specs in the last
    `recent_destr_window` rounds.

    2026-05-13: Lenient version — keep all historical productive pairs BUT
    drop those with OVERWHELMING recent destruction (≥6 specs). Avoids dropping
    pool below 128-spec threshold while still excluding stale-productive that
    became deeply destructive (fxu, iyt).

    Threshold tuned 2026-05-13: 3 → 6 to balance with 128-spec hard constraint."""
    import re
    db = storage.connect(DB_PATH)
    max_round = 0
    for (b,) in db.execute("SELECT DISTINCT batch FROM experiments WHERE batch LIKE 'gen_afql3b_div%'").fetchall():
        m = re.search(r'div(\d+)', b)
        if m:
            max_round = max(max_round, int(m.group(1)))
    cutoff = max_round - recent_destr_window if max_round > 0 else 0
    noop_per_batch: dict[str, float] = {}
    for b, v in db.execute(
            "SELECT batch, AVG(car_mdd) FROM experiments "
            "WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL GROUP BY batch"
            ).fetchall():
        if v is not None:
            noop_per_batch[b] = v
    name_re = re.compile(r's002_\w+?_([a-z]{2,5})_(\w+?)_\d')
    # Historical pos: any time
    historical_pos: set[tuple[str, str]] = set()
    # Recent destructive: in window
    recent_destr_count_map: dict[tuple[str, str], int] = {}
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE car_mdd IS NOT NULL AND name LIKE 's002_%' AND name NOT LIKE '%NOOP%'").fetchall():
        m = name_re.match(name)
        if not m: continue
        noop = noop_per_batch.get(batch)
        if noop is None: continue
        sig = (m.group(1), m.group(2))
        if cm - noop > pos_threshold:
            historical_pos.add(sig)
        elif cm - noop < -0.001:
            m_batch = re.search(r'div(\d+)', batch)
            if m_batch and int(m_batch.group(1)) >= cutoff:
                recent_destr_count_map[sig] = recent_destr_count_map.get(sig, 0) + 1
    db.close()
    # Productive = historical-pos AND not heavily destructive in recent window
    return {sig for sig in historical_pos
            if recent_destr_count_map.get(sig, 0) < recent_destr_count}


def db_productive_etfs(pos_threshold: float = 0.0005) -> set[str]:
    """ETFs with ≥1 historical positive spec. Bias bulk queue toward these
    instead of speculative novel cells. Added 2026-05-10 per user directive
    "every backtest must be meaningful".

    Untested ETFs aren't included — they need to be probed via UTNT (which
    has its own filter). This is for DV2/DV3/FILL block to bias toward
    known-responsive ETFs.
    """
    import re
    db = storage.connect(DB_PATH)
    noop_per_batch: dict[str, float] = {}
    for b, v in db.execute(
            "SELECT batch, AVG(car_mdd) FROM experiments "
            "WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL GROUP BY batch"
            ).fetchall():
        if v is not None:
            noop_per_batch[b] = v
    name_re = re.compile(r's002_\w+?_([a-z]{2,5})_')
    productive: set[str] = set()
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE car_mdd IS NOT NULL AND name LIKE 's002_%' AND name NOT LIKE '%NOOP%'").fetchall():
        m = name_re.match(name)
        if not m: continue
        noop = noop_per_batch.get(batch)
        if noop is None: continue
        if cm - noop > pos_threshold:
            productive.add(m.group(1))
    db.close()
    return productive


def db_bfsw_silent_axes(min_salts: int = 3,
                         eps: float = 0.0001,
                         recent_window: int = 200) -> set[tuple[str, str]]:
    """Returns (etf, lever_class) pairs where ANY single value of the lever
    has ≥min_salts BFSW samples ALL behaviorally NOOP (lift < eps).

    Aggressive variant of db_behavioral_noop_etf_axes(min_distinct_vals=2):
    BFSW's alphabetical rotation hits each (etf, lever, value) cell only ONCE
    per round, so the 2-distinct-values requirement fires too late. A single
    fully-silent value across 3 salts is strong evidence the ETF is not
    selected by the strategy at all — banning the entire (etf, lever_class)
    is correct (the ETF won't be in trades regardless of value).

    R3118 case: pho atr_sl_2.0 × 3 silent (R3103), pho month_mask_3583 × 3
    silent (R3105). Conservative filter (min_distinct=2) missed pho because
    only ONE atr_sl value tested within 20-round window.
    """
    import re, collections
    db = storage.connect(DB_PATH)
    noop_per_batch: dict[str, float] = {}
    for b, v in db.execute(
            "SELECT batch, AVG(car_mdd) FROM experiments "
            "WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL GROUP BY batch"
            ).fetchall():
        if v is not None:
            noop_per_batch[b] = v
    max_round = 0
    for (b,) in db.execute("SELECT DISTINCT batch FROM experiments WHERE batch LIKE 'gen_afql3b_div%'").fetchall():
        m_b = re.search(r'div(\d+)', b)
        if m_b:
            max_round = max(max_round, int(m_b.group(1)))
    cutoff_round = max_round - recent_window if max_round > 0 else 0
    name_re = re.compile(r's002_BFSW_([a-z]{2,5})_(.+?)_rv\d+_')
    def axis_class(raw: str) -> str:
        if raw.startswith('atr_sl'): return 'atr_sl'
        if raw.startswith('month_mask'): return 'month_mask'
        if raw.startswith('dd_haircut'): return 'dd_haircut'
        if raw.startswith('vol_max'): return 'vol_max'
        return raw.rsplit('_', 1)[0]
    by_pair_val: dict[tuple[str, str, str], list[float]] = {}
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE name LIKE 's002_BFSW_%' AND car_mdd IS NOT NULL").fetchall():
        m = name_re.match(name)
        if not m: continue
        m_b = re.search(r'div(\d+)', batch)
        if not m_b: continue
        if int(m_b.group(1)) < cutoff_round: continue
        etf, raw = m.group(1), m.group(2)
        ac = axis_class(raw)
        noop = noop_per_batch.get(batch)
        if noop is None: continue
        by_pair_val.setdefault((etf, ac, raw), []).append(cm - noop)
    db.close()
    out: set[tuple[str, str]] = set()
    for (etf, ac, _raw), deltas in by_pair_val.items():
        if len(deltas) >= min_salts and max(abs(d) for d in deltas) < eps:
            out.add((etf, ac))
    return out


def db_dead_axis_values(min_specs: int = 10,
                        min_etfs: int = 5,
                        eps: float = 0.0001,
                        recent_window: int = 30) -> set[tuple[str, str]]:
    """Returns (axis_name, val_label) pairs that are dead across many ETFs:
    ≥min_specs specs / ≥min_etfs distinct ETFs / 100% NOOP-equivalent.

    R3230 30m audit found sl_grow_110pct (15/15 NOOP / 5 ETFs) and atr_sl_2_0
    (12/12 NOOP / 4 ETFs) as cross-ETF dead values. Per-ETF noop filter catches
    individual ETFs only after they're tested; this global filter prevents the
    axis-value from being probed on ANY new ETF.

    Conservative: only fires when 100% NOOP across many independent samples,
    so won't suppress productive directions.
    """
    import re, collections
    db = storage.connect(DB_PATH)
    noop_per_batch: dict[str, float] = {}
    for b, v in db.execute(
            "SELECT batch, AVG(car_mdd) FROM experiments "
            "WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL GROUP BY batch"
            ).fetchall():
        if v is not None:
            noop_per_batch[b] = v
    max_round = 0
    for (b,) in db.execute("SELECT DISTINCT batch FROM experiments WHERE batch LIKE 'gen_afql3b_div%'").fetchall():
        m_b = re.search(r'div(\d+)', b)
        if m_b:
            max_round = max(max_round, int(m_b.group(1)))
    cutoff_round = max_round - recent_window if max_round > 0 else 0
    name_re = re.compile(
        r's002_(?:BFSW|UTNT|UTNTW|BTI|WTX|STX|CFX|SFX|NEWLEV|BORD|NEWAX|LEVAX|'
        r'COLD|DIV|DV2|DV3|VRFY|STACK|FILL|C2D|AT|RT|SHRTAX|BURX|CRMX)_'
        r'([a-z]{2,5})_(.+?)_rv\d+_')
    # (axis_name, val_label) -> {(etf, batch): lift}
    stats: dict[tuple[str, str], dict] = collections.defaultdict(
        lambda: {'lifts': [], 'etfs': set()})
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE name LIKE 's002_%' AND car_mdd IS NOT NULL").fetchall():
        m = name_re.match(name)
        if not m: continue
        m_b = re.search(r'div(\d+)', batch)
        if not m_b: continue
        if int(m_b.group(1)) < cutoff_round: continue
        etf, lever_value = m.group(1), m.group(2)
        noop = noop_per_batch.get(batch)
        if noop is None: continue
        axis_name, val_label = _split_lever_value(lever_value)
        if not val_label: continue
        key = (axis_name, val_label)
        stats[key]['lifts'].append(cm - noop)
        stats[key]['etfs'].add(etf)
    db.close()
    out: set[tuple[str, str]] = set()
    for key, d in stats.items():
        if (len(d['lifts']) >= min_specs and
            len(d['etfs']) >= min_etfs and
            max(abs(l) for l in d['lifts']) < eps):
            out.add(key)
    return out


def db_catastrophic_cells(catastrophic_threshold: float = -0.05,
                          min_specs: int = 2,
                          single_spec_threshold: float = -0.1) -> set[tuple[str, str, str]]:
    """Returns (etf, axis_name, val_label) cells with EITHER:
      - ≥min_specs historical samples at lift ≤ catastrophic_threshold, OR
      - ≥1 sample at lift ≤ single_spec_threshold (-10% MDD: deterministic catastrophe)

    NO recency window — once a cell is shown to cause catastrophic lift,
    it stays banned permanently because the base hasn't changed enough to
    recover.

    R3116 case: rgi tp_grow_105pct landed at -0.26 × 3 in R2980 (outside
    20-round recency window of db_destructive_cells). Re-queued R3068+R3116.
    R3132 case: aor xf_shrink_95pct landed at -0.457 × 1 — single-spec
    catastrophe should immediately block, not wait for 2nd confirmation.
    """
    import re, collections
    db = storage.connect(DB_PATH)
    noop_per_batch: dict[str, float] = {}
    for b, v in db.execute(
            "SELECT batch, AVG(car_mdd) FROM experiments "
            "WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL GROUP BY batch"
            ).fetchall():
        if v is not None:
            noop_per_batch[b] = v
    name_re = re.compile(
        r's002_(?:NEWAX|LEVAX|BAKERX|COLD|DIV|DV2|DV3|BORD|VRFY|STACK|FILL|'
        r'C2D|AT|RT|BFSW|SHRTAX|BURX|CRMX|UTNT|UTNTW|BTI|WTX|STX|CFX|SFX|NEWLEV)_'
        r'([a-z]{2,5})_(.+?)_rv\d+_')
    cell_counts: dict[tuple, int] = collections.defaultdict(int)
    single_catastrophic: set[tuple] = set()
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE car_mdd IS NOT NULL AND name LIKE 's002_%'").fetchall():
        m = name_re.match(name)
        if not m: continue
        etf, lever_value = m.group(1), m.group(2)
        noop = noop_per_batch.get(batch)
        if noop is None: continue
        lift = cm - noop
        # 2026-05-19 R3798 bug fix: multi-underscore values (atr_sl_1_5,
        # dd_haircut_0_3, etc.) need smarter splitting. Otherwise dbc dd_0_3
        # gets stored as ('dbc','dd_haircut_0','3') but lookup uses
        # ('dbc','dd_haircut','0_3') — filter defeated.
        axis_name, val_label = _split_lever_value(lever_value)
        sig = (etf, axis_name, val_label)
        if lift <= single_spec_threshold:
            single_catastrophic.add(sig)
        if lift <= catastrophic_threshold:
            cell_counts[sig] += 1
    db.close()
    return single_catastrophic | {sig for sig, n in cell_counts.items() if n >= min_specs}


def _split_lever_value(lv: str) -> tuple[str, str]:
    """Smart splitter for lever_value strings into (axis_name, val_label).

    Handles multi-underscore values:
      'tp_shrink_90pct' → ('tp_shrink', '90pct')
      'atr_sl_1_5' → ('atr_sl', '1_5')
      'dd_haircut_0_3' → ('dd_haircut', '0_3')
      'month_mask_3839' → ('month_mask', '3839')
      'wt_grow_105pct' → ('wt_grow', '105pct')
    """
    # Known multi-word axes (longest first to match correctly)
    KNOWN_AXES = ['dd_haircut', 'atr_sl', 'month_mask',
                  'tp_grow', 'tp_shrink', 'sl_grow', 'sl_shrink',
                  'wt_grow', 'wt_shrink', 'cf_grow', 'cf_shrink',
                  'sf_grow', 'sf_shrink', 'ef_grow', 'ef_shrink',
                  'xf_grow', 'xf_shrink', 'cb_grow', 'cb_shrink',
                  'cm_grow', 'cm_shrink', 'ub_grow', 'ub_shrink',
                  'um_grow', 'um_shrink', 'rg_grow', 'rg_shrink',
                  'bw_grow', 'bw_shrink', 'am_grow', 'am_shrink',
                  'cd_grow', 'cd_shrink']
    for axis in KNOWN_AXES:
        prefix = axis + '_'
        if lv.startswith(prefix):
            return axis, lv[len(prefix):]
    # Fallback: rsplit last underscore (original behavior)
    parts = lv.rsplit('_', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return lv, ''


def db_persistent_destructive_cells(min_distinct_rounds: int = 2,
                                      neg_threshold: float = -0.0005,
                                      recent_pos_window: int = 30,
                                      pos_threshold: float = 0.0005) -> set[tuple[str, str, str]]:
    """Returns (etf, axis_name, val_label) cells with destructive incidents
    across ≥min_distinct_rounds DIFFERENT rounds AND no recent POS specs.

    Complements db_destructive_cells (50-round window misses old incidents).
    Example: fxn tp_grow_110pct was destructive in R3758 + R3812 + R3813
    (54 rounds between first/last). With recent_window=50, R3758 outside
    window so filter doesn't fire on R3812 queue → wasted 1 + 3 = 4 specs.

    Safety check: if cell has positive specs in last `recent_pos_window`
    rounds, do NOT ban (base may have changed making cell productive).
    """
    import re, collections
    db = storage.connect(DB_PATH)
    # Find max round for recent-pos window
    max_round = 0
    for (b,) in db.execute("SELECT DISTINCT batch FROM experiments WHERE batch LIKE 'gen_afql3b_div%'").fetchall():
        m = re.search(r'div(\d+)', b)
        if m: max_round = max(max_round, int(m.group(1)))
    pos_cutoff = max_round - recent_pos_window
    noop_per_batch = {b: v for b, v in db.execute(
        "SELECT batch, AVG(car_mdd) FROM experiments WHERE name LIKE '%NOOP%' "
        "AND car_mdd IS NOT NULL GROUP BY batch").fetchall() if v is not None}
    name_re = re.compile(
        r's002_(?:NEWAX|LEVAX|BAKERX|COLD|DIV|DV2|DV3|BORD|VRFY|STACK|FILL|'
        r'C2D|AT|RT|BFSW|SHRTAX|BURX|CRMX|UTNT|UTNTW|BTI|WTX|STX|CFX|SFX|NEWLEV)_'
        r'([a-z]{2,5})_(.+?)_rv\d+_')
    cell_rounds = collections.defaultdict(set)
    cells_recent_pos = set()
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE car_mdd IS NOT NULL AND name LIKE 's002_%'").fetchall():
        m = name_re.match(name)
        if not m: continue
        noop = noop_per_batch.get(batch)
        if noop is None: continue
        lift = cm - noop
        m_batch = re.search(r'div(\d+)', batch)
        if not m_batch: continue
        r = int(m_batch.group(1))
        etf, lever_value = m.group(1), m.group(2)
        axis_name, val_label = _split_lever_value(lever_value)
        sig = (etf, axis_name, val_label)
        if lift < neg_threshold:
            cell_rounds[sig].add(r)
        elif lift > pos_threshold and r >= pos_cutoff:
            cells_recent_pos.add(sig)
    db.close()
    return {sig for sig, rounds in cell_rounds.items()
            if len(rounds) >= min_distinct_rounds and sig not in cells_recent_pos}


def db_destructive_cells(min_neg_specs: int = 3,
                         neg_threshold: float = -0.0003,
                         recent_window: int = 50) -> set[tuple[str, str, str]]:
    """Returns (etf, axis_name, val_label) cells with ≥min_neg_specs confirmed
    NEG specs (lift < neg_threshold) within the last `recent_window` rounds.

    Threshold tightened 2026-05-16 from -0.001 to -0.0003 to catch deterministic
    mild-destructives like fxn tp_shrink_95pct (-0.00048 × 3 std=0 in R3222 was
    re-queued in R3225 because -0.00048 didn't cross -0.001). car_mdd quantum
    is ~0.00024 = 1 trade-loss; -0.0003 catches ≥1.25 trade-loss without
    flagging variance.

    2026-05-12: Added `recent_window` parameter to fix stale-NOOP shielding.
    Cells with old POS (against a different base) were protecting recent
    NEG specs from being filtered. Example: fxu tp_shrink_80pct +0.00071
    in R2881 (different base) blocked 6 -0.235 specs from R2900+R2905.

    Enforces user directive: every backtest must be meaningful.
    """
    import re, collections
    db = storage.connect(DB_PATH)
    # Find max round_num to derive recent window
    max_round = 0
    for (b,) in db.execute("SELECT DISTINCT batch FROM experiments WHERE batch LIKE 'gen_afql3b_div%'").fetchall():
        m = re.search(r'div(\d+)', b)
        if m:
            max_round = max(max_round, int(m.group(1)))
    cutoff_round = max_round - recent_window if max_round > 0 else 0
    noop_per_batch: dict[str, float] = {}
    # 2026-05-17: skip DRIFT batches (NOOP within-round range > 0.005). In
    # R3368/R3369 the bimodal salt-drift (9.9971 ↔ 10.0264) shifted NOOP
    # avg by +0.0073, causing baseline probes to look -0.0073 destructive.
    # Cells get incorrectly added to destructive_cells.
    drift_batches: set[str] = set()
    # Within-round drift (requires ≥2 NOOPs per batch)
    for b, mn, mx, n_ in db.execute(
            "SELECT batch, MIN(car_mdd), MAX(car_mdd), COUNT(*) FROM experiments "
            "WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL GROUP BY batch"
            ).fetchall():
        if n_ is not None and n_ >= 2 and mx - mn > 0.005:
            drift_batches.add(b)
    # 2026-05-17 cross-round drift: with --noop=1, fall back to comparing
    # each batch's NOOP against window of prior NOOPs (±3 rounds).
    import re as _rdc
    _batch_noop = {b: v for b, v in db.execute(
        "SELECT batch, AVG(car_mdd) FROM experiments WHERE name LIKE '%NOOP%' "
        "AND car_mdd IS NOT NULL GROUP BY batch").fetchall()}
    _sorted_batches = sorted(_batch_noop.keys())
    for i, b in enumerate(_sorted_batches):
        if b in drift_batches: continue
        nv_b = _batch_noop[b]
        # Compare to prior 3 batches' avg
        prior = [_batch_noop[_sorted_batches[j]] for j in range(max(0, i-3), i)]
        if prior and abs(nv_b - sum(prior)/len(prior)) > 0.005:
            drift_batches.add(b)
    for b, v in db.execute(
            "SELECT batch, AVG(car_mdd) FROM experiments "
            "WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL GROUP BY batch"
            ).fetchall():
        if v is not None and b not in drift_batches:
            noop_per_batch[b] = v
    # 2026-05-16: added WTX/STX/CFX/SFX/NEWLEV. Earlier regex silently
    # skipped these blocks → 6/9 NEWLEV destructive cells were never
    # aggregated into destructive_cells filter (dth/gsg/dem/xlb/pnqi
    # destructive lifts of -0.0019 to -1.47 left unblocked).
    name_re = re.compile(
        r's002_(?:NEWAX|LEVAX|BAKERX|COLD|DIV|DV2|DV3|BORD|VRFY|STACK|FILL|'
        r'C2D|AT|RT|BFSW|SHRTAX|BURX|CRMX|UTNT|UTNTW|BTI|WTX|STX|CFX|SFX|NEWLEV)_'
        r'([a-z]{2,5})_(.+?)_rv\d+_')
    cell_stats: dict[tuple, list[int]] = collections.defaultdict(lambda: [0, 0])
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE car_mdd IS NOT NULL AND name LIKE 's002_%'").fetchall():
        m = name_re.match(name)
        if not m: continue
        # Recency check: only count specs from rounds within recent_window
        m_batch = re.search(r'div(\d+)', batch)
        if not m_batch: continue
        if int(m_batch.group(1)) < cutoff_round: continue
        etf, lever_value = m.group(1), m.group(2)
        noop = noop_per_batch.get(batch)
        if noop is None: continue
        axis_name, val_label = _split_lever_value(lever_value)
        sig = (etf, axis_name, val_label)
        lift = cm - noop
        if lift < neg_threshold:
            cell_stats[sig][0] += 1
        elif lift > 0.0005:
            cell_stats[sig][1] += 1
    # 2026-05-19 R3813: track min NEG lift per cell for severity-aware rule
    cell_min_neg: dict[tuple, float] = {}
    for name, cm, batch in db.execute(
            "SELECT name, car_mdd, batch FROM experiments "
            "WHERE car_mdd IS NOT NULL AND name LIKE 's002_%'").fetchall():
        m = name_re.match(name)
        if not m: continue
        m_batch = re.search(r'div(\d+)', batch)
        if not m_batch: continue
        if int(m_batch.group(1)) < cutoff_round: continue
        etf, lever_value = m.group(1), m.group(2)
        noop = noop_per_batch.get(batch)
        if noop is None: continue
        axis_name, val_label = _split_lever_value(lever_value)
        sig = (etf, axis_name, val_label)
        lift = cm - noop
        if lift < neg_threshold:
            if sig not in cell_min_neg or lift < cell_min_neg[sig]:
                cell_min_neg[sig] = lift
    db.close()
    # Mark destructive if EITHER:
    #   - 0 pos AND ≥min_neg_specs neg (pure destructive)
    #   - neg >= 5 × pos (overwhelmingly destructive)
    #   - 2026-05-18: post-bake direction-flip catch. wood sl_shrink_90pct had
    #     3 pre-bake +0.00095 (=baked-value lift) + 6 post-bake -0.00714
    #     (=overshoot). Mixed history shielded by 5× rule (6 < 15). Add: any
    #     cell with ≥6 NEG specs banned regardless of pos count.
    #   - 2026-05-19 R3813 fix: severity-based rule. Stale single POS shielded
    #     R3804 qqq ef_grow_105pct (3 NEG at -0.00786 std=0 vs 1 POS from
    #     R3766 pre-bake context). When any NEG ≤ -0.005 (clearly deterministic
    #     destructive, not variance), require only 3:1 ratio not 5:1.
    # 2026-05-19 R3813: severity-based min_neg_specs. NEWLEV queues 1 spec/cell/round,
    # so 3-spec threshold takes 3 incidents to ban (wasting 3 rounds × 3 = 9 specs).
    # When NEG magnitude is large (≤-0.005), lower threshold to 2 specs (catches faster).
    return {sig for sig, (neg, pos) in cell_stats.items()
            if (
                # Standard: ≥3 neg + (no pos OR overwhelming)
                (neg >= min_neg_specs and (
                    pos == 0 or neg >= 5 * pos or neg >= 6 or
                    (cell_min_neg.get(sig, 0) <= -0.005 and neg >= 3 * pos)
                )) or
                # Severity: ≥2 neg with min lift ≤ -0.005 (deterministic, not variance)
                (neg >= 2 and cell_min_neg.get(sig, 0) <= -0.005 and pos == 0)
            )}


def db_saturated_newax_combos(min_salts: int = 6,
                              eps: float = 0.0001) -> set:
    """Returns set of (etf, lever, value) tuples that have been NEWAX-tested
    ≥min_salts times across history with all near-zero lift.

    Prevents NEWAX from re-probing the same dead combo round after round.
    Pass 18 — Cass evidence: kre/kxi/sptm atr_sl variants tested 12-15 times
    each across 5 rounds, all zero lift = ~150 wasted backtests.
    """
    import re
    db = storage.connect(DB_PATH)
    # Group experiments by (etf, lever, value) and count + check max lift
    rows = db.execute(
        "SELECT name, car_mdd, batch FROM experiments "
        "WHERE name LIKE 's002_NEWAX_%' AND car_mdd IS NOT NULL").fetchall()
    db.close()
    by_combo: dict[tuple, list[float]] = {}
    # Cache NOOP per batch
    db = storage.connect(DB_PATH)
    noop_per_batch: dict[str, float] = {}
    for (b,) in db.execute(
            "SELECT DISTINCT batch FROM experiments WHERE name LIKE 's002_NEWAX_%'").fetchall():
        v = db.execute(
            "SELECT AVG(car_mdd) FROM experiments WHERE batch=? AND name LIKE '%NOOP%' "
            "AND car_mdd IS NOT NULL", (b,)).fetchone()[0]
        if v is not None:
            noop_per_batch[b] = v
    db.close()
    name_re = re.compile(r's002_NEWAX_([a-z]{2,5})_([\w_]+?)_rv\d+_')
    for name, cm, batch in rows:
        m = name_re.match(name)
        if not m:
            continue
        etf, lever_value = m.group(1), m.group(2)
        # Split lever_value: lever is everything before last "_<numeric>"
        # e.g. atr_sl_2_5 → lever=atr_sl, value=2.5
        # bb_width_max_0_1 → lever=bb_width_max, value=0.1
        parts = lever_value.split('_')
        # Heuristic: last 1-2 underscore-separated parts are value
        val_str = parts[-1]
        try:
            float(val_str)
            # If last is numeric, check second-to-last
            if len(parts) >= 2 and (parts[-2].isdigit() or '.' in parts[-2]):
                val = '.'.join(parts[-2:])
                lever = '_'.join(parts[:-2])
            else:
                val = val_str
                lever = '_'.join(parts[:-1])
        except ValueError:
            val = val_str
            lever = '_'.join(parts[:-1])
        noop = noop_per_batch.get(batch)
        if noop is None:
            continue
        try:
            v = float(val)
        except ValueError:
            continue
        by_combo.setdefault((etf, lever, v), []).append(cm - noop)
    out = set()
    for k, lifts in by_combo.items():
        if len(lifts) >= min_salts and max(abs(l) for l in lifts) < eps:
            out.add(k)
    return out


def db_recent_quasi_noop_cells(min_specs: int = 3,
                                eps: float = 0.0005,
                                n_rounds: int = 30) -> set[tuple[str, str, str]]:
    """(etf, axis_name, val_label) cells with ≥min_specs recent specs ALL in
    [-eps, +eps] lift range. Catches borderline-NOOP cells (like vo
    wt_shrink_95pct = -0.00024 × 5+ rounds) that slip past noop_sigs
    (eps=0.0001) and destructive_cells (lift<-0.0005).

    Reason: baked-exempt blocks bypass _inert_etf_axes per-ETF filter to
    enable cross-lever iteration. But once a specific (etf, axis, val) cell
    plateaus, further iteration is pure waste. This filter blocks the
    specific dead cell while keeping other axes/values open.

    2026-05-18 R3642 30m audit: 15 vo wt_shrink_95pct re-tests over 45 rounds.
    """
    import re, collections, qc_storage as _sq
    db = _sq.connect(DB_PATH)
    batches = [r[0] for r in db.execute(
        "SELECT DISTINCT batch FROM experiments WHERE batch LIKE 'gen_afql3b_div%' "
        "ORDER BY batch DESC LIMIT ?", (n_rounds,)).fetchall()]
    if not batches:
        db.close()
        return set()
    placeholders = ','.join('?' for _ in batches)
    noop_per_batch = {b: v for b, v in db.execute(
        f"SELECT batch, AVG(car_mdd) FROM experiments WHERE name LIKE '%NOOP%' "
        f"AND car_mdd IS NOT NULL AND batch IN ({placeholders}) GROUP BY batch",
        batches).fetchall() if v is not None}
    name_re = re.compile(r's002_[A-Z]+_([a-z]{2,6})_([a-z_]+?)_(\d+pct|_\d)_rv\d')
    stats = collections.defaultdict(list)
    for name, cm, batch in db.execute(
            f"SELECT name, car_mdd, batch FROM experiments "
            f"WHERE car_mdd IS NOT NULL AND name LIKE 's002_%' "
            f"AND name NOT LIKE '%NOOP%' AND batch IN ({placeholders})",
            batches):
        m = name_re.match(name)
        if not m: continue
        noop = noop_per_batch.get(batch)
        if noop is None: continue
        etf, lever, val = m.group(1), m.group(2), m.group(3)
        stats[(etf, lever, val)].append(cm - noop)
    db.close()
    out = set()
    for k, lifts in stats.items():
        if len(lifts) >= min_specs and max(abs(l) for l in lifts) < eps:
            out.add(k)
    return out


def db_recent_inert_etfs(min_probes: int = 10, since_n_rounds: int = 180,
                          eps: float = 0.0005) -> set[str]:
    """ETFs where ALL recent probes returned |lift| < eps across ≥min_probes.

    Catches ETFs that are structurally non-responsive in current base config
    (sized too small to trade, or behavior thresholds not met). Distinct from
    db_inert_etfs which requires 30+ probes and skips UTNT/BTI prefixes.

    2026-05-18 R3630 30m audit: 73 ETFs found inert across 5+ probes since
    R3450; 26% of recent specs wasted on these. Filter targets UTNT/BTI/XX
    blocks. BFSW excluded — different discovery mechanism (regime/month_mask)
    can unlock inert ETFs (ewc was inert then BAKE-337 via cross-round
    cumulative pathway).
    """
    import re, collections, qc_storage as _sq
    db = _sq.connect(DB_PATH)
    # All batches sorted descending
    batches = [r[0] for r in db.execute(
        "SELECT DISTINCT batch FROM experiments WHERE batch LIKE 'gen_afql3b_div%' "
        "ORDER BY batch DESC LIMIT ?", (since_n_rounds,)).fetchall()]
    if not batches:
        db.close()
        return set()
    placeholders = ','.join('?' for _ in batches)
    noop_per_batch = {b: v for b, v in db.execute(
        f"SELECT batch, AVG(car_mdd) FROM experiments WHERE name LIKE '%NOOP%' "
        f"AND car_mdd IS NOT NULL AND batch IN ({placeholders}) GROUP BY batch",
        batches).fetchall() if v is not None}
    name_re = re.compile(r's002_[A-Z]+_([a-z]{2,6})_')
    stats = collections.defaultdict(list)
    for name, cm, batch in db.execute(
            f"SELECT name, car_mdd, batch FROM experiments "
            f"WHERE car_mdd IS NOT NULL AND name LIKE 's002_%' "
            f"AND name NOT LIKE '%NOOP%' AND batch IN ({placeholders})",
            batches):
        m = name_re.match(name)
        if not m: continue
        noop = noop_per_batch.get(batch)
        if noop is None: continue
        stats[m.group(1)].append(cm - noop)
    db.close()
    inert = set()
    for etf, lifts in stats.items():
        if len(lifts) >= min_probes and max(abs(l) for l in lifts) < eps:
            inert.add(etf)
    return inert


def db_bti_exhausted_etfs(min_distinct_cells: int = 2,
                            min_total_specs: int = 6,
                            recent_window: int = 80,
                            neg_threshold: float = -0.0005) -> set[str]:
    """ETFs with ≥min_distinct_cells distinct destructive tp_grow/tp_shrink cells
    in last `recent_window` rounds — BTI iteration exhausted.

    2026-05-19 R3803 30m audit: 6 tp-baked ETFs (ewd/gsg/igv/sptm/vo/xlb)
    accumulated 52 destructive BTI specs over 50 rounds. db_destructive_cells
    catches each cell individually but BTI rotation keeps trying NEW cells on
    same ETF. After 2+ distinct cells confirmed destructive, the whole tp axis
    is exhausted for that ETF (post-bake symmetric destruction pattern).

    Differs from db_destructive_etf_axes (which catches at axis-class level
    via aggregate) — this is BTI-specific and bypasses the baked_exempt logic.
    """
    import re, collections, qc_storage as _sq
    db = _sq.connect(DB_PATH)
    batches = [r[0] for r in db.execute(
        "SELECT DISTINCT batch FROM experiments WHERE batch LIKE 'gen_afql3b_div%' "
        "ORDER BY batch DESC LIMIT ?", (recent_window,)).fetchall()]
    if not batches:
        db.close()
        return set()
    placeholders = ','.join('?' for _ in batches)
    noop_per_batch = {b: v for b, v in db.execute(
        f"SELECT batch, AVG(car_mdd) FROM experiments WHERE name LIKE '%NOOP%' "
        f"AND car_mdd IS NOT NULL AND batch IN ({placeholders}) GROUP BY batch",
        batches).fetchall() if v is not None}
    name_re = re.compile(r's002_BTI_([a-z0-9]+)_(tp_(?:grow|shrink)_\d+pct)_rv\d+')
    cells = collections.defaultdict(lambda: collections.defaultdict(int))
    for name, cm, batch in db.execute(
            f"SELECT name, car_mdd, batch FROM experiments "
            f"WHERE car_mdd IS NOT NULL AND name LIKE 's002_BTI_%' "
            f"AND batch IN ({placeholders})",
            batches):
        m = name_re.match(name)
        if not m: continue
        noop = noop_per_batch.get(batch)
        if noop is None: continue
        if cm - noop >= neg_threshold: continue
        etf, cell = m.groups()
        cells[etf][cell] += 1
    db.close()
    exhausted = set()
    for etf, by_cell in cells.items():
        if len(by_cell) >= min_distinct_cells and sum(by_cell.values()) >= min_total_specs:
            exhausted.add(etf)
    return exhausted


def db_untouched_etfs() -> set[str]:
    """Return ETFs that have NEVER been probed (no specs in experiments).

    For full-diversification probe ordering — prioritize untouched ETFs in
    NEWAX/COLD slots since they're the largest unexplored productive surface.
    """
    import re
    db = storage.connect(DB_PATH)
    probed = set()
    for (n,) in db.execute("SELECT name FROM experiments").fetchall():
        m = re.search(
            r's002_(?:NEWAX|LEVAX|BAKERX|COLD|DIV|DV2|DV3|BORD|VRFY|STACK|FILL|C2D|AT|RT)_'
            r'([a-z]{2,5})_', n)
        if m:
            probed.add(m.group(1))
    db.close()
    return probed  # actual probed; caller does set diff with universe


def db_recent_bfsw_etf_axes(n_batches: int = 10) -> set[tuple[str, str]]:
    """Return (etf, lever) tuples probed by BFSW (or UTNT) in last N batches.

    Used to spread BFSW exploration across untuned ETFs round-over-round —
    without this, the alphabetical-clustered round_offset rotation keeps
    re-surfacing the same ~10 ETFs per axis (R3056-R3065 covered only
    31/217 untuned ETFs across 10 rounds = 14%). With axis-level memory,
    BFSW only re-probes an (etf, lever) pair once per n_batches.

    Returns (etf, lever) — value-agnostic so 'efa atr_sl=1.5' next round
    won't re-test 'efa atr_sl=1.75' from last round.
    """
    db = storage.connect(DB_PATH)
    out: set[tuple[str, str]] = set()
    rows = db.execute(
        "SELECT DISTINCT batch FROM experiments "
        "WHERE batch LIKE 'gen_afql3b_div%' ORDER BY batch DESC LIMIT ?",
        (n_batches,)).fetchall()
    pat = re.compile(
        r's002_(?:BFSW|UTNT)_([a-z]{2,5})_([a-z_]+?)_\d')
    for (b,) in rows:
        for (n,) in db.execute("SELECT name FROM experiments WHERE batch=?", (b,)):
            m = pat.search(n or '')
            if m:
                etf = m.group(1)
                lever_label = m.group(2)
                # Normalize lever_label → axis key (atr_sl_1, month_mask, dd_haircut, etc.)
                if lever_label.startswith('atr_sl'):
                    out.add((etf, 'atr_sl'))
                elif lever_label.startswith('month_mask'):
                    out.add((etf, 'month_mask'))
                elif lever_label.startswith('dd_haircut'):
                    out.add((etf, 'dd_haircut'))
                elif lever_label.startswith('vol_max'):
                    out.add((etf, 'vol_max'))
                elif lever_label.startswith('tf_t'):
                    out.add((etf, 'tf_t'))
    db.close()
    return out


def db_recent_etfs(n_batches: int = 5) -> set[str]:
    db = storage.connect(DB_PATH)
    out: set[str] = set()
    rows = db.execute(
        "SELECT DISTINCT batch FROM experiments "
        "WHERE batch LIKE 'gen_afql3b_div%' ORDER BY batch DESC LIMIT ?",
        (n_batches,)).fetchall()
    for (b,) in rows:
        for (n,) in db.execute("SELECT name FROM experiments WHERE batch=?", (b,)):
            m = re.search(r'_(?:DIV|DV2|C2D|VRFY|AT|RT|COLD)_([a-z]{2,5})_', n)
            if m:
                out.add(m.group(1))
    db.close()
    return out


def db_existing_names_hashes() -> tuple[set[str], set[str]]:
    db = storage.connect(DB_PATH)
    names = set(r[0] for r in db.execute("SELECT name FROM experiments"))
    names |= set(r[0] for r in db.execute(
        "SELECT name FROM backtest_queue WHERE status IN ('queued','running')"))
    hashes = set(r[0] for r in db.execute(
        "SELECT code_hash FROM experiments WHERE code_hash IS NOT NULL"))
    hashes |= set(r[0] for r in db.execute(
        "SELECT code_hash FROM backtest_queue "
        "WHERE code_hash IS NOT NULL AND status IN ('queued','running')"))
    db.close()
    return names, hashes


def db_round_summary(batch: str) -> dict | None:
    """Get NOOP avg + top probes by car_mdd for a batch."""
    db = storage.connect(DB_PATH)
    noop_rows = db.execute(
        "SELECT car_mdd FROM experiments WHERE batch=? AND name LIKE '%NOOP%' "
        "AND car_mdd IS NOT NULL", (batch,)).fetchall()
    if not noop_rows:
        db.close()
        return None
    noop_avg = sum(r[0] for r in noop_rows) / len(noop_rows)
    top = db.execute(
        "SELECT name, car_mdd FROM experiments WHERE batch=? "
        "AND name NOT LIKE '%NOOP%' AND car_mdd IS NOT NULL "
        "ORDER BY car_mdd DESC LIMIT 20", (batch,)).fetchall()
    db.close()
    return {'noop_avg': noop_avg, 'noop_n': len(noop_rows), 'top': top}


# ─── Round builder ─────────────────────────────────────────────────────────
def derive_salts(round_num: int, count: int = 4) -> list[int]:
    return [int(f"{round_num}{i:05d}") for i in range(1, count + 1)]


@dataclass
class RoundBuilder:
    round_num: int
    base_path: str
    batch: str
    based_on: str
    target: int = 128
    excluded_pairs: set = field(default_factory=set)
    base: str = field(init=False)
    salts: list[int] = field(init=False)
    specs: list[tuple] = field(init=False, default_factory=list)
    _noop_hashes: set[str] = field(init=False, default_factory=set)
    _spec_hashes: set[str] = field(init=False, default_factory=set)
    _noop_sigs: set = field(init=False, default_factory=set)
    _dead_pairs: set = field(init=False, default_factory=set)
    _destructive_cells: set = field(init=False, default_factory=set)
    _catastrophic_cells: set = field(init=False, default_factory=set)
    _noop_etf_axes: set = field(init=False, default_factory=set)
    _destr_etf_axes: set = field(init=False, default_factory=set)
    _inert_etf_axes: set = field(init=False, default_factory=set)
    n_skipped_dead: int = field(init=False, default=0)
    n_skipped_behavioral_noop: int = field(init=False, default=0)
    n_skipped_dead_pair: int = field(init=False, default=0)
    n_skipped_destructive: int = field(init=False, default=0)
    n_skipped_axis_noop: int = field(init=False, default=0)
    n_skipped_axis_destr: int = field(init=False, default=0)

    def __post_init__(self):
        self.base = open(self.base_path).read()
        self.salts = derive_salts(self.round_num)
        for s in self.salts:
            c = mut_etf({'_rvtag': s}, 'vti', self.base)
            self._noop_hashes.add(codehash(c))
        self._noop_sigs = db_behavioral_noop_signatures()
        self._dead_pairs = db_dead_etf_axis_pairs()
        # 2026-05-19: union with persistent destructive (no recency window)
        # to catch cells with multi-round destructive history beyond 50-round
        # recent_window. Fixes fxn tp_grow_110pct repeating R3758→R3812→R3813.
        self._destructive_cells = db_destructive_cells() | db_persistent_destructive_cells()
        self._catastrophic_cells = db_catastrophic_cells()
        self._noop_etf_axes = db_behavioral_noop_etf_axes()
        self._destr_etf_axes = db_destructive_etf_axes()
        # 2026-05-17 filter cross-talk fix: failed VRFY (etf, lever) pairs
        # should be excluded from discovery block re-probing. Without this,
        # dem cd VRFY failed R3385 (-0.00024 × 4) but R3387 NEWLEV re-
        # queued dem cd_grow_1. Union into _destr_etf_axes.
        self._destr_etf_axes |= db_recent_failed_vrfy_etf_levers(n_rounds=80)  # 2026-05-17: widened 30→80. R3423/R3425 saw dem cd (R3385, 38 rounds back) + iyz tp (R3377, 48 rounds back) re-queued. Failed VRFY evidence should persist longer; 80 rounds covers full session window.
        self._inert_etf_axes = db_lever_inert_etf_axes()
        # 2026-05-18 R3642 30m: borderline-NOOP cells (|lift|<0.0005 across ≥3
        # specs in last N rounds). Catches cells slipping noop_sigs (eps=0.0001)
        # and destructive_cells (lift<-0.0005). Targets baked-exempt re-tests.
        # 2026-05-18 R3673: widened 30→80. 2026-05-18 R3727: widened 80→200
        # because vo wt_shrink_95pct re-queued R3727 (only 2 of 4 historical
        # specs in 80-round window; threshold needs ≥3).
        self._quasi_noop_cells = db_recent_quasi_noop_cells(min_specs=3,
                                                             eps=0.0005,
                                                             n_rounds=200)
        # 2026-05-16: global dead axis-values (cross-ETF 100% NOOP).
        # Recency widened 30→60 (covers full bake-drought). Tried no-window
        # first but old PRODUCTIVE lifts (cd +0.00887 at R3148) prevent dead
        # classification. 60-round window covers R3188+ — enough to capture
        # post-bake-310 era patterns while excluding pre-bake productive cells.
        self._dead_axis_values = db_dead_axis_values(min_specs=10, min_etfs=3,
                                                     recent_window=60)
        # Cross-round dedup: load all prior code_hashes into _spec_hashes
        # so generator skips specs that would collide with DB queue/experiments.
        # 2026-05-11: was rejecting at INSERT level, causing under-128 rounds.
        _, existing_hashes = db_existing_names_hashes()
        self._spec_hashes |= existing_hashes

    @property
    def remaining(self) -> int:
        return self.target - len(self.specs)

    def add_noop(self, count: int = 4) -> int:
        added = 0
        for i, s in enumerate(self.salts[:count], 1):
            c = mut_etf({'_rvtag': s}, 'vti', self.base)
            nm = f's002_VBAKE_NOOP_rv{i}_{self.batch}'
            self.specs.append((nm, c, 'NOOP', self.based_on, 1))
            added += 1
        return added

    def _add_one(self, kind: str, etf: str, axis_name: str, val_name: str,
                 changes: dict, salt: int, salt_idx: int, prio: int) -> bool:
        if self.remaining <= 0:
            return False
        # Dead-pair exclusion: never re-probe (etf, lever) pairs that have been
        # observed inert across recent rounds. VRFY slots bypass exclusion (we
        # explicitly want to re-confirm sub-threshold lifts).
        if kind != 'VRFY' and self.excluded_pairs:
            for lever in changes.keys():
                if (etf, lever) in self.excluded_pairs:
                    self.n_skipped_dead += 1
                    return False
        # Behavioral-noop exclusion: skip (etf, axis, val) signatures that
        # produced exact NOOP across ≥3 historical salts. R2575 audit found
        # 75-95% of recent specs were such no-ops — purest waste of compute.
        if kind != 'VRFY' and self._noop_sigs:
            combined = f'{axis_name}_{val_name}' if val_name else axis_name
            if '_' in combined:
                sig_axis, sig_val = combined.rsplit('_', 1)
            else:
                sig_axis, sig_val = combined, ''
            if (etf, sig_axis, sig_val) in self._noop_sigs:
                self.n_skipped_behavioral_noop += 1
                return False
            # Destructive-cell exclusion (added 2026-05-10): cells with ≥3
            # confirmed NEG specs and 0 positive — pure waste of backtest budget.
            if self._destructive_cells and (etf, sig_axis, sig_val) in self._destructive_cells:
                self.n_skipped_destructive += 1
                return False
        # Dead (etf, axis) pair exclusion: if any value of an axis on this ETF
        # has been confirmed inert, ALL values on that pair are likely inert.
        # Generalizes the value-level filter to axis-level (R2582 audit:
        # pwb dd_haircut_0_5 NOOP → pwb dd_haircut_{0_3,0_4,0_7} also NOOP).
        if kind != 'VRFY' and self._dead_pairs:
            # Use same parsing as db_behavioral_noop_signatures so keys match.
            combined2 = f'{axis_name}_{val_name}' if val_name else axis_name
            if '_' in combined2:
                pair_axis = combined2.rsplit('_', 1)[0]
            else:
                pair_axis = combined2
            if (etf, pair_axis) in self._dead_pairs:
                self.n_skipped_dead_pair += 1
                return False
            for lever in changes.keys():
                if (etf, lever) in self._dead_pairs:
                    self.n_skipped_dead_pair += 1
                    return False
        # Axis-NOOP exclusion (2026-05-15): bans (etf, axis_class) where ≥2
        # distinct values were all behavioral-NOOP. R3066 audit: 49% of specs
        # (BFSW/BTI/STX) returned exact NOOP — single-value filter only catches
        # one at a time, axis-level prevents wasting another round on a sibling
        # value (e.g., tp_grow_110 dead → tp_grow_105 also dead next round).
        if kind != 'VRFY' and (self._noop_etf_axes or self._destr_etf_axes or self._inert_etf_axes):
            for lever in changes.keys():
                # Map lever to axis_class: tp/sl/wt/cf/sf/ef/xf are direct,
                # asl→atr_sl, dh→dd_haircut, etc.
                ac_map = {'asl': 'atr_sl', 'dh': 'dd_haircut',
                          'mm': 'month_mask', 'month_mask': 'month_mask',
                          'vol_max': 'vol_max', 'vmax': 'vol_max'}
                axis_class_key = ac_map.get(lever, lever)
                if (etf, axis_class_key) in self._noop_etf_axes:
                    self.n_skipped_axis_noop += 1
                    return False
                if (etf, axis_class_key) in self._destr_etf_axes:
                    self.n_skipped_axis_destr += 1
                    return False
                if (etf, axis_class_key) in self._inert_etf_axes:
                    self.n_skipped_axis_noop += 1
                    return False
        try:
            c = make_spec(etf, changes, salt, self.base)
        except ValueError:
            return False
        if c is None:
            return False
        h = codehash(c)
        if h in self._noop_hashes or h in self._spec_hashes:
            return False
        nm = f's002_{kind}_{etf}_{axis_name}_{val_name}_rv{salt_idx}_{self.batch}'
        hyp = f'{kind} {etf} {changes} (axis={axis_name})'
        self.specs.append((nm, c, hyp, self.based_on, prio))
        self._spec_hashes.add(h)
        return True

    def add_probes(self, probes: Iterable[Probe], salts: Sequence[int] | None = None,
                   prio: int = 2, prefix: str | None = None,
                   max_specs: int | None = None,
                   max_probes: int | None = None) -> int:
        """Add probes; salts × probes = specs.

        max_specs caps total specs added (across all salts).
        max_probes caps unique probes used.
        """
        salts = list(salts or self.salts)
        added = 0
        probes_used = 0
        for p in probes:
            if max_probes is not None and probes_used >= max_probes:
                break
            if max_specs is not None and added >= max_specs:
                break
            if self.remaining <= 0:
                break
            kind = prefix or p.kind
            this_probe_added = 0
            for i, s in enumerate(salts, 1):
                if self.remaining <= 0:
                    break
                if max_specs is not None and added >= max_specs:
                    break
                if self._add_one(kind, p.etf, p.axis, p.val, p.changes, s, i, prio):
                    added += 1
                    this_probe_added += 1
            if this_probe_added > 0:
                probes_used += 1
        return added

    def add_verify(self, etf: str, changes: dict, label: str, prio: int = 1,
                   salts: Sequence[int] | None = None) -> int:
        salts = list(salts or self.salts)
        added = 0
        for i, s in enumerate(salts, 1):
            if self.remaining <= 0:
                break
            if self._add_one('VRFY', etf, label, 'verify',
                             changes, s, i, prio):
                added += 1
        return added

    def queue(self) -> tuple[int, int]:
        db = storage.connect(DB_PATH)
        db.execute('PRAGMA busy_timeout=60000')
        existing_names, existing_hashes = db_existing_names_hashes()
        ins = skp = 0
        for nm, code, hyp, bo, prio in self.specs:
            if nm in existing_names:
                skp += 1
                continue
            ch = codehash(code)
            if ch in existing_hashes:
                skp += 1
                continue
            try:
                db.execute(
                    "INSERT INTO backtest_queue (name,code,description,hypothesis,"
                    "based_on,batch,priority,status,code_hash) "
                    "VALUES (?,?,?,?,?,?,?,'queued',?)",
                    (nm, code, hyp, hyp, bo, self.batch, prio, ch))
                ins += 1
                existing_hashes.add(ch)
            except storage.IntegrityError:
                skp += 1
        db.commit()
        db.close()
        return ins, skp

    def composition(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for nm, *_ in self.specs:
            m = re.match(r's002_(\w+?)_', nm)
            if m:
                out[m.group(1)] = out.get(m.group(1), 0) + 1
        return out


# ─── Bake helper ───────────────────────────────────────────────────────────
def apply_bake(base_path: str, etf: str, changes: dict, label: str) -> str:
    """Backup base, apply changes to etf cfg, return path of backup."""
    ts = _dt.date.today().isoformat().replace('-', '')
    bak = f"{base_path}.bak_pre_{etf}_{label}_bake_{ts}"
    if not os.path.exists(bak):
        shutil.copy2(base_path, bak)
    code = open(base_path).read()
    new_code = mut_etf(changes, etf, code)
    if new_code is None:
        raise RuntimeError(f"etf {etf} not found in {base_path}")
    if codehash(new_code) == codehash(code):
        raise RuntimeError("bake produced identical code (no-op)")
    with open(base_path, 'w') as f:
        f.write(new_code)
    return bak
