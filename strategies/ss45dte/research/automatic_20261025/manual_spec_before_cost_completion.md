# 45DTESS: quantitative framework for discretionary execution

Revision: 2026-10-25, Asia/Shanghai. Strategy identity: the manual 45-DTE-entry /
21-DTE-exit short strangle, also called SS45DTE in `qc_work`. It is independent
of SSTRANGLE. This is the current manual rule specification; it supersedes the
conflicting manual rules in the dated short-strangle reports. Historical reports,
receipts and backtest sources remain unchanged. This revision is a specification,
not implemented alerts, a validated edge, or permission to place orders.

## 1. Cycle confirmed by the trader

Enter the monthly expiry near **45 calendar DTE**; **close at 21 calendar DTE**.
At that time the next monthly expiry is usually near 45 DTE: assess it for the
next cycle. Monthly spacing varies; calculate actual DTE rather than assuming
it is always 45. Use 40–50 DTE as the reference entry band; outside it is a
separately recorded variant, not silent drift in the baseline.

DTE is expiry date minus the venue's current session date. Close by the scheduled
session for expiry minus 21 calendar days. If that date is a holiday, weekend or
half session, use the preceding full session. Save the exchange calendar version,
expiry/last-trading-time distinction, and intended closing window. Earlier exits
are allowed for risk or a recorded discretionary reason. No discretionary extension
past the 21-DTE deadline in this baseline.

Replacement on the same day is allowed **after the old close is confirmed** and
positions, margin and buying power are refreshed. It is a fresh entry decision,
not an automatic roll or a requirement to keep premium income constant. If no
candidate passes the gates, remain in cash. A partial close does not free the
whole risk budget.

## 2. What must be quantitative, and where discretion belongs

“Hard to quantify” means a reliable decision model is unavailable; it does not
mean the inputs or subsequent outcome should go unmeasured.

| Decision area | Must be measured / reproducible | Permitted discretionary judgment | Boundary and audit record |
| --- | --- | --- | --- |
| Cycle | Exact expiry, DTE, session calendar, exit deadline | Entry timing within the eligible window; skipping a cycle | No extension beyond 21 DTE; record reason for early exit or skip |
| Volatility | Same-source IVR and IV percentile separately; actual-expiry leg IV, skew, term structure; RV20 and RV60 | Is elevated IV sufficient compensation for the particular uncertainty? | IVR >50 is the baseline screen, not proof of positive expected return; no size increase solely because IVR rises |
| Regime / trend | Returns, gaps, RV, drawdown, trend measures and sector exposures | Is this a temporary repricing or a persistent change? Is a catalyst already priced? | Record evidence available at decision time, alternatives and invalidation; avoid a fabricated confidence probability |
| Event risk | Event date/time, source, confirmation status, ex-dividend and planned holding window; implied-move convention | Importance of news, credibility of guidance, likely market reaction | Known earnings inside the planned holding window excluded from baseline; missing date is unresolved, not “no event” |
| Strikes | Both deltas, dollar delta, strike distances, credit, bid/ask and stress loss | Choose among eligible strikes; avoid a level where the thesis is weak | Reference absolute delta band 0.16–0.22 on each leg; material directional tilt is a separately tagged variant |
| Liquidity / execution | Exact-leg spreads, quote ages/sizes, OI timestamp, volume, commissions, partial fills | Patience, limit price, whether quoted depth is credible, abandoning a trade | Never report midpoint as a fill; stale or invalid quotes cannot pass entry readiness |
| Size / portfolio | Actual holdings, equity, broker margin/buying power, joint stress loss, risk remaining and contract units | Allocate less than the computed maximum; choose among candidates | Discretion can reduce risk or skip; it cannot override precommitted dollar limits to rescue a position |
| Management | P&L net of costs, delta/gamma/vega, strike distance, stress loss, event changes, data freshness | Hold, reduce or exit after reviewing an alert; judge whether the thesis remains valid | Hard risk/expiry boundaries prevail; decision and reason saved, including “hold” |
| Profit taking | Net realized/unrealized P&L and fraction of original net credit captured | Take an early gain when remaining reward no longer warrants exposure | Compare with the frozen 21-DTE baseline later; 50% credit capture can be a review alert, not a proven optimum |
| Evaluation | Trade episodes, fees, slippage, drawdown, stress breaches, matched baseline and rejected candidates | Interpret unusual context; propose the next hypothesis | Do not rewrite old rationales or optimize parameters on the same evaluation sample |

Quantification measures exposure and tests decisions. It does not by itself supply
an optimal threshold: the tolerable drawdown and capital committed remain trader
preferences, translated into fixed numerical limits before entry.

## 3. Entry decision card

1. **Identity and readiness:** exact contracts, expiry, multiplier, currency,
   exercise/settlement style, adjustments, current broker holdings and account
   capacity. Confirm both legs have usable, contemporaneous quotes.
2. **Quantitative screen:** monthly 40–50 DTE; both leg |delta| 0.16–0.22;
   baseline IVR strictly >50. Follow the repository's same-source 252-observation
   convention, minimum 60, clearly flag partial windows. Missing IVR does not pass.
   IV percentile is additional context, never a substitute. IV minus RV20/RV60 is
   context, not a mandatory positive-edge test or a claim about future RV.
3. **Liquidity:** judge the contracts actually traded, not ATM OI. Reference
   gates are OI >500 and (ask−bid)/mid <5% **per selected leg**, with positive
   bid, ask >= bid, known OI date, executable-size context and quote freshness.
   These are unvalidated conservative conventions; store absolute spread/ticks
   too. Failing candidates can stay on a watchlist, not silently pass the gate.
4. **Events:** evaluate the actual planned holding interval through the 21-DTE
   exit, with an execution-delay buffer recorded. Earnings after that interval
   are not automatically disqualifying. Recheck schedules before entry and daily.
   For macro/country events, record the discretionary hold/reduce/avoid decision
   with an event stress. If it cannot fit the budget, skip or exit before the event.
5. **Thesis:** one paragraph: why sell volatility here, what could invalidate
   that view, and why this candidate rather than an alternative or cash.
6. **Risk:** save one-contract and post-entry portfolio scenarios, size, limits,
   margin reserve, monitoring plan, exit deadline and reason codes before ordering.

Start the manual watchlist with instruments you understand and can monitor;
retain the broader US optionable discovery universe and missing-coverage report.
The five historical study names are not an approved or validated trading list.
CN/futures/index options require their own delivery, margin, expiry and model
conventions; do not inherit equity-option assumptions simply because they screen.

## 4. Sizing must be quantitative; the risk appetite is a choice

Retire `vega × p5(IV − future RV)` as the sizing rule. That statistic is neither
a change in IV nor a realized strangle-loss quantile. A low TLT proxy must not
mechanically authorize many contracts. A sum of marginal p5 values is not a
mathematical upper bound on portfolio loss. Historical p5 is also not maximum loss.

Before an entry, specify numerical dollar limits for **one trade, one correlated
cluster, the whole strategy, and account drawdown**, plus a minimum buying-power
reserve and planned review times. These are required configuration, not values
inferred from the old 5% convention. If not specified, no “approved quantity” can
be calculated. An illustrative pilot discussion could start at 0.5% of account
NAV per trade / 1% per cluster / 2% total modeled stress loss; these are proposals,
not trader-approved limits, guarantees, or empirically optimal numbers.

Compute per-contract full repricing over an explicit scenario set including both
spot directions, gap moves, IV increases/decreases, skew and time passage, plus
historical joint stresses when usable. Retain scenario definitions and model
limitations. A first exploratory grid might include spot ±5%, ±10%, ±20% and IV
+10/+20 percentage points, extended for the instrument's observed gaps and event
risk; it is not an exhaustive tail bound. Test correlated names together and
include existing exposures across brokers, with timestamped FX conversions.

For positive one-contract modeled stress loss L, a preliminary bound is
`floor(available trade stress budget / L)`. Search quantities at or below it,
reprice the whole post-trade book under the same scenarios, and select the largest
integer satisfying **all** trade, cluster, portfolio and broker-capacity limits.
Avoid double counting multiplier or quantity. Report vega in currency per **one
percentage point** of IV, with decimal-vol vega /100 where needed. Margin is an
additional feasibility constraint; it is not a loss estimate.

Zero/invalid L or missing risk inputs cannot justify unlimited quantity. If even
one contract is too large, skip, choose a smaller suitable instrument, or evaluate
a separately tagged defined-risk structure. A spread/iron condor changes the
payoff and costs and must be assessed independently. Naked strangles have
unbounded upside loss; modeled stresses and stop orders cannot cap gap losses.

## 5. Monitoring, alerts and exits

Review near the session open and sufficiently before its close to execute, and
after material news or an alert. US regular hours extend into the Shanghai night:
record actual availability or a responsible monitoring arrangement before entry.
The suggestion is an operating convention, not a demand for continuous screen time.
If monitoring cannot be arranged, use less exposure, a separately assessed defined
risk structure, or skip. Data collection alone does not establish that alerts work.

| Trigger | Classification | Required response |
| --- | --- | --- |
| 21-DTE closing session | Hard baseline rule | Close and reconcile fills; if market/broker prevents execution, record incident and outstanding risk until closed |
| Precommitted loss/stress/margin/drawdown limit breached | Hard risk rule | Reduce/close toward compliance promptly; no adding risk or postponing because of a recovery forecast |
| Absolute delta >0.35 on either leg | Quantitative review alert, unvalidated threshold | Reassess spot path, events, portfolio exposure and cost of exit; record hold/reduce/exit and next review |
| Strike within 0.5 daily sigma | Quantitative review alert, unvalidated threshold | Same review; define signed OTM distance below; an ITM leg must remain alerted |
| 50% initial net credit captured | Optional review alert | Assess remaining credit versus risk and costs; early closure permitted |
| New event, stale inputs, broken feed or uncertain positions | Data/risk incident | Block new exposure; verify through broker and manage existing risk explicitly |

For an OTM put use `(S−K)/(S × IV/√252)`; for a call use
`(K−S)/(S × IV/√252)`, IV in decimal annual units. Negative values mean ITM.
This is a labeled daily-volatility approximation, not a probability or stop price.
Use a documented day-count convention; do not divide a dollar distance by a
unitless return volatility.

Default management is hold/reduce/close the whole pair. No adding contracts to
recover losses. A same-strike later-month roll, recentering or single-leg adjustment
is a separate hypothesis: record the realized close, new risk, costs and reason;
do not relabel a realized loss as extra credit. The confirmed cycle replacement
at 21 DTE remains a fresh entry and is not prohibited by “no rescue rolling.”
Assignment creates real stock/futures exposure; reconcile it and manage it even
when no option chain is available. Do not assume the second leg closed because
the first leg filled.

## 6. Make discretion testable without pretending it is an algorithm

Save a decision record for every entry, rejected candidate, alert, hold, adjustment
and exit: decision/session time, strategy version, data release/as-of, exact legs,
account, thesis, evidence known then, event outlook, invalidation, action, alternative,
risk before/after, next review and whether it departed from the baseline. Preserve
original entries; append later reviews. Link broker executions with a trade-episode
ID, including commissions, partial fills, assignments and related underlying trades.

Useful reason codes: CYCLE_21, PROFIT_REVIEW, RISK_LIMIT, EVENT_CHANGE,
THESIS_INVALIDATED, LIQUIDITY, DATA_STALE, SKIP, ALERT_HOLD, VARIANT.
Confidence can be an ordinal score with a written meaning; do not present it as a
calibrated success probability without evidence.

Review monthly: net P&L, drawdown, largest losses, stress-limit incidents, slippage,
remaining exposure, rule adherence and performance by decision reason. Record
MAE/MFE only to the resolution of available executable marks. Evaluate discretionary
exits against a matched same-entry/same-size 21-DTE hold using actual-contract quotes
and realistic costs; missing quotes make the comparison unavailable. Keep capital
reuse effects separate. Evaluate skipping decisions too, to avoid judging only
trades selected after hindsight. Separate directional P&L, volatility effects and
execution where the data support it; residuals stay explicit.

A useful first research question is **whether discretionary early exits improve
net drawdown-adjusted outcomes versus the fixed 21-DTE exit**. Test one change at a
time, with training cutoffs and held-out evaluation. Do not freeze a demonstrated
safety defect for twelve months, and do not tune for every recent loss. Sample
adequacy depends on independent episodes/regimes, not an arbitrary calendar duration.

## 7. Corrections and evidence limits

- Prior prose uses 21-DTE entry; the actual requested cycle is 45 to 21, about
  24 calendar days of exposure at a literal 45-DTE entry. A 21-session future-RV
  measurement is a different horizon.
- `(1−delta)^2` is not an exact strangle win probability. The two terminal ITM
  events are mutually exclusive for ordered strikes, not independent; delta is
  price sensitivity, and profit also depends on premium, exit time and costs.
- A model touch probability is not realized stop performance. The 38% versus 35%
  touch statistic does not establish that every roll has zero expected value.
- IV−future RV is a volatility comparison, not captured trade premium or dollar
  P&L. The historical study also needs a clock audit: its return index includes
  the following close in trailing RV, and its forward window starts one return
  late. Do not use the reported correlations to declare RV60 optimal.
- The saved provider assessment reports event rows exist but lack first-known
  timestamps; “no event calendar at all” was too strong. Its 21-DTE coverage
  inventory does not establish coverage at the 40–50 DTE entry window.
- Existing SS45DTE audit identifies a 100× vega-unit mismatch, missing-chain
  management gating and optimistic fill state. Its diagnostic trades and unrelated
  SSTRANGLE backtests do not validate this manual strategy. No code fixes or new
  backtest results are claimed in this revision.

Sources inspected on 2026-10-25: [prior manual report](../../reports/loss_attribution_2026-10-25/STRATEGY_short_strangle_final_20261025.md),
[calculation source](../../apps/trade_profile/strategy_quantification_20261025.py),
[SS45DTE audit handoff](../../../qc_work/strategies/ss45dte/research/review_20261025/HANDOFF.md),
and [provider assessment](../../../data_providers/docs/requirements/DTE21_P5_PROVIDER_STATUS_20261025.md).
These are saved evidence, not refreshed live account or market measurements.
For independent mechanics, see [OIC: short strangle](https://www.optionseducation.org/strategies/all-strategies/short-strangle)
and [OIC: leverage and risk](https://www.optionseducation.org/optionsoverview/leverage-risk).

Provider delivery contract: [45DTESS discretionary quantitative inputs](../requirements/45DTESS_DISCRETIONARY_DATA_20261025.md).
