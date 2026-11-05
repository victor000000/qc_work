# Draft 0.7.5 data admission and design PoC

[Design report](../../research/design_20261026_v075/DESIGN_REPORT.md) and [machine-readable contract](../../research/design_20261026_v075/design_contract.json).

The frozen 0.7 trading references remain unchanged. This revision adds strict quote/package input checks, exchange-session entry grids, full-ticker capacity estimates, six-account archived payoff reconstruction and admission diagnostics against a pinned provider sample. It does not start downloads, optimization, QC runs or orders.

Run from the workspace root:

```bash
.venv/bin/python -m pytest strategies/sstrangle/poc/v075 -q
.venv/bin/python strategies/sstrangle/poc/v075/run_review.py
.venv/bin/python strategies/sstrangle/research/design_20261026_v075/build_report.py
```

Outputs go to `strategies/sstrangle/results/qc_design_poc_20261026_v075/`. Provider clocks that are unknown remain unknown. A five-minute snapshot cannot satisfy a strict pre-slot two-minute age check simply because its sampling interval is five minutes. An empty admission rejection list establishes input checks only, never contract-selection correctness, a fill, buying power or economic performance.
