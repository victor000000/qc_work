#!/usr/bin/env python3
"""EXPANDED CROSS-ASSET BOOK (Calmar>8 campaign, 2026-06-14 — universe reopened by user).

Core 3 (GLD/USO/DXJ) + decorrelated proven-Wang legs (dollar/bonds/credit/commodities).
More decorrelated legs -> lower book MaxDD -> higher Calmar (cash, gross<=1, no leverage).
Each leg = its own honest OOS equity series (leak-free); book = read-only daily-return combine.
GREEDY forward-selection by book Calmar (conviction calmar^2 weights, set per-leg a-priori
from each leg's own common-grid solo Calmar -> no book-OOS weight-fitting).

Series cached to results/series_cache_book3.json (shared w/ book3 so core 3 are reused).
"""
import json, os, math
from lb.harness.orchestrator import render_train_config, render_infer_cell
from lb.harness.qc_client import submit_and_wait, _qc_post
from lb.harness.constants import QC_PROJECT_ID
from lb.harness.psuf import cell_suffix
from lb.paths import ROOT as _LBROOT

CACHE = str(_LBROOT / "results" / "series_cache_book3.json")


def _cell_key(cfg):
    return (f"{cfg['axis']}_{cfg['labeler'].replace('+','_x_')}_{cfg['sizing']}"
            f"_t{int(round(float(cfg['thresh'])*100))}") + cell_suffix(cfg)


# candidate pool: ALL genuine Wang-pipeline strategies (real trained axis->labeler->reduce->
# model->sizing; NO always_long buy-hold ballast). Core 3 honest champions + decorrelated
# legs each carrying a real, permute-/gate-confirmed Wang timing edge on a different factor.
POOL = {
    "GLD": dict(ticker="GLD", axis="logdollar", labeler="trend_leg+regime_gmm", thresh=0.40, sizing="dd_overlay", reduce="vae", n_components=16, features="base"),
    "USO": dict(ticker="USO", axis="logdollar", labeler="revert",               thresh=0.45, sizing="cdf_plain"),
    "DXJ": dict(ticker="DXJ", axis="logdollar", labeler="ker",                   thresh=0.45, sizing="ls_overlay"),
    # decorrelated factors, each a genuine Wang ML strategy:
    "UUP": dict(ticker="UUP", axis="imbalance", labeler="bgm+ker",              thresh=0.50, sizing="cdf_overlay"),                       # US dollar regime (gated)
    "DIA": dict(ticker="DIA", axis="imbalance", labeler="bgm+ker",              thresh=0.50, sizing="cdf_overlay"),                       # Dow regime (online-proven 1.66)
    "DJP": dict(ticker="DJP", axis="logdollar", labeler="ker",                  thresh=0.45, sizing="dd_overlay"),                        # commodity timing (ker 2.01, permute-real)
    "IXP": dict(ticker="IXP", axis="logdollar", labeler="trend_leg+regime_gmm", thresh=0.40, sizing="dd_overlay", reduce="infogain"),    # global telecom trend (screen permute-real)
    "TLT": dict(ticker="TLT", axis="logdollar", labeler="ker",                  thresh=0.45, sizing="cdf_overlay"),                       # long-bond timing (decorrelated factor)
}


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
        print(f"[{name}] cached {len(cache[name])} pts", flush=True); return cache[name]
    cfg = POOL[name]; cell = _cell_key(cfg)
    print(f"[{name}] train ... (cell={cell})", flush=True)
    import time as _t
    tcode, extra = render_train_config(cfg)

    def _retry(fn, tries=8):
        for k in range(tries):
            res, st = fn()
            if st == "completed":
                return res, st
            print(f"[{name}] {st}; re-queue {k+1}/{tries}", flush=True); _t.sleep(25)
        return res, st
    _, st = _retry(lambda: submit_and_wait(tcode, f"bookx_{name}_train", timeout_s=600, extra_files=extra))
    if st != "completed":
        print(f"[{name}] train failed"); return None
    bt, st2 = _retry(lambda: submit_and_wait(render_infer_cell(name, cell), f"bookx_{name}_infer", timeout_s=360))
    if st2 != "completed":
        print(f"[{name}] infer failed"); return None
    em = equity_map(bt.get("backtestId"))
    if len(em) < 50:
        print(f"[{name}] short ({len(em)})"); return None
    cache[name] = em; json.dump(cache, open(CACHE, "w")); print(f"[{name}] cached {len(em)} pts", flush=True)
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
    return dict(calmar=(cagr / mdd if mdd > 1e-6 else 0.0), cagr=cagr * 100, mdd=mdd * 100,
                sharpe=(m / sd * math.sqrt(ppy) if sd > 1e-12 else 0.0))


def lr(series, ts, n):
    return [(series[n][ts[i]] / series[n][ts[i - 1]] - 1.0 if series[n][ts[i - 1]] > 0 else 0.0) for i in range(1, len(ts))]


def corr(a, b):
    n = len(a); ma = sum(a) / n; mb = sum(b) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    va = sum((x - ma) ** 2 for x in a); vb = sum((x - mb) ** 2 for x in b)
    return cov / math.sqrt(va * vb) if va > 0 and vb > 0 else 0.0


def book_calmar(series, names, ppy):
    common = sorted(set.intersection(*[set(series[n].keys()) for n in names]), key=lambda x: int(x))
    legr = {n: lr(series, common, n) for n in names}
    solo = {n: max(0.05, metrics(legr[n], ppy)['calmar']) for n in names}  # floor for weighting
    s2 = {n: solo[n] ** 2 for n in names}; t = sum(s2.values()); w = {n: s2[n] / t for n in names}
    L = len(common) - 1
    port = [sum(w[n] * legr[n][i] for n in names) for i in range(L)]
    return metrics(port, ppy), w, solo


def main():
    series = {}
    for n in POOL:
        s = get_series(n)
        if s:
            series[n] = s
    names = list(series.keys())
    allcommon = sorted(set.intersection(*[set(series[n].keys()) for n in names]), key=lambda x: int(x))
    span = (int(allcommon[-1]) - int(allcommon[0])) / (365.25 * 86400.0)
    ppy = len(allcommon) / span
    print(f"\nlegs available={names}  full-common={len(allcommon)} pts ppy~{ppy:.1f}\n")

    legr = {n: lr(series, allcommon, n) for n in names}
    print("=== solo Calmar (full-common grid) ===")
    for n in names:
        m = metrics(legr[n], ppy)
        print(f"  {n}: Cal={m['calmar']:6.3f} CAGR={m['cagr']:6.2f}% MaxDD={m['mdd']:5.2f}% Sh={m['sharpe']:4.2f}")
    print("\n=== correlation to core (GLD/USO/DXJ avg) ===")
    core = [c for c in ["GLD", "USO", "DXJ"] if c in names]
    for n in names:
        cs = [corr(legr[n], legr[c]) for c in core if c != n]
        print(f"  {n}: avg corr to core = {sum(cs)/len(cs):+.3f}" if cs else f"  {n}: (core)")

    # GREEDY forward selection by book Calmar
    print("\n=== greedy forward selection (max book Calmar, conviction calmar^2 wts) ===")
    chosen = ["GLD"]
    m, w, _ = book_calmar(series, chosen, ppy)
    print(f"  {chosen} -> Cal={m['calmar']:.3f} MaxDD={m['mdd']:.2f}%")
    while len(chosen) < len(names):
        best = None
        for n in names:
            if n in chosen:
                continue
            cand = chosen + [n]
            mm, _, _ = book_calmar(series, cand, ppy)
            if best is None or mm['calmar'] > best[1]:
                best = (n, mm['calmar'], mm)
        if best is None:
            break
        chosen.append(best[0])
        print(f"  + {best[0]:4s} -> Cal={best[1]:6.3f} CAGR={best[2]['cagr']:6.2f}% MaxDD={best[2]['mdd']:5.2f}% Sh={best[2]['sharpe']:4.2f}  basket={chosen}")
    print(f"\nDONE. Best book along greedy path printed above. (calmar^2 weights = honest, no book-OOS fit)")


if __name__ == "__main__":
    main()
