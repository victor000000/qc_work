#!/usr/bin/env python3
"""REAL-ONLINE cross-asset book (2026-06-14). NOT replay.

For each leg: train (saves frozen model+reduce_tf bundle to ObjectStore) -> run live_trade.py
(loads ONLY the frozen bundle; generates custom bars ONLINE, features ONLINE, dim-reduction
ONLINE incl vae, predict ONLINE, causal _size, set_holdings). The fetched equity is the GENUINE
online model-only OOS backtest. Combine the online equity series into the cash book (gross<=1).
This is the deployable-fidelity number; infer.py replay (book3) is cross-checked against it.

Cache: results/series_cache_online.json
"""
import json, os, math, time
from lb.harness.orchestrator import render_train_config, render_live_trade
from lb.harness.qc_client import submit_and_wait, _qc_post
from lb.harness.constants import QC_PROJECT_ID
from lb.harness.psuf import cell_suffix
from lb.paths import ROOT as _LBROOT

CACHE = str(_LBROOT / "results" / "series_cache_online.json")


def _cell_key(cfg):
    return (f"{cfg['axis']}_{cfg['labeler'].replace('+','_x_')}_{cfg['sizing']}"
            f"_t{int(round(float(cfg['thresh'])*100))}") + cell_suffix(cfg)


POOL = {
    "GLD": dict(ticker="GLD", axis="logdollar", labeler="trend_leg+regime_gmm", thresh=0.40, sizing="dd_overlay", reduce="vae", n_components=16, features="base"),
    "USO": dict(ticker="USO", axis="logdollar", labeler="revert",               thresh=0.45, sizing="cdf_plain"),
    "DXJ": dict(ticker="DXJ", axis="logdollar", labeler="ker",                   thresh=0.45, sizing="ls_overlay"),
}


def equity_map(bid):
    r = _qc_post("/backtests/chart/read", {"projectId": QC_PROJECT_ID, "backtestId": bid,
                 "name": "Strategy Equity", "count": 5000, "start": 0, "end": 2000000000})
    if not r.get("success"):
        return {}
    vals = ((r.get("chart") or {}).get("series") or {}).get("Equity", {}).get("values") or []
    return {str(int(row[0])): float(row[-1]) for row in vals if isinstance(row, list) and len(row) >= 2 and row[-1] > 0}


def _retry(fn, label, tries=8):
    for k in range(tries):
        res, st = fn()
        if st == "completed":
            return res, st
        print(f"   {label}: {st}; re-queue {k+1}/{tries}", flush=True); time.sleep(25)
    return res, st


def get_online(name):
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    if name in cache and len(cache[name]) > 50:
        print(f"[{name}] cached {len(cache[name])} pts", flush=True); return cache[name]
    cfg = POOL[name]; cell = _cell_key(cfg)
    print(f"[{name}] TRAIN (save bundle) cell={cell}", flush=True)
    tcode, extra = render_train_config(cfg)
    _, st = _retry(lambda: submit_and_wait(tcode, f"online_{name}_train", timeout_s=600, extra_files=extra), "train")
    if st != "completed":
        print(f"[{name}] train failed"); return None
    print(f"[{name}] LIVE_TRADE (real online) ...", flush=True)
    lt_main, lt_extra = render_live_trade(name, cell)
    bt, st2 = _retry(lambda: submit_and_wait(lt_main, f"online_{name}_live", timeout_s=600, extra_files=lt_extra), "live")
    if st2 != "completed":
        print(f"[{name}] live_trade failed: {bt.get('status') if isinstance(bt,dict) else st2}"); return None
    rt = (bt.get("runtimeStatistics", {}) or {}) if isinstance(bt, dict) else {}
    st_stats = (bt.get("statistics", {}) or {}) if isinstance(bt, dict) else {}
    print(f"[{name}] live stats: Calmar~{st_stats.get('Calmar Ratio','?')} warm={rt.get('warm','?')} trades={st_stats.get('Total Orders','?')}", flush=True)
    em = equity_map(bt.get("backtestId"))
    if len(em) < 50:
        print(f"[{name}] online series too short ({len(em)})"); return None
    cache[name] = em; json.dump(cache, open(CACHE, "w")); print(f"[{name}] cached {len(em)} online pts", flush=True)
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


def main():
    series = {}
    for n in POOL:
        s = get_online(n)
        if s:
            series[n] = s
    if len(series) < 2:
        print("too few online series"); return
    names = list(series.keys())
    common = sorted(set.intersection(*[set(series[n].keys()) for n in names]), key=lambda x: int(x))
    span = (int(common[-1]) - int(common[0])) / (365.25 * 86400.0)
    ppy = len(common) / span
    legr = {n: lr(series, common, n) for n in names}
    print(f"\n=== REAL-ONLINE book (live_trade, model-only) — {len(common)} pts ppy~{ppy:.1f} ===")
    SOLO = {}
    for n in names:
        m = metrics(legr[n], ppy); SOLO[n] = max(0.05, m['calmar'])
        print(f"  {n} online: Cal={m['calmar']:6.3f} CAGR={m['cagr']:6.2f}% MaxDD={m['mdd']:5.2f}% Sh={m['sharpe']:4.2f}")
    for sc in ("equal", "calmar^2"):
        if sc == "equal":
            w = {n: 1.0 / len(names) for n in names}
        else:
            s2 = {n: SOLO[n] ** 2 for n in names}; t = sum(s2.values()); w = {n: s2[n] / t for n in names}
        L = len(common) - 1
        port = [sum(w[n] * legr[n][i] for n in names) for i in range(L)]
        m = metrics(port, ppy)
        print(f"  BOOK {sc:9s} Cal={m['calmar']:6.3f} CAGR={m['cagr']:6.2f}% MaxDD={m['mdd']:5.2f}% Sh={m['sharpe']:4.2f}  {' '.join(f'{n}={w[n]:.2f}' for n in names)}")


if __name__ == "__main__":
    main()
