> 2026-11-07: 0.9.1/0.9.2 diagnostic design, self-review and implementation: [release evidence](releases/qc-v092-review.md). Cloud and economic acceptance remain open.

> Latest 0.9.0 validation (2026-11-05): [C0 margin and IV evidence](../strategies/sstrangle/results/margin_verified_v090_20261105/RESULTS.md). 427 tests passed. Cloud-tested diagnostic/API and publication-race fixes preserve exact native account parity. C0 still fails on margin; IV replay passes but historical root cause remains open. Pre-trigger margin state, full sidecar/feature parity, strict provider inputs and economic acceptance remain gaps.

> Updated 2026-11-05: [0.9.0 clock fix confirmed](../strategies/sstrangle/results/fix_v090_20261105/RESULTS.md). 421 tests passed; four fresh QC runs confirm 390/390 regular and 210/210 early-close coverage, valid finalization, exact orders/cash/equity parity. Independent sidecar readback, warmed-axis/C1/P1 validation, strict provider inputs and native IV robustness remain open.

> Updated 2026-11-05: [0.9.0 provider and QC validation](../strategies/sstrangle/results/validation_v090_20261105/RESULTS.md). Latest October 31 publication reproduces sampled results; strict data remains blocked. Six cloud jobs completed. Regular C0: 47 orders, $2,342.24 net cash and 260 equity points match exactly. Early-close native error, observer minute deficits/fill-forward rejection, and licensed sidecar-export restriction prevent full cloud acceptance. 91 local tests passed; queues idle and validation server stopped.

> Updated 2026-10-30: [0.9.0 design](../strategies/sstrangle/research/design_20261030_v090/DESIGN.md) is confirmed within local engineering scope: **417 tests passed**, synthetic PoCs and a same-source SPY activity/time comparison completed. [Results](../strategies/sstrangle/results/custom_axis_v090_20261030/RESULTS.md). Strict provider data, actual QC cloud parity and funded acceptance remain open. No cloud job or background controller was started for 0.9.0.

> Historical 0.8.7 execution evidence: [implementation](../strategies/sstrangle/poc/v087/README.md), [results](../strategies/sstrangle/results/qc_poc_20261027_v087/RESULTS.md). The older sections below preserve dated strategy findings; they do not describe the live QC queue.

# Current work

Updated: 2026-10-26. Scope: workspace documentation and options research. This page records verified artifacts; it is not a live QC queue monitor.

## Environment

Native Linux/Ubuntu WSL is the project default; Docker is unnecessary for the QC cloud/local AKQuant workflow. On 2026-10-23, native research/provider imports, Rust CLI startup and all 20 workspace Python tests passed. Docker Desktop was removed during machine cleanup; this workspace's Docker recovery archives were subsequently deleted at the user's request. [Setup and cleanup evidence](ENVIRONMENT.md).

## Current focus: Version 0.8.5 completed research pipeline

[Full design PDF](../strategies/sstrangle/research/design_20261026_v085/DESIGN_REPORT.pdf) · [readable design](../strategies/sstrangle/research/design_20261026_v085/DESIGN_REPORT.md) · [implementation](../strategies/sstrangle/poc/v085/README.md) · [verification](../strategies/sstrangle/results/qc_poc_20261026_v085/final_verification.json) · [comparison](../strategies/sstrangle/results/qc_poc_20261026_v085/final_comparison.csv).

Completed fresh condor QC baseline → 13-rule local search → frozen funded QC verification, over 2022-05-16–2026-10-22. Re-audited ten inherited accounts / 73,819 episodes; all 7,753 original-period condor control trades reproduce exactly. The fixed filter uses prior QQQ daily range >0.016380462988098386, thresholds fitted on unique baseline-filled 2022–2023 days, selection on 2024 only. Later counts and outcomes do not choose the rule.

Final candidate: **3,510 trades, $251,600.30 native net profit, 16.2% native MDD, 2.019 Calmar**, minimum 434 trades/year and $9,762.96 minimum sampled margin remaining. The 3,506 shared local/native episodes match contracts and profit exactly; four extra funded trades add $216.62 and have actual baseline buying-power rejection explanations. Baseline: 8,358 trades, $158,166.74, 38.2% MDD, negative sampled margin headroom.

The candidate improves full-period risk metrics, but 2025–2026 profit is $41,454.74 versus the unfiltered $80,295.54; uplift intervals include zero. Official-settlement fixed-contract sensitivity is −$6,144 for the candidate and −$31,440 for the baseline, with missing PM dates retained. These are not corrected funded accounts. No robust-alpha, exact Option Omega parity, independent quote/funding simulator, or live-readiness claim.

The optional $100k/two-leg put-spread add-on passed its smoke but stopped at a native margin call on 2022-07-12. Its 1,141 orders and failure remain archived. A scope amendment excluded it before selection; no truncated-tape optimization, capital increase or replacement candidate was used.

The design incorporates the newer [eleven-underlying data requirement](OPTIONOMEGA_0DTE_5M_DATA_REQUIREMENTS_20261026.md), QQQ quote delivery and partial Greeks receipts as the next data stage. Completed trades remain SPXW-only. Historical availability/gamma/coverage gaps and independent 5m/finer parity remain gated. Frozen 0.7/0.8 and the 0.7.5 design remain preserved below.

## Previous Draft 0.7.5 design and data admission

[Design PDF](../strategies/sstrangle/research/design_20261026_v075/DESIGN_REPORT.pdf) · [readable design](../strategies/sstrangle/research/design_20261026_v075/DESIGN_REPORT.md) · [contract](../strategies/sstrangle/research/design_20261026_v075/design_contract.json) · [verification](../strategies/sstrangle/results/qc_design_poc_20261026_v075/final_verification.json).

The requested 0.7.5 revision preserves frozen 0.7/0.8 evidence, separates SPXW execution from seven underlying feature series and QQQ surface inputs, and makes 5m sampled research distinct from minute-native execution. Strict pre-slot 5m snapshots cannot silently satisfy the existing two-minute quote-cache gate. A runnable local PoC checks quote/package admission, sessions, storage scope, six archived accounts and pinned provider sampling evidence. It does not launch new QC runs or claim new funded results.

Re-audited 34,689 baseline and 12,785 final candidate episodes. The retained 46,136-row provider sample has zero strict quote-input admissions because originating and historical availability clocks are unknown. Preserve the condor/put reference filters for research; the rejected strangle filter stays rejected. Independent quote-backed paths, full opportunity/funding replay and prospective validation remain gated work.

[Provider addendum](/home/vic/data_providers/docs/requirements/QC_0DTE_V075_ADDENDUM_20261026.md) clarifies the existing bounded pilot. This design change does not alter SS45DTE or extend acquisition to every ETF's option chain.

## Preserved Draft 0.8 evidence

[Draft 0.8 design and findings](../strategies/sstrangle/research/design_20261024_v8/DESIGN_REPORT.pdf) · [text](../strategies/sstrangle/research/design_20261024_v8/DESIGN_REPORT.txt) · [verification](../strategies/sstrangle/results/qc_sizing_poc_20261024/final_verification.json).

Latest scope: all equity available, no Tom sizing limits; original $100k condor/$2m put, 20-point wings and one-lot execution remain. Full allocation is a ceiling, not forced full margin usage. No capital-increase or narrow-wing variant was run.

The 150-feature, 1,802-rule local search freezes choices using historical walk-forward validation with increased costs. Six native runs (two smokes, two matched Draft 0.7 controls, two new candidates) cover execution parity and the extended period through October 22, 2026. Legacy control trades reproduce Draft 0.7; all full native runs pass >=360 episodes in every included year.

Final candidates: condor: 5,674 trades, $234,806.22 net, 24.0% native MDD, 1.302 Calmar, minimum 911/year; put: 10,273 trades, $789,259.86 net, 6.5% native MDD, 1.196 Calmar, minimum 1703/year. [Comparison](../strategies/sstrangle/results/qc_sizing_poc_20261024/final_comparison.csv) · [Robustness evidence](../strategies/sstrangle/results/qc_sizing_poc_20261024/robustness.json).

Robustness is not established: historical bootstrap intervals include zero, repeated-search diagnostics are weak, and adaptive annual reoptimization fails some yearly frequency gates. The fixed candidates are separate from that failed adaptive process. The reserved July14–October22 interval is a short held historical test, not prospective live evidence.

condor: Retain Draft 0.7 as the preferred reference: the new candidate does not improve both native Calmar and reserved-interval profit.

put: Retain Draft 0.7 as the preferred reference: the new candidate does not improve both native Calmar and reserved-interval profit.

## Previous Draft 0.7 evidence

[Draft 0.7 design and findings](../strategies/sstrangle/research/design_20261024_v7/DESIGN_REPORT.pdf) · [text](../strategies/sstrangle/research/design_20261024_v7/DESIGN_REPORT.txt) · [verification](../strategies/sstrangle/results/qc_final_poc_20261024/final_verification.json).

The missing funded QC stage is complete for all three frozen local alpha candidates. All three baseline tapes reproduce locally at episode/account level; a fresh full unfiltered condor reproduces the original 7,753 trades and $138,586.34 net exactly. Local reproduction uses native observations, not independent option quotes or a cloned native margin engine.

Final funded results: condor: 4,755 trades, $132,103.40 net, 29.7% native MDD, 0.752 Calmar, minimum 652/year; strangle: 3,147 trades, $158,521.08 net, 16.2% native MDD, 0.114 Calmar, minimum 403/year; put: 4,883 trades, $722,370.06 net, 4.2% native MDD, 1.825 Calmar, minimum 585/year. Each passes at least 360 completed trades in every included year (2022 and 2026 partial). [Baseline/local/final comparison](../strategies/sstrangle/results/qc_final_poc_20261024/final_comparison.csv) · [Annual counts](../strategies/sstrangle/results/qc_final_poc_20261024/final_annual.csv).

Search: 144 eligible daily price/volume features, 864 rules per strategy, training 2022–2023 cash Calmar, full-period count feasibility >=400, immutable selection before native results. Selected rules use prior GLD range, IWM volume z-score and QQQ range. Common native/local trades match contracts and P&L; changed entries must reconcile to actual native buying-power messages. Engineering verification does not imply economic improvement. All periods remain development evidence; original Option Omega trade-level parity and fresh prospective evaluation remain unresolved.

## Previous Draft 0.65 evidence

[Draft 0.65 design and findings](../strategies/sstrangle/research/design_20261024_v065/DESIGN_REPORT.pdf) · [text](../strategies/sstrangle/research/design_20261024_v065/DESIGN_REPORT.txt) · [verification](../strategies/sstrangle/results/qc_delta_poc_20261024/final_verification.json).

Native condor delta tolerances ±0.02 and ±0.05 completed 7,753 and 11,584 episodes, respectively; minimum annual counts 1,281 and 1,605. Both pass >=360 in every included year. Native net P&L: $138,586.34 and $154,255.02. Exact Option Omega parity remains unverified; tighter exposure trades off coverage.

Local PoC now has **211 fields / 144 eligible alpha candidates / 288 rules per baseline**, with pinned daily provider exports and strict as-of joins on all three 0.6 baselines and both tighter condors. The 20 broker-IV fields are sensitivity-only. Conditional filters do not recompute native funding; all periods are development evidence, not untouched OOS. [Local results](../strategies/sstrangle/results/qc_delta_poc_20261024/local/summary.json) · [feature registry](../strategies/sstrangle/results/qc_delta_poc_20261024/local/feature_registry.json) · [implementation](../strategies/sstrangle/poc/v065/README.md).

Provider requirements delivered: [readable contract](/home/vic/data_providers/docs/requirements/QC_DRAFT_065_FEATURE_AND_PARITY_REQUIREMENTS_20261024.txt) and [machine-readable scope](/home/vic/data_providers/docs/requirements/QC_DRAFT_065_FEATURE_AND_PARITY_REQUIREMENTS_20261024.json). This is a requirements handoff; data acquisition has not been started by this task.

## Previous Draft 0.6 evidence

Review **[overall design Draft 0.6](../strategies/sstrangle/research/design_20261023_v6/DESIGN_REPORT.pdf)**: three native QC baselines, the 3,606 wing-admission skips, and the revised research architecture. [Design text](../strategies/sstrangle/research/design_20261023_v6/DESIGN_REPORT.txt) · [diagram](../strategies/sstrangle/research/design_20261023_v6/design_graph.svg) · [verified evidence](../strategies/sstrangle/results/qc_three_demo_poc_20261023/final_verification.json).

Source interval **2022-05-16–2026-07-13**, SPXW 0DTE. All three pass **>=360 completed whole episodes in every included year**; 2022 and 2026 are partial actual counts. Tom-inspired 16-delta strangle and 25-delta put are user-authorized 0DTE adaptations, not reproductions of the saved 45-DTE source.

| Baseline | Episodes | Capital | Net P&L | CAGR | Native MDD | Calmar |
|---|---:|---:|---:|---:|---:|---:|
| condor | 12,884 | $100,000 | $164,705.02 | 26.255% | 48.1% | 0.546 |
| strangle | 13,465 | $2,000,000 | $514,677.10 | 5.638% | 15.4% | 0.366 |
| put | 13,471 | $2,000,000 | $600,324.72 | 6.488% | 11.5% | 0.564 |

Condor coverage increased from 9,841 to 12,884, closing 83.3% of the gap to 13,492. Exact-width feasible-pair search retains the original quote gates but can materially change delta exposure. A separate no-order diagnostic recovers the complete original 3,606 skip breakdown. Source contract/fill parity remains unverified.

Native 4/2/1-leg orders, expiry cash, fees and zero residuals reconcile. The condor sampled minimum margin remaining was negative; completion does not prove continuously positive buying power. Separate $2m naked accounts must not be compared with the $100k condor without acknowledging capital. No result is untouched OOS or a shared-capital portfolio.

[Annual counts](../strategies/sstrangle/results/qc_three_demo_poc_20261023/analysis/annual.csv) · [trial ledger, including failures](../strategies/sstrangle/results/qc_three_demo_poc_20261023/trial_ledger.json) · [implementation](../strategies/sstrangle/poc/v06/README.md). The [Draft 0.5 control](../strategies/sstrangle/research/design_20261023_v5/DESIGN_REPORT.pdf) remains frozen.

The proposed workflow is:

**Single-ticker QC baseline → genuine orders and opportunity audit → native accounting + entry-safe features → Parquet/DuckDB research → AKQuant simulation + robustness → funded final QC individual/portfolio validation → user decision.**

Full intraday/options provider coverage, 100,000+ feature expressions, independent option paths and shared-capital portfolios remain future deliverables. Draft 0.65 now supplies daily cross-market feature packs and retrospective chronological screening; it is not a complete feature platform.

## What is actually completed

| Artifact | Verified outcome | Scope |
|---|---|---|
| [Original basket baseline](../strategies/sstrangle/results/strangle_basket_20261018_191012/baseline_report/REPORT.md) | $60,000 → −$42.29; 145 cycles, 1,010 fills, $3,405.54 fees | Insolvent on 2020-03-12; did not reach 2026. CAGR/Calmar undefined. |
| [Later broad research control](../strategies/sstrangle/results/strangle_basket-calmar_20261019_204146/research_report/REPORT.txt) | $60,000 → $48,817.43; 188 cycles, 1,134 fills; Calmar −0.068, conservative MDD 20.44% | Completed 2012-01-03–2026-09-30. Calmar >2 goal not achieved. |
| [Local joined dataset](../strategies/sstrangle/results/liquidity_local_research_20261020/summary.json) | 188 reconciled trade/cycle joins and 566 native contract requests | Opening annotations and labels; not the full proposed market-feature dataset. |
| [Local AKQuant adapter](../strategies/sstrangle/local/README.md) | Frozen-fill replay and sensitivity tooling exists | Not independent optimization of arbitrary option paths. |
| [Liquidity prototype](../strategies/sstrangle/liquidity/plan.json) | Top-50/top-100 selector prototype exists | No native top-N universe campaign established by this prototype. |

The broad control's local polling transport error was followed by confirmed cloud completion and [terminal queue recovery](../strategies/sstrangle/results/strangle_basket-calmar_20261019_204146/terminal_queue_recovery.json). Old “running” or “failed” snapshots do not supersede that terminal evidence. The Draft 0.6 native campaign is recorded above.

## Data and implementation gaps

The provider scope is **US and CN PV/options data, excluding HK**. The last reviewed October 20 pilot had trade bars but no published NBBO, OI or point-in-time contract-history pilot. This is a dated coverage snapshot, not a fresh provider status check. Historical/delisted identities, quote coverage, corporate actions and reproducible IV/Greeks need admission tests before independent local simulation.

A minimal five-field registry and 28 entry-safe daily joins pass local PoC checks. The full typed expression engine, shared research notebooks, independent path simulation and portfolio builder remain design/PoC work. The 100,000+ feature target is an architectural goal, not a delivered feature count. Prior component speed tests do not establish total research-pipeline throughput.

Provider references: [base local-backtest requirements](/home/vic/data_providers/docs/requirements/QC_SHORT_STRANGLE_LOCAL_BACKTEST_20261019.md), [liquidity requirements](/home/vic/data_providers/docs/requirements/QC_OPTIONS_TOP50_TOP100_20261020.md), [frequency revision](/home/vic/data_providers/docs/requirements/QC_TRADE_FACTOR_FREQUENCY_REVISION_20261021.txt). Draft 0.6 needs a consolidated provider contract after review; do not silently treat older frequency/universe requirements as the approved new design.

## Operating boundary

Use the shared Rust client for genuine QC orders/trades. Preserve failed runs and source identities. Never restart `serve`, cancel or duplicate a nonterminal cloud run to obtain progress. Local polling errors alone do not establish cloud failure. Do not export licensed quote history through Insights/logs or other workarounds. Follow [CLI usage](../USAGE.md) and check actual queue/cloud identity before execution.
