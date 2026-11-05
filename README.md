> Latest 0.9.0 validation (2026-11-05): [C0 margin and IV evidence](strategies/sstrangle/results/margin_verified_v090_20261105/RESULTS.md). 427 tests passed. Cloud-tested diagnostic/API and publication-race fixes preserve exact native account parity. C0 still fails on margin; IV replay passes but historical root cause remains open. Pre-trigger margin state, full sidecar/feature parity, strict provider inputs and economic acceptance remain gaps.

> Latest validation: [warmed C1/P1 parity confirmed](strategies/sstrangle/results/warmed_v090_20261105/RESULTS.md). 422 tests; 31 complete sessions and ready-axis evaluations for C1/P1. C0 margin failure and unresolved IV/sidecar/provider gates are retained.

> Latest result (2026-11-05): [0.9.0 minute-coverage fix verified](strategies/sstrangle/results/fix_v090_20261105/RESULTS.md). 421 tests and four QC runs pass; regular/early-close coverage and short account parity confirmed. Remaining gates are documented.

> Latest validation (2026-11-05): [provider audit and QC cloud results](strategies/sstrangle/results/validation_v090_20261105/RESULTS.md). Regular C0 account parity passed; full observer acceptance remains blocked by measured coverage/errors and sidecar-export restrictions.

> Current SSTRANGLE design: [0.9.0](strategies/sstrangle/research/design_20261030_v090/DESIGN.md). Local engineering tests and sampled PoCs passed; strict data, native QC cloud parity and funded acceptance remain open. Start with the [project handbook](docs/PROJECT_HANDBOOK.md) for setup, code/data contracts, reproduction and continuation.

# QuantConnect experiment workspace

Historical funded reference: **[Version 0.8.5](strategies/sstrangle/research/design_20261026_v085/DESIGN_REPORT.pdf)** — completed condor QC baseline → bounded local research → funded QC verification; optional put-spread add-on rejected on a native margin call. [Evidence](strategies/sstrangle/results/qc_poc_20261026_v085/final_verification.json). Research release; robust alpha and official-settlement parity are not established.


Shared execution infrastructure for QuantConnect experiments, with isolated strategy development.
The Rust server schedules all registered strategies through a common pool of QC projects and
compute nodes. Each strategy owns its source, research artifacts, queue database and results.

## Start here

[Documentation guide](docs/README.md) · [Current work](docs/CURRENT_WORK.md) · [Next steps](docs/TODO.md) · [CLI usage](USAGE.md)

The latest [0DTE design and measured findings](strategies/sstrangle/research/design_20261030_v090/DESIGN.md) cover the tested custom-axis pipeline and its remaining acceptance gates. Current work separates completed research from remaining independent replay and prospective validation.

Before starting `serve`, check existing local and cloud executions. Startup recovery can cancel an in-flight backtest; never restart it to recover progress from a local polling error.

## Structure

```text
crates/qc-server/       Rust server, API client, CLI, schema and regression tests
strategies/
  s001/                Fundamental cross-sectional research, generators and tests
  s002/                Independent cross-sectional strategy templates
  sml01/               ML autoresearch Python package, templates, evidence and tests
  sstrangle/           Transcript short-strangle algorithm, queue runner and audited results
  wang-ml/             Historical Wang ML pipelines and reference materials
scripts/               Workspace setup, checks, project bundling and API diagnostics
workspaces/lean/       Imported local LEAN checkout and incubation projects
data/                  Local runtime: S*.duckdb, projects.json, logs (not source code)
docs/                  Architecture, usage and reconstruction evidence
```

The canonical strategy and execution paths replace the imported top-level folder names.
The migration map is in [docs/MIGRATION.md](docs/MIGRATION.md). Historical downloaded
environments and the old prebuilt server are preserved under ignored `.local/`.

Active storage uses DuckDB with immutable Parquet exports; see the
[storage migration and access protocol](docs/DUCKDB_MIGRATION.md).
The [local AKQuant strangle report](strategies/sstrangle/results/local_akquant_20261017/LOCAL_RESULTS.md)
records the QC accounting control, provider-data coverage and replay limitations.

## Setup and validation

The supported default is **native Linux / Ubuntu WSL, without Docker**.
See the [native environment guide](docs/ENVIRONMENT.md) for setup and research dependencies.
The guide also records local validation and Docker retirement/recovery evidence.

Prerequisites: Rustup, a C compiler, and `uv` (for Python 3.12 environments).
The current storage lock protocol and shell scripts require Linux; on Windows,
run them inside WSL against the Linux workspace and its Linux virtual environment.
Run from this workspace root:

```bash
./scripts/setup.sh
./scripts/check.sh
cargo build --release --locked
```

Rust is pinned in `rust-toolchain.toml`. Python host tests use the pinned `requirements-dev.lock` (input: `requirements-dev.txt`);
the QuantConnect cloud provides its own algorithm runtime. CI runs Rust formatting,
Clippy, tests, a release build, dependency auditing and separate S001/S002/SML01 test jobs.
Cloud tests are explicit and excluded from normal CI.

## Run the shared server

```bash
./target/release/qc-backtest-server --data-dir ./data serve
./target/release/qc-backtest-server --data-dir ./data status
./target/release/qc-backtest-server --data-dir ./data queue \
  --strategy s001 --name S001_example --code-file strategies/s001/s001_20260628_base.py
```

`data/projects.json` has the form `{"projects": [123456, 123457]}` and lists dedicated compute projects. The server reconciles each project's
files with its job specification before compiling, so extra source files cannot leak between
strategies. Do not use manually maintained development projects as compute-pool projects.
One server may own a data directory at a time; independent data directories may run separately.

Credentials can be supplied through `QC_USER_ID`, `QC_API_TOKEN`, and `QC_ORGANIZATION_ID`,
or stored in the `settings` table of the first discovered strategy DB:
`credentials/qc_user_id`, `credentials/qc_api_token`, and `project/organization_id`.
Keep runtime databases and credential files private. Never copy a production DB into source control.

## Add a strategy

```bash
./target/release/qc-backtest-server --data-dir ./data init-strategy --strategy s005
mkdir -p strategies/s005
```

Initialization creates an independent queue, results, code storage and settings schema.
The strategy ID starts with `s` and contains lowercase letters, digits or underscores.
With a configured shared project pool, its `S005.duckdb` is discovered automatically.
Strategy-specific tables belong to that strategy; the generic server does not interpret them.
Any Python QC project folder can be submitted through the shared server:

```bash
python3 scripts/enqueue_project.py --strategy s005 --name S005_example \
  --project path/to/qc-project --dry-run
# Remove --dry-run to enqueue the validated main.py + module bundle.
```

Multi-file queue submissions store `{filename: source}` JSON in `backtest_queue.extra_files`.
The CLI accepts `--extra-files path/to/files.json` for this multi-file specification.
Raw results are written to `backtest_queue.result_json`, including custom runtime statistics.

## Strategy tests and research

```bash
(cd strategies/s001 && ../../.venv/bin/python -m pytest)
(cd strategies/s002 && ../../.venv/bin/python -m pytest)
(cd strategies/sml01 && ../../.venv/bin/python -m pytest)
.venv/bin/python -m s001.next_round_s001   # queues real experiments; run intentionally
```

The cloud ObjectStore was cleared at the user's request on 2026-10-17 and verified at
zero files / zero bytes after testing. Earlier cloud models/caches must be regenerated;
local source, configurations and research history were retained. SML01's round driver
trains before inference.

Read each strategy's own workflow or program before starting research. Historical Wang ML
submission scripts remain a separate research workspace and do not run during test discovery.

## Explicit cloud checks

```bash
python3 scripts/qc_api_check.py                        # read-only authentication/project listing
cargo test --test live_qc -- --ignored --nocapture     # temporary cloud backtest + DuckDB collection
cargo test --test live_server -- --ignored --nocapture # actual server, two strategies, file isolation
.venv/bin/python scripts/validate_strategies.py         # render/validate current baselines locally
.venv/bin/python scripts/validate_strategies.py --live  # cloud S001/S002 and SML01 train + inference
# Add --strategies s001 to validate only one strategy.
```

The live Rust test uses credentials from `data/S001.duckdb` (`QC_DATA_DIR` overrides the directory),
creates its own project, and deletes it after success or failure. It consumes QC backtest compute.
The read-only Python diagnostic also accepts `QC_USER_ID` and `QC_API_TOKEN` from the environment.

The baseline validator starts an isolated server and fresh local queues, uses its own
cloud project and UUID ObjectStore prefix, and checks SML01 model creation and prediction
replay. Evidence is written under `.local/verification/strategy-baselines-*`.

Read-only ObjectStore cleanup planning:

```bash
.venv/bin/python scripts/inventory_object_store.py --out .local/object-store-inventory/current
```

This writes file/group CSVs, completeness evidence and a filterable HTML review. It
lists metadata without downloading stored contents or deleting artifacts. Local SML01
champion-config matches and selector/manifest files receive conservative preserve hints;
other keys are not automatically considered obsolete. Optional `--max-files` and
`--max-bytes` record observed quotas for that snapshot.

If a cloud test is interrupted by a network failure, resume recorded project cleanup with
`python3 scripts/cleanup_smoke_projects.py`.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for execution boundaries,
[USAGE.md](USAGE.md) for the CLI reference and
[docs/RECONSTRUCTION.md](docs/RECONSTRUCTION.md) for the remaining migration and review checklist.
Current test results and cloud limitations are recorded in [docs/VERIFICATION.md](docs/VERIFICATION.md).

## Shared market data

The sibling `data_providers` project owns market-data maintenance and delivery,
including its live `data_providers/runtime` storage. Its deployment is managed independently;
this project reads published data through the native Python SDK and does not require a local container.
The SDK resolves that shared home automatically; `DATA_PROVIDERS_HOME` or the
export adapter's `--home` can override it. QC execution/strategy databases remain
in this project's own `data/` directory.
Install the optional local research integration with
`uv pip install --python .venv/bin/python -r requirements-data.txt`, then export
selected datasets with `scripts/export_market_data.py --help`.
Exports are immutable CSV/Parquet directories with schema and checksum manifests.
This adapter does not upload custom data or submit QuantConnect cloud work.

Shared market exports use the `data_providers` DuckDB–Parquet platform. The export
script accepts `--backend parquet` to require a published release and `--release`
to pin an immutable version for reproducible research; its output manifest records
the originating release. Run the shared project's maintenance with `--publish`
after updating data.
