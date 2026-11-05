#!/usr/bin/env python3
"""Audit a completed s002 round and emit:
  - NOOP avg, salt-cluster sanity check
  - Top probes by lift
  - Bake candidates (multi-salt confirmed lifts ≥ THRESHOLD)
  - Sub-threshold-confirmed probes (carry as VRFY in next round)
  - Suggested commands for next round

Usage:
  python3 strategies/s002/audit_round.py 2511b
  python3 strategies/s002/audit_round.py 2512 --threshold 0.001 --min-salts 3
  python3 strategies/s002/audit_round.py 2512 --emit-vrfy   # one-liner per VRFY slot
"""
from __future__ import annotations
import argparse
import re
import qc_storage as storage
import sys
import os
from collections import defaultdict
from statistics import mean, pstdev

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from round_lib import DB_PATH  # noqa: E402

# Probe naming: s002_<KIND>_<etf>_<axis_or_label>_<val>_rv<i>_<batch>
PROBE_RE = re.compile(
    r's002_(?P<kind>[A-Z][A-Z0-9]+?)_(?P<etf>[a-z]{2,5})_(?P<rest>.+?)_rv(?P<rv>\d+)_'
)

THRESHOLD_DEFAULT = 0.0005
MIN_SALTS_DEFAULT = 3


def parse_probe_name(name: str) -> dict | None:
    m = PROBE_RE.match(name)
    if not m:
        return None
    return {'kind': m.group('kind'), 'etf': m.group('etf'),
            'rest': m.group('rest'), 'rv': int(m.group('rv'))}


def load_round(batch: str) -> tuple[list[float], list[tuple[str, float, str]]]:
    """Returns (noop_car_mdds, probes_rows). probes_rows = [(name, car_mdd, hypothesis)]."""
    db = storage.connect(DB_PATH)
    rows = db.execute(
        "SELECT name, car_mdd, hypothesis FROM experiments "
        "WHERE batch=? AND car_mdd IS NOT NULL", (batch,)).fetchall()
    db.close()
    noops = [cm for n, cm, _ in rows if 'NOOP' in n]
    probes = [(n, cm, h) for n, cm, h in rows if 'NOOP' not in n]
    return noops, probes


def cluster_probes(probes: list[tuple[str, float, str]]) -> dict[tuple, list]:
    """Group probes by (kind, etf, rest) — collect car_mdds across salts."""
    clusters: dict[tuple, list] = defaultdict(list)
    for n, cm, hyp in probes:
        p = parse_probe_name(n)
        if p is None:
            continue
        key = (p['kind'], p['etf'], p['rest'])
        clusters[key].append((p['rv'], cm, hyp))
    return clusters


def audit(batch: str, threshold: float, min_salts: int) -> dict:
    noops, probes = load_round(batch)
    if not noops:
        return {'error': f'no NOOPs found in {batch}', 'batch': batch}

    noop_avg = mean(noops)
    noop_std = pstdev(noops) if len(noops) > 1 else 0.0

    clusters = cluster_probes(probes)

    # Score each cluster
    cluster_stats = []
    for key, vals in clusters.items():
        kind, etf, rest = key
        cms = [cm for _, cm, _ in vals]
        n_salts = len(cms)
        avg_cm = mean(cms)
        lift = avg_cm - noop_avg
        max_lift = max(cms) - noop_avg
        min_lift = min(cms) - noop_avg
        std = pstdev(cms) if n_salts > 1 else 0.0
        # 2026-05-17 salt-bias defense: count salts strictly above NOOP
        # to filter "1 lift / 3 specs" single-salt outliers from VRFY queue.
        n_above_noop = sum(1 for cm in cms if cm - noop_avg > 0.001)
        hyp = vals[0][2]
        cluster_stats.append({
            'kind': kind, 'etf': etf, 'rest': rest,
            'n_salts': n_salts, 'avg': avg_cm, 'lift': lift,
            'max_lift': max_lift,
            'min_lift': min_lift,
            'n_above_noop': n_above_noop,
            'std': std, 'hyp': hyp,
        })

    cluster_stats.sort(key=lambda c: -c['lift'])

    # Bake candidates: lift ≥ threshold, salt-stable, ≥min_salts
    bakes = [
        c for c in cluster_stats
        if c['lift'] >= threshold and c['n_salts'] >= min_salts and c['std'] < 0.001
    ]

    # 2026-05-16: skip sub-thresh VRFYs when NOOP itself is bimodal (drift round).
    # On drift rounds (noop_std > 0.005), single-round lifts are dominated by
    # salt-set noise; sub-thresh candidates become spurious. ~4 of last 15 rounds
    # hit drift. Anti-stale filter cleans them next round, but skipping at source
    # saves 4-8 specs per drift round.
    noop_is_drift = noop_std > 0.005
    # Sub-threshold confirmed (VRFY-worthy): 0.0002 ≤ lift < threshold, ≥3 salts
    vrfys = [] if noop_is_drift else [
        c for c in cluster_stats
        if 0.0002 <= c['lift'] < threshold and c['n_salts'] >= 3 and c['std'] < 0.0005
        and c['kind'] not in ('NOOP', 'VBAKE')
    ]
    # 2026-05-15 (R3093 audit): variance-trap candidates — lift hits BAKE hard
    # threshold (+0.001 raised from +0.0005) but std too high for confident bake.
    # Auto-VRFY them so next round adds salts. Without this, igv wt_grow_105
    # (+0.00246 × 3, std=0.00123 → BAKE-307) would have been dropped.
    # 2026-05-15 R3122 30m: lowered lift threshold from 0.001 to threshold (0.0005)
    # to catch the [0.0005, 0.001) × high-std GAP. R3122 sub:tp_grow_120pct
    # +0.00087 × 3 std=0.00123 fell in this gap and was never carried as VRFY.
    # Tightened by also requiring max_lift ≥ +0.001 (at least one strong salt)
    # to filter pure-noise candidates.
    # 2026-05-16: also require min_lift >= -0.005 — same salt-safety as
    # cross_round_cumulative. R3300 prf cb had 2/4 negative salts (-0.007)
    # but avg passed threshold — variance_trap kept emitting prf cb VRFY
    # × 4 rounds despite salt-destructive risk.
    variance_trap = [
        c for c in cluster_stats
        if c['lift'] >= threshold and c['n_salts'] >= 3 and c['std'] >= 0.001
        and c.get('max_lift', c['lift']) >= 0.001
        and c.get('min_lift', 0) >= -0.005
        # 2026-05-17 salt-bias defense: require ≥2 salts above NOOP.
        # Last 20 rounds: 8/8 auto-VRFYs from 1-lift/3-spec candidates
        # FAILED (vbr/iyz/dem/sptm/jkh/efg/ief/agg) = 32 wasted backtests.
        # Salt-bias map: 6 candidates on rv1, 2 on rv2, 2 on rv3 — all
        # variance not real. Require 2+ above-NOOP salts in same probe.
        and c.get('n_above_noop', 0) >= 2
        and c['kind'] not in ('NOOP', 'VBAKE')
    ]
    # 2026-05-16: strong-lift partial salts (n=2 with clean +0.003+ signal).
    # BAKE-311 case: ewc e_grow_105pct had n=2 at +0.00429 std=0 in R3180
    # (rv2 timed out). Strict bake needs n≥3; missed pathway. Now carry as
    # VRFY when lift is exceptionally strong (≥+0.003) with std=0.
    strong_partial = [
        c for c in cluster_stats
        if c['lift'] >= 0.003 and c['n_salts'] >= 2 and c['std'] < 0.001
        and c['kind'] not in ('NOOP', 'VBAKE')
    ]
    # Add to vrfys for cross-round salt accumulation
    seen_kv = {(v['etf'], v['hyp']) for v in vrfys}
    for c in variance_trap + strong_partial:
        if (c['etf'], c['hyp']) not in seen_kv:
            vrfys.append(c)

    return {
        'batch': batch,
        'noop_avg': noop_avg, 'noop_std': noop_std, 'noop_n': len(noops),
        'n_clusters': len(cluster_stats),
        'top': cluster_stats[:10],
        'bakes': bakes,
        'vrfys': vrfys,
    }


def changes_from_hypothesis(hyp: str) -> dict | None:
    """Extract `{'tp': 0.15}` style dict from hypothesis like 'DIV ewg {'tp': 0.135} (axis=tp_grow)'.

    Fallback: extract from arrow notation 'wt 0.055→0.035' for old-format hypotheses.
    """
    m = re.search(r"\{([^}]+)\}", hyp)
    if m:
        body = m.group(1)
        out: dict = {}
        for kv in re.finditer(r"'(\w+)'\s*:\s*([^,}]+)", body):
            k, v = kv.group(1), kv.group(2).strip()
            try:
                out[k] = float(v) if '.' in v else int(v)
            except ValueError:
                out[k] = v.strip("'\"")
        if out:
            return out
    # Fallback: ' <key> <oldval>→<newval> '
    m2 = re.search(r'\s(\w+)\s+([\d.]+)\s*→\s*([\d.]+)', hyp)
    if m2:
        k, _old, new = m2.group(1), m2.group(2), m2.group(3)
        try:
            return {k: float(new) if '.' in new else int(new)}
        except ValueError:
            pass
    # 2026-05-12: Fallback for UTNT/BTI format 'UTNT vti tp=0.096' or 'BTI ewj tp=0.123'
    m3 = re.search(r'\s(\w+)=([\d.]+)\s*$', hyp)
    if m3:
        k, v = m3.group(1), m3.group(2)
        try:
            return {k: float(v) if '.' in v else int(v)}
        except ValueError:
            pass
    return None


def emit_report(rep: dict, threshold: float) -> str:
    if 'error' in rep:
        return rep['error']
    lines = []
    lines.append(f"Round audit: {rep['batch']}")
    lines.append(f"  NOOP avg = {rep['noop_avg']:.4f}  (n={rep['noop_n']}, std={rep['noop_std']:.5f})")
    if rep['noop_std'] > 0.0005:
        lines.append(f"  ⚠ NOOP salt drift >0.0005 — investigate salt orthogonality")
    lines.append(f"  Probe clusters: {rep['n_clusters']}")
    lines.append('')
    lines.append('  Top 10 by lift:')
    for c in rep['top']:
        flag = '✓BAKE' if c['lift'] >= threshold and c['n_salts'] >= 3 and c['std'] < 0.001 else ''
        lines.append(f"    {c['lift']:+.5f}  {c['kind']:5s} {c['etf']:6s} {c['rest']:32s} "
                     f"(n={c['n_salts']}, std={c['std']:.5f}) {flag}")
    lines.append('')
    if rep['bakes']:
        lines.append(f"  ✓ BAKE candidates ({len(rep['bakes'])}):")
        for c in rep['bakes']:
            ch = changes_from_hypothesis(c['hyp']) or {}
            chs = ' '.join(f'{k}={v}' for k, v in ch.items())
            lines.append(f"    bake_round.py {c['etf']} {chs} --label tp  "
                         f"# +{c['lift']:.4f} across {c['n_salts']} salts")
    else:
        lines.append('  ✓ BAKE candidates: none')
    lines.append('')
    if rep['vrfys']:
        lines.append(f"  📋 Sub-threshold (carry as VRFY in next round, {len(rep['vrfys'])}):")
        for c in rep['vrfys']:
            ch = changes_from_hypothesis(c['hyp']) or {}
            chs = ','.join(f'{k}={v}' for k, v in ch.items())
            lines.append(f"    --vrfy '{c['etf']}:{chs}'  "
                         f"# +{c['lift']:.4f} n={c['n_salts']}")
    return '\n'.join(lines)


def emit_vrfy_args(rep: dict) -> str:
    """One-liner: --vrfy 'etf:k=v' --vrfy 'etf:k=v' ... for piping into queue_round."""
    out = []
    for c in rep.get('vrfys', []):
        ch = changes_from_hypothesis(c['hyp']) or {}
        chs = ','.join(f'{k}={v}' for k, v in ch.items())
        out.append(f"--vrfy '{c['etf']}:{chs}'")
    return ' '.join(out)


def cross_round_strong_signal(n_rounds: int = 30,
                              min_above_noop_rate: float = 0.7,
                              min_specs: int = 6,
                              min_avg_lift: float = 0.001) -> list[dict]:
    """Aggregates by (etf, lever, value) across last N rounds and surfaces
    candidates with statistically-strong elevation that single-round strict
    bake (std<0.001) misses.

    Criteria for bake-promotable signal:
    - ≥min_specs total specs across ≥2 rounds
    - ≥min_above_noop_rate fraction strictly above NOOP_max in their round
    - avg lift ≥ min_avg_lift
    - max lift ≥ +0.00262 (at least one full trade-win)

    Catches cases like igv wt_grow_105pct (6/6 above NOOP across R3103+R3110)
    where per-round std fails strict bake but cross-round evidence is
    overwhelming. Designed to break "no-bakes" droughts caused by quantized
    car_mdd values producing high std on partial-win rounds.
    """
    db = storage.connect(DB_PATH)
    batches = [r[0] for r in db.execute(
        "SELECT DISTINCT batch FROM experiments WHERE batch LIKE 'gen_afql3b_div%' "
        "ORDER BY batch DESC LIMIT ?", (n_rounds,)).fetchall()]
    aggr: dict[tuple, dict] = {}
    for b in batches:
        noop_rows = db.execute(
            "SELECT car_mdd FROM experiments WHERE batch=? "
            "AND name LIKE '%NOOP%' AND car_mdd IS NOT NULL", (b,)).fetchall()
        if not noop_rows: continue
        noop_max = max(v[0] for v in noop_rows)
        noop_avg = sum(v[0] for v in noop_rows) / len(noop_rows)
        rows = db.execute(
            "SELECT name, car_mdd, hypothesis FROM experiments WHERE batch=? "
            "AND name NOT LIKE '%NOOP%' AND car_mdd IS NOT NULL", (b,)).fetchall()
        for n, cm, hyp in rows:
            p = parse_probe_name(n)
            if p is None or p['kind'] in ('NOOP', 'VBAKE'):
                continue
            key = (p['etf'], p['kind'], p['rest'])
            d = aggr.setdefault(key, {
                'cms': [], 'noop_avgs': [], 'noop_maxes': [],
                'rounds': set(), 'hyp': hyp,
            })
            d['cms'].append(cm)
            d['noop_avgs'].append(noop_avg)
            d['noop_maxes'].append(noop_max)
            d['rounds'].add(b)
    db.close()
    out = []
    for (etf, kind, rest), d in aggr.items():
        n_specs = len(d['cms'])
        if n_specs < min_specs: continue
        if len(d['rounds']) < 2: continue
        above_noop = sum(1 for cm, mx in zip(d['cms'], d['noop_maxes']) if cm > mx)
        rate = above_noop / n_specs
        lifts = [cm - na for cm, na in zip(d['cms'], d['noop_avgs'])]
        avg_lift = sum(lifts) / n_specs
        max_lift = max(lifts)
        # 2026-05-16: deterministic-small-lift path (BAKE-312 itot pattern).
        # If ALL specs above NOOP_max with std≈0 and lift≥+0.0002 across ≥10
        # specs, treat as bake-eligible even if avg_lift < min_avg_lift.
        # This catches signals like itot tp=0.0709: 16 specs all at +0.00024
        # exactly (std=0 across rounds) — small magnitude but perfectly deterministic.
        lift_std = (sum((l - avg_lift)**2 for l in lifts) / n_specs) ** 0.5
        is_deterministic = (n_specs >= 10 and rate == 1.0 and lift_std < 0.0001
                            and avg_lift >= 0.0002)
        if not is_deterministic:
            if rate < min_above_noop_rate: continue
            if avg_lift < min_avg_lift: continue
            if max_lift < 0.00262 * 0.95: continue
        out.append({
            'etf': etf, 'kind': kind, 'rest': rest,
            'avg_lift': avg_lift, 'max_lift': max_lift,
            'n_specs': n_specs, 'above_noop': above_noop,
            'above_rate': rate, 'n_rounds': len(d['rounds']),
            'hyp': d['hyp'],
        })
    out.sort(key=lambda r: -r['above_rate'])
    return out


def cross_round_cumulative(n_rounds: int = 5,
                           cum_threshold: float = 0.001,
                           min_total_salts: int = 6) -> list[dict]:
    """Aggregate (etf, lever, value) lifts across last N rounds.

    Surfaces probes with sustained sub-threshold-but-positive signal —
    e.g., kxi atr_sl_2.0 at +0.00048 in R2535 might compound to +0.001
    across multiple rounds.

    Returns sorted list of {etf, key, lever, total_lift, n_salts, n_rounds}.
    """
    db = storage.connect(DB_PATH)
    batches = [r[0] for r in db.execute(
        "SELECT DISTINCT batch FROM experiments WHERE batch LIKE 'gen_afql3b_div%' "
        "ORDER BY batch DESC LIMIT ?", (n_rounds,)).fetchall()]
    # Aggregate by (etf, kind, rest) — same probe identity across rounds
    aggr: dict[tuple, dict] = {}
    for b in batches:
        noop = db.execute(
            "SELECT AVG(car_mdd) FROM experiments WHERE batch=? "
            "AND name LIKE '%NOOP%' AND car_mdd IS NOT NULL", (b,)).fetchone()[0]
        if noop is None:
            continue
        rows = db.execute(
            "SELECT name, car_mdd, hypothesis FROM experiments WHERE batch=? "
            "AND name NOT LIKE '%NOOP%' AND car_mdd IS NOT NULL", (b,)).fetchall()
        for n, cm, hyp in rows:
            p = parse_probe_name(n)
            if p is None or p['kind'] in ('NOOP', 'VBAKE'):
                continue
            key = (p['etf'], p['kind'], p['rest'])
            d = aggr.setdefault(key, {'lifts': [], 'rounds': set(), 'hyp': hyp})
            d['lifts'].append(cm - noop)
            d['rounds'].add(b)
    db.close()

    out = []
    for (etf, kind, rest), d in aggr.items():
        n_salts = len(d['lifts'])
        if n_salts < min_total_salts:
            continue
        lifts = d['lifts']
        avg_lift = sum(lifts) / n_salts
        max_lift = max(lifts)
        min_lift = min(lifts)
        # Cumulative-positive: avg lift is positive AND consistent across rounds
        if avg_lift < 0.0001:
            continue
        if max_lift < 0.0002:  # too weak even at peak
            continue
        # 2026-05-16: reject if ANY salt shows substantial negative lift —
        # risky to bake when some salts get hurt. R3274 30m caught ixp
        # tp_grow_105pct with 1 pos / 2 neg / 3 zero across rounds — avg
        # passed +0.00123 but min was -0.00738 (would destroy 2/6 salts).
        if min_lift < -0.0005:
            continue
        out.append({
            'etf': etf, 'kind': kind, 'rest': rest,
            'avg_lift': avg_lift, 'max_lift': max_lift,
            'n_salts': n_salts, 'n_rounds': len(d['rounds']),
            'hyp': d['hyp'],
        })
    out.sort(key=lambda r: -r['avg_lift'])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n', 1)[0])
    ap.add_argument('round_id', nargs='?', default=None,
                    help='Round number, batch name, or "cross" for cross-round cumulative')
    ap.add_argument('--threshold', type=float, default=THRESHOLD_DEFAULT)
    ap.add_argument('--min-salts', type=int, default=MIN_SALTS_DEFAULT)
    ap.add_argument('--emit-vrfy', action='store_true',
                    help='Emit only --vrfy args for next-round CLI')
    ap.add_argument('--cross', action='store_true',
                    help='Cross-round cumulative-evidence audit (last N rounds)')
    ap.add_argument('--n-rounds', type=int, default=5,
                    help='Rounds to aggregate when --cross is set')
    args = ap.parse_args(argv)

    if args.cross or args.round_id == 'cross':
        rep = cross_round_cumulative(n_rounds=args.n_rounds)
        print(f'Cross-round cumulative audit (last {args.n_rounds} rounds):')
        print(f'  candidates with avg_lift > 0.0001 and ≥6 salts: {len(rep)}')
        print()
        print(f"  {'etf':6s} {'kind':6s} {'probe':28s} {'avg':>8s} {'max':>8s} {'n_salt':>7s} {'rounds':>7s}")
        for r in rep[:20]:
            print(f"  {r['etf']:6s} {r['kind']:6s} {r['rest']:28s} "
                  f"{r['avg_lift']:>+.5f} {r['max_lift']:>+.5f} "
                  f"{r['n_salts']:>7d} {r['n_rounds']:>7d}")
        return 0
    if args.round_id is None:
        print("Usage: audit_round.py <round_id> | audit_round.py cross | audit_round.py --cross")
        return 1

    batch = (args.round_id if args.round_id.startswith('gen_')
             else f'gen_afql3b_div{args.round_id}')

    rep = audit(batch, args.threshold, args.min_salts)
    if args.emit_vrfy:
        print(emit_vrfy_args(rep))
    else:
        print(emit_report(rep, args.threshold))
    return 0


if __name__ == '__main__':
    sys.exit(main())
