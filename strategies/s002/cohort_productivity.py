"""Cohort-level productivity tracking — analyze (indicator, lever) classes
across recent rounds and identify which classes are productive vs dead.

This is one level of abstraction above probe_history.py (which tracks
individual (etf, lever) pairs). Cohort-level signal lets us:
  - Skip probing dead-cohort levers (e.g., cf appears universally dead
    across all indicators — saving compute on entire axis families)
  - Favor probes on productive cohorts (e.g., hma + tp is the most
    productive class with +0.0064 historical max)

Use:
  from cohort_productivity import dead_cohort_pairs, cohort_stats
  dead = dead_cohort_pairs(DB_PATH, n_batches=8)  # set of (ind, lever)
"""
from __future__ import annotations
import re
import qc_storage as storage
from collections import defaultdict

_NAME_RE = re.compile(
    r's002_(?P<kind>[A-Z][A-Z0-9]+?)_(?P<etf>[a-z]{2,5})_(?P<rest>.+?)_rv\d+_'
)
_LEVER_FROM_HYP = re.compile(r"\{'(\w+)'")


def _lever_for(name: str, hyp: str | None) -> str | None:
    if hyp:
        m = _LEVER_FROM_HYP.search(hyp)
        if m:
            return m.group(1)
    return None


def _parse_etf_indicators(base_path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    code = open(base_path).read()
    for m in re.finditer(r"\s'([a-z]{2,5})':\s*\{([^}]+)\}", code, re.M):
        etf, body = m.group(1), m.group(2)
        if etf == 'vti':
            continue
        im = re.search(r"'i'\s*:\s*'(\w+)'", body)
        if im:
            out[etf] = im.group(1)
    return out


def cohort_stats(db_path: str, base_path: str, n_batches: int = 8,
                 baked_etfs: set[str] | None = None
                 ) -> dict[tuple[str, str], list[float]]:
    """Returns {(indicator, lever): [lift, ...]} from last n_batches.

    Excludes observations on baked_etfs (their cfg changed, observations stale).
    """
    baked_etfs = baked_etfs or set()
    etf_ind = _parse_etf_indicators(base_path)
    db = storage.connect(db_path)
    batches = [r[0] for r in db.execute(
        "SELECT DISTINCT batch FROM experiments "
        "WHERE batch LIKE 'gen_afql3b_div%' "
        "ORDER BY batch DESC LIMIT ?", (n_batches,)).fetchall()]
    out: dict[tuple[str, str], list[float]] = defaultdict(list)
    for b in batches:
        noop_avg = db.execute(
            "SELECT AVG(car_mdd) FROM experiments WHERE batch=? "
            "AND name LIKE '%NOOP%' AND car_mdd IS NOT NULL", (b,)).fetchone()[0]
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
            if etf in baked_etfs:
                continue
            lever = _lever_for(n, hyp)
            if lever is None:
                continue
            ind = etf_ind.get(etf)
            if not ind:
                continue
            out[(ind, lever)].append(cm - noop_avg)
    db.close()
    return out


def dead_cohort_pairs(stats: dict[tuple[str, str], list[float]],
                      eps: float = 0.0001, min_obs: int = 6
                      ) -> set[tuple[str, str]]:
    """A cohort (ind, lever) is dead if every observation has |lift| < eps
    AND we have ≥min_obs (high bar — cohorts are bigger groups).
    """
    out: set[tuple[str, str]] = set()
    for k, lifts in stats.items():
        if len(lifts) < min_obs:
            continue
        if max(abs(l) for l in lifts) < eps:
            out.add(k)
    return out


def alive_cohort_pairs(stats: dict[tuple[str, str], list[float]],
                       min_lift: float = 0.001
                       ) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for k, lifts in stats.items():
        if max(abs(l) for l in lifts) >= min_lift:
            out.add(k)
    return out


def expand_cohort_to_etf_pairs(cohort_pairs: set[tuple[str, str]],
                               base_path: str
                               ) -> set[tuple[str, str]]:
    """Map (indicator, lever) → set of (etf, lever) for ETFs in that cohort.

    Used to add cohort-dead pairs to the (etf, lever) exclusion set.
    """
    etf_ind = _parse_etf_indicators(base_path)
    out: set[tuple[str, str]] = set()
    for (ind, lever) in cohort_pairs:
        for etf, e_ind in etf_ind.items():
            if e_ind == ind:
                out.add((etf, lever))
    return out


def cohort_summary(stats: dict[tuple[str, str], list[float]]) -> dict:
    dead = dead_cohort_pairs(stats)
    alive = alive_cohort_pairs(stats)
    n_obs = sum(len(v) for v in stats.values())
    return {
        'n_cohort_pairs': len(stats),
        'n_obs': n_obs,
        'dead_cohorts': dead,
        'alive_cohorts': alive,
    }


def best_axis_per_indicator(stats: dict[tuple[str, str], list[float]],
                            min_lift: float = 0.0005
                            ) -> dict[str, str]:
    """For each indicator, find the lever with highest historical lift.

    Returns {indicator: lever}. Only includes indicators where some lever
    cleared min_lift threshold. Used to direct COLD probes toward the
    most productive axis for each ETF's cohort.
    """
    by_ind: dict[str, list[tuple[str, float]]] = {}
    for (ind, lever), lifts in stats.items():
        if not lifts:
            continue
        mx = max(lifts)
        by_ind.setdefault(ind, []).append((lever, mx))
    out: dict[str, str] = {}
    for ind, lst in by_ind.items():
        lst.sort(key=lambda x: -x[1])
        if lst and lst[0][1] >= min_lift:
            out[ind] = lst[0][0]
    return out
