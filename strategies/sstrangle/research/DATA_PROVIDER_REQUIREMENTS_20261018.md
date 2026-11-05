# Historical options data requirements for qc_work

Requested by the user on 2026-10-18. Consumer: `/home/vic/qc_work`.
Provider owner: `/home/vic/data_providers`. Priority: validate the QuantConnect
short-strangle baseline, then enable independent local AKQuant backtests.

## Immediate deliverable

Implement or extend the existing provider interface to deliver historical
one-minute option bid/ask quotes with synchronized underlying data. Investigate
ThetaData first for US equity/ETF/index options using existing access. Start with
a small SPY validation sample and a documented coverage/entitlement report before
scaling ingestion. Reuse the current provider runtime, ingestion locks, staging,
verified publication and consumer API. Coordinate with active maintenance jobs.

The current frozen release has no option-minute rows for our requested contracts.
An Alpaca trade-bar capture supplied prices for 36 of 570 historical executions;
27 individual executions had prints within five minutes, but only six of those
formed a complete strangle cycle. The other cycles have missing or stale legs.
This is inadequate for executable-price validation. Trade OHLC and
last trades must remain separate from quote datasets.

## Baseline context, owned by qc_work

- Latest confirmed account/sizing settings: initial cash **60,000 USD**. At each
  entry, use an equal account-equity margin/collateral budget of `equity / x`,
  where `x` is the number of held plus selected new underlyings (maximum 13).
  Determine integer equal put/call contract quantities using margin and fees,
  subject to buying power. Apply this allocation **only to new openings**;
  existing contract counts stay unchanged as the basket count changes.
- Latest batch rule: **no new entries until every position, pending combo and
  exit in the previous batch is closed**. Use **standard monthly options only**,
  for both entries and roll replacements; no weekly or daily-expiry series.
- The user reconfirmed **entry near 45 DTE and mandatory exit at 21 DTE**.
  The temporary suggestion to enter at 21 DTE was clarified and does not apply.
- Desired period: 2012-01-03 through 2026-09-30, subject to actual data coverage.
- Broad point-in-time US equity/ETF and US futures-option universe. No claim of
  all-market coverage based on today's symbol list or discovered definitions.
- True IV rank: `100 * (latest_iv - min_iv) / (max_iv - min_iv)` over 504 valid
  daily observations, including the latest completed observation available at
  the decision time. All 504 are required; a flat range is undefined. IV
  percentile is a different diagnostic and must never be substituted.
- IVR strictly greater than 70; descending prior-session underlying volume;
  maximum 13 concurrent underlyings. Stock volume is shares; futures volume is
  contracts. Preserve units rather than converting these to dollar volume.
- Equity screen uses 20 completed sessions: average raw price >30, average
  share volume >5 million, known market cap >1 billion; unknown market cap is
  retained under the current screen rules.
- First eligible standard monthly expiry at least 35 calendar DTE, targeting
  approximately 45 DTE. Each short leg has absolute delta 0.16-0.22, target 0.19;
  open interest at least 100. Known earnings through expiry veto an equity entry.
- Decisions normally at 12:00 America/New_York; forced exit on the first eligible
  session at or below 21 calendar DTE. Management also requires fresh quotes for
  profit/stop/roll decisions and subsequent exit retries. Keep full session data
  for held and candidate contracts, including replacement legs.

These rules explain the required inputs. Screening, IV-series construction,
portfolio selection, order simulation and optimization remain in qc_work.

## Required datasets and semantics

1. **Option quotes at one-minute resolution.** Historical NBBO for equity/ETF/
   index options; appropriate venue best bid/offer for futures options. Include
   bid, ask, sizes, condition/exchange codes when available, interval timestamp,
   original quote timestamp when available, session date and source. Store
   timezone-aware UTC and retain the documented source timezone. Explicitly
   state whether the timestamp denotes an interval boundary or an actual quote
   update. Never relabel a carried-forward quote as a fresh update. If the source
   cannot establish quote age, record it as unknown and expose that limitation.
   One-minute last-NBBO snapshots and QuoteBar OHLC have different semantics;
   document the difference when comparing with LEAN. Tick/second quotes around
   selected fills may be needed to investigate discrepancies; they are not the
   default all-market bulk request.
2. **Underlying data.** Raw/unadjusted minute OHLCV (quotes when available) and
   daily OHLCV synchronized to option sessions. Expose adjusted series separately
   with adjustment factors. Include corporate actions, dividends, splits, symbol
   changes and delistings. Futures must reference the actual delivery contract;
   a back-adjusted continuous series cannot replace the underlying used to price
   a particular option. Cash indices have no directly traded share volume: mark
   this in metadata rather than assigning a fabricated volume.
3. **Historical contract and chain inventory.** Point-in-time listed contracts,
   canonical IDs plus vendor/QC/OCC mappings, root, exchange, underlying ID,
   expiry and last trading timestamps, strike and its units, put/call, multiplier,
   tick size, exercise style, settlement type/time, deliverables and adjustments.
   Distinguish standard monthly, weekly and other series, including historical
   Saturday expiry labels. Futures options require the underlying delivery ID
   and exchange-specific option-expiry mapping. Include delisted/expired symbols.
4. **Daily OI, IV and Greeks.** Preserve observation and availability timestamps,
   source and model/version. Need delta for put/call selection, ATM observations
   near 45 DTE for the daily IV series, and adequate history for the 504-observation
   warmup. Expose the surrounding expiry/strike grid, not only contracts that QC
   eventually traded. Label provider-supplied and locally derived Greeks
   separately; preserve rate/dividend/forward inputs where available. Do not
   splice IV sources or models silently. Missing/zero native futures IV is not
   usable IV; label it missing and provide pricing inputs for consumer modeling.
5. **Point-in-time auxiliary data.** Trading calendars, timezones, early closes,
   market-cap observations, earnings announcement schedules with known-as-of
   timestamps and revisions, interest rates and dividends needed for pricing.
   Separate announced earnings schedules from hindsight actual dates. Report
   limited calendar horizons explicitly; our QC feed does not establish a full
   expiry-horizon earnings calendar.

## Coverage and sources

First validate SPY; then the originally requested SPX, QQQ, IWM, AAPL, MSFT,
AMZN, NVDA, TSLA, TLT, GLD and IBIT, and then the broad eligible historical
universe. SPX remains relevant to separate index-option research; its missing
underlying trade volume requires an explicit consumer policy before basket use.
Respect actual instrument/option listing dates, especially newer products.

For futures, report source and quote coverage per root and delivery. Our current
QC test set covers CL, RB, HO, NG, ZN, ZT, ZB, ZC, ZS, ZW, NQ, ES, HG, GC and SI;
the user's requested universe is broader. List additional supported markets and
unsupported ones. Catalog discovery, daily bars, option quotes and IV coverage
are separate statuses. VIX index options are not evidence of CME futures-option
coverage.

ThetaData's options page advertises OPRA history since June 2012. Its current FAQ
says CME futures data is not offered. Verify actual terminal version, account
entitlements, endpoints and first usable dates, rather than assuming access from
the marketing coverage. Check underlying stock and index coverage separately.
Use existing permitted futures providers and explicitly report remaining gaps.
Do not purchase or upgrade subscriptions as part of this requirement.

History starting in June 2012 cannot cover January-May 2012 and cannot yield a
504-observation IV signal in early 2012. Report both the earliest observation and
the first date with a complete IV window. If earlier compatible history cannot
be sourced, the consumer must report warmup and begin trading later; do not fill
the missing history using future observations or reduce the lookback silently.

## Storage and delivery

- Canonical ownership stays under the existing data_providers runtime. Provide
  partitioned Parquet and DuckDB query access through the existing MarketData
  API, with versioned schema and an immutable release manifest. No new SQLite
  store or duplicate canonical warehouse inside qc_work.
- Expose explicit dataset kinds such as quotes, trades, bars and derived Greeks;
  map them to current project conventions rather than forcing these exact names.
- Include request parameters, source/endpoint/version, retrieval time, raw receipt
  hashes, normalized row counts, partition checksums, units and validation status.
  Preserve raw receipts according to existing storage conventions.
- Support predicate pushdown for contract IDs and date/time ranges, bounded
  chunked downloads, restart checkpoints, idempotent merge and rate limits.
- Provide a read-only consumer example and a coverage manifest by asset class,
  symbol, contract, session and data kind. Distinguish not listed, outside source
  history, not entitled, missing upstream, request failed, invalid/quarantined,
  and downloaded/validated/published. Missing data must not silently become zero,
  synthetic quotes, same-day closing prices or a different provider's prices.

## Validation sample and acceptance

Use these existing immutable qc_work inputs:

- `/home/vic/qc_work/strategies/sstrangle/results/strangle_single_20261018_072859/SSTRANGLE_20261018_072859_SPY/`
  contains the audited historical SPY reference. QC project 31338456, backtest
  `e959c69c28fef2262d89e0eea16680e3`. This is the older SPY IVR >=50 reference,
  not the new 504-observation IVR >70 basket baseline.
- `/home/vic/qc_work/strategies/sstrangle/results/spy_baseline_consistency_20261018/qc_executions.csv`
  contains all 570 executions across 69 cycles, with timestamps and contracts.
- The same folder contains `manifest.json`, `price_coverage.csv`,
  `replay_summary.json` and provider captures. AKQuant using QC fill prices
  reproduces net P&L of -3,621 USD exactly. This verifies the ledger, not external
  data equivalence. The frozen local release is `20261017T224803Z_854bef67`.

Start with the 2024-02-01 onward contract-days already requested in that folder,
including both open/close legs and roll replacements. Download full-session
one-minute quotes plus matching underlying observations for these contract-days.
Then expand to the baseline's execution/holding intervals that fall inside
verified source coverage. Pre-source-history fills must remain explicit gaps.
For independent optimization, expand to all point-in-time candidate strikes and
expiries, and all management sessions; the baseline's fills alone are insufficient.

Acceptance requires:

- A machine-readable contract/time coverage report, quote-age distribution and
  invalid/locked/crossed/one-sided quote counts with explicit handling rules.
- Stable identities and documented prices/multipliers, including adjusted equity
  contracts and futures units. Quarantine impossible prices; do not guess scales.
- No observation later than the decision time, no arbitrary forward filling, and
  no known-in-hindsight OI/earnings/contract inventory treated as contemporaneous.
- Per-execution as-of bid/ask comparison to the QC fill and direction, with time
  offsets, spread, source and reason for mismatch. Report differences rather than
  forcing vendor prices to equal QC simulated fills or declaring every outside-
  spread fill a data error. Consumer performs P&L and strategy reconstruction.
- Readable immutable Parquet from qc_work's real environment, matching DuckDB
  counts/checksums, and a minimal example joining quotes, underlying and metadata.
- An explicit ready/partial/blocked status by data kind, required entitlement or
  alternate source, estimated size/request count before broad ingestion, and
  the earliest supportable backtest and full-IV-window dates.

QC's historical-data probe found quotes for all 570 fills and 3,753 daily SPY
observations inside its platform. Downloading that raw history from Object Store
was refused by QC because institutional export permission is required. Do not
work around this restriction through logs or alternate export channels. Downloaded
orders/trades remain valid comparison inputs; independently source local market
data and leave any unavailable raw cross-feed checks explicitly unverified.

## Official references checked 2026-10-18

- [ThetaData historical quote endpoint and interval semantics](https://thetadata.net/docs/operations/option_history_quote.html)
- [ThetaData options coverage](https://www.thetadata.net/options-data)
- [ThetaData subscription documentation](https://thetadata.net/docs/Articles/Getting-Started/Subscriptions.html)
- [ThetaData FAQ: CME futures and separate index data access](https://www.thetadata.net/faq)

First deliver the capability/entitlement check, schema/API additions where needed,
and the bounded SPY sample with a coverage report. Save findings in the provider
project and publish validated data through its existing release workflow. Leave
the ongoing maintenance jobs intact and report their relationship to this work.
