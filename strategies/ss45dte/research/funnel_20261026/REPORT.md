# Current conclusion — corrected daily IV history

**The earlier 25-trade +$293 result is superseded as a normal daily-IVR baseline.** It omitted IV observations while a position was held. The corrected five-name control has 18 trades, −$3,002 net and 5.2% account drawdown. Historical receipts below remain valid for their actual code, not for a complete daily-IV series.

## Final comparisons using the corrected series

| Policy | Pairs | Net P&L | Drawdown |
|---|---:|---:|---:|
| Update IV history while holding | 18 | $-3,002.00 | 5.200% |
| Corrected IV history: spread <10% | 24 | $-3,573.00 | 5.100% |
| Corrected IV history: afternoon retry | 21 | $-3,926.00 | 6.300% |
| Corrected IV history: 17 names | 62 | $-10,101.00 | 10.100% |
| Corrected IV history: exit 14 DTE | 16 | $-4,687.00 | 6.500% |
| Corrected IV history: exit 7 DTE | 16 | $-3,632.00 | 5.800% |
| Corrected IV history: 1% capped paper pilot | 6 | $156.00 | 0.000% |

The canonical research algorithm now updates daily IV history on held sessions; 13 targeted tests pass, including the new regression. No live routing was enabled. Pilot thresholds remain proposed risk preferences. None of these in-sample comparisons establish manual-trading alpha or an optimal parameter.

The original-universe broad diagnostic and the corrected broad diagnostic both use fixed one-pair sizing, up to five open positions and 50% account margin. They are not the 1% stress pilot. Correlated exposures and different entry sequences prevent interpreting the difference as a pure universe-selection effect.

## Corrected baseline economics

Eleven winners earn $4,173 and seven losers lose $7,175. Mean win $379.36, mean loss $1,025, profit factor 0.582, mean trade −$166.78 and largest realized loss $4,605. The 61.1% win rate is below the approximately 73.0% break-even rate implied by these observed mean gains/losses. Small samples make these descriptive estimates, not future probabilities.

Actual entry DTE: 41–50, median 46; only three of 18 entries were at exactly 45 DTE. Ten exits were scheduled at 21 DTE (or prior full session) and eight were earnings exits. This is a near-45 entry policy with early exits, not an exact 45/21-only experiment.

## How to interpret the historical diagnostics below

The following section answers why the originally reported 25 trades occurred. Calendar-first masks and the 100-fill reproduction make that attribution auditable. It is preserved separately from the corrected-series results above. Do not combine their trade counts or rank their P&Ls as if they came from one unchanged implementation.

# SS45DTE quantitative review — 26 October 2026

**Manual execution remains the intended strategy. QC tests its measurable components; these runs do not validate discretion.**

Sample: 2 January 2024–23 October 2026. Starting equity: $150,000. Same one-pair size, $1/contract/order fee, one-cent/share adverse slippage and bid/ask market fills unless stated. No live orders.

## Completed comparisons

| Change from five-name control | Closed pairs | Net P&L | Account drawdown | Wins / pairs |
|---|---:|---:|---:|---:|
| [Five names, original rules](https://www.quantconnect.com/project/31338460/93cc0d0d216c23268947e8895b150086) | 25 | $293.00 | 4.500% | 17/25 |
| [Remove IVR >50](https://www.quantconnect.com/project/31338461/65b4876eec8631ca19e401964b4bbe29) | 73 | $-10,306.00 | 11.100% | 49/73 |
| [Spread <10% instead of <5%](https://www.quantconnect.com/project/31338456/b8ee21e4a1956a39ecb61aae0f5b81e2) | 31 | $-183.00 | 4.500% | 20/31 |
| [Allow afternoon retry](https://www.quantconnect.com/project/31338455/ba39584efd5618df9e10b9710077c786) | 27 | $1,170.00 | 4.500% | 19/27 |
| [Expand to 17 names](https://www.quantconnect.com/project/31338454/1c8c559029f4d4129c65a848d7306b83) | 93 | $-8,627.00 | 10.900% | 62/93 |
| [Update IV history while holding](https://www.quantconnect.com/project/31338453/5a4464990c7157d8120892b5005374e1) | 18 | $-3,002.00 | 5.200% | 11/18 |
| [Exit at 14 DTE](https://www.quantconnect.com/project/31338461/54a79f87ad1874b3b197b1ebafcd725a) | 17 | $-3,357.00 | 6.500% | 12/17 |
| [Exit at 7 DTE](https://www.quantconnect.com/project/31338458/c0e8a6a644a910eb40aca1af8f7c74d4) | 20 | $-1,593.00 | 4.900% | 13/20 |

These are full-policy comparisons: entries, holdings, earnings windows, future IV history and available capital can change after a rule change. They are not a matched-entry estimate of each filter’s causal value. The 14/7-DTE variants also change subsequent entry availability. Choosing the best row would be in-sample optimization.

## Where the original opportunities disappear

Count one underlying/session at most once per stage, even if the program retries each minute. Multiple days can concern the same monthly expiry, so these are candidate-days, not independent trade opportunities. The original stage order checks IVR before DTE. The unchanged calendar-mask rerun attributes the monthly window first to avoid calling off-window sessions IVR rejections.

| Stage | Candidate-days remaining | Removed at this step |
|---|---:|---:|
| Available for evaluation | 3,054 | — |
| Monthly expiry in 40–50 DTE | 1,009 | 2,045 |
| IVR >50 within that window | 224 | 785 |
| Event feed/policy | 181 | 43 |
| Both daily deltas in 0.16–0.22 and positive IV | 152 | 29 |
| Both selected legs OI >500 | 86 | 66 |
| Fresh usable quotes | 82 | 4 |
| Each spread <5% of midpoint | 39 | 43 |
| Selected legs pass live BSM delta recheck | 25 | 14 |
| One-pair size and margin pass; submitted | 25 | 0 |

All original quote-ready dates passed the fixed-one-pair sizing/margin stage if their live delta passed. Therefore the 25-trade result is not the zero-trade 0.5% sizing test. The earlier 479 stress rejections belong to that separate strict-sizing run.

## Which names are actually tradable under these rules?

| Name | IVR pass | Monthly window after IVR | Daily delta pass | OI pass | Quote-ready | Spread pass | Submitted |
|---|---:|---:|---:|---:|---:|---:|---:|
| CRWD | 181 | 63 | 42 | 22 | 22 | 5 | 3 |
| EWZ | 92 | 32 | 20 | 17 | 13 | 0 | 0 |
| META | 91 | 29 | 27 | 27 | 27 | 20 | 12 |
| SWKS | 260 | 86 | 49 | 6 | 6 | 0 | 0 |
| TLT | 46 | 14 | 14 | 14 | 14 | 14 | 10 |

EWZ and SWKS produce no original trades. Every quote-ready candidate-day for each failed the 5% spread gate; SWKS also lost many candidates on OI. The selected pair is the closest to 0.19 delta before live liquidity is checked: another acceptable pair is not searched. A failed morning pair blocks another attempt that afternoon. The retry comparison isolates the latter operational restriction.

## Why profit is low

- 17 winners earned $6,196; eight losers lost $5,903. Average win $364.47 versus average loss $737.88; profit factor 1.05. A 68% win rate barely exceeds the approximately 66.94% break-even rate implied by those observed averages. This is descriptive, not a forecast.
- Largest loss: $3,247 on META. Keep this valid loss in the analysis; removing it would disguise the short-option tail.
- Net profit averages $11.72 per pair. Using dates of actual fills, 540 calendar position-days across 1,025 calendar sample days imply about 0.53 pairs open on average. Low deployed scale depresses account return, but scaling does not repair weak net expectancy.
- Against contemporaneous submission midpoints, modeled execution cost is $938.50 half-spread plus $100 slippage and $100 fees. A hypothetical midpoint, no-fee/no-slippage arithmetic result is $1,431.50; it is not an executable strategy result.
- An extra three cents/share of adverse slippage on the same 100 standard-contract fills costs $300 and changes +$293 to −$7. This is fixed-ledger sensitivity, not a new backtest.

## Is five names too narrow?

Yes for researching or sourcing opportunities for a general short-strangle strategy. The five names were inherited from prior data/p5 coverage, not selected by a defensible market-wide universe process; three are technology names. The effective traded universe is only META, CRWD and TLT.

The expanded diagnostic retains the original five and adds SPY, QQQ, IWM, DIA, EFA, EEM, XLF, XLE, XLV, GLD, SLV and HYG. These are predeclared research additions, not buy recommendations or 12 independent risk factors. The fixed one-pair control retains a five-open-position cap and 50% modeled account margin cap; it does not use the stricter proposed 1% stress pilot. Ordering and capital constraints can alter the original names’ trades.

| Expanded-universe name | Closed pairs | Net P&L |
|---|---:|---:|
| CRWD | 1 | $237.00 |
| DIA | 1 | $272.00 |
| GLD | 14 | $-3,426.00 |
| IWM | 22 | $56.00 |
| META | 9 | $-2,703.00 |
| QQQ | 12 | $-1,647.00 |
| SLV | 13 | $-62.00 |
| SPY | 11 | $-1,790.00 |
| TLT | 4 | $299.00 |
| XLE | 2 | $112.00 |
| XLF | 4 | $25.00 |

A broader list is more representative but does not itself establish a positive edge. This is a static surviving universe and a shared in-sample period. SPY/QQQ/DIA and sector ETFs overlap; never treat their ticker count as diversification. Recheck actual contract size against the account stress budget before recommending any broader live book.

## Evidence ledger for the manual strategy

| Component | Evidence | Status |
|---|---|---|
| 45-DTE entry | 40–50 calendar DTE monthly band used consistently | Operating convention; no test establishes optimal entry DTE |
| 21-DTE exit | Compared with 14 and 7 DTE as complete policies | Quantified sensitivity; no pure same-entry or independent optimality proof |
| IVR >50 | Removal comparison plus conditional entry-window counts | Quantified filter; do not infer optimum threshold |
| Delta 0.16–0.22 | Counted daily and live recheck losses | Threshold not optimized or independently validated |
| Liquidity | OI, quotes and 5%/10% spread comparison; native cost reconciliation | Costs are material; limit-order performance remains unmeasured |
| Universe | Five versus predeclared 17 names | Opportunity breadth tested; surviving/static-universe and correlation limitations remain |
| Position size | Prior strict 0.5% versus capped 1% pilot, documented in 25 Oct report | Risk tolerance choice, not statistically established maximum loss |
| Manual discretion | No prospectively labeled manual decision/skip/fill sample | Not validated by these algorithmic runs |
| Robustness | Name/year decomposition, cost sensitivity and corrected units | No untouched holdout or reliable tail probability estimate |

## Recommendations for hand execution

1. Broaden the watchlist rather than forcing more size or removing safety gates. Select by current liquidity, contract-size suitability and distinct risk exposures; apply the same total portfolio budget.
2. Retain the verified continuous daily-IV fix for further validation. The old code skipped a name’s IV observations while holding it; the DAILYIV comparison measures this implementation effect. Keep one consistent same-source IVR definition and clearly label its approximate ATM basis.
3. Reassess an eligible name later in the session after a failed first attempt, and choose among eligible strikes using current quotes. The existing program’s one preselected pair/one attempt restriction is not a necessary manual rule. Do not assume the retry result guarantees improvement.
4. Keep 45→21 as a simple declared baseline unless a prospectively tested alternative justifies a change. Do not pick an exit, IVR threshold or spread threshold just because its row wins this sample.
5. Record entry/skip/hold/exit decisions with as-of data and actual fills; compare against a frozen quantitative baseline. Separate selection, execution and early-exit effects. This is how manual judgment becomes measurable.

## Limits and provenance

QC option-universe Greeks/IV are prior-session values; the live delta check instead uses a midpoint-implied European BSM approximation, constant 4% interest and zero dividends. Rejections can reflect model mismatch as well as market movement. Upcoming earnings exposes only seven days, not full-window knowledge at entry. Monthly expiry selection, holiday shifts, no new entries in the final 35 days and early risk/event exits remain explicit. These conventions are not a full replication of discretionary limit trading.

Calendar-month and annual outcomes are descriptive partitions of the same inspected data, not held-out evidence. Twenty-five baseline trades cannot establish robust tail probabilities, expected annual income or a durable edge. All results are modeled historical outcomes, not guaranteed manual performance.

Reproducible files: `manifest.json`, `latest.json`, per-run `.py`, `.result.json`, `.orders.json`, `.reconciliation.json`, `evidence.json`, `pnl_attribution.json` and `instrumentation_regression.json`. The instrumented baseline reproduces all original 100 order identities, times, quantities and prices. All reported outcomes require native-fill reconciliation.

Official mechanics: [QC equity-option universe and prior-day Greeks](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity-options); [QC upcoming earnings](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/eod-historical-data/upcoming-earnings); [OIC short strangle](https://www.optionseducation.org/strategies/all-strategies/short-strangle).
