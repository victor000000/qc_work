# QuantConnect research workspace

A shared Rust executor schedules QuantConnect backtests from independent Python strategy projects. Each strategy has its own DuckDB queue and results. Cloud projects are mutable execution workspaces; the executor reconciles source files before creating each backtest and retains its immutable remote identity for collection/recovery.

Current implementation: executor **1.2.0**, custom-axis feature engine **0.9.0**, and bounded diagnostic tooling **0.9.2**. These are separate version sequences. Diagnostics improve evidence collection; they do not establish margin/IV root causes or economic acceptance.

## Start here

- [Documentation guide](docs/README.md): navigation and document status.
- [Environment](docs/ENVIRONMENT.md): native Linux/WSL installation and dependency bootstrap.
- [Architecture](docs/ARCHITECTURE.md), [configuration](docs/CONFIGURATION.md), [CLI](USAGE.md).
- [Operations and recovery](docs/OPERATIONS.md): ownership, remote identities and failure handling.
- [Research handbook](docs/PROJECT_HANDBOOK.md): input/output contracts and versioned experiments.
- [Development and CI](docs/CI_CD.md), [documentation audit](docs/DOCUMENTATION_AUDIT.md).

## Install and verify locally

Use a Linux filesystem and Python 3.12 virtual environment, including inside WSL. Prerequisites are Rustup, a C toolchain, and uv. Docker is unnecessary for this workflow. Run from the checkout root:

```bash
bash scripts/setup.sh
bash scripts/check.sh
./target/release/qc-backtest-server --help
```

Setup installs the locked Python stack and editable workspace/strategy packages, then builds the release executor. The check script runs offline unit/regression suites and native writer integration; dependency installation and DuckDB bootstrap can need public registry/release downloads. It submits no QC jobs. Explicit credentialed cloud tests stay ignored. The pinned DuckDB dependency setup is rerun after Cargo cache restore to repair missing native libraries; see [CI](docs/CI_CD.md).

## Workspace map

| Path | Ownership |
|---|---|
| `crates/qc-server/` | Generic executor, API client, CLI, queue schema and Rust regressions |
| `qc_storage/` | Python access-lock/transaction adapter for shared DuckDB files |
| `strategies/s001/`, `s002/`, `sml01/` | Independent fundamental, cross-sectional and ML projects |
| `strategies/sstrangle/` | Options research, versioned designs, replay and diagnostics |
| `strategies/ss45dte/` | Separate longer-expiry options research |
| `scripts/` | Setup/checks, exports, migration and explicit operational tools |
| `data/` | Private runtime queues, pool configuration and logs; excluded from Git |

The adjacent provider project owns acquisition, coverage, provenance and publication of market data. This repository consumes pinned deliveries; it does not inherit authorization to replay protected provider requests. The screener's risk/execution interface is separately owned. Historical/nested research projects are not automatically covered by this workspace's CI.

## Execution is an operational action

Read [configuration](docs/CONFIGURATION.md) and [operations](docs/OPERATIONS.md) before configuring a runtime. Use dedicated QC pool projects: their files are reconciled and can be removed. Starting `serve` performs recovery and can cancel an identified in-flight backtest before requeueing it. An API polling error does not establish remote termination.

Commands below describe a deliberately configured runtime; they are not setup smoke tests:

```bash
./target/release/qc-backtest-server --data-dir ./data serve
./target/release/qc-backtest-server --data-dir ./data status
```

Credentials come from environment variables or a private JSON file, never strategy databases. See [credentials](docs/CREDENTIALS.md). Runtime databases, provider data and account archives must remain private.

## Evidence and limitations

Published source includes public synthetic regressions and a reduced calendar reference. Private market data, historical cloud receipts, generated plots and result archives are omitted; links in dated reports may refer to operational-only evidence. See [publication boundaries](PUBLICATION.md).

The November 7 diagnostic candidate passed local supported suites (749 Python and 75 Rust tests; two credentialed cloud tests ignored). The native-cache correction was subsequently published as `8c29672d76968b1bd18c31fb3bc3dc33d75d3c2e`; [its seven-job hosted run](https://github.com/victor000000/qc_work/actions/runs/42367520420) passed. Those checks establish the tested source/CI scope, not cloud research parity, strict provider readiness, live trading safety or investment performance. The C0 margin trigger, historical IV cause, full sidecar/feature parity and economic acceptance remain open.

[Current work](docs/CURRENT_WORK.md) and [next steps](docs/TODO.md) preserve dated research results with their limits. [Changelog](CHANGELOG.md) preserves earlier implementation history.
