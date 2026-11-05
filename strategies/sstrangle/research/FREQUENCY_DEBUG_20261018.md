# SPY entry-frequency investigation

The 2009–September 2026 baseline closed 69 strangles because it required min/max
IV rank >=50. The user retained that rule for the SPY reference; the subsequent
broader basket request instead specifies IV rank >70 and at most 13 underlyings.

Reconstructing all 4,463 sessions from orders and the equity calendar gives:

| Session outcome | Count |
|---|---:|
| Flat entry checks | 3,415 |
| Already invested (excluding entry and exit sessions) | 974 |
| Exit day, no same-day re-entry | 69 |
| Final entry blackout | 5 |

Of the 3,415 flat checks, the IV gate rejected 3,259 (95.4%), 69 entered, and 44
found no eligible liquid delta contract. Another 43 checks cannot be classified
from the old counters: no eligible expiry used to return silently. IV rejections
also combined unavailable IV rank and rank below 50. Both ambiguities are fixed
in the new entry-decision accounting.

Mean holding time was 21.94 calendar days, median 22, range 4–35. The first entry
was May 6, 2010, and the longest exit-to-next-entry gap was 587 days. Entries
actually ranged from 35–54 DTE, averaging 47.06. All 30 TIME exits passed the
first-eligible-session <=21-calendar-DTE audit. The 21 DTE exit was not responsible
for the sparse count.

45 minus 21 is 24 calendar days. January 2009 through September 2026 contains 213
calendar months. About 200-plus trades would be a useful monthly benchmark for an
unrestricted strategy, not a required count for an IV-gated strategy. Early profit
and stop exits and the monthly expiry window also affect frequency.

## Controlled cloud regression

Both tests used history from January 2016 and traded January 3–December 29, 2017,
with identical execution/exit/roll parameters, through the shared Rust server.

| Entry gate | Closed cycles | Orders | Net P&L |
|---|---:|---:|---:|
| IVR >=50 | 2 | 10 | $226 |
| Disabled, diagnostic only | 12 | 76 | $489 |

The high-IV run recorded 222 below-threshold checks and one unavailable-IV check.
Its 251 session decisions reconcile exactly. The unrestricted run also accounts
for all 251 sessions: 12 entries, 12 exit days, 205 invested sessions, 19 without
an entry expiry and 3 without a delta candidate. Both its TIME exits occurred at
exactly 21 DTE. These controls diagnose frequency; they are not optimization.

- [High-IV cloud control](https://www.quantconnect.com/project/31338456/4ec6b2d65471a207a15185009632f21a)
- [Unrestricted cloud control](https://www.quantconnect.com/project/31338456/aba68a0eb3b843a38cb0a01f10de0901)
- Original full history: `results/strangle_single_20261018_072859`
- High-IV control: `results/strangle_single_20261018_081628`
- Unrestricted control and verified DuckDB/Parquet: `results/strangle_single_20261018_080744`

## Early-data failure retained

The attempted unrestricted 2009–2026 run failed on January 30, 2009. A TIME close
was submitted at 21 DTE, but neither combo leg filled within five minutes. At
15:36 the cached last-data times were 10:07 for the put and the previous day's
09:33 for the call. A focused reproduction failed identically. This is retained
as failed evidence, not a valid full-period performance result or a new cycle count.
The stale cache is confirmed; the attempted historical-data diagnostic messages
were absent from the returned logs, so a subscription-versus-source attribution
has not been conclusively established.

Failed campaigns: `strangle_single_20261018_081042` and
`strangle_single_20261018_081407`. Mandatory exits still fail explicitly when they
cannot fill; stale quotes are never manufactured into completed trades.

## Code changes and scope

The entry gate is now explicit, with the original IVR >=50 default retained.
Every ticker/session has one terminal decision. Missing IV, low IV, no expiry,
missing delta and illiquidity are distinguished. Annual decision and coverage
logs are reconciled and exported. A disabled-IV diagnostic can enter without IV
history; metadata and collection handle missing rank correctly. Performance
windows apply the history prerequisite only when that gate is enabled.

57 local tests pass. The original backtest and its downloaded evidence are
preserved. The new basket baseline uses the user's later rules and is a separate
experiment. The sibling screener's IV percentile/IV rank mislabelling is being
corrected in the user's separate project-review chat; this backtest will use true
min/max IV rank, not percentile.
