# Short strangle research

Current US optimization: one full-universe candidate is running through the shared Rust QC queue: `strangle_basket-calmar_20261019_204146`, backtest `330e590273d094393cec5448670a0c32`. It retains true 504-observation IVR >70 and monthly options, and combines the equity IV/RV gate, capped initial collateral, guarded voluntary exits, fresh-quote risk retries and a 24-calendar-day holding cap. The first product-open noon at <=21 DTE remains an upper holding deadline. The original baseline is unchanged. **Calmar >2 is unproven.** [Frozen candidate](results/strangle_basket-calmar_20261019_204146/manifest.json), [current continuation state](optimization/CURRENT_RESEARCH_PROGRESS.json).

The local Rust observer later stopped after a read transport error, while the same cloud backtest continued. Its local queue `failed` state is not an algorithm-failure verdict. Continue with the read-only collector in the current-state file; do not restart `serve` while cloud execution is nonterminal. The future read-retry and launcher-classification repairs passed 51 Rust and 47 Python tests; a release binary was built but no server was restarted. [Repair evidence](optimization/rust_poll_retry_fix_20261019.json).

The isolated TWTR holding-cap audit passed with six genuine fills, $7.50 in fees, a $253.50 loss and no residual positions. The control reproduced the original failed exit and retained its actual short exposure. These are execution tests, not full-strategy results. [Native paired audit](results/strangle_basket-twtr-age-regression_20261019_203155/twtr_age_summary.json).

[Training entry diagnosis](optimization/training_entry_diagnostics_20261019/FINDINGS.txt) joins 99 audited closed cycles from 2012–2019 to their original entry annotations. All passed IVR >70; stocks/ETFs lost $861.75 and futures lost $8,441.45 after fees. Trade-group sums do not represent a different strategy or funded account Calmar. DuckDB and matching Parquet tables are saved beside the findings.

Latest status: the optimized full baseline completed cleanly in QC and passed its account, native execution and frozen-rule audits. The economic outcome is insolvency on2020-03-12: $60,000 became -$42.29 after145 closed strangles,1,010 fills and$3,405.54fees, with zero holdings. All1,010 native economic fills match the preserved pre-optimization full run exactly. The requested2026 end was not reached; no post-insolvency data or CAGR are invented. [Audited baseline report](results/strangle_basket_20261018_191012/baseline_report/REPORT.md), [summary](results/strangle_basket_20261018_191012/baseline_report/summary.json), [execution equivalence](results/strangle_basket_20261018_191012/baseline_equivalence.json). CSV, DuckDB, Parquet and the equity chart are saved alongside the report. Monitoring is paused.

QC speed validation measured futures preparation1.51x and short equity seeding1.60x with identical selections/fills. The optimized full run took3433seconds through insolvency; this is not a controlled full-cloud speedup measurement. Aggregate timings identify daily preparation/history/chain processing as the remaining dominant cost. [QC speed proof and DuckDB/Parquet](results/performance_fix_20261018/cloud_summary.json).

The prior full run stopped on2020-03-12 after account insolvency: all1,010 fills,145closed cycles and$3,405.54fees reconcile from$60,000 to-$42.29 with zero holdings. The terminal handling repair passed native BAC regression `ce1e9106a49b7c458d79944c45871da9`: all six fills unchanged, no duplicate liquidation, debt/date preserved. [Insolvency repair proof](results/insolvency_fix_20261018/summary.json). An insolvent result ends the observed path; no prices, trades or performance are invented through2026. The optimized full baseline passed those audits through its explicit insolvency outcome.

The CL quote repair and ZW sequential closing repair both survived this run, including their first eligible 21-DTE exits. [ZW repair proof](results/zw_exit_fix_20261018/summary.json). The necessary next engineering change is an explicit fully flat insolvency terminal state preserving debt, date and a prohibition on further entries. Risk-rule changes require separate review and have not been applied.

The previous CL-corrected full run `8257ae601fe9ccb8918762562e5663ac` failed on2017-08-04 at the ZW exit. All726 order attempts and724 fills were retained and Rust/Python exports match. Account equity reconciles to actual fills and open marks, but the interrupted run is invalid as full performance. [ZW failure evidence](results/strangle_basket_20261018_145612/failure_diagnostics/summary.json).

The CL repair remains bounded to LO/CL source sessions December21–24,2015 only: factor.01 on trade/quote data before caching, fills and margin, and completed daily-chain premiums before IV modeling. The exact CL regression passed with10 fills, three rolls, a21DTE TIME exit, zero margin calls and zero holdings; its+$145.30 is engineering evidence. The corrected full run also passed that CL cycle. [CL repair proof](results/cl_scale_fix_20261018/summary.json).

Performance update: redundant chain/model work, repeated equity-window allocation/validation and history-list scans were removed. Local exact-output benchmarks: solver2.0x, chain/selection4.3x, equity candidates5.0x,504-day seeding1.25x;117tests pass. These are component measurements. The failed frozen baseline was unchanged. Paired native futures/equity validation has passed with matching selections and actual fills; total-cloud speedup is not established. [Runtime findings and benchmark artifacts](results/performance_fix_20261018/summary.json).

## Current monthly basket baseline

The current user-confirmed baseline starts with **$60,000**, requests history from
2012-01-03 through 2026-09-30, and waits for **504 completed daily IV observations**.
IVR is the true min/max range rank, strictly **>70**. Screen the point-in-time US
equity/ETF universe and the 15 QC-supported US futures-option roots; rank eligible
underlyings by prior-session underlying share/contract volume, maximum 13.

Use **standard monthly options only**. Entry is the first eligible monthly expiry
at least 35 DTE, targeting around 45; mandatory exit is the first product-open noon
at or below 21 calendar DTE. Existing profit/stop and same-expiry untested-side roll
rules remain. No new batch opens until **all prior holdings,  pending orders and
exit requests have closed**. No replacement entries during a batch.

At opening, allocate account equity/x as a margin/collateral budget to each of
the x selected underlyings. Equal put/call integer quantities use conservative
LEAN initial leg margins and fees, subject to available buying power. Existing
quantities are unchanged as positions close; there is no rebalancing. Combo
quantities use a global lot multiplier with unit leg ratios. These settings
supersede the older fixed-one-contract and 25%-reserve assumptions below.

The engineering run `strangle_basket-smoke_20261018_092403` passed the execution
audit: 288 orders, 41 cycles, five batches, three futures cycles, peak 13 holdings, 
all time exits on their first eligible sessions, no residual holdings and
reconciled fills and fees. Its **20-observation IV history is engineering-only**;
its performance is not the requested full baseline.

The earlier full run `strangle_basket_20261018_092946` has invalid interim performance because native margin liquidation bypassed its ledger. The first repair regression exposed QC's non-empty margin-event return requirement. The corrected focused margin probe `f4490852d042fb2dce9e9e2d51896cd7` then passed: four actual fills, one full 47-contract paired MARGIN close, no duplicate liquidation, zero holdings, Rust/Python exports and account ledger reconciled. It is an engineering reproduction, not baseline performance.

The corrected full 504-observation baseline is `strangle_basket_20261018_101158`, failed on 2015-12-21 after QC rejected a CL paired margin close. The attempted close used a suspicious 317/321 put quote against a $38 strike with multiplier1000; unit/normalization or bad data is suspected but not confirmed. All466 orders and464 fills were downloaded through Rust and Python and match. The monitor is paused. See `results/strangle_basket_20261018_101158/failure_diagnostics/summary.json` and its DuckDB/Parquet evidence. No full baseline performance can be published from this run. The source and helper comparison is saved in its `engineering_validation.json`. The local suite passes 96 tests, including identity and terminal-state checks for resuming an existing execution.
Screening is a QC-compatible port with the user's 504-observation / >70 IVR overrides, rather than an import of today's local candidate list. [The parity comparison](research/screener_parity_20261018.json) records data-source and capitalization-policy differences across the sibling screener's entry points. Requirements were delivered to the active `Continue data providers work` chat and to its project requirements folder.

See [current progress](research/CURRENT_BASELINE_PROGRESS.json) and the frozen
campaign manifest; do not infer completion from a successful engineering run.

```bash
QC_BACKTEST_TIMEOUT_SECS=10800 .venv/bin/python strategies/sstrangle/run.py --phase basket --timeout 11100
.venv/bin/python strategies/sstrangle/basket_pipeline.py strategies/sstrangle/results/<basket_campaign>
```

For an interrupted local session, resume the same cloud execution without submitting a duplicate:

```bash
.venv/bin/python strategies/sstrangle/resume_basket.py strategies/sstrangle/results/strangle_basket_20261018_145612
```

This checks progress once and collects terminal results through the existing pipeline. The app heartbeat is paused after audited completion; no further runs are scheduled. Do not start the Rust server merely to monitor a running cloud backtest: its startup recovery cancels unfinished cloud executions before requeuing them. Routine monitor processes from a previous chat session may have stopped even though the cloud simulation continues.

The pipeline waits for the cloud run, downloads results and full orders through
Python and the shared Rust client, reconciles native contract IDs and execution
details, validates batch separation/IVR/sizing/21-DTE exits, and writes an audited
report plus CSV, DuckDB and checksum-recorded Parquet with readback row counts.
Historical mapped display aliases are preserved; expiry/strike/right come from
LEAN SecurityIdentifiers. This avoids guessing from malformed display names.

Known limits include the historical earnings feed's short forward horizon,
Black76 approximation for American futures options, raw volume comparisons
across different units, and unavailable/invalid contract marks. All exclusions
must remain visible. The [frozen basket specification](basket/baseline_plan.json)
and [data provider requirements](research/DATA_PROVIDER_REQUIREMENTS_20261018.md)
describe these inputs and limits. The local-data work does not block QC baseline
execution. This is backtesting code only.

## Historical SPY reference and earlier experiments

Entry-frequency debugging found that the original 69-cycle historical run required
IV rank >=50, an implementation assumption rather than a numeric rule in the transcript.
The user retained this threshold for that historical SPY reference on October18,
2026. The current basket uses the updated IVR>70/two-year rule described above.
It rejected 3,259 of 3,415 flat-account entry checks. Average holding time was 21.94
calendar days; the low count came primarily from long waits to enter. A separate
`--entry-policy continuous` control removes the IV gate and its history prerequisite.
It retains the existing nearest-45 expiry within 35–55 DTE, monthly options,
profit/stop/21-DTE exits, rolls, sizing and next-session re-entry. It does not force
one trade per month or exact 45-DTE entries. The original high-IV policy remains
available as `--entry-policy high-ivr`; old campaigns remain reproducible.

Every trading session now has one entry-decision reason. Annual JSON logs preserve
the reason counts and data coverage; reporting verifies them against session and
entry totals and saves the decisions to DuckDB and Parquet. The focused 2017
continuous-entry regression completed with 12 cycles and 76 filled orders; both
TIME exits occurred at exactly 21 DTE.
The attempted 2009–2026 continuous control failed on January 30, 2009 because a
mandatory TIME combo had stale contract data and could not fill. That failed run
does not establish a replacement full-history cycle count or performance result.

The [extended SPY baseline, 2009–2026](results/strangle_single_20261018_072859/HISTORICAL_RESULTS.md)
completed through the Rust server: 69 closed strangles, 570 orders, net P&L -$3,621
on $250,000, and 1.92% maximum daily drawdown. IV rank was ready on January 7,
2009; the first entry was May 6, 2010. All 30 time exits passed the first-eligible-session
21 DTE audit. Raw evidence, annual results, a chart, DuckDB and Parquet exports are saved.
This longer test also exposed and corrected stale entry/IV quotes from prior sessions.

The [SPY 21 DTE audit and order-downloader fixes](results/spy_21dte_audit_20261018/RESULTS.md)
include fresh original and corrected QC orders, leg trades, fill CSVs and an expiry-based exit audit.

QuantConnect implementation of strategy 10 from the user-saved [transcript](../../data/youtube/transcripts), using the workspace Rust server, source bundling, independent SSTRANGLE.duckdb queue, and configured shared QC project pool. This is backtesting code only.

The [completed 2024–2025 comparison](results/strangle_comparison_20261017_134629/RESULTS.md) returned −1.37% with managed rolls and −1.71% without rolls. All 324 filled orders were downloaded and independently reconciled to cycle P&L and fees. Eight local tests passed. Both runs finished with no assignments or residual positions.

## Source rules and supplied assumptions

Source rules: sell an OTM put and call together near 45 DTE at 16–20 absolute delta; prefer high IVR; take 50% of opening credit as profit; roll the untested side to control delta; keep sizing small and underlyings diversified.

Implementation assumptions:

- Fixed SPY, GLD, TLT universe; $250,000 initial capital; IB margin brokerage model and its default fee/fill/assignment models. No interest is added to idle cash by this algorithm.
- Minute subscriptions with standard monthly options, strike filter ±40 listed strikes, expirations 21–55 DTE. Decisions once daily, on the first data slice after the scheduled event 30 minutes before SPY closes. There are no intraday stop checks between these snapshots.
- Prefer expiry nearest 45 DTE within 35–55 DTE; choose OTM contracts nearest 0.18 absolute delta inside [0.16, 0.20]. Delta takes precedence over the narrative expected-move guideline; no separate expected-move filter.
- Legacy QuantLib Crank–Nicolson pricing model (`OptionPriceModels.QuantLib.crank_nicolson_fd`); daily ATM IV is the average of the two contracts nearest spot at the target expiry. IVR uses the min/max of the prior 252 valid daily observations, excluding the current observation and clipping to [0,100]. IVR ≥50 is required. This is ATM IV rank, not IV percentile or a vendor constant-maturity IV series. Before the trading period, subscriptions are restricted to ±1 ATM strike because only IV and return history are needed.
- Run 2022-12-01 through 2025-12-31; no entries before 2024-01-02 and 252 prior valid IV observations. The initial thirteen months build IV and correlation history. IV sampling uses expiries 21–55 DTE nearest 45; new entries still require 35–55 DTE. QC headline annualized statistics include the idle initialization period; custom active_return, active_cagr, and active_daily_mdd isolate the intended trading period.
- Bid ≥$0.05, OI ≥100, spread ≤max($0.10, 25% of midpoint); IV calculation, entry, rolling and profit/loss management require quote bars no more than five minutes old. Fresh trades cannot make old bid/ask quotes eligible. Mandatory time, final-date and split exits bypass that quote-age gate and submit a market combo. Submitted orders are monitored on every minute slice and recorded only after both legs fill; rejection or an unresolved order after five minutes fails the run. This preserves same-session calendar exits. Combo market orders use QC default fills; no extra slippage overlay.
- Exactly one put and one call per ETF; one concurrent cycle per ETF. Skip if the 20%-of-spot-notional sizing reserve exceeds 10% of equity per cycle or 25% aggregate; require remaining margin ≥twice the candidate reserve. This is a sizing guard, not maximum loss or an exact broker margin estimate.
- Require absolute 60-observation return correlation ≤0.70 with every open underlying, aligned on snapshot dates with at least 40 common observations. Snapshot returns use raw stock prices and are not dividend-adjusted total returns.
- Profit exit is net cycle cash flow less fees and ask-price close estimate ≥50% of initial gross credit. Include prior rolls in cash flow but keep the target anchored to original credit. Estimated close commission is $2.00, matching the one-contract minimum fees observed in the smoke test; actual realized fees come from fill events.
- Additional loss exit: net cycle P&L ≤minus twice original credit. Time exit: at the first daily evaluation with calendar days until contract expiry ≤21, independently of quote freshness; this is not 21 days held. If the 21 DTE date is a market holiday, the first subsequent session can have fewer than 21 DTE. End-date flattening takes precedence, then time, then split, then profit, then loss. No re-entry on the same day as exit; no entries during final seven calendar days.
- Managed variant: when short-position net delta magnitude ≥0.20, roll only the untested leg toward spot to 16–20 delta in the same expiry. Require at least $0.05 quoted net credit, no crossed strikes, at most one roll per day and three per cycle. No-roll control differs only by disabling these rolls.
- If assigned, flatten delivered stock and remaining options at the next daily evaluation; assignment cycles are flagged and excluded from option-only cycle win-rate/P&L metrics. Portfolio-level QC returns still include holdings. This policy does not preempt ex-dividend assignment risk.
- End-of-run validation rejects zero-entry tests and unclosed cycles. Any stale quotes, missing roll contracts, rejected candidates, assignments and exit reasons are counted in runtime statistics.

## Run

```bash
.venv/bin/python -m pytest strategies/sstrangle/tests -q
python3 strategies/sstrangle/run.py --phase smoke --dry-run
python3 strategies/sstrangle/run.py --phase smoke
python3 strategies/sstrangle/run.py --phase comparison
python3 strategies/sstrangle/collect.py strategies/sstrangle/results/<comparison_batch>
```

Smoke: SPY only, January–April 2024, 20-observation lookback, IVR threshold zero, entries from February. It verifies cloud behavior, not performance under the final strategy assumptions.

Historical single-ticker dates can be overridden explicitly:

```bash
QC_BACKTEST_TIMEOUT_SECS=3600 .venv/bin/python strategies/sstrangle/run.py \
  --phase single --tickers SPY --start 2008-01-01 --trade-start 2009-01-02 \
  --end 2026-09-30 --timeout 4200
```

Add `--entry-policy continuous` to run the regular-entry control. With the default
high-IV policy, trading requires 252 prior valid IV observations; continuous mode
collects IV features but does not wait for them. Runtime statistics record the
first chain, valid IV and usable IV-rank dates. Annual coverage and entry-decision
counts are also written to compact JSON logs. Date-overridden campaigns are baseline
studies and require their own frozen plan before local optimization. The 2024–2026
optimization plan is not automatically applied to them.

The collector requests charts over the actual backtest window with sufficient
sampling density for daily observations. Historical reporting rejects a daily
equity chart whose observation count differs from the algorithm's snapshots.

Comparison: managed versus no-roll, identical default settings otherwise. Source snapshots, manifest, raw results, and logs are saved under results/. The runner reuses an already-running server or starts and later stops its own server; it does not modify other strategies' sources or queue entries. The shared server may process any other queued workspace work according to its normal scheduler.

The collector downloads full cloud result details, charts, order history, and available log lines, and exports summary.json and summary.csv. QC may return empty log responses; downloaded orders and runtime counts remain available for execution checks.

## Improvement research

The [completed improvement study](results/strangle_improvements_20261017_141237/RESEARCH_RESULTS.md) tested all three changes and audited 494 new filled orders. On 2024–2025 data the IV/RV gate reduced the net loss from $3,429 to $831. Frozen validation on January–September 2026 returned −$82 versus −$4,776 for the unchanged baseline, but the candidate traded only one cycle. It has not established a profitable edge. All 14 local tests pass.

The [baseline diagnosis](research/baseline_diagnostics.md) attributes the original losses by exit, ETF and option right. The [frozen research plan](research_plan.json) specifies three separate changes: loss exit at one opening credit; an entry gate against strong trailing 20-session trends; and ATM IV at least 1.2 times trailing 20-session realized volatility. They retain the baseline ETF universe, one-contract sizing, IVR threshold and daily management schedule.

Both return features use the existing raw-price decision snapshots and only observations available at entry. Realized volatility is sample standard deviation of the latest 20 simple returns times sqrt(252). Trend displacement is the sum of log(1 + return) over those observations divided by realized volatility times sqrt(20/252). The trend variant requires absolute displacement ≤1; the premium variant requires IV/RV ≥1.2. Neither condition uses future returns.

```bash
python3 strategies/sstrangle/diagnose.py
python3 strategies/sstrangle/run.py --phase improvements
python3 strategies/sstrangle/campaign.py strategies/sstrangle/results/<improvements_batch>
python3 strategies/sstrangle/research_report.py strategies/sstrangle/results/<improvements_batch>
```

The campaign waits for discovery, audits completed results, selects the highest net P&L candidate with at least ten cycles, freezes its configuration, and tests unchanged baseline versus candidate over 2026-01-02 through 2026-09-30, using history from 2024-12-01. Discovery results are on an already inspected period and cannot establish out-of-sample performance. Validation data must not be used to re-select thresholds. Entry features are saved in opening-order annotations and exported as entry_features.csv for audit.

## Single-ticker campaign

The [2026-10-17 campaign report](results/strangle_single_20261017_162036/RESULTS.md)
contains per-ticker cloud results, local filter research and provider coverage.

`run.py --phase single` runs SPX, SPY, QQQ, IWM, AAPL, MSFT, AMZN, NVDA,
TSLA, TLT, GLD and IBIT independently through the Rust queue. The trading window
is 2024-01-02 through 2026-09-30, with earlier IV history. SPX uses standard
monthly index options and European Black–Scholes pricing; the other tickers retain
the baseline equity-option model. SPX uses $2.5 million initial capital so one
contract passes the original sizing guard; other accounts use $250,000.
IBIT requires 252 valid option IV observations before any entry, so its eligible
period is substantially shorter. [Nasdaq](https://www.nasdaq.com/newsroom/nasdaq-listed-ibit-options-end-first-day-top-1-all-options-products-traded)
dates its options launch to November 19, 2024.

```bash
.venv/bin/python strategies/sstrangle/run.py --phase single --timeout 14400
.venv/bin/python strategies/sstrangle/single_pipeline.py strategies/sstrangle/results/<single_batch>
```

The pipeline downloads full QC results, available charts and logs, all orders,
QC leg trades, entry annotations and independently reconstructed cycles. It runs
36 local entry-filter combinations under the [frozen plan](single_research_plan.json),
using actual AKQuant execution checks and separate discovery/validation periods.
Provider trade-bar repricing is reported separately with whole-cycle coverage and
staleness limits. These are conditional filters of a frozen baseline, without
replacement entries or changed management paths. Historical bid/ask quotes are
unavailable through the current Alpaca integration; current quotes are never used
as historical fills.

## Interpretation limits

The [local AKQuant implementation](local/README.md) replays the frozen QC order tape
using shared `data_providers` exports. Its [audited results](results/local_akquant_20261017/LOCAL_RESULTS.md)
reconcile the baseline and disclose the limits of historical option trade coverage.
The [audio workflow notes](../../data/audio/options_backtest_workflow/WORKFLOW.md)
describe entry-time feature joins and chronological research boundaries.

The two-year trading period is a first historical test, not an out-of-sample validation of a strategy selected independently of this period. Monthly-only selection, limited strike range, once-daily management, fixed one-contract sizing, default QC fills, assignment treatment, and supplied defensive exits materially affect results. Check skip counts, actual rolls, cycle counts, and residual positions before drawing conclusions. Default QC trade win rate counts individual legs; use cycle_win_rate for closed, non-assignment strategy cycles. Neither margin reserve nor the daily stop bounds gap or tail losses.

API references: [QC short strangles](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/option-strategies/short-strangle), [QC combo market orders](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/combo-market-orders).
