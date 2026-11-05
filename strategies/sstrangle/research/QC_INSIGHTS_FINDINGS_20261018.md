# QuantConnect Insights: findings and actual API check

Checked 2026-10-18 for the user's proposal to save information in Insight fields
and download those Insight records for local research.

## What an Insight represents

An Insight is a prediction for a security, with generation/close times, direction,
prediction horizon, optional magnitude/confidence/weight, model identity and tag.
The API also exposes initial/final reference values and scoring fields. These
reference values are scoring context; they do not represent a historical quote
chain or bid/ask bar dataset.

The `tag` field can contain additional metadata, and the documented results UI
and API support downloading Insights. Thus the user's proposed storage and
download mechanism exists technically. Its availability is distinct from
permission to export the underlying market data.

Insights can be emitted from an Alpha model or explicitly through the algorithm's
emit method. They are consumed by portfolio construction in Framework algorithms.
They are not orders or confirmed fills. Grouping related predictions does not
replace our existing combo-order fill and reconciliation logic. Likewise an
Insight's horizon/expiry is not a substitute for an actual 21-DTE closing order.

## Read-only check against our completed baseline

Requested `/backtests/read/insights` with project 31338456, backtest
`e959c69c28fef2262d89e0eea16680e3`, start 0 and end 99. The authenticated API
returned `success: true`, `insights: []`, `length: 0`. No new backtest was run.
The strategy source does not emit Insights, so its 570 genuine orders do not
automatically imply 570 Insights.

The request and original response are preserved in
`insight_check_20261018/baseline_insights_response.json`. No credentials were
written to the receipt.

## Application to our pipeline

Useful exportable strategy artifacts include genuine signal identities,
prediction direction/horizon, strategy version and entry/exit/roll reasons.
Orders and actual fills remain the execution reference. These can supplement
local research but cannot supply the unobserved paths and alternative contracts
needed to independently optimize the strategy.

QC previously refused the requested raw historical-data export with an explicit
institutional-permission/licensing restriction. Encoding that same restricted
history into Insight tags or numeric prediction fields and then downloading it
would route around that denial. No such encoder, synthetic Insight generator or
export backtest was created. The read-only empty-response check above concerns
genuine existing signals only.

No optimization credit was spent. The existing Rust server already runs ordinary
parameterized backtests; whether additional sequential experiments are available
depends on the account's current backtesting limits. Paid Optimization-service
credits and the availability of ordinary backtest runs are separate questions.

## Primary sources

- [Alpha concepts and Insight fields](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/alpha/key-concepts)
- [Insight lifecycle and manager](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/insight-manager)
- [Backtest Insight read API](https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/backtest-management/read-backtest/insights)
- [Download Insights from backtest results](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/results)
- [LEAN Insight implementation](https://github.com/QuantConnect/Lean/blob/master/Common/Algorithm/Framework/Alphas/Insight.cs)
