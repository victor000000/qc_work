# Execution and strategy boundaries

The Cargo workspace owns one generic service crate, `crates/qc-server`. Strategy code is
an input to this service. The service never imports S001/S002/SML01 research packages or
interprets their hypotheses, feature definitions, or custom objective metrics.

```mermaid
flowchart LR
    A[Strategy source and generators] --> B[Per-strategy DuckDB queue]
    B --> C[Atomic job claim]
    C --> D[Exclusive compute project lock]
    D --> E[Reconcile complete job files]
    E --> F[Compile and create QC backtest]
    F --> G[Release project lock]
    G --> H[Poll immutable backtest identity]
    H --> I[Collect statistics and raw runtime metrics]
    I --> J[Per-strategy results and queue status]
```

## Ownership

- `strategies/<id>/`: algorithm templates, generators, strategy tests and experiment evidence.
- `data/<ID>.duckdb`: one queue and results namespace per strategy. Identical job names in different
  strategy databases remain independent. The generic schema is `crates/qc-server/schema.sql`.
- `data/projects.json`: dedicated mutable compute projects shared by active strategies:
  `{"projects": [123456, 123457]}`. Pool projects are disposable execution workspaces.
- Authentication comes from `QC_USER_ID`/`QC_API_TOKEN` or the private file selected by `QC_CREDENTIALS_FILE`; it is never read from strategy databases. Organization selection is separate through `QC_ORGANIZATION_ID` or ordinary settings. `QC_DATA_DIR` selects the CLI runtime directory.

`init-strategy` creates an isolated generic schema. Opening a legacy strategy DB adds newer
execution columns, preserving research tables and research-owned version metadata.
Legacy SQLite files require the verified import described in [DUCKDB_MIGRATION.md](DUCKDB_MIGRATION.md).
A strategy without configured projects remains available for settings and inspection;
runner and warmer database lists are matched to active strategy configurations by name.

## Job isolation

A queue specification is `code` (main.py) plus `extra_files` (a JSON object of Python paths
and sources). Validation rejects malformed JSON, traversal paths, main.py overrides and
oversized files before project mutation. Project reconciliation removes files absent from
the job, preserves attached libraries, and fails closed when listing/deletion fails.

The project lock covers upload, compilation and backtest creation. After creation, the
server uses `(project_id, backtest_id)` to poll and collect; changing project files cannot
change that already-created backtest. Database compile/backtest identity is retained for recovery. File hashes include all
job sources in deterministic order.

## Failure and shutdown

Compile and backtest polling have outer deadlines covering API retries and rate-limit waits.
Permanent compile/runtime errors become failed jobs. Missing final statistics return a
collection error, so completion counters cannot report failed collections as successes.
Every collection read also rejects runtime errors: an error in `on_end_of_algorithm`
can arrive after QC's initial completion flag and must not become a zero-order success.
Retry clears the previous execution IDs, timestamps and result fields. Explicit project
pins are retained in `requested_project_id`, separately from the current execution's
`project_id`, so recovery and retry cannot silently move a pinned job. Experiment
metrics and queue completion commit atomically; updating metrics preserves research
annotations and experiment row IDs. Ambiguous project/backtest creation responses
are not automatically replayed, avoiding duplicate remote creations.

An OS file lock enforces one server per runtime directory. Starting another server cannot
terminate unrelated processes. SIGINT/SIGTERM stop acquisition, allow up to 30 seconds for
slot preparation and two minutes for collection, then leave unfinished rows recoverable on
restart. QC node occupancy and unfinished result collection use separate counters.

Startup recovery collects completed results and records runtime errors. It cancels a
confirmed running backtest before requeueing it. Failed cloud reads, cancellation errors
and local collection errors abort recovery while preserving execution identity, so a
transient API outage cannot erase a recoverable result or launch a duplicate run.

## Verification

- `scripts/check.sh`: formatting, strict Clippy, local Rust tests, workspace tools and each
  active strategy's Python tests; no QC credentials needed.
- `cargo test --test live_qc -- --ignored --nocapture`: temporary QC project, compilation,
  backtest and DuckDB result collection.
- `cargo test --test live_server -- --ignored --nocapture`: actual server process, two
  strategy DBs, one shared temporary project, extra-file isolation and graceful shutdown.
- SML01's producer opens the selected database without creating a missing file, keeps
  unique queue names for repeated submissions and validates completed result payloads.
  A driver deadline cancels queued work; running execution remains owned by the server.
- Google Drive backup code checkpoints and copies DuckDB while holding the shared access
  lock. Prior cloud backups are preserved. Backup regression tests never upload data.

Live checks create/delete their own temporary projects and consume account compute; they remain ignored by default. The published repository has hosted CI. The separate operational checkout may lack Git metadata; that filesystem fact does not describe the published repository. See [CI](CI_CD.md) and [publication](../PUBLICATION.md).

## Versioned diagnostic boundary

The v090 axis pipeline consumes pinned minute data and publishes completion-bound replay evidence. The v092 probe is a separate, bounded observer: it inserts callbacks into an ordinary supported QCAlgorithm source, captures native account/group state, and publishes digest-last receipts. A decoder rejects missing/corrupt/out-of-window/error/capacity evidence. Hashes detect internal corruption; they do not authenticate QC origin or prove margin-scan ordering. Source hooks preserve supported callback bodies/returns, but dynamic Python mutation lies outside the assembler contract. See the [reviewed v092 design](../strategies/sstrangle/research/design_20261107_v092/DESIGN.md).

Acquisition and provider release certification belong to the adjacent provider project. This executor owns queue/result persistence; strategy packages own research hypotheses and selection. The external screener owns its risk/execution UI. Passing one project's tests does not clear another's acceptance gates.
