# Pipelined slots: early project release + async poll/collect

**Date:** 2026-04-20
**Scope:** `qc-backtest-server` (Rust orchestrator) — slot loop refactor for throughput
**Goal:** push steady-state throughput from 11.3 bt/m to ≥18 bt/m by decoupling the slot's hot path from post-create polling and collection.

## Current state (baseline)

- 10 slots × 26 projects; warm-pool fills in background
- Slot serializes: `acquire → lock → push+compile+create → poll → collect → unlock`
- Polling tail dominates: avg bt_run ≈ 26-48s; 10-22 polls per backtest at 1.5s = 15-33s of polling per cycle
- Throughput: **11.3 bt/m** observed; theoretical ≈ **26 bt/m** at 10 slots × 23s/cycle → **~43% utilization**

### Instrumentation bug

`src/runner/backtest.rs:109` computes `create_bt_secs = bt_create_start.elapsed()` AFTER `poll_backtest()` completes, capturing 20-40s per cycle. The actual `create_backtest` API call takes 1-2s (visible in `qc_full.log`). Aggregated 900s/60s `create_bt=90%` reports are therefore misleading — they attribute polling time to create.

## Core architectural change

**"Slot ends at create, not collect."**

```
OLD:  slot: acquire → lock → push+compile+create → poll → collect → unlock → next
                                                  ^^^^^^^^^^^^ blocks slot ~30s
NEW:  slot: acquire → lock → push+compile+create → UNLOCK → spawn(poll+collect) → next
                                                  ^^^^^^ slot freed ~3s after create
                                                         poll+collect runs async
```

### Why this is safe

Collection only needs `(project_id, backtest_id)` as identity keys to call `qc.read_backtest(...)`. It does NOT need the project lock. Three guarantees:

1. **QC stores the compiled binary at `create_backtest` time.** The backtest tied to `backtest_id` uses the compile snapshot taken at create. Subsequent file pushes to the same project do NOT affect a running backtest.
2. **`read_backtest(project_id, backtest_id)` is stateless.** It fetches by ID, not by scanning project files. Two different `backtest_id`s on the same `project_id` return independent results.
3. **Collection code uses the `(project_id, backtest_id)` tuple as primary key everywhere** (poll, collect, collect_parse, DB write). Never reads project state.

### Additional safeguards

- On `spawn_collect`: log `collect_spawned project={pid} bt={bid}` with context
- Collect-side assertion: if the QC response's `backtest_id` differs from the expected `bt_id`, log error and fail this collect (defensive; must not happen)
- New metric `active_collects: AtomicI64` — bumped on spawn, decremented on completion — exposed in status tick

## Dedicated pipeline log

Mirrors the `qc_overhead.log` pattern. All events DEBUG level on new target `qc::pipeline`:

```
2026-04-20 10:00:12.345 [DEBUG] qc::pipeline slot-3: lock_acquired project=29979167
2026-04-20 10:00:13.892 [DEBUG] qc::pipeline slot-3: push_done project=29979167 elapsed=1.5s
2026-04-20 10:00:14.701 [DEBUG] qc::pipeline slot-3: compile_done project=29979167 compile_id=25297... elapsed=0.8s
2026-04-20 10:00:16.503 [DEBUG] qc::pipeline slot-3: create_bt_done project=29979167 backtest_id=8ba80... elapsed=1.8s
2026-04-20 10:00:16.510 [DEBUG] qc::pipeline slot-3: project_released project=29979167 (pipeline handoff)
2026-04-20 10:00:16.512 [DEBUG] qc::pipeline slot-3→collect-task-42: collect_spawned project=29979167 bt=8ba80... active_collects=3
2026-04-20 10:00:16.514 [DEBUG] qc::pipeline slot-3: next_acquire starting (slot freed)
2026-04-20 10:00:47.228 [DEBUG] qc::pipeline collect-task-42: poll_started project=29979167 bt=8ba80...
2026-04-20 10:00:47.856 [DEBUG] qc::pipeline collect-task-42: poll_done project=29979167 bt=8ba80... polls=12 bt_run=30.7s
2026-04-20 10:00:47.920 [DEBUG] qc::pipeline collect-task-42: result_stored project=29979167 bt=8ba80... car_mdd=5.57 active_collects=2
```

### Log file setup (in `src/log_setup.rs`)

Add 4th file layer, filter whitelists only `qc::pipeline`:

```rust
let pipeline_file = format!("{name}_pipeline.log");
let pipeline_appender = tracing_appender::rolling::daily(log_dir, &pipeline_file);
let (pipeline_writer, pipeline_guard) = tracing_appender::non_blocking(pipeline_appender);
guards.push(pipeline_guard);

let pipeline_layer = fmt::layer()
    .with_writer(pipeline_writer)
    .with_ansi(false)
    .event_format(BracketFormat {
        timer: ChronoLocal::new("%Y-%m-%d %H:%M:%S%.3f".to_string()),
        show_target: true,
        prefix: Some(prefix.clone()),
    })
    .with_filter(
        EnvFilter::new("off")
            .add_directive("qc::pipeline=debug".parse().unwrap()),
    )
    .boxed();
```

Register alongside existing layers. `qc_full.log` continues to receive all DEBUG as today.

### Required fields per event

`slot_id` (or `collect-task-N`), phase name, `project_id`, `backtest_id`, elapsed, `active_collects`. Enough to reconstruct any slot's trajectory offline.

## Adaptive polling tiers

Current: 1.5s fixed interval. 10-22 polls per backtest. New tiered schedule (inside `poll_and_collect`, off the slot's hot path):

| Poll # | Delay before next poll | Rationale |
|---|---|---|
| 1 | 0 (no sleep before first) | Catch already-complete backtests instantly |
| 2-4 | 0.5s | Early phase; catch ≤3s backtests |
| 5-15 | 1.0s | Typical s002 range (~15-25s bt_run) |
| 16+ | 2.0s | Slow path (s001 / long backtests) |
| cap | 3.0s | Hard ceiling (rate-limit safety) |

### Behavior tweaks

1. **No initial sleep before first poll** (preserves current behavior)
2. **Progress-aware tighten**: if `bt_result.progress >= 0.80`, next delay = 0.5s (near completion)
3. **Per-task 429 elasticity**: on rate-limit response, double current tier's delay for the NEXT 3 polls in this task only. Reset when next poll succeeds. Does not affect other concurrent poll tasks.

### Metrics to `qc_pipeline.log`

- `poll_interval_used`: per-poll delay actually applied (distinguishes adapted vs static)
- `polls_total` and `polls_tier_distribution` on task completion

## Measurement fix

Split the misleading `create_bt_secs`:

| Field | Meaning |
|---|---|
| `create_api_secs` | NEW. Duration of the `create_backtest` API call alone. Target 1-3s. |
| `poll_tail_secs` | NEW. Duration from create return → collect done. Includes poll + collect. |

In `SessionCounters` (overhead module), replace `create_bt_ms` with two fields: `create_api_ms` and `poll_tail_ms`. Update `qc_overhead.log` summary format to show both. Update status tick to use `create_api_ms` for the dominant-phase diagnostic.

Old `create_bt_ms` field is removed (no backward-compat shim needed — internal only).

## Slot refactor details

### Split `run_backtest` into two phases

| New function | File | Responsibility |
|---|---|---|
| `prep_backtest()` | `src/runner/backtest.rs` | push + compile + create_backtest + DB write of `backtest_id` on queue row. Returns `(backtest_id, project_id, create_api_secs)`. Honors `skip_push`/`pre_compile_id` warm-pool fast path (same as today). Owns project lock. |
| `poll_and_collect()` | `src/runner/pipeline.rs` (NEW) | Runs in `tokio::spawn`. Polls + parses stats + marks done. No project lock. Uses `(project_id, backtest_id)` tuple as primary key. Constructs its own `BacktestResponse` via polling (does not receive from caller). |

### New `run_loop.rs` shape

```rust
loop {
    let (job, db, project_id, skip_push, pre_compile_id) = acquire_job().await?;
    let project_id = lock_project(...).await?;

    match self.prep_backtest(prep_params).await {
        Ok((backtest_id, pid, create_api_secs)) => {
            self.unlock_project(pid);  // ← EARLY RELEASE
            let ctx = PollCollectCtx { client, session, backtest_id, project_id: pid, job, db, bt_poll_cfg };
            tokio::spawn(pipeline::poll_and_collect(ctx));  // ← async; slot loops immediately
        }
        Err(e) => {
            self.handle_backtest_error(e, ...).await;
            self.unlock_project(project_id);
        }
    }
    // slot immediately loops to next acquire_job
}
```

### Backpressure (defensive)

If `active_collects > 2 * num_slots` (=20 by default), slot waits 500ms before calling `acquire_job()` to avoid unbounded memory growth. If `active_collects > 3 * num_slots` (=30), slot waits 2s. Logged once per backoff event to `qc_pipeline.log`.

### Error handling

Errors in `poll_and_collect` bump `session.failed`, write `status='failed'` on the queue row, and log full context (project_id, backtest_id, phase-of-failure) to `qc_pipeline.log`. `active_collects` is managed via an `ActiveCollectsGuard` RAII struct constructed at task entry (`Drop` impl decrements). Ensures the counter cannot leak on panic, cancellation, or early return.

## File inventory

| File | Change |
|---|---|
| `src/runner/backtest.rs` | Split into `prep_backtest`; remove polling from this file; fix `create_bt_secs` → `create_api_secs` instrumentation |
| `src/runner/pipeline.rs` | **NEW** — `poll_and_collect` + `ActiveCollectsGuard` RAII |
| `src/runner/poll.rs` | Implement tiered delays + progress-aware tighten + per-task 429 elasticity |
| `src/runner/run_loop.rs` | Use prep_backtest + spawn `poll_and_collect`; early unlock; backpressure check |
| `src/runner/mod.rs` | Export new `pipeline` module |
| `src/server_mod/mod.rs` | Add `active_collects: AtomicI64` to `SessionCounters` |
| `src/server_mod/overhead.rs` | Add `create_api_ms` + `poll_tail_ms` counters; remove old `create_bt_ms` |
| `src/server_mod/status.rs` | Show `active_collects` in status tick; use new phase fields |
| `src/log_setup.rs` | Add `qc_pipeline.log` layer |

## Rollout (single aggressive session, ~6hr)

1. **Measurement fix + pipeline log file** (~30 min) — ship first for visibility. Commit 1.
2. **Slot refactor: early release + poll_and_collect spawn** (~2 hr) — Commit 2.
3. **Adaptive polling tiers** (~1 hr) — Commit 3.
4. **Active-collects metric + backpressure** (~30 min) — Commit 4.
5. **Rebuild + restart + zombie cleanup** (~15 min)
6. **Soak test ~30 min; compare metrics** (~30 min)

Each step is its own git commit. Stop-and-verify between steps. Roll back if throughput regresses >10% vs prior commit.

## Success criteria

1. `cargo clippy --all-targets --all-features -- -D warnings` exits 0 (preserves zero-suppression)
2. `cargo build --release` finishes with 0 warnings
3. Server starts, runs 30+ min without panic/crash
4. Throughput **≥ 18 bt/m** steady-state (baseline 11.3)
5. `qc_pipeline.log` contains the expected events for at least 100 completed jobs
6. `create_api_secs` averages **1-3s** (confirms measurement fix)
7. `active_collects` stays below `2 * num_slots` (=20) in 99% of samples
8. No increase in `failed` or zombie `running` rows vs prior 30 min baseline (DB consistency)
9. S001 and S002 experiment results bit-identical vs single-run reference (collection correctness preserved)

## Non-goals

- No change to warm-pool architecture beyond what the refactor demands (filler stays as-is)
- No change to strategy code (`data/s001/`, `data/s002/`)
- No change to project-locking policy (still exclusive for push+compile)
- No global rate-limit state machine changes beyond per-task adaptive delay
- No UI / dashboard work
- No breaking of existing log formats — only additions

## Risk + rollback

- **If pipeline refactor breaks collection**: revert Commit 2 via `git revert`. Collection regression shows as `failed` rate spike or bit-different `car_mdd` outputs.
- **If adaptive polling causes 429 storms**: per-task backoff + 3s ceiling self-corrects. Disable via `POLL_TIER_DISABLE=1` env var (add this flag for operator escape hatch).
- **If memory grows (too many active_collects)**: backpressure kicks in at 2x, 3x thresholds. If still unbounded, hard-cap at 30 and block slot loop.

Each rollback = single `git revert <commit-sha>` + server restart.

## Verification after each commit

```
cd /home/bwg/qc_work
cargo clippy --all-targets --all-features -- -D warnings 2>&1 | tail -5
cargo build --release 2>&1 | tail -3
# operator-side soak:
tail -F data/logs/qc_pipeline.log.$(date +%Y-%m-%d) &
tail -F data/logs/qc.log.$(date +%Y-%m-%d) | grep "bt/m"
```

Expect post-soak throughput ≥ 18 bt/m and ≤ 30 `active_collects` concurrently.
