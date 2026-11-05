#!/usr/bin/env python3
"""Run Wang's same-ticker multi-axis COMBINATION on QC for a set of component configs.

Usage: python3 scripts/research/run_combine.py '<cfgA>' '<cfgB>' [ '<cfgC>' ... ]
Each cfg is the SAME JSON a training round used (so its cell key is reproducible). The component
cells must already be trained+saved (run_round trains them). Submits the 'agree' (chop detector ->
flat on disagreement) and 'net' (mean) combinations and prints the real OOS Calmar of each."""
import sys
import json
import time

from lb.harness.qc_client import (submit_backtest, read_backtest_status, read_backtest,
                                   delete_backtest, is_done)
from lb.harness.orchestrator import render_combine
from lb.harness.psuf import cell_suffix


def _cell_key(cfg):
    prefix = (f"{cfg['axis']}_{cfg['labeler'].replace('+', '_x_')}_{cfg['sizing']}"
              f"_t{int(round(float(cfg['thresh']) * 100))}")
    return "cell_" + prefix + cell_suffix(cfg) + ".json"


def _f(x, d=0.0):
    try:
        return float(str(x).replace("%", "").strip())
    except (ValueError, TypeError):
        return d


def _run(label, code):
    bid = submit_backtest(code, label)
    t0 = time.time()
    while True:
        status, _, _ = read_backtest_status(bid)
        if is_done(status):
            return read_backtest(bid) if status.startswith("Completed") else {"status": status}
        if time.time() - t0 > 300:
            delete_backtest(bid)
            return {"status": "timeout"}
        time.sleep(10)


def main(argv):
    cfgs = [json.loads(a) for a in argv]
    ticker = cfgs[0]["ticker"]
    keys = [_cell_key(c) for c in cfgs]
    print("ticker:", ticker)
    for c, k in zip(cfgs, keys):
        print(f"  component: {c['axis']}/{c['labeler']}/{c['sizing']} -> {k}")
    for mode in ("agree", "net"):
        code = render_combine(ticker, keys, mode)
        bt = _run(f"combine_{ticker}_{mode}", code)
        st = (bt.get("statistics", {}) or {}) if isinstance(bt, dict) else {}
        rt = (bt.get("runtimeStatistics", {}) or {}) if isinstance(bt, dict) else {}
        cagr = _f(st.get("Compounding Annual Return", "0%"))
        mdd = _f(st.get("Drawdown", "0%"))
        calmar = round(cagr / mdd, 4) if abs(mdd) > 0.01 else 0.0
        trades = st.get("Total Orders", "?")
        print(f"COMBINE[{mode}]: Calmar={calmar}  CAGR={cagr}%  MaxDD={mdd}%  "
              f"trades={trades}  n_loaded={rt.get('n_loaded')}  status={bt.get('status','?')}")


if __name__ == "__main__":
    main(sys.argv[1:])
