## 1. What this version changes

Version 0.8.5 executes the established **QC baseline → local research → funded QC verification** sequence for the SPXW iron condor. It also tests a simpler two-leg put credit spread, which fails the full native baseline gate and is rejected before optimization. The original plan allowed 13 predeclared rules per strategy; only the surviving condor’s 13 rules are evaluated. It removes future-year count feasibility from selection, verifies every native payoff and records an independent official-settlement sensitivity. It does not redefine a failed economic result as a successful strategy merely because the pipeline ran.

The inherited 0.7.5 plan remains the architecture for independent market-data replay. That larger pipeline is not complete: provider quote availability, full candidate coverage and local funding simulation remain unresolved. This version completes the narrower fixed-contract filter POC, which uses native baseline trades and native expiry outcomes for local research. Python/pandas implements this calculation; calling it AKQuant or an independent options backtest would misstate what ran.

Earlier evidence is immutable. Draft 0.6 established three native baselines; 0.65 constrained condor delta error; 0.7 closed the funded verification loop; 0.8 added robustness tests but did not establish robust alpha; 0.7.5 formalized data admission. The version sequence includes a later-written 0.7.5 design and is not a ranking of profitability. The 0.7 condor/put references remain historical comparators. The rejected IWM-volume strangle filter remains rejected. SS45DTE is a separate strategy and was not changed.

## 2. Source review and strategy choice

The review covers the saved Tom “3 Best Trading Strategies” transcript, all eleven extracted strategies and their missing-rule checklist, the sizing transcript, the timestamped audio-demo extraction, versioned 0.6–0.8 evidence, the 0.7.5 data contract and the latest saved provider receipts. `reviewed_source_manifest.json` pins the relevant source and evidence files; this is not a claim to have audited every unrelated workspace file.

Tom's three-strategy source covers naked puts, credit spreads and covered calls. The saved platform transcript discusses roughly 25-delta, 45-DTE naked puts, credit spreads, and stock-backed calls. Its preference for some call spreads and its discretionary cheap/expensive judgments do not supply a complete 0DTE algorithm. The eleven-strategy source explicitly includes short put spreads at 03:58–05:18. That section supplies a defined-risk construction and a 30–35%-of-width credit target but leaves DTE, delta, width and timing unresolved. The present POC does **not** impose that credit target or 50% profit-taking; it adopts the audio demo's expiry-held research structure and labels the departure. The 360-episode annual gate is our engineering requirement, not Tom's trading-frequency rule. Delta and credit/width are not guaranteed probabilities of profit, and the speaker's performance claims are not independently verified.

| Tom's eleven strategies | v0.8.5 disposition and reason |
| --- | --- |
| 1. Short puts | Preserve existing 25-delta/$2m reference. No new naked account in this campaign |
| 2. Jade lizard | Defer: extra naked downside, credit/width and management choices |
| 3. Covered calls | Defer: stock delivery, dividends and assignment require another execution model |
| 4. Short put spreads | Tested additional POC, rejected after full-baseline margin call; two legs and exact protection do not settle native funding behavior |
| 5. Put ratio spreads | Defer: extra short leg and unresolved tail/management rules |
| 6. Short call spreads | Reasonable future comparator; omitted from this bounded campaign to avoid expanding the search after results |
| 7. Broken-wing butterfly | Defer: three strikes, unequal widths and discretionary adjustments |
| 8. Unbalanced iron condor | Defer: asymmetric width/delta specification adds parameters |
| 9. Iron condor | Retain audio-defined condor as the main baseline, not a literal replication of this source |
| 10. Short strangles | Preserve earlier 0DTE adaptations and their failures; 45-DTE management belongs to SS45DTE |
| 11. Mean reversion/pairs | Defer: no executable spread, hedge ratio, thresholds or exits are supplied |

The sizing transcript is reviewed context. The prior user direction removed Tom's numerical sizing caps; v0.8.5 preserves one-lot orders and a 100% equity ceiling, without Kelly, conviction scaling or martingale. All equity being available is not an instruction to use all margin at every entry. Two $100k research accounts are not a $100k shared portfolio.

Audio baseline evidence: setup at 22:35–29:56; expiry-held research rationale at 81:27–82:56. The screenshot/extraction identifies Option Omega, SPX, short put 20 delta, short call 8 delta, 20-point wings, one lot, $100k and 13 daily entry slots. The displayed 13,492 trades and $101,790 profit are source claims, not QC targets to force-match. Opening/closing fee and slippage semantics are incompletely specified. The original trade CSV/config is still required for exact source parity.

| Audio feature | Status |
| --- | --- |
| VIX opening gap; SPY open versus prior 10-day SMA | Hypotheses; contemporaneous opening availability and exact formulas need admission |
| `qqq_skew_0dte_atm_iv` | Undefined tenor/formula; not replaced by generic broker IV |
| VRP thresholds 0.25/0.5 | Scaling and realized-volatility convention unresolved |
| Intraday SPY VWAP | Needs complete traded-volume/notional bars and strict completion clocks |
| Hurst after noon | Estimator, window and bar interval unresolved |
| Prior GLD/QQQ daily range | Explicit existing research primitives selected for this bounded POC; not claimed as verbatim audio rules |

## 3. Executable strategy contract

Both accounts were specified to trade SPXW same-day options from **2022-05-16 through 2026-10-22**, with a settlement tail through October 24. The condor completes that interval. The spread baseline stops on a margin-call fill at 2022-07-12 15:37 New York, so its partial return/CAGR is not accepted as full-period performance. Source-period results through July 13 remain identifiable. Every year is reported as observed; 2022 and 2026 are partial. No result is prospective live evidence or a newly untouched holdout.

| Rule | Iron condor | Additional put credit spread |
| --- | --- | --- |
| Initial capital / quantity | $100,000; one contract per leg | $100,000; one contract per leg |
| Short put | Target −0.20 delta, absolute error ≤0.02 | Same target and tolerance |
| Short call | Target +0.08 delta, error ≤0.02 | None |
| Protection | Long put 20 points below; long call 20 points above | Long put 20 points below |
| Candidate choice | Preserve prior nearest-short/exact-pair recovery algorithm | Choose nearest-delta admissible exact-width pair; tie by short strike |
| Order | Native four-leg combo market order | Native two-leg combo market order |
| Exit | Native European cash expiry; no discretionary exit | Same |
| Fee | $1.18 per opening contract, $4.72/package | $1.18 per opening contract, $2.36/package |
| Reference fill | Midpoint with $0.05 index-point adverse package slippage | Same package slippage, allocated across two legs |

Decision times are 09:35, then 10:00/10:30 through 15:00/15:30, America/New_York. Exchange-open checks exclude close-boundary entries and respect half-days. No position is intentionally carried beyond same-day expiry. Native orders must resolve within three minutes; unexpected partial/rejected combinations, margin-intervention fills, residual holdings or ledger mismatch stop the algorithm.

The native cache gate requires a non-fill-forward QuoteBar no older than two minutes, positive ask, nonnegative bid not above ask, and spread no greater than three index points. These are inherited simulation gates, not proof of a fresh exchange NBBO or executable midpoint. Zero-bid wings can pass the native reference but fail the stricter independent-data checker; the difference is explicit.

For a credit c in index points, the put spread's ideal maximum expiry loss is `(20 − c) × 100`, plus opening fees. The algorithm reserves the sum of per-episode ideal maximum losses against current equity, and native QC buying power still governs every order. Position grouping and intraday marks can produce different margin behavior; theoretical defined loss does not certify nonnegative native margin headroom. Rejections are retained, never removed to make trade counts look better. The spread smoke already exhibits this distinction: 21 package rejections cite native insufficient buying power, with one maintenance-margin delta of $68,461.85 despite the isolated 20-point spread bound. This is observed simulated margin behavior; its cause and equivalence to a broker must be investigated, not assumed.

Official product references distinguish European cash settlement and SPXW PM conventions: [Cboe specifications](https://www.cboe.com/tradable-products/sp-500/spx-options/spx-specifications). The two-put combo construction follows [QuantConnect's bull put spread documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/option-strategies/bull-put-spread). These references justify structure and lifecycle, not the profitability or realism of the chosen fill assumptions.

## 4. Pipeline and persisted evidence

**Stage A — native baseline.** Freeze contract and algorithm, run the new spread smoke, then attempt full unfiltered condor and spread accounts. The spread fails on a native margin intervention. Its source, failed terminal result, 1,141 raw orders and actual margin-call fills are archived. `scope_amendment.json`, saved before any local selection, excludes it; the condor budget and selection criteria do not change. The existing Rust worker owns submissions. Preserve queue identity, actual project/backtest IDs, source readback, full terminal response, paginated orders, events, logs, fees, annual counts and residual checks. The condor's original-period trades must reproduce the archived control.

**Stage B — local research.** Independently recompute each native expiry payoff from contract identity, signed quantity, opening fill, fee and native settlement reference. Join only completed prior-day raw daily features. Keep labels physically separate from entry features. Filter whole episodes, aggregate daily cash, evaluate the predeclared rule set, save all trials and freeze one rule per strategy. Native baseline funding has already selected the available tape; this stage cannot invent omitted trades or recompute their prices.

**Stage C — funded QC verification.** Submit the frozen predicate with readable raw daily input modules; compute the feature before native order submission. Preserve its value/source-day in tags. Reconstruct final cash again. Compare local and native common episodes by exact contracts, quantities and P&L. Explain added/missing episodes using actual baseline/final native buying-power rejection messages. Zero unexplained differences is an engineering gate. A failed gate is reported; no retrospective reselection is allowed.

**Stage D — research decision.** Compare full native marked drawdown/Calmar and 2025–2026 profit against the matched unfiltered account, then inspect costs, dependence, official settlement and margin. Accounting, frequency, economic preference, model validity and deployment are separate decisions. This final design is generated from the completed evidence rather than a forecast of favorable results.

| Artifact | Key and purpose | What it cannot establish |
| --- | --- | --- |
| experiment contract / job manifests | Version, source/input hashes, dates, budgets | Economic edge |
| native orders/events / raw pages | Backtest + order/event IDs; complete receipts | Executable live fills |
| episodes / legs / labels | Strategy + session-slot episode; contract identity | Unfilled opportunities absent from tape |
| entry features / registry | Episode + source day; formula, units, missingness | Certified historical vendor publication |
| all trials / frozen rules | All 13 trials per strategy and immutable decision | Untouched out-of-sample inference |
| local–QC bridge | Common/added/missing contracts and cash | Equivalence for opportunities absent from both runs |
| official settlement sensitivity | Expiry + official source hash | Refunded account path after changing settlement |
| final verification / decision record | Independent gates and limitations | Live authorization |

## 5. Feature timing and local selection

Only `gld_range_pct` and `qqq_range_pct` are searched. Formula: `(high − low) / close` from the latest completed earlier session. The current day is strictly excluded. Missing/nonfinite inputs or a prior date at least eight calendar days old reject the entry. Raw daily bars are current vintage; next-session availability is an explicit historical assumption. The same-day/future-mutation test verifies code ordering, not publication provenance.

Thresholds are the 25th, 50th and 75th percentiles of **unique baseline-filled days in 2022–2023**. Daily weighting avoids giving a day more weight merely because more of its 13 slots filled. For each threshold test `value > threshold` and `value ≤ threshold`; equality belongs only to the latter. Add an unfiltered benchmark: 2 × 3 × 2 + 1 = 13 trials per strategy. The original budget was 26 total across two strategies; the spread failed baseline admission, so only 13 condor trials were executed. No truncated spread tape is optimized.

Require at least 400 locally retained episodes in each of 2022, 2023 and 2024. Rank eligible trials by 2024 realized-cash Calmar after an additional $10/package cost; break ties by validation net profit, feature, side and quantile. Freeze the winning original training threshold; do not refit on 2025–2026. If none qualifies, retain the unfiltered reference and record the failure. The final native gate remains 360 completed episodes in every included year, without annualizing partial years.

The 2025–2026 evaluation contributes neither outcome nor count to selection. This removes the previous later-count feasibility leak, but does not make the period untouched: prior versions already inspected related market outcomes. A unit test changes later profits/features and removes later rows, asserting the selected rule is unchanged. No claim of a large new feature platform, automated portfolio optimizer or independent option simulator is made.

## 6. Risk and robustness interpretation

Native reported drawdown includes the platform's marks; local search uses realized end-of-day cash. They measure different paths and must not be substituted for one another. Local subperiod Calmars reset the analytical starting cash to $100k; native 2025–2026 profit follows the full funded account path. A local subperiod score is not a reset native account result. All overlapping intraday positions are grouped by session for resampling. Trade count is an engineering/data-sufficiency check, not a count of independent experiments.

The report includes additional costs of $0/$10/$25/$50 per package, removal of the five best days, frozen-threshold ±10%/±20% neighborhoods, annual results and 2,000-replicate circular block bootstraps with 5/20/60-session blocks. Later-period uplift is paired against the same unfiltered reference. A centered 20-day maximum-across-13-rule diagnostic on 2024 is exploratory and includes the no-filter rule; it is not a calibrated proof of alpha or a Calmar hypothesis test. It cannot undo earlier researcher selection across versions.

Local stress cases keep contracts and funding fixed. Higher actual costs or different settlement can alter subsequent account state and order admission, so cash subtraction is a sensitivity, not a funded rerun. The report separately shows the final native uplift bootstrap, which incorporates the candidate's actual native funding path. Neither bootstrap is prospective evidence.

## 7. Independent data architecture and current admission

Execution universe remains SPX/SPXW. Daily context retains SPY, QQQ, IWM, TLT, GLD, SPX and VIX; only two features are used here. Intraday context is primarily SPY/QQQ/SPX/VIX, with IWM/TLT/GLD secondary. QQQ option-surface research is a distinct acquisition/formula task. Price-only feature tickers do not imply a need to buy all their option chains. SPX/VIX have no invented trade volume.

Default independent research cadence remains 5m option snapshots, 30m underlying signals and 15m comparison; native reference execution remains minute-based. At strictly before 09:35, a 09:30 five-minute snapshot fails a two-minute age limit. A 09:34 source observation can satisfy age in principle, but still needs historical availability and coherent cross-leg clocks. Delaying an entry until a 09:35 snapshot arrives defines a different strategy variant.

The latest saved provider clock report has four at-time observations with source quote clocks recovered, approximately 60 seconds old at the probes. Historical availability is unknown for all four; strict acceptance remains zero. The report also records 382,992 pilot quote rows without known source age/historical availability, 4,852 published OI observations and eleven canonically published official settlement observations. Those are distinct evidence classes and coverage scopes. Four clock probes do not certify a full chain. Official outcome archives can support settlement sensitivity without being admitted as entry features.

Provider owns acquisition, licenses, canonical contracts, staging and immutable releases. QC research owns admission, feature formulas, decisions, fill/cost assumptions, funding and evaluation. Read pinned SDK/Parquet releases; do not create another ingestion database here. A complete independent replay still needs contract-effective dates, candidate quote/Greek snapshots, source and availability clocks, actual exchange sessions, underlying basis/actions, and official settlement. OI publication timing and QQQ surface definitions remain unresolved.

A newer October 26 handoff extends the future data-research universe to eleven underlyings: Tier A SPX/SPXW, SPY, QQQ, IWM; Tier B TSLA, NVDA; Tier C AAPL, AMZN, MSFT, GLD, TLT. Its 17-date pilot adds one-minute decision windows to the five-minute panel. This supplements the existing SPXW pilot; it does not retrospectively broaden the completed strategy campaign. Actual same-day listings are required, and physical/American products need their own assignment, dividend and share-delivery design. VIX/VIX9D are context series, not additional execution tickers.

The late provider receipt reports 23,951,694 QQQ quote rows over 1,066 usable sessions, 47 sessions with no same-day expiry and one preserved request failure (2024-06-21), release `20261026T023104Z_9d452096`. Its later Greeks receipt reports 4,842,068 rows across 241 non-contiguous sessions, 825 quoted sessions still pending, release `20261026T060840Z_38acf71e`. Gamma is absent, units are unverified and source-quote/historical-availability clocks remain unknown. This is delivered sampled data with explicit gaps, not an admitted audio-skew feature. `late_provider_review/` pins the exact reviewed receipts because acquisition may continue independently.

OptionOmega's [backtest setup](https://docs.optionomega.com/backtesting/backtest-setup), [FAQ](https://docs.optionomega.com/backtesting/backtesting-faq) and [custom signals documentation](https://docs.optionomega.com/backtesting/advanced-options/custom-signals-tester) distinguish its native backtest data from imported signals. Provider option chains are independent research inputs, not an OO chain upload. The new request's generic “SET” settlement wording must be resolved to the actual SPXW PM series; never substitute AM SET or a generic closing index observation for missing PM outcomes.

The future opportunity ledger must record every scheduled slot, candidate/quote exclusions, chosen legs, feature rejection, funding state and order outcome. Present aggregates and order rejection tags do not recover every rejected chain candidate. Independent replay must compare selection, package credit, expiry outcome, account state and 5m-vs-1m differences before it can replace the fixed-tape stage.

## 8. Capacity and implementation plan

Retain 0.7.5's explicit scope budget: at 1,100 full sessions, 1,000 SPXW contracts/session and 400 QQQ surface contracts/session, 5m core-plus-surface storage is roughly 18–37 GB at 150–300 retained bytes/row; plan 40–80 GB working headroom. These are assumptions, not a measured full-chain census. The newer eleven-underlying request has a separate, larger plan: about 333 million five-minute rows and 50–100 GB retained at its assumed 3,830 contracts/session; its decision-window layer adds roughly another panel of observations. Do not confuse that expanded requirement with the smaller SPXW-plus-QQQ budget or completed acquisition. Seven underlying series are a small additional footprint. SPY options are optional execution expansion; SS45DTE/CN/futures are outside this budget.

Reuse retained finer data and derive views locally; partition source/day/underlying/expiry, sort contract/time, avoid tiny files, keep raw receipts and pin manifests. Derive 15m/30m views without duplicating every source table. Held-contract-only data supports payoff replay but cannot support arbitrary alternative strike selection. Scale acquisition only after the bounded SPXW pilot passes coverage and clock checks.

Next implementation sequence: resolve source/availability policy; complete pilot candidate and official settlement coverage; build the all-slot ledger; implement independent selection/payoff/funding replay; quantify 5m/finer deviations with predeclared tolerances; freeze a future evaluation boundary; run funded individual and shared-capital QC verification. A shared portfolio requires one capital/margin path and correlated stress exposure, not addition of independent account profits or averaging Calmars.

## 9. Reproduction and operational safeguards

Use the commands in `poc/v085/README.md` in order. Baseline execution precedes local selection; frozen selection precedes final submission. The source file and raw input modules are hashed and read back from QC before the serial project can be reused. The existing worker owns writes; no worker was restarted to obtain progress, and no live trading API was used. A local polling failure is not a cloud failure; inspect the recorded native identity before retrying anything.

The artifact directory retains all trial rules, tests, manifests, raw native pages, local labels/features, funding messages, official-settlement comparisons and gate results. Older campaign directories are preserved. Failures are evidence and must remain visible. A later revision must use a new contract/result directory rather than overwriting this campaign to improve its headline.
