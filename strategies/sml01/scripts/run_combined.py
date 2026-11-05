#!/usr/bin/env python3
"""SML01 = ONE strategy. This runs a REAL combined OOS backtest of the BOOK (all legs
held together as one QC algorithm via render_portfolio -> portfolio.py.tmpl), NOT per-leg
and NOT read-only series synthesis. Goal: improve the COMBINED portfolio Calmar.

Usage:
  python3 scripts/run_combined.py                 # full ledger, conviction(calmar^2) weights
  python3 scripts/run_combined.py equal           # full ledger, equal weights
  python3 scripts/run_combined.py only AAA,BBB,... # only these tickers (conviction wt)
  python3 scripts/run_combined.py drop AAA,BBB     # full ledger minus these
The combined real-OOS stats (Calmar/CAR/MaxDD/Sharpe) are printed as COMBINED_RESULT json.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from lb.harness.orchestrator import render_portfolio
from lb.harness.qc_client import submit_and_wait
from lb.harness.psuf import cell_suffix
from lb.paths import ROOT as LBROOT

KJSON = os.path.join(os.path.dirname(__file__), "..", "knowledge.json")


def cell_key(cfg):
    prefix = (f"{cfg['axis']}_{cfg['labeler'].replace('+','_x_')}_{cfg['sizing']}"
              f"_t{int(round(float(cfg['thresh'])*100))}")
    return prefix + cell_suffix(cfg)


def build_champions(mode, arg_tickers, weight_mode, explicit_w=None):
    k = json.load(open(KJSON))
    pe = k["per_etf_best"]
    champs = []
    for t, v in pe.items():
        if not isinstance(v, dict) or not v.get("config"):
            continue
        cal = v.get("real_calmar") or 0.0
        if cal <= 0:
            continue
        if mode in ("only", "weights") and t not in arg_tickers:
            continue
        if mode == "drop" and t in arg_tickers:
            continue
        cfg = v["config"]
        if explicit_w is not None:
            w = explicit_w.get(t, 0.0)
        else:
            w = (cal * cal) if weight_mode == "conviction" else 1.0
        # portfolio.py.tmpl reads autoresearch/{tk}/{key} VERBATIM, so key must be the
        # full ObjectStore object name: cell_{_cell_key}.json (matches infer's cell_{CELL}.json).
        obj = "cell_" + cell_key(cfg) + ".json"
        champs.append([t, obj, float(w), float(cal)])
    # normalise weights to gross 1.0
    tot = sum(c[2] for c in champs) or 1.0
    out = [[c[0], c[1], round(c[2] / tot, 6)] for c in champs]
    return out, champs


def main():
    argv = sys.argv[1:]
    weight_mode = "conviction"
    mode, arg_tickers, explicit_w = "all", set(), None
    if argv:
        if argv[0] == "equal":
            weight_mode = "equal"
        elif argv[0] == "weights" and len(argv) > 1:
            # weights T1:w1,T2:w2,...
            mode = "weights"
            explicit_w = {}
            for pair in argv[1].split(","):
                tk, w = pair.split(":")
                explicit_w[tk.strip().upper()] = float(w)
            arg_tickers = set(explicit_w.keys())
        elif argv[0] in ("only", "drop") and len(argv) > 1:
            mode = argv[0]
            arg_tickers = set(x.strip().upper() for x in argv[1].split(","))
    champs, detail = build_champions(mode, arg_tickers, weight_mode, explicit_w)
    print(f"[combined] {len(champs)} legs | weight={weight_mode} | mode={mode} {sorted(arg_tickers) if arg_tickers else ''}")
    for t, cell, w in sorted(champs, key=lambda x: -x[2])[:12]:
        print(f"   {t:6s} w={w:.4f}  cell={cell[:60]}")
    code = render_portfolio([[c[0], c[1], c[2]] for c in champs], leverage=1.0)
    name = f"combined_{mode}_{weight_mode}_{len(champs)}legs"
    print(f"[combined] submitting REAL OOS backtest: {name} ({len(code)} bytes)")
    res = submit_and_wait(code, name, timeout_s=1800)
    stats = {}
    if isinstance(res, dict):
        stats = res.get("statistics") or res.get("runtimeStatistics") or res.get("Statistics") or {}
        if not stats:
            for kk in ("result", "results", "data"):
                if isinstance(res.get(kk), dict):
                    stats = res[kk].get("statistics", {}) or stats
    print("COMBINED_RESULT", json.dumps({"name": name, "n_legs": len(champs), "status": res.get("status") if isinstance(res, dict) else str(res)[:80], "stats": stats}))


if __name__ == "__main__":
    main()
