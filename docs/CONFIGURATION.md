# Executor configuration

This reference follows `crates/qc-server/src/cli/`, `config_load.rs`, `config_discover.rs`, `config_resolve.rs` and `runner/run_loop/mod.rs`. Values below belong to executor 1.2.0, not every strategy's optional tools.

## Process inputs

| Input | Default / precedence | Effect |
|---|---|---|
| `--data-dir`, `QC_DATA_DIR` | Flag, then environment, then `data` | Directory holding `S*.duckdb` queues and `projects.json` |
| `--log-dir` | `<data-dir>/logs` | Executor log directory |
| `QC_USER_ID`, `QC_API_TOKEN` | Each environment value wins over the matching private-file field | QC authentication; a blank environment value fails rather than falling back |
| `QC_CREDENTIALS_FILE` | `<data-dir parent>/.local/credentials.json` | Private JSON path; fields `qc_user_id` and `qc_api_token` |
| `QC_ORGANIZATION_ID` | Environment, otherwise `project/organization_id` in the first discovered DB | Organization for account API operations |
| `QC_BACKTEST_TIMEOUT_SECS` | 600; accepts integer 1–86400 | Outer backtest polling budget; invalid input warns and uses 600 |
| `DUCKDB_DOWNLOAD_LIB` | `1` in `.cargo/config.toml` | Build-time pinned native library bootstrap |
| `DUCKDB_LIB_DIR` | Unset | Explicit build-time existing matching native library; see environment guide |
| `LD_LIBRARY_PATH` | Host loader default | Linux runtime search path when the matching native library is not beside the binary/deps |

Strategy package environment variables are documented by their owners. Provider export flags are separate: `scripts/export_market_data.py --help` supports `--home`, `--backend auto/parquet/duckdb`, `--release`, `--dataset` (default `us_prices`), repeatable `--symbol`, date bounds and a new `--output` directory. This adapter reads published/local provider data; it submits no QC job.

## Queue and project discovery

At least one `S*.duckdb` must exist for `ServerConfig::load`. Create a new isolated schema through `init-strategy --strategy <id>` after choosing its runtime directory. Existing legacy schemas gain execution columns; their research metadata is preserved. Do not create an empty database with a generic SQL client to bypass schema setup.

`projects.json` is a JSON object containing a `projects` list of dedicated QC project IDs. A nonempty shared list overrides per-strategy `project/cloud_project_id` and `cloud_project_id_2` through `_20`. With no projects for a strategy, its DB remains available for settings/inspection but is excluded from active scheduling. Pool projects are mutable workspaces, not manually maintained development projects.

`strategy/scheduler_weight` defaults to 1.0. Parsed values must be finite and positive. Unparseable settings fall back to 1.0; a parsed zero/negative/nonfinite value fails configuration. Organization settings remain non-secret DB configuration. User IDs and API tokens do not.

## Credentials and storage

Use [private credentials](CREDENTIALS.md) and [DuckDB access protocol](DUCKDB_MIGRATION.md). The private credential file must satisfy Unix permission checks; never put secret values into example commands, generated strategy source, queue annotations, logs or commits. Merely setting `QC_DATA_DIR` does not prevent a command from contacting QC. See the CLI effect table before executing it.
