# DuckDB and Parquet migration — 2026-10-17

Active execution storage now uses native DuckDB in both the Rust server and Python producers. SQLite is retained only for explicitly reading legacy inputs and the unchanged original database files.

| Store | Verified original rows | Original explicit indexes |
|---|---:|---:|
| S001.duckdb | 23,063 | 25 |
| S002.duckdb | 37,806 | 17 |
| SML01.duckdb | 23,688 | 15 |
| SSTRANGLE.duckdb | 19 | 1 |
| Total | 84,576 | 58 |

Every original row was compared with a consistent SQLite backup using logical SHA-256 hashes. IDs, precise floating-point values, nulls, blobs, settings, credentials and research tables were preserved. Primary/unique/foreign-key constraints and explicit indexes were retained. Sequence high-water marks include deleted rows, so empty tables do not restart retired identifiers. Additional execution columns and private schema metadata remain owned by the generic framework.

The originals `data/S*.db` remain unchanged. Source/binary rollback material, consistent backups and migration verification manifests are under `.local/migrations/`. The four active files have mode 0600. No credentials are copied into research Parquet exports.

## Storage boundaries

- `data/S*.duckdb`: mutable strategy queues, settings and collected results.
- `data/parquet/migration_20261017/<strategy>/`: immutable research snapshots, with row counts, schemas and checksums. Settings/source blobs are excluded; queue exports omit algorithm source and extra files.
- `strategies/sstrangle/results/local_akquant_20261017/research.duckdb`: first local options research warehouse.
- `strategies/sstrangle/results/local_akquant_20261017/parquet/`: normalized QC fills, provider option bars, AKQuant execution ledgers, cycle labels, prior-day features and entry-time joins.
- `/home/vic/data_providers/runtime`: remains the canonical shared market-data home. This migration does not relocate or modify its stores. Consumer exports and targeted API receipts are research evidence, not replacements for canonical ingestion.

## Coordinated access

DuckDB does not provide SQLite WAL's cross-process access behavior. Rust and Python therefore acquire the same `<database>.access.lock` before opening a native handle and close it before releasing the lock. Rust `Db` retains a path, not an idle native connection. Python buffers read results; a write transaction retains the handle until commit/rollback. Connection context exit releases native handles while allowing the logical Python object to be reused.

Use `qc_storage.connect()` for shared operational files. Independent analytical processes should read immutable Parquet snapshots; a long-lived direct DuckDB connection to a mutable server file bypasses this coordination protocol.

```python
import qc_storage as storage
with storage.connect('data/SSTRANGLE.duckdb') as conn:
    rows = conn.execute('SELECT name,status FROM backtest_queue').fetchall()
```

```bash
.venv/bin/python scripts/export_results.py --output data/parquet/<new-release-name>
.venv/bin/python scripts/status_box.py
./target/release/qc-backtest-server --data-dir data list --strategy sstrangle
```

`qc_storage` provides the DB-API operations used by current producers, including named rows, transaction rollback and safe duplicate handling. Native SQL was adjusted where DuckDB requires explicit grouping and typed keys. This is an adapter for this project's producers, not a promise to emulate arbitrary SQLite SQL or triggers.

## Build and repeat migration

Run `scripts/setup.sh` to install the local storage package and strategy packages. Python uses DuckDB 1.5.6; Rust uses duckdb-rs 1.10506.1 against the matching official native library. Cargo's `DUCKDB_DOWNLOAD_LIB=1` downloads the prebuilt library; Linux binaries locate it beside the build's `deps` directory. Keep that library with the binary when packaging it. Source bundling and QuantConnect cloud execution remain handled by the Rust server.

For another legacy runtime, stop its server before importing:

```bash
.venv/bin/python scripts/migrate_duckdb.py --data-dir <legacy-data-dir> \
  --audit-dir <new-private-audit-directory>
```

Migration refuses to overwrite an existing target. It creates a consistent SQLite backup first, checks source integrity, imports into a temporary native database, verifies all rows and exports, and only then publishes the `.duckdb` file. Old SQLite files and historical experiment source snapshots are preserved. Rollback requires stopping the server and restoring the matching original binary/code and original SQLite files together; do not mix an old binary with new native files.

## Verification

The Rust regression suite passed on native DuckDB, including atomic completion/rollback and queue isolation. S001's 244 tests and S002/SML01's 48 tests passed. Added tests verify Python/Rust concurrent inserts, duplicate handling, rollback, precise migration, deleted-ID counters, private export exclusion and feature availability.

The explicit live shared-server test passed using temporary QC project 37973954: two strategy queues completed, uploaded auxiliary files were isolated, an intentional late runtime error failed correctly, and graceful shutdown and cloud project deletion succeeded. It did not start the production queues. Final consolidated check evidence is saved under `.local/verification/duckdb_checks_20261017.log`.

## Local options results

See the [local AKQuant report](../strategies/sstrangle/results/local_akquant_20261017/LOCAL_RESULTS.md). All 216 QC fills and −$3,429 net P&L reconcile in AKQuant. Provider-price replays are explicitly marked as trade-print sensitivity tests; historical bid/ask and chain/OI coverage remain insufficient for an independent reproduction of the baseline's decisions.

The supplied [audio workflow](../data/audio/options_backtest_workflow/WORKFLOW.md) and timestamped transcript explain the baseline-log → feature-store → entry-time join → filter-research design. Existing 2024–2025 outcomes have already been inspected and are not an untouched holdout.
