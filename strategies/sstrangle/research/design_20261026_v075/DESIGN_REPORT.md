# Draft 0.7.5 0DTE strategy PoC design

26 October 2026 · SPXW execution, complete cross-market inputs, 5m sampled research

**Version 0.7.5 retains the verified 0.7 reference strategies and adds a smaller, explicit path to independently sourced 5m option research.** It incorporates the negative robustness findings from 0.8 rather than treating a later version number as evidence of a better strategy. Version 0.8 and its frozen experiments remain intact. This is a design revision with a runnable local admission and evidence-audit PoC; it does not claim new funded returns or completed independent option execution.

The immediate optimization is to collect the right data once, keep data quality separate from strategy selection, and avoid spending compute on a wider search before contract, timing and funding differences are understood. The trading universe remains SPXW. Seven underlying feature series and the QQQ option-surface extension are explicitly included in the data inventory and capacity plan.

## 1. Review findings and decisions

| Finding | Revision in 0.7.5 |
| --- | --- |
| Earlier storage estimate counted SPXW options but omitted the complete 0DTE feature dataset; it mixed in the separate SS45DTE book | Separate SPXW options, seven underlying series, QQQ option surfaces and optional SPY/QQQ execution expansion. SS45DTE is outside this PoC |
| A 5m sampling timestamp was at risk of being interpreted as a fresh quote | Preserve snapshot time, originating quote time and historical availability separately. Unknown clocks fail strict execution-input admission |
| Strict pre-09:35 joins use 09:30 on a 5m grid and 09:34 on a 1m grid | Keep a strict reference mode. Treat any decision after the 09:35 snapshot arrives as a separately timestamped sampled variant, with no native-parity claim |
| Fixed funded-trade filtering omits opportunities rejected by the original capital path | Require a complete opportunity ledger before independent selection/funding claims. Keep fixed-tape screening labeled conditional |
| Draft 0.7's IWM-volume strangle filter reduced native Calmar and lost money in its later period | Retain the unfiltered strangle control; retire that filter from candidate promotion without deleting its evidence |
| Condor accounting passed despite negative sampled margin headroom | Keep it as a research reference, with a separate margin-readiness failure. Do not change capital or wings to hide the issue |
| Broad repeated searches and future-year count feasibility weakened inference | Freeze existing rules; future bounded searches use training-only feasibility. Report later-year count failures without reranking on them |
| More timestamps and features do not automatically produce independent evidence | Use day-clustered comparisons, explicit source lineage and a capped pilot; reject unsupported features before search |

The earlier 0.7/0.8 accounting, feature and funded-native verification is valuable and reusable. It does not establish independently sourced prices, historical publication clocks, native margin replication, Option Omega parity or robust alpha.

## 2. Strategy references and preserved conventions

Use the existing 0.7 source hashes and frozen thresholds as the reference. The three strategy accounts remain independent; they are not a funded combined portfolio.

| Strategy | Frozen structure | Research disposition |
| --- | --- | --- |
| Condor | SPXW 0DTE; short put about −0.20 delta, call about +0.08; exact 20-point protective wings; ±0.02 short-delta tolerance; one lot; $100,000 | Compare unfiltered control with frozen GLD prior-range filter. Negative sampled margin headroom prevents promotion |
| Strangle | SPXW 0DTE; about ±0.16 delta; one lot; $2 million | Keep unfiltered control. Preserve the rejected IWM-volume filter as failed evidence |
| Put | SPXW 0DTE; about −0.25 delta; one lot; $2 million | Compare unfiltered control with frozen QQQ prior-range filter |

Preserve 09:35 then 10:00, 10:30 through 15:30 New York decisions, strictly before the actual exchange close; no 13:00 entry on a 13:00 half-day. Normal sessions have 13 slots, half-days seven. The frozen baseline holds to same-day cash expiry without discretionary stop/target/roll. Keep $0.05 index-point adverse slippage per package, $1.18 opening fee per contract and the original modeled zero expiry commission as reference assumptions, not verified universal transaction costs. Do not silently assign the condor delta tolerance to naked strategies.

Source interval: 2022-05-16 through 2026-07-13. Extension: through 2026-10-22; tag it separately. Daily warmup begins 2021-01-01. Previously inspected dates remain development evidence. The source calendar counted 1,042 sessions and 13,492 eligible original-period slots; actual extended-period grids must come from the exchange calendar, not the rough storage-session assumption below.

Inherited 0.7 funded results are context, not new 0.7.5 performance:

| Filtered candidate | Episodes | Native net P&L | Native MDD | Native Calmar | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| Condor | 4,755 | $132,103.40 | 29.7% | 0.752 | Further research only; sampled margin deficit |
| Strangle | 3,147 | $158,521.08 | 16.2% | 0.114 | Reject filter; later-period loss |
| Put | 4,883 | $722,370.06 | 4.2% | 1.825 | Further research only |

Do not compare naked-account dollar profits to the condor without their different capital bases. Original Option Omega trade exports/configuration and official settlement provenance remain dependencies for exact source parity.

## 3. Complete ticker and dataset map

| Instrument | Data required | Frequency and priority | Need full option history now? |
| --- | --- | --- | --- |
| SPX / SPXW | Official index observations, eligible same-day PM option inventory, quotes, delta/IV, contract master, settlement | P0: 5m quotes; finer entry discrepancy slices; daily and timestamped index open/close | SPXW candidate expiry on pilot dates; broader history only after admission |
| SPY | Raw OHLCV, actions, opening prefix, traded-volume VWAP inputs | P0: daily and completed 5m source bars, 30m/15m features | No. SPY options are a distinct deferred execution expansion |
| QQQ | Raw OHLCV, actions; separately named 0DTE ATM-IV/skew primitives | P0 price bars; P1 option-surface extension | Yes for the surface extension, with explicit strikes/expiries; not all maturities |
| IWM | Raw OHLCV and actions; volume-z reference context | Daily P0; intraday P1 | No |
| TLT | Raw OHLCV and actions | Daily P0; intraday P1 | No |
| GLD | Raw OHLCV and actions; prior-range reference | Daily P0; intraday P1 | No |
| VIX | Index daily/opening/closing observations, source clocks | P0 daily context; intraday P1 unless an opening feature is admitted | No VIX option-chain requirement |

SPX and VIX have no fabricated trade volume. ETF listing market is US even where an ETF holds foreign assets. CN/futures, 45-DTE strategies and top-50/top-100 expansion remain separate projects. Potential later SPY/QQQ trading requires its own exercise, assignment, dividends, share-delivery and margin model; SPX cash-settlement semantics cannot be copied to those products.

QQQ surface acquisition must preserve raw contract/expiry/quote inputs. Record actual 0DTE availability on each date rather than assuming every historical weekday had the same expiries. The audio's named skew feature is still undefined: do not relabel a broker 30-day IV series as that feature. ATM-IV, put/call skew and risk reversal each need a distinct formula and provenance before use.

## 4. Three clocks and two research modes

Keep **observation cadence**, **strategy decision time** and **execution observation time** separate.

**Reference mode:** reproduce the frozen native 0.7 schedule, minute QuoteBar cache gates and costs. Same-timestamp data without ordering evidence is not treated as known. Targeted finer or at-time source observations are required where 5m snapshots cannot support an entry. Native QuoteBar end-age is not exchange quote age; report the two checks independently.

**Sampled mode:** 5m historical NBBO snapshots and compatible underlying/Greeks inputs; 30m completed underlying signals, 15m comparison. All resulting marks and drawdowns are explicitly sampled. An observation labeled 09:35 can support only a decision after its recorded availability, or after a separately declared historical latency assumption in exploratory mode. The latter cannot pass strict point-in-time admission. Do not pretend a 09:35:01 decision is the original 09:35 execution.

Concrete case: at strictly pre-09:35, the most recent 5m row is 09:30 and the most recent 1m row is 09:34. The former fails a two-minute snapshot-age limit. Delaying the decision may admit the 09:35 snapshot, but unknown originating quote time and historical availability still block freshness certification. Neither increasing the age tolerance nor forward filling silently resolves this conflict.

The provider's saved October 26 sampling report covers 584 retained CRWD/EWZ/SPY contracts, not SPXW. It found different bid/ask values for all 584 at those strict pre-09:35 joins, with a 240-second sampling-time difference. This demonstrates sampling mechanics only. Its 46,136 derived 5m rows have no known originating quote age. Preserve that finding and the pinned file hash; do not infer strategy P&L from it.

The new admission primitive requires finite positive two-sided prices and sizes, NBBO classification, timezone-aware clocks, source and snapshot age within 120 seconds, availability strictly before decision, and consistent clock ordering. Package checks also expose a proposed 30-second originating-quote skew limit. This is a stricter research-input gate, not a modification of the frozen algorithm or proof of a fill. Illiquid/zero-bid wings need an explicit alternative acceptance study rather than an invisible relaxation.

## 5. Pipeline and ownership

Provider receipts and identities → immutable source release → schema/clock/coverage admission → opportunity ledger and features → independent quote-backed replay → bounded historical comparison → frozen native QC rerun → research decision.

Provider owns licensed acquisition, source fields, canonical identities, calendar/actions, provenance, staging and publication. QC owns feature decisions, alpha search, contract selection, cost/fill assumptions, portfolio funding and statistical evaluation. Read provider releases through the existing SDK/Parquet contract; do not create another ingestion store in qc_work.

Persist these logical tables separately:

- Contract master keyed by source/canonical contract and effective validity, with underlying, expiry/last-trade time, settlement/exercise, multiplier and adjustments.
- Quote snapshots keyed by source/contract/interval, retaining quote timestamps, availability, conditions, sizes and raw receipt references.
- Greeks keyed by source/model/contract/time, with units, spot/rates/dividends and failure states. Daily Greeks never fill intraday rows without a labeled model calculation.
- Underlying bars keyed by instrument/basis/session/interval; preserve actual completion and availability. Exact VWAP needs notional/volume.
- Opportunity ledger keyed by strategy/version/ticker/session/decision slot. Record every scheduled attempt, candidates considered, excluded/missing reasons, chosen legs, feature pass, funding result and final disposition. A rejected or missing-data slot stays in the ledger.
- Holdings, orders, fills, settlement and labels separate from entry features. No outcome or successful-fill-only fields in alpha inputs.

For multi-leg entry use one coherent decision snapshot and report per-leg ages/skew. Do not sum unrelated bid/ask extremes to invent a package price. Preserve midpoint reference, conservative quote-side sensitivity and actual native fills as separate observations. Cash expiry uses independently evidenced official settlement where available; native expiry-reference replay remains a distinct weaker evidence class.

## 6. Data volume and storage optimization

The earlier measured benchmark had 583 contracts, whereas the newer provider sampling report has 584. They are different retained samples and must not be conflated. The 583-contract measurement used 227,953 one-minute rows and 46,057 five-minute rows. Compressed raw + indexed DuckDB + sorted ZSTD Parquet measured 19.4 MB versus 3.7 MB. Null quote clocks and absent full Greeks make this a lower-complexity sample.

Planning below uses 150–300 bytes per option snapshot for retained raw, indexed canonical storage, one Parquet release and an assumed Greeks allowance. These are budget ranges, not measured full-chain storage. Contract counts include both calls and puts across requested expiries. Roughly 1,100 full sessions are used for capacity only; half-days reduce rows slightly.

| Complete 0DTE scope | Contract/session assumption | 1m retained | 5m retained |
| --- | ---: | ---: | ---: |
| SPXW core | 1,000 | 65–129 GB | 13–26 GB |
| QQQ surface extension | 400 | 26–52 GB | 5–10 GB |
| Core plus QQQ surface | 1,400 | 90–181 GB | 18–37 GB |
| All seven underlying series | Seven instruments; 40–160 bytes/bar assumption | 0.12–0.48 GB | 0.02–0.10 GB |
| Optional SPY execution expansion | Additional 400 | Additional 26–52 GB | Additional 5–10 GB |

Daily history, metadata and small manifests add further overhead; these are not full-market/all-expiry estimates. Use approximately **40–80 GB working headroom for the 5m core plus QQQ surface**, or **180–365 GB for 1m**, before separate backups and extra release retention. At 1,000 SPXW contracts, the 11-session 5m pilot is about 0.13–0.26 GB under the same allowance. Replace assumptions with an actual contract-session census and populated-field measurements after the pilot.

Optimize collection and storage in this order:

1. Reuse verified retained 1m data; derive 5m/15m/30m views locally. This saves network work, not the space occupied by retained originals.
2. Pilot full eligible same-day SPXW candidate coverage. Scale to chain snapshots at declared selection slots plus exact held-leg 5m paths only if alternative entry/strike research does not need the excluded rows. Declare sparse coverage explicitly; a held-leg-only panel cannot support arbitrary selection replay.
3. Store QQQ surface slices separately; avoid fetching every option expiry for a price-only feature ticker. Include enough raw neighboring contracts to audit interpolation and expiry selection.
4. Sort/partition Parquet by source, date and underlying/expiry with contract/time ordering. Benchmark row-group/file sizes; avoid a tiny file per contract. Preserve stable metadata once per contract/version instead of expanding repeated JSON into every row.
5. Prefer virtual 15m/30m snapshot views and materialize only frequently reused feature panels. Keep source clocks through every transform. Aggregate true OHLCV only from complete children; sampled quote extrema are not interval extrema.
6. Keep pinned release references and retention manifests. Additional releases, staging and backups consume capacity according to physical copies/deduplication; no deletion of raw evidence is authorized by this revision.

## 7. Smaller experiment and acceptance design

Do not rerun the 864-rule search or launch new native jobs simply to change a version label. Recheck the frozen evidence first. Use the same entry opportunity universe, pricing convention and calendar when comparing frequencies; attribute missing coverage separately from changed selection, feature availability and funding.

The next bounded experiment permits at most six admitted primitive features and 36 single-feature rules per strategy: three training quantiles, two directions, no compound filters. Existing GLD/QQQ reference rules remain frozen. Proposed new primitives must have a published definition, units, warmup, missingness rule and known availability before entering that six-feature budget. Undefined audio skew and uncertain-clock IV are excluded from strict tests.

Use expanding chronological folds with whole sessions kept together. Fit thresholds and feature transforms only inside training. Purge overlapping outcome intervals and account for label availability at fold boundaries. Keep training-only frequency feasibility; later counts are reported once without using them to select or reselect a rule. Preserve the legacy >=360 actual completed episodes/year engineering gate, including partial years, but never manufacture or annualize trades to pass it. Any prospective short-window gate must be declared separately.

Report all trials, unfiltered controls, costs, missingness, annual and stress-session outcomes. Compare realized cash risk, sampled marked risk and native marked risk as different metrics. Use day/week blocks for confidence intervals because intraday entries overlap; thousands of trades do not represent thousands of independent market regimes. Cost/delta/threshold perturbations and failed adaptive tests remain visible. No already inspected 2022–2026 segment is newly called untouched OOS; freeze a future evaluation boundary only after data admission and before outcome access.

The 5m versus 1m comparison must report per-strategy/slot/year differences in availability, selected contracts/deltas, package credit, settlement payoff, costs, sampled drawdown and funding/admission. For a claim of exact reproduction, require zero unexplained contract/admission changes and zero accounting differences within arithmetic tolerance. For exploratory sampled adequacy, show the differences without a pass label until consumer tolerances are preregistered. Material unexplained differences trigger targeted finer data, not retrospective tolerance tuning.

## 8. Stage gates and delivery state

| Gate | Evidence required | Current state |
| --- | --- | --- |
| A Frozen evidence | Source/rule hashes, independent baseline and candidate accounting | Re-audited by the local 0.7.5 runner; see verification artifacts |
| B Data admission | Complete universe, quote/source/availability clocks, schemas and gaps | Local checker implemented; retained sample cannot pass strict clocks |
| C Frequency comparison | SPXW 5m versus finer observations across pilot/stress/half-day cases | Provider acquisition underway; retained equity-option mechanics are not SPXW parity |
| D Independent path PoC | Candidate ledger, coherent leg selection, quotes and official settlement | Design specified; implementation/coverage not established by this revision |
| E Funded native closure | Frozen variant, actual QC cash/order/feature/funding reconciliation | Existing 0.7 evidence preserved; no new 0.7.5 native campaign |
| F Economic validation | Costs, dependence, selection uncertainty and future evaluation | Robust alpha and deployment readiness remain unestablished |

The new runnable PoC covers quote/package admission, exchange-session entry grids, scope-aware storage planning, archived six-account payoff reconstruction and a read-only pinned provider-sample check. It does not simulate a profitable trading strategy from the incomplete new feed. Runnable code: `strategies/sstrangle/poc/v075/`. Machine-readable design: `design_contract.json`. Results: `strategies/sstrangle/results/qc_design_poc_20261026_v075/`.

## 9. Reproduction and provider handoff

From the workspace root:

```
.venv/bin/python -m pytest strategies/sstrangle/poc/v075 -q
.venv/bin/python strategies/sstrangle/poc/v075/run_review.py
.venv/bin/python strategies/sstrangle/research/design_20261026_v075/build_report.py
```

These commands create only 0.7.5 local artifacts and do not submit QC work or start acquisition. The runner pins the saved provider report and checks its Parquet hash before reading. Frozen 0.7/0.8 source and campaign files remain unchanged. Refreshing a provider snapshot creates a new evidence observation; it cannot retroactively alter an earlier acceptance claim.

The October 26 provider requirements remain the acquisition contract. The scoped 0.7.5 addendum clarifies all ticker roles, the QQQ surface budget and the two-clock/timing failure; it does not broaden the existing bounded pilot into all-market history. Provider jobs remain owned by the data providers chat, which has already received the user's pilot authorization.

Primary reviewed sources: Draft 0.6/0.65 context, Draft 0.7 design/code/results, Draft 0.8 design and robustness conclusions, current provider requirements and saved sampling evidence. The local source manifest records the exact files/hashes used for numerical checks. All performance values above are inherited historical observations, and all storage totals are explicitly conditional on scope.
