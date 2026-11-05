# Project review and debugging — 2026-10-18

Reviewed the Rust QC execution framework, DuckDB access boundary, and the recent
single-ticker short-strangle collection, provider capture and AKQuant pipeline.
Changes were made in `/home/vic/qc_work` inside Ubuntu WSL. The configured Windows
working directory `C:\home\vic\qc_work` does not exist. No cloud experiments,
production server processes, or provider downloads were started during this review.

## Findings and fixes

1. **High — incomplete local research could be reported as finished and skipped
   forever.** `single_pipeline.py` skipped any ticker present in progress, including
   failed stages. It now checkpoints each stage atomically, skips only successful
   stages, returns an error if any local stage fails, and resumes failed stages on
   the next invocation. Exclusive-create stages retain their prior directories as
   `*.incomplete.<timestamp>` before restarting. Capture keeps its resumable files.
   A changed QC source is rejected even when the previous stages were complete.
   An integration regression simulates a failed optimization, successful provider
   stages, and a rerun; only optimization restarts, and partial evidence survives.

2. **High — cached cloud evidence could be attributed to a different backtest.**
   `collect.py --reuse-downloads` trusted the output directory alone. It now verifies
   project and backtest IDs before using any cached orders/charts. Missing provenance
   fails explicitly. Opening orders missing group identity now fail instead of
   silently collapsing into one entry. CSV headers include all observed feature keys.

3. **High — multiple fills for one order could silently reuse the last fill price.**
   Replay price maps use order IDs, while execution tapes can contain multiple fill
   events per order. Replay now rejects duplicate order IDs before creating output
   or running AKQuant. Supporting partial fills requires event-level price keys
   throughout the research pipeline. Nonfinite/nonpositive prices, invalid quantities,
   fees and starting capital also fail before engine execution.

4. **Medium — provider cache identity and pagination were unchecked.** Existing
   files were trusted without comparing contract/date/timeframe query parameters or
   requiring a completed final page. Capture now checks those properties, requires
   the expected bars structure, and stops repeated pagination tokens instead of
   looping indefinitely. Invalid responses are not published as completed caches.

5. **Medium — local Rust fixtures inherited the external proxy.** The initial full
   check reproduced three failures: source reconciliation, object-store traversal
   and completed-result recovery. Requests to local fixtures traversed the configured
   proxy, producing HTTP 502 responses or timeouts. The shared mock client now disables
   proxying and uses short bounded timeouts. Production proxy behavior is unchanged.

6. **Environment — native Windows is not the supported execution environment.**
   The storage adapter uses Linux `fcntl` locks shared with Rust, and setup/check
   scripts target Linux. README now explicitly requires WSL on Windows. This review
   did not add or claim native Windows compatibility.

## Validation

- `scripts/check.sh` passed: Rust formatting, strict Clippy, 60 Rust tests and
  345 Python tests (workspace 20, S001 244, S002 10, SML01 38, short strangle 33).
  Two live-cloud Rust tests were intentionally ignored. Full results are saved in
  `.local/verification/project_review_20261018.log`.
- Read-only compatibility audit: 12 completed QC identities, 507 provider response
  caches and 980 execution rows pass the new validation. Saved campaign tapes contain
  no duplicate order IDs. Existing research outputs were not rewritten.
- Evidence audit: `.local/verification/review_evidence_20261018.json`; reproducible
  script alongside it.

## Remaining limits

Local runs still replay frozen QC signals and test conditional entry filters. They
do not regenerate independent entry/exit/roll decisions from historical option
quotes. Historical bid/ask coverage remains insufficient for that claim. Partial
fills are explicitly unsupported until event-level price maps are implemented.
The two live-cloud integration tests remain opt-in; this review uses local fixtures.
