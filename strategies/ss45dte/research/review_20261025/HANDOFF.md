# SS45DTE standalone review handoff — 2026-10-25

User asked to treat SS45DTE as an independent strategy, never sharing its strategy folder with SSTRANGLE. Strategy work is moving to another chat; the originating chat continues the Options Workspace webpage.

## Saved evidence and scope

- Source: `/home/vic/qc_work/strategies/ss45dte/strategy.py`
- Queue/results: `/home/vic/qc_work/data/SS45DTE.duckdb`
- This folder's `audit.py` performs a read-only source and queue audit through `qc_storage.connect`, preserving shared DB locking. `audit.json` contains the source SHA-256, observed time, sanitized queue/results and two deterministic control-flow/unit demonstrations.
- No changes to the algorithm, no backtests queued, no shared QC server restarts, no paper/live orders submitted. No files written in SSTRANGLE.
- Existing web strategy specification is `/home/vic/dte_21_screener/reports/loss_attribution_2026-10-25/web/strategy.html`; its general evidence is background, not validated SS45DTE results.

## Findings to continue

1. **P1 — Vega sizing is 100× too conservative in units.** `strategy.py:113–131` computes dollar vega per 1.00 decimal volatility (multiplies by 100 contract multiplier). `P5_SIGMA` values 2.5–52.3 are volatility points. Convert vega to dollars per volatility point (`vega_decimal / 100`) or convert the stress points to decimal. Audit fixture: $1,500 name budget, vega_decimal $1,000, TLT stress 2.5 points: current quantity 0; same proxy with corrected units 30. This is only a unit demonstration, NOT a recommended quantity or validated risk model.
2. **P1 — Held positions are not managed when the entry chain is absent.** `OnData:56–64` continues before `_manage` when no chain arrives. Audit with an existing TLT position and empty chains records zero management calls. Move held-position management ahead of new-entry chain gating and add explicit missing-mark behavior.
3. **P1 — Order state is optimistic.** `94–99` immediately records both legs after two independent Sell calls; `143–149` deletes state immediately after Liquidate calls. There are no fill/rejection/partial-fill reconciliation or assignment handlers. One rejected leg or close can leave untracked naked exposure; assignment can leave underlying shares. Track broker/order events and holdings, using a combo execution/state machine as appropriate.
4. **P1 — p5 proxy is not portfolio loss or an IV shock distribution.** `strategy_quantification_20261025.py:48–64,97–114` measures `100*(entry ATM IV - subsequent 21-session realized vol)`. Multiplying its tail by option vega does not produce a calibrated loss quantile for a 45-DTE 20-delta strangle. Gamma, spot gaps, skew, assignment and costs are missing. The stated 5% budget is not a maximum-loss guarantee or validated VaR. Label this a sensitivity proxy pending exact-contract replay.
5. **P1 — Historical calibration leakage.** Fixed p5 values estimated from data through 2026 are applied at the start of 2024. Any resulting backtest is in-sample and cannot establish out-of-sample performance. Record training cutoffs and use walk-forward estimates from information available before each entry.
6. **P2 — Specification mismatch.** The source implements a probe/ablation, not the full linked spec: no strict IVR>50, IV minus 60-session RV filter, OI/spread gate, event check, sigma-distance stop or 5-min-before-close scheduling. Actual expiry acceptance is ±12 days instead of ±5. Independent nearest-delta selection does not enforce a net-delta tolerance. Explicitly freeze the intended SS45DTE specification and list ablations before testing.
7. **P2 — Exit/re-entry schedule differs.** `.days` floors remaining time; exits are attempted intraday rather than the prescribed full-session calendar schedule. Cooldown is measured from entry, so re-entry may occur the next minute after exit (the original entry was over 5 days ago). Track last successful exit/session and enforce next-session entry.
8. **P2 — Empty chain crashes and incomplete diagnostics.** `_enter` takes `min` on an empty expiry set before checking contracts. The chain counter is never incremented. Guard empty chains, stale/nonfinite IV/Greeks and rejected size/margin, recording decision reasons.

## Current local results (see audit.json for exact snapshot)

9 queue records: 6 failed, 3 done. Completed `A_exit21_v5` has zero orders. `DIAG_v1` has zero orders. `DIAG_v3` has 3 orders and +4.458% net return, but `diag2.py` explicitly buys one CRWD share and one arbitrary option to test routing: this is NOT SS45DTE performance. `A_probe_v6` is locally failed with `backtest_timeout`, not running as its README says. A local timeout alone does not prove the remote QC job stopped; inspect remote state before any retry. `A_exit21_v2` is locally failed/timeout, also disagreeing with the README. Preserve these discrepancies.

## Suggested next steps

1. Confirm the intended standalone rule specification and name the baseline/ablation variants.
2. Repair unit/position-lifecycle correctness with deterministic offline tests first.
3. Run a small isolated backtest only after checking existing remote jobs and obtaining any task-specific execution authorization. Preserve source hashes, matched entry cohorts and all receipts.
4. Compare exit21 vs hold vs stop with matched sizing/entries/costs. Do not claim their P&L difference isolates only the exit rule if capital reuse changes subsequent entries.
5. Use point-in-time inputs and a genuinely held-out period before considering performance conclusions.

## Primary references consulted

- https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/equity-options/handling-data (contract Greeks, order/assignment handling)
- https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity-options (universe, pricing and normalization)
- https://prd-web.optionseducation.org/advancedconcepts/volatility-the-greeks (vega quoted per one percentage point of IV)

The optional strategy review tab was removed from this webpage iteration after the user moved strategy work to its own chat. Keep strategy analysis in this isolated folder; the original chat owns the webpage.
