# Design 0.9.0 — tested custom-axis research pipeline

Date: 2026-10-30. **Engineering design confirmed by local tests and executable PoCs; sampled-data research only.** Strict provider acceptance, native QC cloud parity and funded economic acceptance remain open. This version supersedes 0.8.9 for the changes below; its sources, results and failures remain immutable.

[Implementation](../../poc/v090/README.md) · [Measured evidence](../../results/custom_axis_v090_20261030/RESULTS.md) · [Machine-readable acceptance](../../results/custom_axis_v090_20261030/acceptance_matrix.json) · [Previous design](../design_20261030_v089/DESIGN.md).

## Purpose and fixed scope

Provide deterministic information-density sampling and causal features alongside the frozen C0/C1/P1 strategy schedules. Preserve native orders, fees, settlement and funding. No new model, entry rule, profit optimization or recipe winner is introduced. Wang's sampling motivation remains distinct from our choices of recipe, 20 prior eligible sessions and target 26 events; retain the source attribution and limits in 0.8.8/0.8.9.

Keep SPX squared-log-return variation as the proposed index axis, verified SPY actual notional as an alternative, SPY close-times-volume as an explicitly approximate diagnostic, and anchored 15-minute time controls. SPX volume is never invented. The observed SPY experiment tests implementation and diagnostic behavior; it cannot confirm SPX equivalence or executability.

## Corrections established by failing tests

Four unchanged adversarial oracles fail against 0.8.9 and pass against 0.9.0. See [old failures](../../results/custom_axis_v090_20261030/v089_adversarial.txt) and [executable review](test_review.py).

| Defect observed in 0.8.9 | 0.9.0 contract | Confirmation |
|---|---|---|
| Conflicting latest option snapshots raise globally | Exclude the affected contract, preserve healthy contracts; no older-state fallback. A strictly newer unambiguous observation can recover it | Every permutation of conflict/healthy/newer rows preserves candidate identities |
| Malformed observation clocks escape the row exclusion path | Record `invalid_field` and continue evaluating healthy contracts | Malformed timestamp plus healthy contract produces one candidate and an explicit exclusion |
| Zero-activity seed sessions qualify for calibration | Reject nonpositive explicit seeds; complete observed zero-activity sessions are reported but excluded from calibration history | Zero-variation completion stays complete and does not warm up the next session; restart agrees |
| QC adapter loses incomplete bars emitted during gap handling | Export every new sequence in the current session, including incomplete gap bars and any complete crossing in the same update | Exported IDs exactly match engine bar IDs in the gap reproducer |

The existing v090 copy of the duplicate test now asserts contract exclusion rather than an exception. The finalization test checks the completion summary independently of positive-activity calibration. Parquet/JSON parity compares behavior while retaining distinct byte hashes. Original v089 tests and source are unchanged; these are explicit contract corrections, not waivers.

## Causal engine and evidence contracts

Retain 0.8.9's availability-before-decision requirement, independent quote/Greek/input ages <=120 seconds, selected-leg quote skew <=30 seconds, latest-known market validation, calendar-bound sessions, gap-known-time invalidation and no cross-gap/overnight returns. Unknown clocks are diagnostic assumptions only; known future clocks remain rejected in both modes. A malformed observation whose timestamp cannot be ordered is recorded as an exclusion, never fabricated into an event.

Thresholds freeze at session open from the median activity of the latest 20 complete, positive, eligible prior sessions divided by 26. Missing sessions and nonpositive activity do not enter that history. Whole-minute consumption emits at most one crossing per observation, retains overshoot and resets to zero. Early-close inclusion remains explicit. Partial tails stay incomplete. The target 26 is not a promised count.

Keep explicit start-reference closes, close-to-previous-completed-close returns, separate minute realized variation and squared event-return sums. Window lengths, age, availability and segment checks remain explicit. Checkpoints bind full state, release, recipe, version, source cursor and calendar. State integrity hashes are not an external authenticity mechanism.

Time controls now accept an explicit `control_symbol` of SPX or SPY. The default remains SPX. The setting applies only to the time recipe and is included in the recipe/checkpoint hash. This enables a same-source SPY control without passing SPY prices into an SPX-labeled recipe. Time units remain minutes, with 15-minute boundaries anchored at the open. Native 390-minute and 210-minute sessions and gap fragments retain their existing semantics.

## Replay, isolation and reproducibility

Read existing hash-pinned 0.8.9 bundles without rewriting or relabeling them; synthetic 0.9.0 fixtures use their own identities. Preserve all artifact and receipt-content checks, publication state and strict-provider gates. Reports additionally pin underlying, input hashes and calendar digest. Each new run uses a fresh output directory, bounded engine history, streamed JSONL records and a completion manifest written last. Failed runs have no completion marker.

The comparison consumer verifies the complete file inventory and all hashes before analysis. It rejects changes in release, input hashes, calendar, mode, underlying or input kind. External trusted manifests are still required for authenticity; recomputing local hashes cannot establish provider truth.

QC source assembly preserves the frozen v087 trading body, adding observer initialization, observation and finalization hooks. Observer failures invalidate telemetry; native strategy errors propagate. Local mocked execution and compilation confirm only this boundary. Actual Object Store API behavior, quotas and account parity require a short native cloud test with source readback, orders, fees, cash, official settlement and equity comparison. The assembled source here is **not submitted**.

## Frozen statistical PoC

[Registration](../../results/custom_axis_v090_20261030/comparison_registration.json) freezes metric code, session eligibility, 2,000 paired whole-session bootstrap replicates and seed 900 before computing the comparison. This is a historical analysis registration, not a claim of prospective preregistration: all 2022–2026 observations were previously inspected.

Compare SPY close-times-volume with SPY 15-minute controls using the same pinned minute table, calendar and mode. Restrict both to complete sessions with positive frozen thresholds and complete bars; this applies the activity axis's warmup to the control. Keep all excluded dates and reasons visible in run/session sidecars. Do not compare all 858 control bars against only 278 warmed activity bars: the paired comparison contains **278 versus 338 bars across 13 sessions**.

Report event counts, durations, activity and overshoot with units; session-level minute-variation dispersion; return, absolute-return and squared-return lag-one dependence; and absolute-return 95th percentile. Returns need a preceding completed close in the same segment. Dependence never concatenates sessions or gaps. Paired confidence intervals resample sessions, preserving intraday structure but not modeling cross-day dependence. Earlier/later date halves are descriptive chronology, not model-selection folds.

Measured October 6–22 outcome: activity bars average 21.38/day versus 26 controls; session-mean durations average 1,208.37 versus 900 seconds. Mean session minute-variation CV is 0.684 versus 0.849. The return, absolute-return and squared-return dependence-difference intervals all include zero. Event counts change substantially between earlier and later halves. These 13 sessions confirm that the comparison works and expose tradeoffs; they do not establish IID, a superior recipe or profitable trading. Return tails use different event horizons and are not equal-horizon risk forecasts.

## Acceptance decisions

| Gate | Decision | Evidence / limit |
|---|---|---|
| Existing local behavior | Passed | Original 108 cases rerun unchanged; broader workspace/strategy regressions also pass |
| Four defect corrections | Passed | Old failing oracles pass on v090; no xfails |
| Streaming, restart, provenance and local QC hooks | Passed locally | Inherited semantic checks plus SPY-control checkpoint parity, contract-order invariance and export-ID oracle |
| Four synthetic recipes | Passed | Separate end-to-end completion bundles; engineering fixtures only |
| Real sampled replay and matched comparison | Passed within diagnostic scope | 37 declared / 33 complete / 13 paired post-warmup sessions |
| Strict data acceptance | Blocked | Explicit strict rejection before output creation; SPX warmup, historical clocks, PIT listing and accepted expiry-time Greeks remain missing |
| Short native QC parity | Pending | Source assembled and locally checked; no cloud job executed |
| Funded/economic acceptance | Pending | Requires strict data and native execution evidence; prior C0 margin failures/P1 losses remain evidence |

This confirms the bounded 0.9.0 engineering design by tests and PoC. It does not label the full strategy or strict research release accepted. Next, consume a newly pinned provider release when the missing evidence exists, then run the short native QC comparison before any funded experiment. Freeze prospective model/label horizons and purged session splits separately if modeling is later authorized.
