# qc-backtest-server usage

Binary: `./target/release/qc-backtest-server` (or `cargo run --release --`)

Global options:
- `--data-dir <path>` (default: `data`)
- `--log-dir <path>` (default: `<data-dir>/logs`)

## Before starting or resuming

Inspect current queue/cloud identities first. Do not start or restart `serve` while an existing cloud execution is nonterminal: startup recovery can cancel it. A local polling timeout is not proof of cloud failure. Use the existing campaign collector to recover terminal evidence before queue reconciliation. See [current work](docs/CURRENT_WORK.md).

## serve — run the server

Backtests default to a 600-second polling deadline. For a longer run, set a scoped
server-process override before startup:

```bash
QC_BACKTEST_TIMEOUT_SECS=1800 ./target/release/qc-backtest-server serve
```

The accepted range is 1–86400 seconds. Invalid values log a warning and retain the
600-second default. Compile deadlines and result-validation checks are unchanged.

```bash
./target/release/qc-backtest-server serve
```

Runs in foreground. Discovers backtest nodes from QC API, launches one slot per node. Kills orphan server processes on startup, recovers stale `running` jobs from previous crashes.

Logs: `<log-dir>/qc.log` (INFO, readable) and `<log-dir>/qc_full.log` (DEBUG, full trace). Daily-rotated; files older than 16h are pruned automatically. Status box printed every 60s.

## status — show queue status

```bash
./target/release/qc-backtest-server status
```

Auto-detects if server is running (via PID file), shows uptime, throughput, rate-limit backoff, per-strategy queue counts, and recent errors.

## context — full optimizer context

```bash
./target/release/qc-backtest-server context --strategy s002
```

All-in-one view: optimizer description, strategy params, queue counts, next experiment number, currently running jobs, top 10 experiments, latest batch results, recent failures.

## next — next experiment number

```bash
./target/release/qc-backtest-server next --strategy s002
```

Prints the next available experiment number (scans both `experiments` and `backtest_queue` tables).

## queue — enqueue a backtest

```bash
./target/release/qc-backtest-server queue \
  --strategy s002 \
  --name "S002_Exp100_name" \
  --code-file path/to/strategy.py \
  --batch "py_bl05" \
  --priority 5 \
  --description "what changed" \
  --hypothesis "why this experiment" \
  --based-on "S002_Exp99_parent"
```

- `--code-file` or `--code-stdin` (required, mutually exclusive)
- `--priority`: lower = runs first (default 5)
- `--batch`, `--description`, `--hypothesis`, `--based-on`: optional metadata
- Rejects duplicate names; warns on duplicate code hash

## list — list queue entries

```bash
# Queued + running (default)
./target/release/qc-backtest-server list --strategy s002

# All strategies, filter by status
./target/release/qc-backtest-server list --status done --limit 10

# Filter by batch or name pattern
./target/release/qc-backtest-server list --strategy s001 --batch "bl20" --name-like "%g080%"
```

`--status` accepts comma-separated values: `queued,running,done,failed,cancelled`.

## top — leaderboard

```bash
./target/release/qc-backtest-server top --strategy s002 --limit 10
./target/release/qc-backtest-server top --batch "py_bl05"
```

Shows experiments sorted by CAR/MDD descending. Omit `--strategy` for all.

## show — experiment details

```bash
./target/release/qc-backtest-server show --strategy s002 --name S002_Exp561_trail04_nq16
./target/release/qc-backtest-server show --strategy s002 --name S002_Exp561_trail04_nq16 --code
```

Full stats (CAGR, DD, CAR/MDD, Sharpe, Sortino, WinRate, etc). `--code` also prints the stored strategy source.

## errors — recent failures

```bash
./target/release/qc-backtest-server errors --strategy s002 --limit 5

# Full QC API response for a specific failure
./target/release/qc-backtest-server errors --strategy s002 --detail S002_Exp555_dw_vx_tiered
```

## cancel / cancel-all

```bash
# Cancel one queued job
./target/release/qc-backtest-server cancel --strategy s002 --name "S002_Exp100_name"

# Cancel all queued in a strategy
./target/release/qc-backtest-server cancel-all --strategy s002

# Cancel only a batch
./target/release/qc-backtest-server cancel-all --strategy s002 --batch "py_bl05"
```

Only affects jobs in `queued` state (not running).

## retry — requeue failed jobs

```bash
# Retry one
./target/release/qc-backtest-server retry --strategy s002 --name S002_Exp555_dw_vx_tiered

# Retry all failures in a batch
./target/release/qc-backtest-server retry --strategy s002 --batch "py_bl05"
```

Resets failed jobs to `queued` (clears error, retry count, result_json).

## clean — remove old queue entries

```bash
# Preview what would be deleted
./target/release/qc-backtest-server clean --strategy s002 --dry-run

# Delete done/failed entries older than 7 days (default)
./target/release/qc-backtest-server clean --older-than-days 7

# Also remove cancelled entries
./target/release/qc-backtest-server clean --include-cancelled
```

Omit `--strategy` to clean all.

## obj-list / obj-get / obj-put / obj-delete / obj-stats — QC organization Object Store

```bash
# List a prefix (omit --path for root)
./target/release/qc-backtest-server obj-list --path models_hmm/QQQ

# Recursively walk and break down bytes by category (bars_*, models_*, features_*, oos_series, ...)
./target/release/qc-backtest-server obj-stats --path models_hmm

# Get a download URL (free-tier accounts cannot follow the URL; org Object Store
# downloads are gated to Institutional tier). With --out, downloads bytes to a file.
./target/release/qc-backtest-server obj-get --key models_hmm/QQQ/scaler.npz
./target/release/qc-backtest-server obj-get --key models_hmm/QQQ/scaler.npz --out /tmp/scaler.npz

# Upload a local file to a key
./target/release/qc-backtest-server obj-put --key models_hmm/QQQ/my_model.json --file /tmp/model.json

# Delete an object (requires --yes to confirm)
./target/release/qc-backtest-server obj-delete --key models_hmm/QQQ/stale.parquet --yes
```

Credentials and `organizationId` are read from `data/<S>.duckdb` settings — same source `qc_objstore.py` uses.

## obj-props — single-key metadata

```bash
./target/release/qc-backtest-server obj-props --key models_hmm/QQQ/inference_manifest.json
```

Prints key/size/modified/created/md5/mime — wraps `/object/properties`.

## obj-bulk-delete — recursive delete a prefix

```bash
./target/release/qc-backtest-server obj-bulk-delete --prefix /dollar_bars_30k_norm           # dry-run
./target/release/qc-backtest-server obj-bulk-delete --prefix /dollar_bars_30k_norm --yes     # actually delete
```

Walks every leaf key, prints a preview, then deletes (with `--yes`). Mirrors `lb/tools/qc_cleanup.py`.

## backtest-stats — live `runtimeStatistics` for a finished backtest

```bash
./target/release/qc-backtest-server backtest-stats --strategy s003 --name S003_Exp1061_VNQ_mshmm
```

Hits `/backtests/read` and prints standard stats (Net Profit, Return, …) plus
any custom `runtimeStatistics` the strategy posted (e.g. s003's `mean_auc`,
`best_co_cal`, `best_co_mdd`). Same data as `lb/tools/qc_get_stats.py`.

## backtest-orders — order history

```bash
./target/release/qc-backtest-server backtest-orders --strategy s003 --name S003_Exp1061_VNQ_mshmm
./target/release/qc-backtest-server backtest-orders --strategy s003 --name S003_Exp1061_VNQ_mshmm --out /tmp/o.json
```

Paged fetch (100/page) from `/backtests/orders/read`. Without `--out`, prints
a 20-line summary table; with `--out`, dumps full pretty-JSON.

## batch-stats — aggregate `runtimeStatistics` across a batch

```bash
# Default metrics (calmar, mdd, ann, sharpe, mean_auc)
./target/release/qc-backtest-server batch-stats --strategy s003 --batch ms_hmm

# Custom metrics — pulls any keys the strategy posted to runtimeStatistics
./target/release/qc-backtest-server batch-stats --strategy s003 --batch ms_hmm \
  --metrics best_co_cal,best_co_mdd,best_lo_ann
```

Replaces the `for ticker in QQQ TLT GLD ...; do qc_get_stats.py ${ticker}; done | awk ...`
pattern from `lb/tools/qc_get_stats.py`. Ticker is parsed from the experiment name
(third underscore-separated field).

## backtest-log — runtime console log for one backtest

```bash
./target/release/qc-backtest-server backtest-log --strategy s003 --name S003_Exp996_TLT_lblsrch
```

Pages QC's `/backtests/read/log` 200 rows at a time. Strategies that never call `self.Debug()` / `self.Log()` return an empty log (this is normal — use `errors --detail NAME` for the failure message stored in the queue row).

## test-api / mock-test / stress-test

```bash
./target/release/qc-backtest-server test-api       # Auth + node discovery
./target/release/qc-backtest-server mock-test      # Real QC API, tiny backtests
./target/release/qc-backtest-server stress-test    # Mock QC, chaos/race conditions
```

## Scheduling weight

Each strategy gets backtest slots proportional to its weight (default 1.0):

```sql
INSERT OR REPLACE INTO settings (category, key, value)
VALUES ('strategy', 'scheduler_weight', '3.0');
```
