# qc-backtest-server CLI reference

Executor 1.2.0. Use `target/release/qc-backtest-server --help` and `<command> --help` for exact flags. Help/version return before account operations. The following command families exist in `crates/qc-server/src/cli/commands.rs`; legacy `mock-test` and `stress-test` commands are absent.

Global `--data-dir <path>` defaults to `QC_DATA_DIR`, then `data`; `--log-dir <path>` defaults to `<data-dir>/logs`. Put global flags before the subcommand. [Configuration](docs/CONFIGURATION.md) owns credential/path defaults; [operations](docs/OPERATIONS.md) owns lifecycle/recovery guidance.

## Command effects

| Command | Purpose and effects |
|---|---|
| `init-strategy --strategy <id>` | Creates an isolated queue/result schema in the selected runtime |
| `serve` | Starts scheduling, remote submissions and recovery; may cancel identified in-flight executions during recovery |
| `queue --strategy <id> --name <name>` | Inserts work; provide `--code-file` or `--code-stdin`; a running server can submit it immediately |
| `cancel`, `cancel-all` | Cancel queued work by name or optional batch; do not assume this proves remote backtests stopped |
| `retry --strategy <id>` | Resets failed work by optional `--name`/`--batch`; retains explicit requested project pins |
| `list` | Lists selected queue states; default status `queued,running`, limit 20 |
| `errors --strategy <id>` | Recent failures; default limit 10; `--detail <name>` selects detail |
| `top` | Stored experiment ranking; optional strategy/batch, default limit 20 |
| `context --strategy <id>` | Combined local strategy/queue/experiment context |
| `next --strategy <id>` | Next experiment number based on stored names |
| `show --strategy <id> --name <name>` | Stored experiment detail; `--code` includes source |
| `clean` | Deletes selected old local queue records; default older-than-days 7; supports `--dry-run` and `--include-cancelled` |
| `status` | Local server/queue overview; use the intended data directory |
| `test-api` | External authenticated QC connectivity/node discovery |
| `create-projects` | Creates remote pool projects; default count 5 |
| `delete-projects --keep <n>` | Remote project deletion planning/action; supports `--dry-run`, `--yes`, and `--sort-by` |
| `reconcile-projects` | Reads remote projects; `--prune-orphans` changes local pool configuration |
| `obj-list`, `obj-props`, `obj-stats` | External ObjectStore listing/metadata; `obj-props` requires `--key` |
| `obj-get --key <key>` | Gets a download URL or writes contents through `--out` |
| `obj-put --key <key> --file <path>` | Uploads a local file to ObjectStore |
| `obj-delete --key <key>` | Deletes remotely with `--yes` |
| `obj-bulk-delete --prefix <prefix>` | Walks a prefix; `--yes` deletes. A preview still contacts the account |
| `backtest-log --strategy <id> --name <name>` | Fetches remote console log, optional `--start`/`--end` |
| `backtest-stats --strategy <id> --name <name>` | Fetches remote standard/runtime statistics |
| `backtest-orders --strategy <id> --name <name>` | Fetches paginated remote order history; optional JSON `--out` |
| `batch-stats --strategy <id> --batch <batch>` | Aggregates stored runtime statistics, optional comma-separated `--metrics` |

Local database opens may apply schema maintenance. “Inspection” does not imply an arbitrary command is filesystem-free. Remote metadata commands require credentials and network access even when they do not submit work.

## Queue specification

A queue row consists of `main.py` source plus optional `--extra-files <json-path>`, a JSON object mapping additional Python filenames to source strings. The server rejects traversal, malformed mappings, main.py overrides and oversized sources before project mutation. `--project-id` pins the requested execution project. Optional `--batch`, `--priority` (default 5), `--description`, `--hypothesis` and `--based-on` annotate the row.

A deliberately configured example, not a smoke test:

```bash
./target/release/qc-backtest-server --data-dir ./data queue \
  --strategy sstrangle --name RESEARCH_example \
  --code-file path/to/reviewed/main.py --extra-files path/to/extra-files.json \
  --batch reviewed_probe --priority 5
```

Source upload/compile/create are protected by a project lock. After create, collection follows the saved project/backtest identity. Do not reuse manually maintained QC development projects in this pool.

## Serve and shutdown

`serve` runs in the foreground. `QC_BACKTEST_TIMEOUT_SECS` changes the outer polling budget (default 600, accepted 1–86400). Invalid values warn and retain the default. It does not alter QC runtime rules or compile budgets.

Logs default to `<data-dir>/logs/qc.log` and `qc_full.log`; daily-rotated files older than the implemented 16-hour retention are pruned. Logs can contain account/source context and stay private. Graceful shutdown and recovery preserve unfinished identities as described in [operations](docs/OPERATIONS.md). Starting another instance uses a runtime-directory lock and does not kill unrelated processes.

## Safe verification

```bash
./target/release/qc-backtest-server --version
./target/release/qc-backtest-server --help
./target/release/qc-backtest-server queue --help
```

Cloud harnesses are Rust tests named `live_qc` and `live_server`, ignored by default because they use credentials and cloud compute. They are not equivalent to removed CLI commands. Consult [CI](docs/CI_CD.md) and obtain the intended operational scope before running them.
