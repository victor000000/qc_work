# Draft 0.8 — full-equity research and robustness

The local engine is custom Python/pandas, not AKQuant. It computes features and optimizes conditional filters on archived QC baseline episodes and realized unit payoffs. It is sufficient for this fixed-contract, one-lot filter POC, but is not an independent option-chain, execution or portfolio-margin backtester. Filtering a funded opportunity tape can omit trades a different account path would admit. Frozen-rule QC reruns and trade-level reconciliation are therefore mandatory; they do not prove equivalence for opportunities absent from both tapes.

The latest user instruction removes Tom sizing. Keep $100k condor/$2m put, 20-point wings, one-lot orders and native buying power. `capital_fraction=1` makes all equity available as a ceiling; it does not force full margin use. The initial narrow-wing and capital-increase proposals were discarded before native submission.

`EXPERIMENT_CONTRACT.txt` in `results/qc_sizing_poc_20261024` fixes the revised scope before new selection. The directory name preserves initial preparation history. `prepare_features.py` supplies 144 existing price/volume features and six Cboe VIX regime fields; selected native range filters use readable raw source modules. `optimize.py` retains 901 trials per strategy and freezes choices using historical 2023/2024 walk-forward validation with an extra $10 package cost. Later annual counts are explicitly used for >=400 local feasibility.

`robustness.py` adds cost/fee/tail stress, threshold neighborhoods, four annual expanding walk-forward selections, three block lengths and a max-across-rules resampling diagnostic. Historical robustness failures remain visible; none are silently reranked away. The July14–October22 native interval is reserved before new option outcomes are inspected.

`run_campaign.py` serially executes two smokes and four full native runs on the existing node through authenticated Python transport. Frozen Draft0.7 controls and new candidates have identical extended periods. The launcher never blindly repeats an uncertain native create, and archives actual cloud source/input hashes before project reuse. Do not start a queue worker concurrently.

After all runs: `analyze_final.py`, report `build_report.py`, `finish_operations.py`, `verify.py`, then documentation promotion. Verification distinguishes exact legacy accounting/common-trade parity from native funding differences and actual new-interval results. No independent option quote/margin simulator, robust alpha, live deployment or combined portfolio is claimed.
