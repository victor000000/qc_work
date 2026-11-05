# SS45DTE corrected-cost QC completion — 2026-10-25

Completed cloud results; fixed historical universe and in-sample proposal. No live orders.

Sample: 2024-01-02–2026-10-23; initial equity $150,000.

| Run | Closed pairs | Net P&L | Drawdown | Source SHA-256 |
|---|---:|---:|---:|---|
| [SS45DTE_AUTO_STRICT_DIAGNOSTIC_V4](https://www.quantconnect.com/project/31338454/6fb66ff7febced2366d7781113a8a004) | 0 | $0.00 | 0% | `d065459d50275576a41451f4613e95bd3b185e6bf7793747b101524e3b8cc324` |
| [SS45DTE_AUTO_ONEPAIR_COST_V6](https://www.quantconnect.com/project/31338455/b747b2a66e07288f0f65ab5cba7917c3) | 25 | $293.00 | 4.500% | `e0dbe1874e17ae8f6245c11d0d0edb8fcec0a3f62226c49c4f32b1b9a4a16152` |
| [SS45DTE_AUTO_PILOT_ONEPAIR_V6](https://www.quantconnect.com/project/31338456/03d8d418676fcb841ae9a9b47a903451) | 7 | $121.00 | 0.100% | `85080d88348816aa9f73c21432a3accc050ae98049f82abf4a08eed736d62b1d` |

## Findings

- Strict 0.5% sizing: $750 available and all 479 attempts rejected. First eligible symbol/day/expiry samples: CRWD 7, META 29, TLT 11 (47 total). Minimum/median/maximum stress losses: CRWD $2,204.87/$3,066.80/$4,327.35; META $4,884.30/$6,297.00/$7,896.25; TLT $1,303.35/$1,368.97/$1,444.23. No EWZ/SWKS observations reached sizing. Counts are not independent trades.
- TLT ±20% intrinsic loss floor was $1,179.20–$1,431.80, already above $750 without added volatility value. Multipliers and decimal-IV units are correct in the new scenario model. The zero-size outcome reflects the chosen budget and indivisible contracts.
- A separate defect used signed short initial-margin values in a positive reserve comparison. Fixed by summing absolute per-leg requirements, rejecting missing/invalid values. It did not cause the strict sizing rejection because the size check came first.
- Final slippage: $0.01/share/leg execution plus $1/contract/order fee and bid/ask market fills. All 100 control and 28 pilot order fills match this convention. The control has identical order identities/times to the earlier percentage-slippage run: its P&L changed from −$127.435 to +$293 due to costs. Final positive-margin guard reproduced +$293.
- Control: 25 flat pairs, 17 wins, 16 scheduled exits and 9 earnings exits. Pilot: 7 flat TLT pairs, 3 wins, 3 scheduled exits and 4 stress exits. Every native fill reconciles exactly to final equity; no unmatched fills or residual positions.

## Simple proposal: one pair or skip

For paper testing only: one pair maximum per underlying, at most two open pairs. Entry and ongoing cumulative scenario loss ≤1% of equity per trade and correlated cluster; ≤2% across the strategy. New positive standalone margin reserve ≤5% of equity; total account margin ≤20%. No pyramiding or rescue sizing. Drawdown halt at 10% from running account peak. Use actual broker margin preview for manual trading, not the QC estimate.

Cumulative scenario loss uses original net entry credit throughout the trade, including costs; do not reset the basis at each market mark. Close by 21 DTE, earlier for events or risk limits. Actual marked loss above the trade limit also triggers exit. Discretionary delta alerts may produce an earlier exit but cannot delay hard boundaries.

At $150,000: trade/cluster $1,500, strategy $3,000, new margin $7,500, account margin $30,000. This doubles the prior illustrative 0.5% per-trade allowance. It is a proposed risk preference, not a proven optimal limit or live approval. If the user retains 0.5%, skip these naked pairs; evaluate a defined-risk structure as a separately specified strategy.

The first pilot (V5) returned +$23 using additional stress from current midpoint. Final V6 consistently measures cumulative stress from entry and returned +$121 with the same thresholds. Both versions and raw receipts are preserved. This is a correctness change, not performance optimization.

## Limits and next evidence

The pilot was designed after examining this sample, so there is no independent validation. Only TLT passed; no conclusion that TLT will be superior is warranted. 1% modeled risk is not a maximum-loss guarantee for naked options. The finite ±20% spot / +0,+10,+20 volatility-point grid can miss larger moves.

The tested entry band is 40–50 calendar DTE; scheduled holiday/half-session exits move earlier. No new entries in the final 35 calendar days. QC earnings visibility is seven days, not a complete point-in-time holding-window calendar. IVR is an approximate ATM pair near 30 DTE. Risk/delta repricing uses European BSM, constant 4% interest and zero dividend yield. Native broker/assignment behavior and discretionary limit execution are not validated by these ordinary market-fill episodes. No matched 21-DTE versus hold-to-expiry experiment was performed.

Validation: 12 targeted unit tests (slippage units, signed margin, cumulative entry basis, rounding, calendar and lifecycle), native order reconciliation, exact fill-cost checks, and source hashes. Shared server/provider jobs were not restarted or modified. V3 and V5 uncertain control creates were reconciled against complete remote lists before new submissions; absent runs were not duplicated.

Read the updated website’s `qc.html`, `sizing.html`, `qc_evidence.json`, trade CSVs and final source downloads for the reviewable evidence. Raw API receipts stay in this research directory. The initial report is preserved as `REPORT_before_cost_completion.md`.
