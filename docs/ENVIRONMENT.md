# Native environment and setup

Current instructions reviewed 2026-11-07. Use native Linux or Ubuntu WSL on a Linux filesystem. Docker is unnecessary; the historical retirement record remains below with its original dates. The imported LEAN checkout and nested research projects have independent dependencies and are not needed for executor tests.

Install Rustup, a C compiler/toolchain and uv. From the checkout root:

```bash
bash scripts/setup.sh
bash scripts/check.sh
./target/release/qc-backtest-server --help
```

Setup creates/reuses a Linux Python 3.12 environment, installs `requirements-dev.lock` and editable packages, and builds the release executor with Cargo.lock. It does not start the QC server or submit work. Run on a fresh development checkout or coordinate environment/build changes with active local processes. Linux access locks are part of the shared DuckDB protocol; Windows users should run this workflow inside WSL.

DuckDB build cache restoration can omit the native library while keeping Cargo metadata. The local check entrypoint and native CI jobs run `bash scripts/bootstrap_duckdb.sh` to rehydrate the pinned 1.5.6 dependency. Installed dependencies can permit offline test runs, but setup/bootstrap may require public registry/release access. See [CI](CI_CD.md) and [operations](OPERATIONS.md) for diagnostics.

Optional provider integration uses `requirements-data.txt` and the independently maintained adjacent provider checkout. The local options adapter has its own `strategies/sstrangle/local/requirements.txt`. These are optional integrations, not prerequisites for recreating omitted private market evidence. Read their help and delivery contracts before requesting data. [Local replay limits](../strategies/sstrangle/local/README.md) remain applicable.

Safe import smoke:

```bash
.venv/bin/python -c 'import duckdb, pyarrow, akquant; print("research imports OK")'
```

Credentials and operations are covered by [configuration](CONFIGURATION.md), [credentials](CREDENTIALS.md) and [recovery](OPERATIONS.md). Build/import success does not establish native cloud API compatibility or live readiness.

## Scope of the change

Core setup and CI already use native execution; no container migration or data copying was needed. On 2026-10-23, the existing Linux `.venv` successfully imported DuckDB, PyArrow and AKQuant, and the native Rust executable was present. This is an environment smoke check, not a fresh full test-suite or cloud validation.

The sibling provider project and screener now also have native environments; use their own setup and operations guides. Frozen strategy sources and backtest evidence remain unchanged.

## Docker retirement verified on 2026-10-23

Docker provides no required service for the current workflow. `scripts/setup.sh`,
`scripts/check.sh` and CI already execute directly on the host. There is no active
Dockerfile or Compose deployment in this workspace, so no application runtime
rewrite or database relocation was necessary.

Verification during cleanup:

- The workspace `.venv` imported DuckDB, PyArrow, AKQuant and the provider SDK.
- The native Rust executable successfully displayed its CLI help.
- `.venv/bin/python -m pytest tests -q` passed all 20 tests.

These are local checks; no cloud job, data download or full strategy suite was run.

The initial Docker inventory contained two stopped containers (`data_providers`
and `dte_21_screener`), their two images, and three unused `multi-stack_*` volumes.
Source, live provider storage and Windows trading exports were host bind mounts.
Before attempting removal, this workspace saved and read-verified the provider
container filesystem and all three volumes. At the user's subsequent request,
the approximately 143 MiB backup directory
`/home/vic/qc_work/.local/docker-cleanup-20261023/` was deleted along with its
inspection metadata. No Docker recovery copy is retained in this workspace.

The screener container/image disappeared during inspection; its own cleanup record
is `/home/vic/dte_21_screener/docs/DOCKER.md`. Docker Desktop was subsequently
removed by another process before this workspace's removal commands could connect
to the daemon. Those commands did not delete the remaining resources. Final host
inspection found no Docker Desktop executable, registered installation, running
Docker processes or Docker WSL disk directory. Its login startup entry was absent.
The former daemon inventory could therefore no longer be queried. Remaining Docker
CLI binaries or client configuration alone do not provide a running daemon.

Continue using the native setup above. Native project data and environments do
not depend on Docker or its deleted recovery archives.
