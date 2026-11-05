> Historical verification snapshot. Test counts and cloud results below are dated evidence, not a current workspace-wide certification. See [current work](CURRENT_WORK.md) and [next steps](TODO.md).

# Verification — 2026-10-17

## Single-ticker short-strangle campaign

All twelve independent QC baselines completed and their 980 orders, 490 leg trades
and 129 cycles were downloaded and reconciled. The local study evaluated 432
entry-filter settings and published 199 actual AKQuant runs / 8,366 executions.
No change passed the frozen discovery/validation criteria. See the
[campaign report](../strategies/sstrangle/results/strangle_single_20261017_162036/RESULTS.md)
and [verification record](../strategies/sstrangle/results/strangle_single_20261017_162036/verification.json).

SPX required comparing quote timestamps to the security's local clock and a scoped
longer polling deadline. The default remains 600 seconds; this campaign used 1800.
After the timeout change, all 60 Rust tests, strict Clippy and the release build
passed. All 23 short-strangle Python tests passed. Failed/timeout SPX attempts
remain preserved and excluded from valid results.

## DuckDB and local replay update

The final `duckdb_checks_20261017.log` passes formatting, strict Clippy, 59 Rust tests,
20 workspace Python tests, 244 S001 tests, 10 S002 tests, 38 SML01 tests and 18
short-strangle tests. The isolated live DuckDB server test also passed and deleted
temporary project 37973954. See [migration evidence](DUCKDB_MIGRATION.md) and the
[AKQuant replay report](../strategies/sstrangle/results/local_akquant_20261017/LOCAL_RESULTS.md).
The sections below retain the earlier reconstruction checks and their dated evidence.

## Local verification

`scripts/check.sh` passed with Rust 1.95.0 and Python 3.12.14:

| Check | Result |
|---|---|
| Rust formatting | Passed |
| Clippy, all targets/features, warnings denied | Passed |
| Rust unit/integration tests | 59 passed; 2 explicit cloud tests ignored |
| Workspace Python tools | 16 passed |
| S001 Python tests | 244 passed; 3 expected legacy deprecation warnings |
| S002 Python tests | 10 passed |
| SML01 Python tests | 38 passed |
| Python source parsing | Entire discovered source tree passed |
| Python dependency compatibility | 32 installed packages compatible |
| Release build | Passed |
| RustSec audit | 0 vulnerabilities; 0 warnings after dependency updates |

Evidence is under `.local/verification/`: `check-current.log`, `release-build.log`,
`cargo-audit-after-update.json` and `security-summary.json`. The latest inventory-tool
regressions are included in `workspace-current.log`; final Rust guards are verified in
`final-root-guard.log`. Python dependencies are
pinned in `requirements-dev.lock`. The audit initially found ten advisories affecting
h2/quinn-proto/rustls and an anyhow unsoundness warning. The lockfile now uses
h2 0.4.20, quinn-proto 0.11.19, rustls 0.23.46 and anyhow 1.0.104, with required crypto
transitive updates. The advisory snapshot is commit
`64f92cdc64401fab47baa10e2e11fe382aa57155`, dated 2026-10-17.

The workspace-tools CI job now installs pytest with `--constraint requirements-dev.lock`,
so its test dependencies match local pins. A fresh environment containing only pytest
and its dependencies passed all 16 workspace tests; no strategy or numerical packages
were installed. Evidence: `ci-tools-clean-env.log` and `ci-tools-clean-summary.json`.

This imported workspace has no Git metadata or remote, so its version reports
`1.2.0 (unknown)`. Hosted GitHub Actions have not run here.

## Real QuantConnect evidence

- Direct Rust API smoke: upload, compile, backtest, completed statistics and SQLite
  collection passed. Temporary project `37954370` was deleted.
- The updated shared-server cloud harness passed in 93 seconds using project
  `37957968`: separate strategy queues, shared project, unique extra-module import
  for alpha, removal before beta, a deliberate end-of-algorithm runtime error rejected
  as a failed queue row with no experiment, graceful shutdown and project deletion.
  Evidence: `live-server-current.log` and `live-server-37957968/`.
- All eight configured production project IDs were confirmed present. Additional
  account projects were preserved.
- The latest S001 baseline passed its full date range, recording 14,810 orders.
  Evidence: `strategy-baselines-f83f44c07bbc4137a06cbefe6b996f5e/`.
- S002 passed the full-baseline rerun. Evidence:
  `strategy-baselines-564d60491ff24a61b978a82a09946ac1/`.
- The rebuilt Rust ObjectStore listing command successfully read the `test/` directory
  using normalized API paths. Evidence: `rust-object-list.log`.
- SML01 train-to-inference passed after the authorized storage reset: one model cell
  and bundle saved, all 1,109 predictions loaded/replayed, 45 orders and matching
  train/validation metadata. Evidence:
  `strategy-baselines-d3de845b5392442ea2df5423340e6c8d/`.
- Isolated validation projects and UUID-scoped model files were cleaned up. Production
  queues and local research history were preserved. Cloud ObjectStore contents were
  subsequently removed at the user's explicit request, as described below.

## S001 feed migration

The real baseline exposed retired Morningstar getters and direct comparisons of missing
values. The active source now treats explicitly retired getters as unavailable, reports
their paths once, excludes them from new catalogues and guards comparisons involving
optional fundamental values. Other provider exceptions still propagate. The original
source is archived under `strategies/s001/archive/baselines/`.

The successful run reported four unavailable paths: normalized diluted EPS growth at
one-year/three-month periods, payment turnover at three months, and ROIC at three months.
Retired signals are skipped. Historical results are not parity evidence after the
[Morningstar dataset migration](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity/morningstar-migration).

## SML01 persistence and complete ObjectStore reset

Training previously ignored ObjectStore's boolean write result, while inference swallowed
model-loading exceptions. Training now checks every write. Inference rejects missing,
empty, malformed or unordered predictions, reports loaded/replayed counts and fails if
nothing is replayed. Queue transport rejects corrupt completed results, retains unique
suffixes on long names and cannot create missing database files accidentally.

QC can initially report completion before an end-of-algorithm error becomes visible.
The server checks for runtime errors on every collection read, so rejected model writes
cannot become zero-order successes. Both local fixtures and the real-server harness
cover late failures.

The original cloud probe found 16,783 files and 1,917,239,389 bytes against current limits
of 1,000 files / 50 MiB. The user requested a complete inventory, then explicitly
instructed removal of **all** cloud ObjectStore contents, including prior model and cache
artifacts. The metadata inventory is preserved under
`.local/object-store-inventory/20261017/` as a historical pre-reset snapshot.

Directory-delete requests emptied the API root listing while a fresh QC process still
saw files, and the usage counter retained the old total. The operation therefore used
QC's native ObjectStore API to finish deletion and refresh the cache. The native reset
reported 15,994 remaining files deleted, zero failed deletions and zero files afterward;
earlier asynchronous API requests had removed the others. Evidence:
`object-store-reset-20261017/`, `object-store-native-reset.log` and
`strategy-baselines-bd9ef8444a824f9292a638c6e2071769/`.

Real SML01 training then saved its model successfully. Inference loaded and replayed all
1,109 predictions and generated 45 orders. The temporary project `37959493` and its
UUID-scoped artifacts were cleaned up. These metrics verify pipeline operation, not
financial deployment gates or historical campaign parity.

The API cleanup initially left six physical validation files visible to a fresh QC
process. A final native cleanup removed all six and reported zero failures. A separate
fresh QC backtest then confirmed `verified_object_count=0`; its project `37959675`
was deleted. The final API response also reported zero root entries and **zero bytes**
used. All seven temporary projects created for this reset and its validation were
confirmed inactive/recycled, and no pending cleanup records or server processes remained.
Evidence: `object-store-final-native-reset.log`, `object-store-empty-final.log`,
`strategy-baselines-d638681f57034cb381888e1b1682d056/` and
`object-store-reset-20261017/final-root.json` / `project-cleanup.json`.

Local source, configs, experiment history and results remain available. Earlier cloud models/caches were deleted at the
user's request and must be regenerated before standalone historical replay.

## Reproduce

```bash
./scripts/check.sh
cargo build --release --locked
cargo audit
cargo test --test live_server --locked -- --ignored --nocapture
.venv/bin/python scripts/validate_strategies.py --live
.venv/bin/python scripts/inventory_object_store.py --out .local/object-store-inventory/current
```

Install `cargo-audit` if absent. Live checks consume QC compute and own disposable
projects and UUID-scoped storage keys. Resume recorded cleanup after interruption with
`.venv/bin/python scripts/cleanup_smoke_projects.py`.

Historical campaigns have source parsing and portable-path repairs, without exhaustive
cloud reruns of their financial or ML behaviour. Migration paths are documented in
`docs/MIGRATION.md`. Backup tests cover consistent SQLite WAL snapshots and preservation
of prior backups; no external backup upload was performed.

A later REST audit still reports **0 bytes** used and an empty `qcv` directory
marker. Listing `/qcv` confirms no objects inside; deleting the marker returned
success but it remains visible in the root metadata. Evidence:
`object-store-reset-20261017/rechecked-root.json` and `qcv-marker-check.json`.
