# Draft 0.7 — close local optimization through native QC

Baselines are the frozen ±0.02 condor from0.65 and the original0.6 Tom-inspired strangle/put. `recheck_baselines.py` independently reconstructs the payoff of every native opening leg and cash expiry, checks every episode/account, and recomputes selected features from pinned raw provider data. This is an accounting/feature reproduction, not independent option-market data or a replica of QC margin.

`optimize.py` freezes864 single-feature rules per strategy (144 features ×3 training quantiles ×2 directions), ranks by2022–2023 daily realized-cash Calmar, and requires400 historical trades per year as a disclosed all-period count-feasibility constraint. No later P&L is used in ranking. All periods have already been inspected; no untouched OOS claim. Native final gate remains360 completed episodes/year.

`feature_rule.py` contains the selected primitive calculations. Readable raw daily rows are split into ordinary Python source modules, each below32KB, uploaded with the existing Rust queue's `--extra-files <JSON-file-path>`. `build_algorithm.py` adds the pre-order filter and feature/source-day tags to the frozen adapter. No compressed or encoded cloud source is used. A rejected compressed-data submission and a local CLI argument error remain in the ledger.

The campaign runs: readable-input smoke, full unfiltered condor control, then funded condor/strangle/put alpha candidates. `verify_native.py` checks actual cloud source-module hashes, trade-level feature decisions and native accounting. Shared contracts and P&L must match locally; additions/removals must be explained by actual native buying-power rejection messages. Full unfiltered control must reproduce every baseline episode exactly.

No candidate is promoted solely because its training result is attractive. Final native marked drawdown and later-period behavior determine the reported conclusion. Failed upload/transport/verification attempts are preserved; no nonterminal run is duplicated.

Operational recovery: repeated Rust API transport timeouts stalled the put upload before launch. `recover_put_submission.py` requires the owned worker to be stopped, checks for an existing native run and idle node, verifies the same source/input hashes, and records creation intent before a single native launch. It never blindly retries an uncertain backtest create. `put_recovery_*` files preserve the evidence. Controller resume retains archived source snapshots because cloud projects may be reused; read-only source fetches use bounded retries.
