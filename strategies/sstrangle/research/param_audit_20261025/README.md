# Parameter audit 2026-10-25

Read-only audit of the existing `sstrangle` result archive, run from `dte_21_screener` to
check whether the parameters of a 45/21-DTE short-strangle specification can be measured
from what this workspace already holds. Nothing here queues, cancels or re-runs a backtest,
and no other strategy was touched.

## What this folder contains

- `tail_audit.py` — read-only scan of `strategies/sstrangle/results/*/*/backtest.json`
  and the matching `strategy_equity.json`. Writes `tail_audit.json`.
- `tail_audit.json` — the output recorded on 2026-10-25.

## Why it exists

The consumer-side specification needs a measured 5th-percentile loss per trade. Option-price
evidence in `dte_21_screener` gives one (median +1.0 vol points, p5 -37.4, about 36:1), but on
five names and three years. This audit asks a different question: **what do the completed QC
backtests of this strategy family actually show about their loss tail?**

## Result, 2026-10-25

Of 113 run records, 83 completed without a runtime error; 29 produced at least 30 non-flat
daily observations and could be used. The remaining 84 were skipped for a missing equity
file, a failed run, or too few live days — an archive-usability finding in itself.

| Statistic across the 29 usable runs | Value |
| --- | ---: |
| Median maximum drawdown | -1.9% |
| 10th percentile maximum drawdown | **-46.6%** |
| Worst maximum drawdown | -100% |
| Worst daily 5th-percentile loss (worst runs) | -3% to -6% of equity per day |
| Runs that lost essentially all equity | 1 |

**Reading.** A tenth of the usable runs draw down by more than 46%, and one goes to zero. That
is the same shape the option-price evidence shows — a small typical gain against a deep,
rare loss — measured here on real backtested equity rather than on reconstructed premiums.

## What it does not show

- **It is not a distribution of independent strategies.** Several runs are the same strategy
  with small parameter changes over overlapping periods, so the cross-run spread is narrower
  than the true uncertainty.
- **The ratio of tail to typical gain is not reliable here.** Only 13 runs give a usable
  p5-to-mean ratio, and the mean is often near zero, which makes the ratio explode. The 36:1
  figure in the consumer evidence page comes from trade-level option prices, not from this
  audit; the two are consistent in shape, not equal in value.
- **The daily tail is truncated.** Mandatory exits and end-of-day marks cap the observed loss;
  intraday excursions are not in the equity curve.
- **It answers none of the open parameter questions** — entry DTE, the delta band, stop
  thresholds and the 21-DTE exit net of costs all require a replay that prices the untraded
  alternative, which needs a chain this archive does not hold. The requirement for that data
  is R1/R2/R3 in
  `data_providers/docs/requirements/DTE21_P5_SIZING_DATA_REQUIREMENTS_20261025.md`.
