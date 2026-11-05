#!/usr/bin/env python3
"""CROSS-ASSET 3-LEG BOOK (2026-06-14, Calmar>8 campaign).

Combine the 3 HONEST single-asset Wang champions (GLD gold-drift / USO oil-reversion /
DXJ Japan-timing — 3 distinct mechanisms = decorrelated) into ONE cash book (gross<=1,
NO leverage). Each leg is its own honest OOS equity series (leak-free); the book is a
read-only daily-return combine (no look-ahead). Report book Calmar under several weight
schemes + pairwise correlations (the diversification multiplier toward Calmar>8).

Series cached to results/series_cache_book3.json so re-runs are cheap.
"""
import sys, os, json, math
from lb.harness.orchestrator import render_train_config, render_infer_cell
from lb.harness.qc_client import submit_and_wait, _qc_post
from lb.harness.constants import QC_PROJECT_ID
from lb.harness.psuf import cell_suffix
from lb.paths import ROOT as _LBROOT

CACHE = str(_LBROOT / "results" / "series_cache_book3.json")


def _cell_key(cfg):
    prefix = (f"{cfg['axis']}_{cfg['labeler'].replace('+','_x_')}_{cfg['sizing']}"
              f"_t{int(round(float(cfg['thresh'])*100))}")
    return prefix + cell_suffix(cfg)


# 3 honest champions (corrected 2026-06-14 post-audit: GLD = the EXACT stored crown
# trend_leg+regime_gmm + reduce=vae + n_components=16 on the base panel, ~3.87 — NOT
# the ker/default-reduce config that produced the phantom 2.79 restatement).
CFG = {
    "GLD": dict(ticker="GLD", axis="logdollar", labeler="trend_leg+regime_gmm", thresh=0.40, sizing="dd_overlay", reduce="vae", n_components=16, features="base"),
    "USO": dict(ticker="USO", axis="logdollar", labeler="revert",               thresh=0.45, sizing="cdf_plain"),
    "DXJ": dict(ticker="DXJ", axis="logdollar", labeler="ker",                   thresh=0.45, sizing="ls_overlay"),
}
SOLO = {"GLD": 3.97, "USO": 2.42, "DXJ": 2.75}


def equity_map(bid):
    r = _qc_post("/backtests/chart/read", {"projectId": QC_PROJECT_ID, "backtestId": bid,
                 "name": "Strategy Equity", "count": 5000, "start": 0, "end": 2000000000})
    if not r.get("success"):
        return {}
    vals = ((r.get("chart") or {}).get("series") or {}).get("Equity", {}).get("values") or []
    return {str(int(row[0])): float(row[-1]) for row in vals if isinstance(row, list) and len(row) >= 2 and row[-1] > 0}


def get_series(name):
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    if name in cache and len(cache[name]) > 50:
        print(f"[{name}] cached {len(cache[name])} pts", flush=True)
        return cache[name]
    cfg = CFG[name]
    cell = _cell_key(cfg)
    print(f"[{name}] train ... (cell={cell})", flush=True)
    tcode, extra = render_train_config(cfg)

    def _retry(fn, label, tries=6):
        import time as _t
        for k in range(tries):
            res, st = fn()
            if st == "completed":
                return res, st
            msg = str(res.get("error", res.get("status", "")))[:80] if isinstance(res, dict) else ""
            print(f"[{name}] {label} attempt {k+1}/{tries} -> {st} ({msg}); re-queue", flush=True)
            _t.sleep(25)
        return res, st

    _, st = _retry(lambda: submit_and_wait(tcode, f"book3_{name}_train", timeout_s=600, extra_files=extra), "train")
    if st != "completed":
        print(f"[{name}] train failed: {st}"); return None
    print(f"[{name}] infer ...", flush=True)
    bt, st2 = _retry(lambda: submit_and_wait(render_infer_cell(name, cell), f"book3_{name}_infer", timeout_s=360), "infer")
    if st2 != "completed":
        print(f"[{name}] infer failed: {st2}"); return None
    em = equity_map(bt.get("backtestId"))
    if len(em) < 50:
        print(f"[{name}] series too short ({len(em)})"); return None
    cache[name] = em
    json.dump(cache, open(CACHE, "w"))
    print(f"[{name}] cached {len(em)} pts", flush=True)
    return em


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
    calmar = cagr / mdd if mdd > 1e-6 else 0.0
    return dict(calmar=calmar, cagr=cagr * 100, mdd=mdd * 100, sharpe=sharpe)


def leg_rets(series, ts, n):
    return [(series[n][ts[i]] / series[n][ts[i - 1]] - 1.0 if series[n][ts[i - 1]] > 0 else 0.0)
            for i in range(1, len(ts))]


def book_rets(legrets, names, w):
    L = len(legrets[names[0]])
    return [sum(w[n] * legrets[n][i] for n in names) for i in range(L)]


def corr(a, b):
    n = len(a); ma = sum(a) / n; mb = sum(b) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    va = sum((x - ma) ** 2 for x in a); vb = sum((x - mb) ** 2 for x in b)
    return cov / math.sqrt(va * vb) if va > 0 and vb > 0 else 0.0


def main():
    series = {}
    for n in CFG:
        s = get_series(n)
        if s:
            series[n] = s
    if len(series) < 2:
        print("too few series"); return
    common = sorted(set.intersection(*[set(s.keys()) for s in series.values()]), key=lambda x: int(x))
    span = (int(common[-1]) - int(common[0])) / (365.25 * 86400.0)
    ppy = len(common) / span
    names = list(series.keys())
    print(f"\n{len(common)} common timestamps, ppy~{ppy:.1f}, legs={names}\n", flush=True)

    legrets = {n: leg_rets(series, common, n) for n in names}

    # solo (on common grid)
    print("=== SOLO legs (common grid) ===")
    vols = {}
    for n in names:
        m = metrics(legrets[n], ppy)
        vols[n] = (sum((x - sum(legrets[n]) / len(legrets[n])) ** 2 for x in legrets[n]) / len(legrets[n])) ** 0.5
        print(f"  {n}: Calmar={m['calmar']:6.3f} CAGR={m['cagr']:6.2f}% MaxDD={m['mdd']:5.2f}% Sharpe={m['sharpe']:5.2f}")

    print("\n=== pairwise return correlations (decorrelation = diversification fuel) ===")
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            print(f"  corr({names[i]},{names[j]}) = {corr(legrets[names[i]], legrets[names[j]]):+.3f}")

    # weight schemes
    schemes = {}
    schemes["equal"] = {n: 1.0 / len(names) for n in names}
    s2 = {n: SOLO[n] ** 2 for n in names}; tot = sum(s2.values()); schemes["calmar^2"] = {n: s2[n] / tot for n in names}
    iv = {n: 1.0 / vols[n] if vols[n] > 0 else 0.0 for n in names}; tot = sum(iv.values()); schemes["inverse-vol"] = {n: iv[n] / tot for n in names}

    print("\n=== BOOK (gross=1, cash, no leverage) ===")
    print(f"{'scheme':14s} {'Calmar':>7s} {'CAGR%':>6s} {'MaxDD%':>7s} {'Sharpe':>7s}   weights")
    best = None
    for sc, w in schemes.items():
        m = metrics(book_rets(legrets, names, w), ppy)
        wl = " ".join(f"{n}={w[n]:.2f}" for n in names)
        print(f"{sc:14s} {m['calmar']:7.3f} {m['cagr']:6.2f} {m['mdd']:7.2f} {m['sharpe']:7.3f}   {wl}")
        if best is None or m['calmar'] > best[1]:
            best = (sc, m['calmar'], m)
    print(f"\nBEST scheme: {best[0]}  Calmar={best[1]:.3f}  (vs best solo {max(SOLO.values())})")
    print(f"Diversification multiplier: {best[1] / max(SOLO.values()):.2f}x   |   gap to Calmar 8: {8.0 - best[1]:.2f}")


if __name__ == "__main__":
    main()
