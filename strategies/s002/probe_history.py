"""Probe history analysis — detect dead (etf, lever) pairs from recent rounds.

A pair is DEAD when every probe of it in the last N rounds produced
|lift| < EPS. Excluding these from future probe generation reclaims
compute for live pairs.

Pairs are auto-invalidated when an ETF's cfg changes (a bake on that ETF).
We detect this by hashing the ETF block from the base file and only
counting observations from rounds whose probes used the same ETF cfg.

For simplicity (and because most rounds change at most 1-3 ETFs per bake),
we use a heuristic: collect observations from the last N rounds, but
discard observations for ETFs whose cfg in the base file differs from
the cfg in the spec at observation time. Since we don't store per-spec
ETF cfg, we approximate by skipping any (etf, lever) where the ETF was
itself baked since the round was completed.
"""
from __future__ import annotations
import re
import qc_storage as storage
from collections import defaultdict
from typing import NamedTuple

EPS = 0.0001
MIN_OBS = 2  # ≥2 distinct probes needed to flag dead

_NAME_RE = re.compile(
    r's002_(?P<kind>[A-Z][A-Z0-9]+?)_(?P<etf>[a-z]{2,5})_(?P<rest>.+?)_rv\d+_'
)
_LEVER_FROM_HYP = re.compile(r"\{'(\w+)'")
_LEVER_FROM_NAME = re.compile(
    r's002_(?:DIV|DV2|DV3|C2D|VRFY|AT|RT|COLD)_[a-z]+_(\w+?)_'
)


class PairStat(NamedTuple):
    etf: str
    lever: str
    n_probes: int
    max_abs_lift: float
    avg_lift: float


def _lever_for(name: str, hyp: str | None) -> str | None:
    if hyp:
        m = _LEVER_FROM_HYP.search(hyp)
        if m:
            return m.group(1)
    m = _LEVER_FROM_NAME.search(name)
    return m.group(1) if m else None


def collect_recent_pair_stats(db_path: str, n_batches: int = 5,
                              recent_baked_etfs: set[str] | None = None
                              ) -> dict[tuple[str, str], list[float]]:
    """Returns {(etf, lever): [lift, lift, ...]} from last n_batches.

    recent_baked_etfs are dropped — observations on a baked ETF are stale.
    """
    recent_baked_etfs = recent_baked_etfs or set()
    db = storage.connect(db_path)
    batches = [r[0] for r in db.execute(
        "SELECT DISTINCT batch FROM experiments "
        "WHERE batch LIKE 'gen_afql3b_div%' "
        "ORDER BY batch DESC LIMIT ?", (n_batches,)).fetchall()]
    out: dict[tuple[str, str], list[float]] = defaultdict(list)
    for b in batches:
        noop_avg = db.execute(
            "SELECT AVG(car_mdd) FROM experiments WHERE batch=? AND name LIKE '%NOOP%' "
            "AND car_mdd IS NOT NULL", (b,)).fetchone()[0]
        if noop_avg is None:
            continue
        rows = db.execute(
            "SELECT name, car_mdd, hypothesis FROM experiments WHERE batch=? "
            "AND name NOT LIKE '%NOOP%' AND car_mdd IS NOT NULL", (b,)).fetchall()
        for n, cm, hyp in rows:
            m = _NAME_RE.match(n)
            if m is None:
                continue
            etf = m.group('etf')
            if etf in recent_baked_etfs:
                continue
            lever = _lever_for(n, hyp)
            if lever is None:
                continue
            out[(etf, lever)].append(cm - noop_avg)
    db.close()
    return out


def dead_pairs(pair_stats: dict[tuple[str, str], list[float]],
               eps: float = EPS, min_obs: int = MIN_OBS
               ) -> set[tuple[str, str]]:
    """Return pairs whose every observation has |lift| < eps and have ≥min_obs."""
    out: set[tuple[str, str]] = set()
    for k, lifts in pair_stats.items():
        if len(lifts) < min_obs:
            continue
        if max(abs(l) for l in lifts) < eps:
            out.add(k)
    return out


def toxic_pairs(pair_stats: dict[tuple[str, str], list[float]],
                avg_floor: float = -0.05, min_obs: int = MIN_OBS
                ) -> set[tuple[str, str]]:
    """Return pairs whose AVERAGE lift is below avg_floor (catastrophic regressions)."""
    out: set[tuple[str, str]] = set()
    for k, lifts in pair_stats.items():
        if len(lifts) < min_obs:
            continue
        if sum(lifts) / len(lifts) < avg_floor:
            out.add(k)
    return out


def alive_pair_stats(pair_stats: dict[tuple[str, str], list[float]],
                     min_lift: float = 0.001
                     ) -> list[PairStat]:
    out: list[PairStat] = []
    for (etf, lever), lifts in pair_stats.items():
        if max(abs(l) for l in lifts) >= min_lift:
            out.append(PairStat(etf, lever, len(lifts),
                                max(abs(l) for l in lifts),
                                sum(lifts) / len(lifts)))
    out.sort(key=lambda p: -p.max_abs_lift)
    return out


def summary(pair_stats: dict[tuple[str, str], list[float]]) -> dict:
    dead = dead_pairs(pair_stats)
    toxic = toxic_pairs(pair_stats)
    alive = [k for k, lifts in pair_stats.items()
             if max(abs(l) for l in lifts) >= 0.001 and k not in toxic]
    borderline = [k for k, lifts in pair_stats.items()
                  if 0.0001 <= max(abs(l) for l in lifts) < 0.001]
    n_obs = sum(len(v) for v in pair_stats.values())
    return {
        'n_pairs': len(pair_stats),
        'n_obs': n_obs,
        'dead': len(dead),
        'toxic': len(toxic),
        'alive': len(alive),
        'borderline': len(borderline),
        'dead_set': dead,
        'toxic_set': toxic,
        'excluded_set': dead | toxic,
    }
