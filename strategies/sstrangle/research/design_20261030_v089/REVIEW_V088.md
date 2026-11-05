# Review of 0.8.8

2026-10-30. Original suite: **29 passed**. New acceptance suite against preserved 0.8.8: **14 failed, 2 passed**, covering 12 proposed requirements plus two controls. Failures are recorded without xfail or waived assertions. This is evidence of gaps, not an accepted 0.8.9 implementation.

| ID | Priority | Finding and source | Required correction |
|---|---|---|---|
| T01 (3 cases) | High | shadow.py:63 checks availability only in strict mode; sampled mode admits known future quote/Greek/input clocks. | Unknown timing may be assumed only in diagnostics; known future clocks always exclude. |
| T02 | High | shadow.py:63 checks Greek computation age but admits days-old underlying input. | Independently gate input age. |
| T03 | High | axis.py:81 and shadow.py:8: a gap with no new complete bar leaves previous-segment features ready. | Persist as-of gap events and invalidate until recovery. |
| T04 | High | shadow.py:22 uses close/open: consecutive flat-OHLC bars at 100 then 110 produce zero last return. | Define consecutive-close returns with explicit anchors. This clarifies ambiguous original return terminology. |
| T05 | Medium | axis.py:182 restores modified partial activity; configuration hash does not protect state. | Full-state integrity and semantic validation. |
| T06 | High | pipeline.py:36 accepts hashed receipt saying failed/different release. | Validate receipt content and binding, not bytes alone. |
| T07 | Medium | pipeline.py:67 accepts a decision outside supplied calendar and reports unchanged shadow decisions. | Validate complete decision/session coverage. |
| T08 | Medium | axis.py:153 emits activity-derived threshold=1000 for a 15-minute time bar. | Explicit unit and threshold=15; consistent overshoot. |
| T09 | Medium | shadow.py:38 drops a newer crossed quote and returns an older valid quote. | Conservative latest-known-state policy. This is an intentional policy amendment, not a violation of the old latest-eligible specification. |
| T10 | High | qc_adapter.py:27 propagates fill-forward rejection before the original trading callback. | Isolate observer-owned failures and fail shadow acceptance. |
| T11 | Medium | qc_adapter.py has no end-of-algorithm finalization. | Explicit idempotent finish hook. |
| T12 | Medium | axis.py:53 accepts a session label inconsistent with New York interval date. | Calendar-bound identity validation. |

All source paths above are relative to strategies/sstrangle/poc/v088. C01 verifies past emitted bars stay unchanged in a simple prefix; C02 retains the rejection of five-minute input. These two controls pass. They do not establish full replay parity.

Additional static-review gaps are included in the test plan: selected-leg clock gate integration, true point-in-time listing evidence, Greek methodology, actual QC delivery clocks, bounded memory/output, meaningful cloud sidecars, calendar-derived time-to-expiry, and statistical common-sample controls. They have not all been demonstrated by an executable failure in this review.

Provider inventory found 1,074 dated native-minute receipts spanning filenames 20220523–20261022. All report canonical_publication=false and strict_replay_ready=false. This is receipt metadata inventory, not independent hash verification of all artifacts or proof of complete coverage. Staged diagnostics may proceed under distinct identities; strict full-history acceptance remains blocked.

Frozen strategy sources, provider pins and past account results were not rewritten. No cloud jobs were submitted for this design review. The new tests are requirements executable against 0.8.8; interfaces involving the event ledger and finalization must be adapted explicitly when v089 exists, while preserving independent assertions.
