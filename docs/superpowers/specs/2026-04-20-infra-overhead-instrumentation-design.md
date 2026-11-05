# Infra overhead instrumentation

**Date:** 2026-04-20
**Scope:** qc-backtest-server (Rust orchestrator) — observability only, no behavior change
**Goal:** identify where the 10 slots lose ~36% of wall time to overhead, broken down per phase and per strategy, so subsequent optimization targets the right bottleneck.

## Current state

- 10 backtest slots, 26 projects, warm pool
- S002 avg backtest ~22.6s; theoretical peak = 10 × 60/22.6 = **26.5 bt/m**
- Actual peak = **16.8 bt/m** → **63% utilization**, 36% overhead unaccounted
- Phase timings (`push_secs`, `compile_phase_dur`, `bt_phase_secs`, `pick_ms`) already exist in runner code at `debug` level. Summary line (`RUNNING 16.8bt/m`) is the only aggregate; it hides the breakdown.

## What we're measuring

**Overhead phases** (controllable infra):

| Phase | Definition | Where emitted |
|---|---|---|
| `pool_wait` | slot entering `acquire_job` → job returned | `acquire.rs` |
| `lock_wait` | entering `lock_project` → lock acquired | `lock.rs` |
| `push` | code upload to QC | `compile.rs` |
| `compile` | QC compile phase (push done → compile done) | `compile.rs` |
| `create_bt` | `create_backtest` API call | `backtest.rs` |
| `idle` | prior cycle end → next cycle start | `run_loop.rs` |

**Excluded:** `bt_run` (poll until backtest complete) — this is the product we're buying, not overhead. Log separately; don't include in overhead totals.

**Per-strategy counters:** cycle count + overhead_ms per strategy. This isolates s001 (deep QQQ) from s002 (broad ETF) since their bt_run differs but overhead should be similar.

## Logging

All instrumentation emits at **DEBUG** level — not INFO. This keeps `qc.log` (clean status line every minute) untouched and routes the overhead breakdown to:

- `qc_full.log` — existing debug log, already captures `qc::runner::*` at debug. New counters land here automatically.
- `qc_overhead.log` — **new dedicated log file** for overhead analysis, filtered to only the status-tick summary + per-cycle breakdowns. Avoids making `qc_full.log` harder to grep.

### New log file setup (in `src/log_setup.rs`)

Add a fourth file layer mirroring `qc_slots.log` but filtered to overhead-specific targets:

```rust
let overhead_file = format!("{name}_overhead.log");
let overhead_appender = tracing_appender::rolling::daily(log_dir, &overhead_file);
let (overhead_writer, overhead_guard) = tracing_appender::non_blocking(overhead_appender);
guards.push(overhead_guard);

let overhead_layer = fmt::layer()
    .with_writer(overhead_writer)
    .with_ansi(false)
    .event_format(BracketFormat {
        timer: ChronoLocal::new("%Y-%m-%d %H:%M:%S%.3f".to_string()),
        show_target: true,
        prefix: Some(prefix.clone()),
    })
    .with_filter(
        EnvFilter::new("off")  // silent by default
            .add_directive("qc::overhead=debug".parse().unwrap())
    )
    .boxed();
```

Register it alongside the other layers in the `registry().with(...)` chain.

All instrumentation code emits via a dedicated tracing target:

```rust
tracing::debug!(target: "qc::overhead", "phase push duration={:.1}ms slot={slot}", ms);
tracing::debug!(target: "qc::overhead", "summary (60s): s001 cycles=3 overhead=14.2s ...");
```

Using a distinct target `qc::overhead` means:
- Visible in `qc_full.log` (matches the `debug` filter) for cross-referencing with general slot chatter
- Visible in `qc_overhead.log` exclusively (filter whitelists only `qc::overhead`), giving a clean per-phase timeline
- **Invisible in `qc.log`** (INFO-only filter) — no impact on operator view

## Output format (every 60s, DEBUG, target=qc::overhead)

```
overhead summary (last 60s, 10 slots, wall=600s):
  s001:  cycles=3   overhead=14.2s   avg=4.7s/cycle
  s002:  cycles=27  overhead=48.6s   avg=1.8s/cycle
  s003:  cycles=45  overhead=76.5s   avg=1.7s/cycle
  total: cycles=75  overhead=139.3s  avg=1.86s/cycle  (23% of slot-wall)

phase breakdown (all strategies, last 60s):
  push=43s(5%)  compile=281s(34%)  create_bt=87s(10%)
  pool_wait=52s(6%)  lock_wait=3s(0%)  idle=412s(49%)
  bt_run=4_200s  (product — not overhead)
```

- `%` shown is over total overhead-time (push+compile+create_bt+pool_wait+lock_wait+idle), not over wall time — makes the phase ratios directly actionable.
- A separate `idle=49%` and `compile=34%` tells us different stories: idle → close the cycle gap; compile → warm-pool miss rate.

## Components

### `src/server_mod/mod.rs` — SessionCounters

Add fields:
```rust
pub struct SessionCounters {
    pub completed: AtomicU64,   // existing
    pub failed: AtomicU64,      // existing
    // New: aggregate overhead ms
    pub pool_wait_ms: AtomicU64,
    pub lock_wait_ms: AtomicU64,
    pub push_ms: AtomicU64,
    pub compile_ms: AtomicU64,
    pub create_bt_ms: AtomicU64,
    pub idle_ms: AtomicU64,
    pub bt_run_ms: AtomicU64,   // tracked but not in overhead total
    // New: per-strategy cycle and overhead
    pub per_strategy: DashMap<String, StrategyCounters>,
}

pub struct StrategyCounters {
    pub cycles: AtomicU64,
    pub overhead_ms: AtomicU64,
}
```

### `src/runner/run_loop.rs`

- Thread `prev_cycle_end: Option<Instant>` across iterations
- At top of loop (after `cycle_start = Instant::now()`), if `prev_cycle_end` is Some, add `(cycle_start - prev_cycle_end).as_millis()` to `session.idle_ms`
- At end of loop, set `prev_cycle_end = Some(Instant::now())`
- Increment `session.per_strategy[strategy].cycles` and `overhead_ms = (pool_wait + lock_wait + push + compile + create_bt + idle_for_this_cycle)`

### `src/runner/acquire.rs`

- Return `(result, wait_ms)` tuple; caller adds to `pool_wait_ms`

### `src/runner/lock.rs`

- Record Instant at entry, compute elapsed at first successful lock; add to `lock_wait_ms`

### `src/runner/backtest.rs`

- Already has `push_secs`, `compile_phase_dur`, `create_bt_secs` — just add counter increments in ms
- Add `bt_run_ms` from `bt_phase_secs`

### `src/server_mod/status.rs`

- Store last snapshot of each counter in `log_status` state
- Each tick: read current, compute delta from snapshot, log formatted block, update snapshot
- Uses existing 60s tick — no new task
- Log via `tracing::debug!(target: "qc::overhead", ...)` — goes to `qc_full.log` + `qc_overhead.log`, does **not** appear in `qc.log`

### `src/log_setup.rs`

- Add `qc_overhead.log` layer as described in the "Logging" section above
- Register the new layer in the `registry().with(...)` chain

## Non-goals

- No change to `poll_interval`, `compile_poll`, `slot_reserve`, or any behavior parameter
- No per-phase per-strategy double-breakdown (can add later if overhead differs significantly by strategy in the aggregate view)
- No external metrics export (Prometheus etc.) — log lines are enough
- No histogram / percentile tracking — means only
- No new INFO-level output; `qc.log` stays unchanged

## Success criteria

After deploy:
1. `cargo build` succeeds; server starts normally
2. After one run cycle per strategy, 60s status tick shows the overhead summary block
3. Per-strategy cycles + overhead_ms populate correctly (cycles count matches `completed` delta)
4. Sum of `push + compile + create_bt + pool_wait + lock_wait + idle + bt_run` (per tick) ≈ 10 × 60 000 ms (slots × wall). Variance <5% proves accounting is complete.

## Out of scope (future work)

Once we know where the 36% goes, a follow-up spec will:
- Cut `idle` via collect-handoff pipelining, faster poll_interval near completion, eager pre-fetch of next job
- Cut `compile` via warm-pool hit-rate tuning (already at `slot_reserve = max(1, num_slots/10)`; may need different heuristic)
- Cut `push` via compression or in-memory code cache if QC supports it
