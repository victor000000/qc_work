# Version 0.8.7 — Independent reproduction and a simple companion strategy

Design date: 2026-10-27, Asia/Shanghai. Status: design and published-data audit completed; strategy implementation and new QC/local runs pending. This is not a completed performance release. No v0.8.6 implementation was found in the strategy workspace. Frozen 0.8.5 artifacts remain unchanged.

## 1. Objective and decision

Prove whether the existing SPXW iron-condor strategy can be independently reconstructed from provider observations, and determine which differences arise from market data, selection, fill assumptions, settlement or funding. In parallel, evaluate one fixed, simple SPXW put credit spread. An unsuccessful replication or rejected companion is a valid research result; it must not be relabeled success because aggregate profit looks similar.

The pipeline is QC baseline → independent local research → QC verification. QC supplies the native benchmark and reconciliation ledger. Provider data supplies the local candidate universe, quotes, Greeks, features and official expiry values. QC-selected trades or QC payoff labels must never be the input universe or outcome generator for the independent run.

0.8.5 ran a legitimate baseline/filter/funded-QC experiment, but its local research filtered QC episode payoffs. It did not implement an independent market replay. It produced better full-period Calmar but lower 2025–26 net profit than the unfiltered reference, and exposed native-versus-official settlement differences. Those are the questions 0.8.7 addresses; it does not assume a profitable edge.

## 2. Data readiness and limits

The companion coverage_snapshot.json is generated directly from one pinned provider release. It counts only same-day contracts in 2022-05-16 through 2026-10-22 and records the manifest hash, quote/Greek session overlap and source receipts. It excludes raw acquisitions and later releases. Min/max dates do not imply continuous coverage; session overlap does not imply synchronized valid contracts.

At the reviewed provider checkpoint, SPXW had approximately 7.24 million published quote observations over 197 sessions and 7.21 million first-order Greek observations over 195 sessions. QQQ had 23.95 million quote observations over 1,066 sessions and 23.90 million Greek observations over 1,064 sessions. Consult coverage_snapshot.json for the exact audit result and timestamp. The direct 06:30 Shanghai audit pins release 20261026T221548Z_79212fa0 and includes the newly published QQQ tail, which postdates the copied provider summary. Additional SPXW acquisitions are not admitted until published. QQQ has 1,064 quote/Greek overlapping sessions; SPXW has 195. The two QQQ quote sessions without Greeks require explicit reconciliation.

The provider reports 664 completed six-sample timing windows checked, with two uncertain keys excluded. This is a pilot across tickers, not full-period SPXW/QQQ timing coverage. Official SPXW expiry values cover 1,114 dates against the retained census; independent calendar/PM identity and revision-clock acceptance still need checking. Gamma is absent in the first-order delivery. Documented second-order access requires a different entitlement; no purchase is assumed. Vendor Greek version/TTE conventions and units are unresolved.

Three distinct data modes prevent ambiguous claims:

| Mode | Admission | Permitted conclusion |
|---|---|---|
| Same-input engineering fixture | Identical frozen quotes, Greeks, fees and expiry values for two implementations | Selection/arithmetic implementation parity |
| Sampled independent research | Real provider snapshots; known sampling semantics; unknown event/availability clocks flagged | Conditional historical research under declared timing assumptions |
| Strict independent replay | Verified quote event time and historical availability, valid contract eligibility, synchronized inputs | Point-in-time reconstruction within measured sampling limits |

Unknown availability must not be fabricated as next midnight or snapshot time. A one-minute lag is a sensitivity assumption, not proof of historical availability. Gamma is required for the requested full risk dataset but is not an entry input for either fixed strategy: delta-based sampled replay may proceed without it if correctly labeled. Historical availability is a hard gate for strict replay, even if all other data arrives.

## 3. Frozen experiments

Run three separate $100,000 accounts. No shared capital or portfolio blending in this release. All positions use one package per admitted decision, multiplier 100 and actual SPXW PM same-day contracts. No parameter optimization or threshold refitting is authorized by this design.

| ID | Strategy | Purpose |
|---|---|---|
| C0 | Unfiltered 13-slot SPXW iron condor | Reproduce the existing reference |
| C1 | Same condor with the frozen prior-session QQQ range filter | Reproduce the 0.8.5 candidate |
| P1 | One 10:00 ET SPXW put credit spread per session | New simple companion; independent engineering and economic test |

C0/C1 retain the audio-demo-derived geometry: short put target delta -0.20, short call +0.08, tolerance 0.02 inclusive, long put exactly 20 points below its short and long call exactly 20 points above its short. Entry slots are 09:35 and every half hour from 10:00 through 15:30 ET. Half-day entries stop strictly before the actual expiry trading close; do not hard-code an entry after 13:00. Hold accepted packages through expiry. No profit target, stop, rolling or overnight discretionary holding.

Preserve the archived selector: choose nearest admissible OTM short deltas, breaking ties by ascending strike; if an exact wing is unavailable, search admissible exact-width pairs and select nearest target with the same tie rule. Enforce tolerance after pairing. Both implementations must use the same eligible universe; QC's archived ±60-strike subscription is a data boundary to record, not a reason to crop the independent provider universe silently. Compare full-provider and QC-universe-restricted selection as separate diagnostics.

C1 admits a day only when the preceding completed QQQ session's (high-low)/close exceeds 0.016380462988098386. Equality fails. Preserve archived source-row and missing/stale-feature behavior in the legacy track, including the seven-calendar-day age guard. Independently rebuilt raw QQQ OHLC features form a separate feature-parity track; use exchange session calendars and provenance, not a rolling 24-hour interpretation. Never refit the threshold to new provider prices.

## 4. Companion P1: single-entry put credit spread

At 10:00 ET on each eligible session, sell one OTM SPXW put nearest delta -0.20 within 0.02 and buy one put at exactly 20 points lower, same expiry. Tie by ascending short strike. Both legs must pass the chosen quote admission mode. If there is no pair, skip with a reason; no later retry, replacement width or alternate delta. Net opening credit after modeled slippage must be positive and below 20 points. Hold to official PM expiry. No QQQ filter, stops, trend rule or discretionary exceptions.

This is a new schedule variant of the rejected 0.8.5 multi-entry spread, not a claim that the old failure is fixed. It is a deliberately simpler 0DTE adaptation of Tom's credit-spread concept, not a source-exact reproduction of his longer-DTE examples. The 10:00 entry, width and delta are fixed engineering choices, not selected from historical performance.

Reserve theoretical worst-case loss plus opening fees before entry. Additionally require package risk no greater than 2% of previous-session closing equity; with one package daily, this cannot justify increasing size to chase a trade-count target. QC native brokerage/position-group buying power remains independently authoritative. A nonpositive equity or insufficient native buying power means skip. A margin call, unexpected liquidation or unhedged partial fill is a failed execution gate, not a tunable outlier.

The old spread failure occurred on July 12, 2022. Include that session and neighboring sessions in the mandatory smoke. Compare theoretical spread reserve with QC position-group requirements before/after each leg and combo. Log order-event chronology. Do not assume the broker will grant theoretical max-loss margin, suppress native margin calls or increase starting capital to make the smoke pass.

P1 has at most one entry per eligible session. Therefore the old 360/400-episode annual gates cannot apply. Use filled/admissible/scheduled ratios and year-by-year opportunities; no minimum count is achieved by adding entries.

## 5. Price, fee and accounting conventions

Freeze two execution models before evaluation. Legacy benchmark mode reproduces 0.8.5 midpoint fills with 0.05 index points adverse slippage per package ($5), allocated equally across legs; opening fee $1.18 per filled contract. No invented expiry closing fee. These are experimental assumptions, not broker quotes. C0/C1 have $4.72 opening fees; P1 has $2.36. Check individual modeled prices remain positive.

Conservative sensitivity crosses the observed market: sell at bid, buy at ask, plus 0.05 points adverse slippage per leg. Derive all package costs from leg count: four for condors, two for P1. The archived quote-side branch hard-codes four-leg entry-credit slippage, so it must not be reused unchanged for P1. Preserve this finding in the implementation checklist and test two-leg fees/slippage explicitly.

For signed leg quantities q (long positive), opening cash is -100 × sum(q × fill_price), less fees. Expiry cash is 100 × sum(q × intrinsic), where put intrinsic=max(K-S,0) and call intrinsic=max(S-K,0). Equity equals cash plus signed marked positions. Aggregate identical contracts for holdings and buying power but preserve episode allocation. Never double-count identical legs, fees or exercise events across overlapping episodes.

Maintain three outcomes separately: native QC settlement; fixed-contract provider official-settlement sensitivity; and full independent replay with resulting cash/funding changes. Replacing final payoff in a QC tape is not a full funded rerun. Mark equity with contemporaneous quotes, report missing marks and sample interval, and label sampled marked drawdown separately from realized-cash drawdown and QC native drawdown.

## 6. Stage A — QC baseline

Before submission save experiment_contract.json, code/config/input hashes, immutable run identity and all intended variants. Export reference 0.8.5 artifacts into read-only provenance links. Use the existing serial QC queue and inspect project/backtest identities after uncertain creation; do not blindly resubmit.

Run C0/C1 against legacy feature inputs as controls and P1 as a new fixed baseline. First run edge-case smoke, then the full date range. Instrument every scheduled slot, chain visibility, candidate delta, quote/bar clock, wing decision, credit, reserve, native margin, order, fill, expiry and rejection. Separate telemetry-only changes from strategy changes. Run a legacy-control comparison to detect altered decisions from instrumentation.

Capture QC engine/build information where exposed, brokerage model, price model, contract universe, warmup, calendar, data resolution and source hashes. Save native orders, logs, equity and fee/settlement ledgers; page all orders and verify totals. End only after the last expiry events are processed, with zero residual holdings. An incomplete/error run cannot provide performance acceptance.

## 7. Stage B — Independent local research

The local engine reads immutable provider Parquet through a manifest-pinned adapter. It independently builds every scheduled decision, including skips; it does not start from the QC filled-trade table. Build (session, decision, contract) input views, retaining candidate and excluded-contract provenance.

Data contract: identity/root/expiry/right/strike/multiplier/style/settlement; listing and opening eligibility; bid/ask/sizes/conditions; snapshot, quote-event and availability timestamps; Greek observation/model/units/input timestamps; underlying raw price and adjustment lineage; feature source session; official settlement value/type/publication/revision; calendar. UTC storage with explicit New York session interpretation and DST tests. Null means unknown. Do not turn no-expiry days into missing quotes or fill failures into zero-return trades.

Sampled primary timing uses the last snapshot strictly before decision time, no more than 120 seconds old by sampling clock, with the one-minute windows supplying it. Report this as assumed availability. A snapshot equal to decision time is a separate legacy-aligned sensitivity. Strict mode additionally requires verified quote_ts ≤ available_at ≤ decision time, age ≤120 seconds, maximum inter-leg quote skew ≤30 seconds, and point-in-time Greek/feature inputs. A complete minute grid alone does not satisfy those tests. No future, crossed, negative, fill-forward or silently carried quotes. In legacy parity mode preserve bid≥0, ask>0 and spread≤3 points; zero bids remain explicitly visible. Positive-bid-only selection is a separately labeled diagnostic, not a hidden baseline change.

Run deterministic selection, episode accounting, portfolio accounting and worst-case reserve independently. QC-native funding cannot be inferred from max loss: report a local conservative reserve track separately, then reconcile native acceptance differences. An optional LEAN buying-power adapter is a second model with its own pinned version, not the independent accounting oracle.

QQQ options are used for data/Greek/timing validation in 0.8.7; QQQ raw daily prices supply C1's context feature. A QQQ execution strategy is deferred because physical exercise/assignment and adjusted-contract treatment are not yet accepted. SPXW primary evidence must not wait for unrelated breadth data, but no missing QQQ feature is silently replaced by SPX or adjusted-close proxies.

## 8. Reconciliation ladder

| Test | Compare | Acceptance |
|---|---|---|
| Identical-input fixture | Independent selector/accountant vs QC-exported fixture | 100% same decisions/contracts; cash error ≤$0.01 per episode/account event |
| Candidate universe | Every scheduled slot and eligible contract | Every exclusion and difference classified; no unexplained omission |
| Independent provider run | Selection, credit, fees, expiry, skips, marks, funding | Full difference report; not forced numerical equality across vendors |
| Fixed-contract bridge | Same contracts under both price/expiry sources | Attribute quote, Greek/selection, feature, fill, fee and expiry differences |
| Funded bridge | Re-run sequential accounting after each intervention | Explain path-dependent additions/missing trades and margin calls |

Use a fixed attribution order: universe → timing/quotes → Greeks/selection → feature → fills/fees → settlement → funding. Since interactions are order-dependent, publish the order and residual; do not present components as causal estimates. Record selected deltas from both sources and distance from tolerance boundaries. Near-boundary flips are evidence to explain, not automatically waive.

Preregister screening tolerances: daily entry-decision agreement ≥95%, package-contract agreement ≥95% among jointly eligible decisions, and unclassified differences zero. These are diagnostic pass criteria, not statistical proof that vendors are equivalent. Report the complete distribution of per-leg price/expiry errors and dollar impact; do not invent a universal acceptable P&L error across models. Any unexplained difference affecting conclusions fails reproduction acceptance even if percentages pass. No tolerance is loosened after seeing results without a new experiment revision.

## 9. Research design and economic evidence

No new search is needed to prove C0/C1. Treat 2022–2023 as historical development, 2024 as historical validation and 2025–2026-10-22 as already-inspected later evaluation. None is an untouched holdout. Register any future forward window before its observations arrive. P1's fixed parameters avoid a new tuning grid but do not make reused history out-of-sample.

For every strategy report annual/monthly net profit, daily return series, drawdown from marked and realized cash equity, annualized return using actual elapsed time, Calmar, fees, turnover, opportunity/admission/fill counts, holding exposure, minimum cash/equity/margin and residual holdings. Compare C1 vs C0 on matched calendar days (including legitimate no-trade days) and report coverage-qualified overlap separately from full-account results. Do not fill unavailable market-data days with zero returns.

Robustness: both fill models; incremental adverse costs $10/$25/$50 per package; sample timing lag 1/2 minutes where data exists; official vs native expiry; removal of best five days; daily block bootstrap with 5/20/60-session circular blocks, 2,000 replicates, seed 8701. Bootstrap is descriptive dependent-sample uncertainty, not an independent-market guarantee. Report yearly downside and losses concentrated in stress days. Missing gamma blocks gamma diagnostics, not payoff arithmetic; do not create an undocumented Greek proxy.

Economic promotion requires positive net profit under the declared conservative-cost scenario, no unexplained exposure/funding failure, and disclosure of later-period deterioration. C1 may not be advertised as an improvement if the later-period profit sacrifice remains without an explicitly stated user objective. P1 is evaluated independently; it need not beat C0 to demonstrate correct infrastructure, but no edge or deployment claim follows from that engineering success.

## 10. Stage C — QC verification

After local audits, freeze final code/config/feature hashes and a diagnostic decision ledger. Production-style QC verification computes entry decisions from feature inputs and its native chains; never upload future outcome labels or substitute local selected strikes as the final strategy. A separate fixed-contract diagnostic replay may consume preselected contracts only when visibly labeled as a reconciliation experiment.

Run the same C0/C1/P1 rules with the frozen comparison settings. Reconcile full submitted, rejected and filled slot sets, native account P&L, fees, settlement and zero residual exposure. Compare to Stage A and local records. Explain changed QC data/engine behavior before attributing a change to the strategy. If no strategy code change occurred, still distinguish baseline and verification identities and prove their hashes; do not call an old run a new verification.

The final decision has separate flags: engineering_parity, sampled_replay_complete, strict_replay_ready, economic_robustness, companion_margin_safe_in_test, and live_ready=false. A single green pipeline badge is not acceptable. No live order or brokerage deployment is in scope.

## 11. Build plan, tests and outputs

Implement under strategies/sstrangle/poc/v087, keeping v085 read-only. Proposed modules: contract.py (schema/config); provider_inputs.py (pinned views and quality); select.py (pure rules); ledger.py (fills/expiry/marks); funding.py (separate reserve model); qc_adapter.py; reconcile.py; campaign.py; report.py. Share a declarative strategy contract but use independent accounting implementations to avoid testing a function against itself.

Required tests: put/call payoff on both sides and at strike; condor and spread max loss; exact-width ties/missing wings; stale/future/unknown clocks; half-days/DST; prior-session feature equality/missing values; overlapping identical legs; two-leg vs four-leg slippage; cash/equity/fee conservation; partial fills/rejections; margin-call trace; official PM vs AM settlement; deterministic replay hashes. Test the July 2022 spread failure window and data-only stress/holiday/adjustment fixtures without choosing cases for favorable returns.

Deliver: immutable experiment contract; coverage and input manifest; slot/candidate/episode/account ledgers; source/model split metrics; margin trace; reconciliation classifications; robustness results; native QC artifacts; design/report PDF and machine-readable final verdict; a trial ledger of failures and all attempted variants.

Execution order: (1) coverage/contract freeze, (2) identical-input fixtures and QC smoke, (3) C0/C1/P1 QC baselines, (4) provider pilot replay and gap classification, (5) full coverage-qualified independent replay and robustness, (6) frozen QC verification, (7) final report. Provider data gaps may permit fixture/pilot work while preventing full-period claims. Do not let a failed P1 block completion of the core condor investigation; retain its failed status and evidence.

## 12. Sources and provenance

- Existing specification and failure boundary: strategies/sstrangle/poc/v085/README.md and strategy.py.
- Frozen threshold: strategies/sstrangle/results/qc_poc_20261026_v085/frozen_rules.json.
- Native performance/settlement findings: the frozen 0.8.5 design report, final_verification.json and decision_record.json.
- Provider readiness, gamma entitlement, settlement coverage and timing QA: copies in evidence/ and hashes in coverage_snapshot.json.
- [Cboe SPX specifications](https://www.cboe.com/tradable-products/sp-500/spx-options/spx-specifications): SPXW expiry trading cutoff and contract conventions; checked 2026-10-27.
- [QuantConnect bull put spread](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/option-strategies/bull-put-spread): native strategy reference; checked 2026-10-27.

Tom's three-strategy discussion, eleven-strategy extraction and the audio demo remain archived source material documented in 0.8.5. They motivate hypotheses; they do not supply missing timestamps, margin assumptions or proof of an edge. The release manifest records local source hashes for this design.
