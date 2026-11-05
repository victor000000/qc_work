#!/usr/bin/env python3
"""End-to-end smoke test of the qc-backtest-server queue transport.

Submits a tiny MULTI-FILE QC algorithm through the new SML01 transport (writes a
row to data/SML01.duckdb; the Rust server runs it on the shared pool), polls to
completion, and asserts:
  - multi-file upload worked   (main.py imports helper.py — fails to run if the
                                extra file wasn't uploaded by the server)
  - result_json was persisted  (statistics present)
  - runtimeStatistics captured (our set_runtime_statistic('smoke_metric','42'))

Run:  cd SML01 && python3 scripts/smoke_server_queue.py
"""
import sys
import time

from lb.harness import qc_client as qc

MAIN = '''from AlgorithmImports import *
import helper
class Smoke(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2022, 3, 1)
        self.set_cash(100000)
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_runtime_statistic("smoke_metric", "42")
    def on_data(self, data):
        if not self.portfolio.invested:
            self.set_holdings(self.spy, helper.SMOKE_WEIGHT)
'''
HELPER = "SMOKE_WEIGHT = 0.5\n"


def main():
    bid = qc.submit_backtest(MAIN, "SMOKE_server_queue", extra_files={"helper.py": HELPER})
    print(f"submitted bid={bid}", flush=True)
    t0 = time.time()
    last = None
    while time.time() - t0 < 900:
        st, rt, logs = qc.read_backtest_status(bid)
        if st != last:
            print(f"[{int(time.time()-t0):4d}s] status={st!r}", flush=True)
            last = st
        if qc.is_done(st):
            break
        time.sleep(10)
    res = qc.read_backtest(bid)
    status = res.get("status", "?")
    stats = res.get("statistics", {}) or {}
    rts = res.get("runtimeStatistics", {}) or {}
    print("\n=== RESULT ===", flush=True)
    print("status            :", status)
    print("statistics keys   :", sorted(stats.keys())[:10], f"(n={len(stats)})")
    print("Total Orders      :", stats.get("Total Orders"))
    print("runtimeStatistics :", rts)
    print("smoke_metric      :", rts.get("smoke_metric"))

    ok_done = status.startswith("Completed")
    ok_stats = len(stats) > 0
    ok_rt = rts.get("smoke_metric") == "42"
    print("\n=== VERDICT ===", flush=True)
    print("completed         :", ok_done)
    print("statistics stored :", ok_stats, "(proves result_json persisted)")
    print("runtimeStat stored:", ok_rt, "(proves runtimeStatistics persisted)")
    print("multi-file upload :", ok_done, "(main.py imported helper.py successfully)")
    if ok_done and ok_stats and ok_rt:
        print("\nSMOKE PASS ✓")
        return 0
    print("\nSMOKE FAIL ✗")
    return 1


if __name__ == "__main__":
    sys.exit(main())
