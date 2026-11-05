# Draft 0.65: delta fidelity and local alpha mini-PoC

Native experiments preserve the Draft 0.6 condor economics and add a pre-order absolute target-error gate on both short deltas. Candidate tolerances are 0.02 and 0.05. All completed native episodes must pass that gate; full runs must exceed 360 episodes in every included calendar year.

- `campaign.py`: immutable source/config manifests and explicit queue submission.
- `run_campaign.py`: serialize accounting smoke and full candidates; stop on failures; no uncertain-write retries.
- `export_features.py`: read-only exports from a pinned provider release.
- `local_features.py`: daily feature packs, strict as-of joins and training-only single-feature screens.
- `local_diagnostics.py`: DuckDB tables, redundancy, later daily-cluster intervals and fixed threshold sensitivity.
- `analyze.py`: native P&L, annual count, matched-episode and cost/settlement sensitivity attribution.
- `verify.py`: native identity/accounting, delta/count gates, checksums and local leakage checks.

The native collector and enriched order-tag decoder are reused from `../v06`; frozen 0.6 sources/results remain unchanged. Quote-side simulation, new contract/exits and a funded alpha-filtered account are not delivered by conditional local filtering.

Use the workspace `.venv/bin/python`. Set `PYTHONPATH=scripts` when invoking the v06 native collector directly. Reports regenerate without submitting cloud work. The full-interval 0.02 and 0.05 campaigns run serially on the existing B2-8 node.

Feature schema: 25 prior-day raw OHLCV fields + 144 price/volume alpha candidates + 20 broker-IV sensitivity fields + 22 native/calendar/contract fields = 211. IDs and as-of timestamps are additional metadata. All 144 candidates are tested above/below their training median; every trial is retained. No undefined skew/VIX/VWAP/Hurst substitutes are added.

Historical EOD availability is assumed at next New York midnight, with strict joins and seven-day max age. Current-vintage raw bars are not vintage-certified. Broker IV is excluded from primary screening. Labels remain physically separate. Missing strategy legs remain null.
