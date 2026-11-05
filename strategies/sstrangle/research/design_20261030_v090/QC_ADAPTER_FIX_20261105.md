# 0.9.0 QC observer clock correction — 2026-11-05

This addendum changes the current `poc/v090/qc_adapter.py` after the initial cloud validation. The original design, frozen source readbacks and failed validation remain evidence. See [fix results](../../results/fix_v090_20261105/RESULTS.md) and [prior failures](../../results/validation_v090_20261105/RESULTS.md).

## Root cause and behavior

The adapter formerly attached `America/New_York` to naive individual bar timestamps. The SPX security reports an `America/Chicago` exchange clock in QC. A Chicago 08:30 bar was therefore interpreted an hour early; the calendar filter dropped opening observations and admitted observations beyond the intended RTH window, including post-close fill-forward rows on the early-close sample.

For naive bar times the adapter now reads `algorithm.securities[algorithm.index].exchange.time_zone.id` and converts that clock to UTC before applying the pinned session window. Aware timestamps retain their timezone. Missing or unrecognized metadata fails within the observer error boundary; there is no guessed New York fallback. Actual `algorithm.utc_time` is still the receipt clock. Native callback behavior, contract selection, orders, funding and accounting are unchanged.

[QuantConnect's timestamp documentation](https://www.quantconnect.com/docs/v2/research-environment/datasets/key-concepts) distinguishes individual bar clocks from collection/algorithm clocks. The live source metadata and full-session coverage are the acceptance evidence for this adapter.

Fill-forward bars within the declared RTH interval remain prohibited. The correction removes incorrectly included out-of-session observations; it does not weaken source provenance or manufacture missing minutes. Genuine missing observations still produce incomplete summaries and fail coverage acceptance.

The observer retains at most 32 recent session summaries for bounded diagnostic inspection, including the final session. Short cloud tests log only aggregate coverage/validity metadata and the timezone identifier. They do not export licensed prices, raw observations or sidecar data via logs. Object Store restrictions remain in force.

## Regression and acceptance requirements

Four adversarial cases supply naive Chicago bars with New York calendar sessions: a regular summer day, the November 25, 2022 early close, and days before/after the March DST change. Each includes post-close fill-forward observations. All four fail on the original adapter and pass after correction. Existing fake-algorithm tests now supply their explicit New York exchange metadata rather than relying on an implicit timezone assumption.

Acceptance requires exact 390 regular / 210 early-close counts, complete summaries, zero observer errors, idempotent finalization and unchanged baseline/shadow orders, fees, official expiry cash and sampled equity. Successful account parity alone does not prove minute coverage. The new source and its tests are pinned in the fix evidence manifest.

## Separate native IV issue

The prior early baseline's terminal error names `ImpliedVolatility.CalculateIV`. [LEAN's implementation](https://www.lean.io/docs/v2/lean-engine/class-reference/ImpliedVolatility_8cs_source.html) logs that message when root finding fails. This is separate from the observer clock conversion. No pricing model or native solver was changed. Preserve the original failed run; a later clean run is bounded non-recurrence evidence, not a general solver repair. Any recurrence must be investigated from its input/expiry/model conditions before broad acceptance.


## Subsequent margin and IV investigation

See [the final diagnostic report](../../results/margin_verified_v090_20261105/RESULTS.md). 427 tests pass. Native group-margin telemetry and delayed-publication collection are fixed and checked in fresh QC pairs. These are validation-tool fixes; C0 margin intervention and the historical IV error remain release gaps. The captured margin receipts are post-fill, not proof of the triggering margin state.
