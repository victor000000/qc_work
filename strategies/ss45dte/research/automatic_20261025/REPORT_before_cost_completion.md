# SS45DTE automatic QC experiment — 2026-10-25

QC can automate selection, sizing, entry, management and closure. The completed runs establish engineering feasibility, not a profitable edge. The conservative sizing baseline admitted no trades; a one-pair control was approximately flat after its actual simulated costs.

## Completed cloud evidence

Period: 2024-01-02 through 2026-10-23. Starting equity: $150,000. Universe: CRWD, EWZ, META, TLT, SWKS. These names were inherited from earlier research, not independently selected out of sample.

| Run | Closed strangles | Net P&L | Account drawdown | Interpretation |
|---|---:|---:|---:|---|
| STRICT_FULL_V2 | 0 | $0 | 0% | No admissible size under the proposed stress budget; not a performance test |
| ONEPAIR_FULL_V2 | 25 | −$127.44 | 4.6% | Fixed one-pair diagnostic; bypasses stress sizing and stress/loss exits |

[Strict QC run](https://www.quantconnect.com/project/31338453/e57eac96be09d223a5c203691e059876) · [One-pair QC run](https://www.quantconnect.com/project/31338458/6b747484ab463274f57d27fe6502ad12). QC login may be required. Exact source hashes, raw result receipts and remote IDs are in `latest.json` and the adjacent per-run files.

The control had 17 winning strangles of 25 (68%), 100 leg fills and $100 fees. Native order cashflows reconcile to equity within one cent; every episode is flat, with no unmatched orders or residual holdings. QC's displayed 72% win rate is leg-level and is not the strangle win rate. Realized P&L: CRWD −$513.20 (3 episodes), META −$69.33 (12), TLT +$455.09 (10); EWZ/SWKS had no entries. The largest losing episode was META, −$3,314.69. This small sample cannot support an inference that TLT is superior.

16 exits were scheduled 21-DTE exits (moved earlier for holidays/half sessions), and 9 were earnings exits. Therefore this is not a pure exit-only-at-21-DTE test. Entry uses a 40–50-calendar-DTE tolerance around 45, and can enter as early as 50 DTE. It does not enforce exactly 45 DTE. New entries are disabled in the final 35 calendar days so all cycles can finish naturally.

## Cost correction and unresolved reruns

V2 actually used QC ConstantSlippageModel(0.01): **1% of option premium per execution**, plus bid/ask market fills and $1 per contract per order. It did NOT implement the intended $0.01/share slippage. V2 remains valid evidence for that explicit percentage-cost variant, but is not the final intended cost baseline.

V3 implements an absolute $0.01/share slippage model, covered by a unit test. Both V3 submission responses were uncertain; the local queue reports failed without a remote backtest ID. Read-only remote reconciliation has timed out. No V3 result is claimed, and no blind duplicate submission is made. See remote status receipts if subsequently recovered. V2 numbers must not be relabeled as V3 or adjusted arithmetically into a claimed rerun.

## Rules actually encoded

- Standard monthly expiry nearest 45 DTE within 40–50; both absolute deltas 0.16–0.22; each OI strictly above 500; each bid/ask spread below 5% of midpoint.
- Prior-session QC option-universe IV/Greeks for selection; minute quotes must be fresh, positive and not fill-forward. Delta is rechecked using midpoint-implied BSM with a constant 4% rate and zero dividend yield.
- IV rank strictly above 50 using an approximate ATM pair near 30 DTE and up to 252 observations, minimum 60. This is not the provider's exact 30-day IV series.
- Daily upcoming-earnings screening and early closure when an event appears. QC's EODHD universe exposes a seven-day upcoming window: this does not establish a known-at-entry full holding-window earnings exclusion.
- Mechanical combo market orders; confirmed fills and holdings determine state. Partial legs, failed closes, stock assignments and stale exit quotes have explicit recovery paths. Re-entry is allowed only after confirmed closure.
- Strict sizing: floor(min(trade, cluster remaining, book remaining budgets)/scenario loss), capped at 10 pairs. Trade/cluster/book budgets: 0.5%/1%/2% equity; tech names share a cluster. Margin use capped at 50%; 10% peak equity drawdown halts entries. These are research choices, not approved live risk limits.
- Stress grid reprices spot moves −20%, −10%, 0%, +10%, +20%; IV increases 0, 10, 20 volatility points; elapsed time 0, 1, and days to the scheduled exit. Sum standalone losses without diversification credit. This finite grid is not a maximum-loss guarantee or calibrated VaR for naked options.
- One-pair control retains liquidity, IVR, event, margin and drawdown rules but disables stress-based position sizing and loss/stress exits. It is not a recommended sizing policy.

## What is hardest, and what follows

The 45/21 calendar is easy to automate. The hardest unresolved design choice is a defensible risk rule that both admits integer contracts and survives the occasional large short-option loss. At $150,000 the initial 0.5% trade budget is $750; the strict run rejected all otherwise eligible sizing attempts (479 attempts, not 479 independent trades). Relaxing the budget merely to manufacture trades would not validate the strategy.

A second difficulty is matching information genuinely available at the decision time: consistent IV rank, a full-window earnings calendar, contract-level liquidity and practical combo execution. BSM risk approximations do not model American early exercise/dividends fully. QC has its own execution and assignment models, but this run does not validate brokerage behavior under stress. Ten local tests cover core units, boundaries and lifecycle recovery; the 25 completed episodes validate the ordinary cloud path, not every exceptional path.

Recommended next research steps: resolve V3 remote status and complete the corrected-cost baseline; obtain point-in-time earnings visibility over the full planned holding period; freeze sizing choices before further evaluation; then test a longer untouched period and execution-cost sensitivity. Consider defined-risk spreads as a separately specified strategy if naked-contract stress exceeds the intended budget. Do not claim that 21 DTE is optimal: no matched 21-DTE versus hold-to-expiry comparison was run here.

Official mechanics: [QC option universe](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/us-equity-option-universe), [upcoming earnings](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/eod-historical-data/upcoming-earnings), [slippage models](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/supported-models).
