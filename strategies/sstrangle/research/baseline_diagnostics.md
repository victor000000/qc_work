# Why the short strangle baseline lost money

The managed baseline lost $3,429 after costs in 2024–2025 because a few large losing cycles outweighed many small wins. The order-level attribution reconciles to the audited results; it describes this sample rather than proving a permanent market mechanism.

Of 28 managed cycles, 17 won and 11 lost. Average winners were $147.06; average losers were $539.00. With those observed payoff sizes, the empirical break-even win rate is 78.6%, versus 60.7% observed. This break-even calculation assumes the same average win and loss sizes; it is not a forecast probability.

| Exit reason | Managed cycles | Managed net P&L | No roll cycles | No roll net P&L |
|---|---:|---:|---:|---:|
| PROFIT | 8 | $1,516.00 | 10 | $1,919.00 |
| TIME | 15 | $345.00 | 12 | $-582.00 |
| STOP | 5 | $-5,290.00 | 5 | $-5,615.00 |

The five managed stop exits lost $5,290; the other 23 cycles earned $1,861 net. The three largest losing cycles totaled $4,321. This concentration does not justify deleting those trades retrospectively; a usable improvement needs an observable rule available before entry or exit.

| Managed leg attribution | Net cash P&L after fees |
|---|---:|
| SPY_put | $-2,529.00 |
| SPY_call | $-348.00 |
| GLD_put | $1,111.00 |
| GLD_call | $-1,673.00 |
| TLT_put | $-258.00 |
| TLT_call | $268.00 |

SPY put losses dominate the equity ETF result, while GLD calls lost money despite profitable GLD puts. That is consistent with exposure to large moves in both directions. This attribution is cumulative cash flow by option right, including rolled contracts, rather than a Greek-based decomposition.

Commissions were $216.00; excluding them still leaves a $3,213.00 loss. Estimated fill cost against contemporaneous submission midpoints was $507.00. The midpoint figure is an execution diagnostic, not an attainable alternative backtest: market orders filled at the modeled bid/ask, and midpoint fills are not guaranteed.

Daily checks let the realized loss exceed the nominal two-credit stop: the managed SPY cycle opened on 2025-03-31 for $753 and exited on 2025-04-04 with a $1,855 loss. A tighter daily stop can still overshoot after gaps. Intraday stop monitoring is not part of the three current experiments.

Rolling improved the whole comparison by $849, while commissions rose from $108 to $216. The managed run had 28 cycles versus 27 without rolls, so that $849 includes changes in subsequent entry timing and is not a matched-trade estimate of the value of an individual roll.

The IVR threshold of 50 is a comparison with past implied volatility. It does not establish that the option premium exceeds future realized volatility. The planned IV/RV filter uses trailing realized volatility as a causal proxy, not knowledge of future moves.

Fourteen local tests pass after adding disabled-by-default entry filters and a configurable loss multiple. The baseline profit target, time exit, ETF universe, one-contract sizing, quotes, pricing model and roll rules remain unchanged. Original submitted source snapshots and results remain preserved.

## Frozen improvement tests

The [research plan](../research_plan.json) fixes three one-factor changes: one-credit loss exit; a symmetric one-sigma trailing 20-session trend gate; and ATM IV at least 1.2 times trailing 20-session realized volatility. The latter two features use the existing raw-price daily snapshots, so they include dividend-related price changes and are not total-return estimators.

Selection uses highest discovery-period net P&L, then lower daily drawdown and fewer rolls, among candidates with at least ten completed cycles. The selected configuration is frozen before comparing it with the baseline over 2026-01-02 through 2026-09-30. No thresholds will be revised using validation results. Small samples or a failed improvement will be reported.

Source evidence: [original results](../results/strangle_comparison_20261017_134629/RESULTS.md), [diagnostic calculations](baseline_diagnostics.json).
