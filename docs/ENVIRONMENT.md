# Native development and research environment

Updated: 2026-10-23. **Docker is not required.** Run this project directly in Linux or Ubuntu WSL. Existing setup scripts, the Rust QC client/server and Python research tools use this environment already.

## Components

| Component | Runtime |
|---|---|
| QC queue, API client and result collection | Native Rust executable in `target/release/` |
| Feature work, reconciliation and local AKQuant replay | Workspace `.venv` |
| DuckDB and Parquet | Local libraries and files; no database service |
| Strategy execution in QC | QuantConnect cloud runtime |
| Provider integration | Native SDK reading the sibling project's published data |

The imported `workspaces/lean` tree is reference/incubation material, not a prerequisite for this workflow. Local LEAN execution is outside this setup; evaluate its own dependencies separately if that workflow is adopted.

## Setup

Work from the Linux filesystem (`/home/vic/qc_work`), using a Linux virtual environment. Install Rustup, a C compiler and `uv` first. Then:

```bash
cd /home/vic/qc_work
./scripts/setup.sh
```

The script uses the pinned Rust toolchain and Python 3.12 dependency lock, installs workspace packages and builds the native Rust binary. It does not start the QC server or submit a job.

For optional provider integration and options research:

```bash
uv pip install --python .venv/bin/python -r requirements-data.txt
uv pip install --python .venv/bin/python -r strategies/sstrangle/local/requirements.txt
```

The provider integration requires the sibling `../data_providers` checkout. See [local replay limitations](../strategies/sstrangle/local/README.md) before interpreting AKQuant results.

## Verify and operate

```bash
.venv/bin/python -c 'import duckdb, pyarrow, akquant; print("Native research imports OK")'
./target/release/qc-backtest-server --help
```

For code changes, run the relevant tests; `./scripts/check.sh` is the full workspace check. See [CLI usage](../USAGE.md) for operational commands and credentials configuration.

Before starting the Rust server, inspect existing local/cloud execution identities. Never restart it while a cloud backtest is nonterminal: startup recovery can cancel an in-flight run. Setup and dependency changes should also be scheduled outside active local research processes.

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
