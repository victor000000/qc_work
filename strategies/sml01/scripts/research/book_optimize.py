#!/usr/bin/env python3
"""BOOK-LEVEL OPTIMIZER (Calmar>8 campaign, 2026-06-14).

Reads the cached per-leg honest OOS equity series (results/series_cache_book3.json)
and pushes the cross-asset book Calmar via three CASH-LEGAL, CAUSAL, LEAK-FREE levers:
  1. WEIGHT grid-search over the simplex (max book Calmar).
  2. Book-level VOL-TARGET overlay: scale gross by clip(slow_vol/fast_vol, lo, 1) — de-lever
     into book turbulence using only PAST book returns. Never > 1 (cash, no leverage).
  3. Book-level DRAWDOWN-BREAKER: cut gross when the book is in drawdown beyond a band.

All overlays use only past combined-book returns -> no look-ahead. Gross capped at 1.
"""
import json, os, math, itertools
from lb.paths import ROOT as _LBROOT

CACHE = str(_LBROOT / "results" / "series_cache_book3.json")
SOLO = {"GLD": 3.97, "USO": 2.42, "DXJ": 2.75}


def metrics(rets, ppy):
    eq = [1.0]
    for r in rets:
        eq.append(eq[-1] * (1.0 + r))
    peak, mdd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v); mdd = max(mdd, (peak - v) / peak)
    yrs = len(rets) / ppy
    cagr = eq[-1] ** (1.0 / yrs) - 1.0 if yrs > 0 and eq[-1] > 0 else 0.0
    m = sum(rets) / len(rets)
    sd = (sum((x - m) ** 2 for x in rets) / (len(rets) - 1)) ** 0.5 if len(rets) > 1 else 0.0
    sharpe = m / sd * math.sqrt(ppy) if sd > 1e-12 else 0.0
    return dict(calmar=(cagr / mdd if mdd > 1e-6 else 0.0), cagr=cagr * 100, mdd=mdd * 100, sharpe=sharpe)


def leg_rets(series, ts, n):
    return [(series[n][ts[i]] / series[n][ts[i - 1]] - 1.0 if series[n][ts[i - 1]] > 0 else 0.0)
            for i in range(1, len(ts))]


def book_rets(legrets, names, w):
    L = len(legrets[names[0]])
    return [sum(w[n] * legrets[n][i] for n in names) for i in range(L)]


def voltarget(rets, fast=10, slow=60, lo=0.5):
    """Causal book-level vol-target: gross_t = clip(slow_vol_{<t}/fast_vol_{<t}, lo, 1)."""
    out = []
    for i in range(len(rets)):
        if i < slow + 2:
            out.append(rets[i]); continue
        f = (sum((x) ** 2 for x in rets[i - fast:i]) / fast) ** 0.5
        s = (sum((x) ** 2 for x in rets[i - slow:i]) / slow) ** 0.5
        g = min(1.0, max(lo, s / f)) if f > 1e-12 else 1.0
        out.append(g * rets[i])
    return out


def ddbreaker(rets, band=0.015, cut=0.5):
    """Causal drawdown-breaker: when book DD (from running peak, using PAST returns) exceeds
    band, scale next-bar exposure by cut. Leak-free (peak/DD computed from realized past)."""
    out = []
    eq, peak = 1.0, 1.0
    for r in rets:
        dd = (peak - eq) / peak if peak > 0 else 0.0
        g = cut if dd > band else 1.0
        rr = g * r
        out.append(rr)
        eq *= (1.0 + rr); peak = max(peak, eq)
    return out


def main():
    cache = json.load(open(CACHE))
    names = [n for n in ["GLD", "USO", "DXJ"] if n in cache and len(cache[n]) > 50]
    common = sorted(set.intersection(*[set(cache[n].keys()) for n in names]), key=lambda x: int(x))
    span = (int(common[-1]) - int(common[0])) / (365.25 * 86400.0)
    ppy = len(common) / span
    legrets = {n: leg_rets(cache, common, n) for n in names}
    print(f"legs={names}  {len(common)} pts  ppy~{ppy:.1f}\n")

    # baseline schemes
    base = {}
    base["equal"] = {n: 1.0 / len(names) for n in names}
    s2 = {n: SOLO[n] ** 2 for n in names}; t = sum(s2.values()); base["calmar^2"] = {n: s2[n] / t for n in names}
    print("=== baseline weight schemes ===")
    for sc, w in base.items():
        m = metrics(book_rets(legrets, names, w), ppy)
        print(f"  {sc:10s} Cal={m['calmar']:6.3f} CAGR={m['cagr']:5.2f}% MaxDD={m['mdd']:4.2f}% Sh={m['sharpe']:4.2f}  {' '.join(f'{n}={w[n]:.2f}' for n in names)}")

    # 1. WEIGHT grid-search (step 0.05 over simplex)
    print("\n=== weight grid-search (max Calmar) ===")
    bestw = None
    step = 20  # 1/0.05
    grid = []
    if len(names) == 3:
        for a in range(step + 1):
            for b in range(step + 1 - a):
                c = step - a - b
                grid.append((a / step, b / step, c / step))
    else:
        for a in range(step + 1):
            grid.append((a / step, (step - a) / step))
    for combo in grid:
        w = {names[i]: combo[i] for i in range(len(names))}
        m = metrics(book_rets(legrets, names, w), ppy)
        if bestw is None or m['calmar'] > bestw[1]:
            bestw = (w, m['calmar'], m)
    w, _, m = bestw
    print(f"  BEST weights {' '.join(f'{n}={w[n]:.2f}' for n in names)} -> Cal={m['calmar']:.3f} CAGR={m['cagr']:.2f}% MaxDD={m['mdd']:.2f}% Sh={m['sharpe']:.2f}")

    # 2+3. overlays on the best-weight book
    br = book_rets(legrets, names, w)
    print("\n=== book-level overlays on best-weight book (cash, gross<=1, causal) ===")
    m0 = metrics(br, ppy); print(f"  none           Cal={m0['calmar']:6.3f} CAGR={m0['cagr']:5.2f}% MaxDD={m0['mdd']:4.2f}% Sh={m0['sharpe']:4.2f}")
    for lo in (0.3, 0.5, 0.7):
        m1 = metrics(voltarget(br, lo=lo), ppy)
        print(f"  voltarget lo={lo} Cal={m1['calmar']:6.3f} CAGR={m1['cagr']:5.2f}% MaxDD={m1['mdd']:4.2f}% Sh={m1['sharpe']:4.2f}")
    for band, cut in [(0.010, 0.5), (0.015, 0.5), (0.015, 0.0), (0.020, 0.5)]:
        m2 = metrics(ddbreaker(br, band=band, cut=cut), ppy)
        print(f"  ddbreak b={band} cut={cut} Cal={m2['calmar']:6.3f} CAGR={m2['cagr']:5.2f}% MaxDD={m2['mdd']:4.2f}% Sh={m2['sharpe']:4.2f}")
    # combined: voltarget then ddbreaker
    mc = metrics(ddbreaker(voltarget(br, lo=0.5), band=0.015, cut=0.5), ppy)
    print(f"  voltarget+ddbreak Cal={mc['calmar']:6.3f} CAGR={mc['cagr']:5.2f}% MaxDD={mc['mdd']:4.2f}% Sh={mc['sharpe']:4.2f}")

    # split-half stability of the best book
    h = len(br) // 2
    me = metrics(br[:h], ppy); ml = metrics(br[h:], ppy)
    print(f"\nsplit-half best book: early Cal={me['calmar']:.2f} | late Cal={ml['calmar']:.2f}")


if __name__ == "__main__":
    main()
