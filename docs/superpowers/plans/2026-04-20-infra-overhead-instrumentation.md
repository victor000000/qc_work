# Infra Overhead Instrumentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-phase, per-strategy overhead instrumentation to the qc-backtest-server so we can see exactly where each slot's time goes (pool_wait, lock_wait, push, compile, create_bt, idle, bt_run). All output is DEBUG level on a dedicated `qc::overhead` tracing target routed to a new `qc_overhead.log` daily-rolling file.

**Architecture:** Extend `SessionCounters` with 7 `AtomicU64` phase counters + a `DashMap<String, StrategyCounters>` for per-strategy cycle counts. Every phase boundary records its elapsed ms via `fetch_add`. The existing 60s status tick reads deltas from the previous snapshot and emits one `qc::overhead` debug line. A new log layer in `log_setup.rs` writes only `qc::overhead` events to `qc_overhead.log`; they also land in `qc_full.log` (inherits the generic `debug` filter) but are absent from `qc.log` (INFO-only).

**Tech Stack:** Rust, tokio, tracing, tracing-subscriber, tracing-appender, dashmap, `std::sync::atomic::AtomicU64`.

---

## File Structure

**Modified:**
- `Cargo.toml` — add `dashmap` dependency
- `src/server_mod/mod.rs` — extend `SessionCounters` struct
- `src/log_setup.rs` — add fourth file layer for `qc_overhead.log`
- `src/server_mod/slots.rs` — pass `session` through to the status-loop closure and the runner-launch loop (both already get it; just verify)
- `src/server_mod/status.rs` — snapshot + delta + emit the overhead line
- `src/runner/run_loop.rs` — idle_ms measurement between cycles; record per-cycle strategy overhead
- `src/runner/acquire.rs` — pool_wait_ms measurement
- `src/runner/lock.rs` — lock_wait_ms measurement
- `src/runner/backtest.rs` — push/compile/create_bt/bt_run increments

**Created:**
- `src/server_mod/overhead.rs` — new module: `StrategyCounters`, `OverheadSnapshot`, helpers

No test files — this codebase has no existing test harness for the runner pipeline (the instrumentation is a pure observability layer). Validation is by building, running, and reading the new log.

---

## Task 1: Add `dashmap` dependency

**Files:**
- Modify: `Cargo.toml`

- [ ] **Step 1: Check current dependency list**

Run: `grep -A 1 '^\[dependencies\]' /home/bwg/qc_work/Cargo.toml | head -20`

Expected: shows `[dependencies]` header.

- [ ] **Step 2: Add `dashmap` under `[dependencies]`**

Find the `[dependencies]` block. Add this line (sort alphabetically among peers, or append if alphabetical order is not maintained):

```toml
dashmap = "6"
```

- [ ] **Step 3: Verify it resolves**

Run: `cd /home/bwg/qc_work && cargo check 2>&1 | tail -5`

Expected: `Checking qc-backtest-server` … `Finished` (no errors). If `dashmap` is already a transitive dep of another crate and this fails with version conflict, use the version already in `Cargo.lock`:
```bash
grep -A 1 '^name = "dashmap"' /home/bwg/qc_work/Cargo.lock | head -2
```
and pin to that major version instead.

- [ ] **Step 4: Commit**

```bash
cd /home/bwg/qc_work
git add Cargo.toml Cargo.lock
git commit -m "chore: add dashmap dependency for per-strategy overhead counters"
```

---

## Task 2: Create `src/server_mod/overhead.rs` with per-strategy counter type

**Files:**
- Create: `src/server_mod/overhead.rs`
- Modify: `src/server_mod/mod.rs` (declare module)

- [ ] **Step 1: Create the file**

Create `/home/bwg/qc_work/src/server_mod/overhead.rs` with exactly this content:

```rust
//! Per-phase and per-strategy overhead counters.
//!
//! All times are tracked in milliseconds via `AtomicU64::fetch_add`.
//! The status loop reads these counters every 60s, diffs them against
//! the previous snapshot, and emits a DEBUG line on the `qc::overhead`
//! target.

use std::sync::atomic::{AtomicU64, Ordering};

use dashmap::DashMap;

/// Per-strategy cycle and overhead totals.
///
/// `cycles` counts completed slot cycles for that strategy.
/// `overhead_ms` is the summed overhead (excluding bt_run) across those cycles.
#[derive(Default, Debug)]
pub struct StrategyCounters {
    pub cycles: AtomicU64,
    pub overhead_ms: AtomicU64,
}

impl StrategyCounters {
    pub fn record(&self, overhead_ms: u64) {
        self.cycles.fetch_add(1, Ordering::SeqCst);
        self.overhead_ms.fetch_add(overhead_ms, Ordering::SeqCst);
    }
}

/// Snapshot of all overhead counters at a single instant. Used by the
/// status loop to compute deltas between ticks.
#[derive(Default, Debug, Clone)]
pub struct OverheadSnapshot {
    pub pool_wait_ms: u64,
    pub lock_wait_ms: u64,
    pub push_ms: u64,
    pub compile_ms: u64,
    pub create_bt_ms: u64,
    pub idle_ms: u64,
    pub bt_run_ms: u64,
    pub per_strategy: Vec<(String, u64, u64)>,  // (name, cycles, overhead_ms)
}

/// Build a fresh snapshot from the live counters (caller owns the
/// reference; this function does not mutate).
pub fn snapshot(
    pool_wait: &AtomicU64,
    lock_wait: &AtomicU64,
    push: &AtomicU64,
    compile: &AtomicU64,
    create_bt: &AtomicU64,
    idle: &AtomicU64,
    bt_run: &AtomicU64,
    per_strategy: &DashMap<String, StrategyCounters>,
) -> OverheadSnapshot {
    let mut rows: Vec<(String, u64, u64)> = per_strategy
        .iter()
        .map(|e| {
            (
                e.key().clone(),
                e.value().cycles.load(Ordering::SeqCst),
                e.value().overhead_ms.load(Ordering::SeqCst),
            )
        })
        .collect();
    rows.sort_by(|a, b| a.0.cmp(&b.0));
    OverheadSnapshot {
        pool_wait_ms: pool_wait.load(Ordering::SeqCst),
        lock_wait_ms: lock_wait.load(Ordering::SeqCst),
        push_ms: push.load(Ordering::SeqCst),
        compile_ms: compile.load(Ordering::SeqCst),
        create_bt_ms: create_bt.load(Ordering::SeqCst),
        idle_ms: idle.load(Ordering::SeqCst),
        bt_run_ms: bt_run.load(Ordering::SeqCst),
        per_strategy: rows,
    }
}

/// Diff two snapshots and emit a single debug log on `qc::overhead`.
///
/// `num_slots` and `wall_secs` are used to show utilization ratios.
pub fn emit_delta(
    prev: &OverheadSnapshot,
    curr: &OverheadSnapshot,
    num_slots: usize,
    wall_secs: u64,
) {
    let pool = curr.pool_wait_ms.saturating_sub(prev.pool_wait_ms);
    let lock = curr.lock_wait_ms.saturating_sub(prev.lock_wait_ms);
    let push = curr.push_ms.saturating_sub(prev.push_ms);
    let compile = curr.compile_ms.saturating_sub(prev.compile_ms);
    let create = curr.create_bt_ms.saturating_sub(prev.create_bt_ms);
    let idle = curr.idle_ms.saturating_sub(prev.idle_ms);
    let bt_run = curr.bt_run_ms.saturating_sub(prev.bt_run_ms);

    let overhead_total = pool + lock + push + compile + create + idle;
    let pct = |part: u64| -> f64 {
        if overhead_total == 0 {
            0.0
        } else {
            (part as f64) * 100.0 / (overhead_total as f64)
        }
    };

    // Per-strategy block: pair prev/curr by name, only emit rows with cycles > 0 delta
    let mut per_strat_lines: Vec<String> = Vec::new();
    let mut total_cycles: u64 = 0;
    for (name, cycles_now, oh_now) in &curr.per_strategy {
        let (cycles_prev, oh_prev) = prev
            .per_strategy
            .iter()
            .find(|(n, _, _)| n == name)
            .map(|(_, c, o)| (*c, *o))
            .unwrap_or((0, 0));
        let d_cycles = cycles_now.saturating_sub(cycles_prev);
        if d_cycles == 0 {
            continue;
        }
        total_cycles += d_cycles;
        let d_oh = oh_now.saturating_sub(oh_prev);
        let avg_ms = (d_oh as f64) / (d_cycles as f64);
        per_strat_lines.push(format!(
            "{name}: cycles={d_cycles} overhead={:.1}s avg={:.2}s/cycle",
            d_oh as f64 / 1000.0,
            avg_ms / 1000.0
        ));
    }

    let slot_wall_ms = (wall_secs as u128) * (num_slots as u128) * 1000;
    let overhead_of_wall_pct = if slot_wall_ms == 0 {
        0.0
    } else {
        (overhead_total as f64) * 100.0 / (slot_wall_ms as f64)
    };

    tracing::debug!(
        target: "qc::overhead",
        "overhead summary (last {wall_secs}s, {num_slots} slots, wall={}s):\n  \
         {}\n  \
         total: cycles={total_cycles} overhead={:.1}s ({:.1}% of slot-wall)\n\
         phase breakdown:\n  \
         push={:.1}s({:.1}%)  compile={:.1}s({:.1}%)  create_bt={:.1}s({:.1}%)\n  \
         pool_wait={:.1}s({:.1}%)  lock_wait={:.1}s({:.1}%)  idle={:.1}s({:.1}%)\n  \
         bt_run={:.1}s  (product — not overhead)",
        wall_secs * (num_slots as u64),
        per_strat_lines.join("\n  "),
        overhead_total as f64 / 1000.0,
        overhead_of_wall_pct,
        push as f64 / 1000.0,
        pct(push),
        compile as f64 / 1000.0,
        pct(compile),
        create as f64 / 1000.0,
        pct(create),
        pool as f64 / 1000.0,
        pct(pool),
        lock as f64 / 1000.0,
        pct(lock),
        idle as f64 / 1000.0,
        pct(idle),
        bt_run as f64 / 1000.0,
    );
}
```

- [ ] **Step 2: Declare the module in `server_mod/mod.rs`**

Open `/home/bwg/qc_work/src/server_mod/mod.rs`. Find the module declarations near the top (currently ending with `pub(crate) mod status_query;`). Add:

```rust
pub mod overhead;
```

immediately after `pub(crate) mod status_query;`. Save.

- [ ] **Step 3: Verify it compiles**

Run: `cd /home/bwg/qc_work && cargo check 2>&1 | tail -5`

Expected: `Finished` with no errors. `StrategyCounters` and `OverheadSnapshot` will be unused warnings — fine, we wire them up in the next task.

- [ ] **Step 4: Commit**

```bash
cd /home/bwg/qc_work
git add src/server_mod/overhead.rs src/server_mod/mod.rs
git commit -m "feat(infra): add StrategyCounters + OverheadSnapshot module"
```

---

## Task 3: Extend `SessionCounters` with phase atomics

**Files:**
- Modify: `src/server_mod/mod.rs:23-26`

- [ ] **Step 1: Replace the `SessionCounters` struct**

Open `/home/bwg/qc_work/src/server_mod/mod.rs`. Find:

```rust
/// Shared session counters for the status report.
#[derive(Default)]
pub struct SessionCounters {
    pub completed: AtomicU64,
    pub failed: AtomicU64,
}
```

Replace with:

```rust
/// Shared session counters for the status report.
///
/// Phase counters are all in **milliseconds**. Every slot cycle
/// `fetch_add`s the measured elapsed time into the appropriate field.
/// The status loop reads them every 60s and emits a `qc::overhead`
/// debug line with deltas.
#[derive(Default)]
pub struct SessionCounters {
    pub completed: AtomicU64,
    pub failed: AtomicU64,

    // Overhead phases (controllable by infra).
    pub pool_wait_ms: AtomicU64,
    pub lock_wait_ms: AtomicU64,
    pub push_ms: AtomicU64,
    pub compile_ms: AtomicU64,
    pub create_bt_ms: AtomicU64,
    pub idle_ms: AtomicU64,

    // Product phase (logged but excluded from overhead totals).
    pub bt_run_ms: AtomicU64,

    // Per-strategy cycle + overhead tallies.
    pub per_strategy: dashmap::DashMap<String, overhead::StrategyCounters>,
}
```

- [ ] **Step 2: Verify the module path compiles**

The struct references `overhead::StrategyCounters`. Since `pub mod overhead;` is declared in the same module, this works. Run:

```bash
cd /home/bwg/qc_work && cargo check 2>&1 | tail -5
```

Expected: `Finished` with warnings about unused fields (they're wired up in later tasks).

- [ ] **Step 3: Commit**

```bash
cd /home/bwg/qc_work
git add src/server_mod/mod.rs
git commit -m "feat(infra): extend SessionCounters with phase ms atomics + per-strategy map"
```

---

## Task 4: Instrument `pool_wait_ms` in `acquire_job`

**Files:**
- Modify: `src/runner/acquire.rs`

- [ ] **Step 1: Record entry time at top of `acquire_job`**

Open `/home/bwg/qc_work/src/runner/acquire.rs`. Find line 13-16:

```rust
    pub(crate) async fn acquire_job(
        &mut self,
        backoff: &Duration,
    ) -> Option<(QueueJob, Db, i64, bool, Option<String>)> {
        if let Some(ref pool) = self.warm_pool {
```

Insert a new first line inside the function body (between the `{` and the `if let Some(ref pool)`):

```rust
    pub(crate) async fn acquire_job(
        &mut self,
        backoff: &Duration,
    ) -> Option<(QueueJob, Db, i64, bool, Option<String>)> {
        let acquire_start = Instant::now();
        if let Some(ref pool) = self.warm_pool {
```

- [ ] **Step 2: Add a helper closure to record the elapsed time**

Immediately after `let acquire_start = Instant::now();`, add:

```rust
        let record_wait = |session: &Option<std::sync::Arc<crate::server::SessionCounters>>| {
            if let Some(s) = session {
                let ms = acquire_start.elapsed().as_millis() as u64;
                s.pool_wait_ms
                    .fetch_add(ms, std::sync::atomic::Ordering::SeqCst);
            }
        };
```

- [ ] **Step 3: Call `record_wait` at every successful return point inside the function**

There are three `return Some((we.job, we.db, we.project_id, true, Some(cid)));` sites plus the pick_next path. Before each `return Some(...)` or the `match picked { Some((j, d, p)) => Some((j, d, p, false, None)), ... }` block, call `record_wait(&self.session);`.

Specifically, modify each of these three return statements (currently at lines 37, 78, and the match-arm near line 97) by inserting `record_wait(&self.session);` on the line immediately before. For the final match arm, convert:

```rust
        match picked {
            Some((j, d, p)) => Some((j, d, p, false, None)),
            None => {
                tracing::info!(
                    "slot-{}: IDLE — pick_next returned None, backing off {}s",
                    self.slot_id,
                    backoff.as_secs()
                );
                sleep(*backoff).await;
                None
            }
        }
```

into:

```rust
        match picked {
            Some((j, d, p)) => {
                record_wait(&self.session);
                Some((j, d, p, false, None))
            }
            None => {
                tracing::info!(
                    "slot-{}: IDLE — pick_next returned None, backing off {}s",
                    self.slot_id,
                    backoff.as_secs()
                );
                sleep(*backoff).await;
                None
            }
        }
```

For the return at `return Some((we.job, we.db, we.project_id, true, Some(cid)));` (appears twice — once at line ~37, once at line ~78), change each to:

```rust
                let cid = we.compile_id.clone();
                record_wait(&self.session);
                return Some((we.job, we.db, we.project_id, true, Some(cid)));
```

**Do not call `record_wait` on the two `None` (idle) return paths** — idle time is tracked separately via the run_loop idle_ms counter, not as pool_wait.

- [ ] **Step 4: Verify it compiles**

```bash
cd /home/bwg/qc_work && cargo check 2>&1 | tail -5
```

Expected: `Finished`. If an `Instant` import is missing, add `use std::time::Instant;` — the file already has it on line 3.

- [ ] **Step 5: Commit**

```bash
cd /home/bwg/qc_work
git add src/runner/acquire.rs
git commit -m "feat(infra): instrument pool_wait_ms in acquire_job"
```

---

## Task 5: Instrument `lock_wait_ms` in `lock_project`

**Files:**
- Modify: `src/runner/lock.rs`

- [ ] **Step 1: Read the full function to locate exit points**

```bash
cd /home/bwg/qc_work && wc -l src/runner/lock.rs
```

The function `lock_project` spans from line 12 to the end of the file (it's the only function). It has multiple return points: the `skip_if_prewarmed` early return (line ~22), the happy path at line ~35, and alternative-project paths (lines ~50+).

- [ ] **Step 2: Wrap the function body with a timing guard**

Open `/home/bwg/qc_work/src/runner/lock.rs`. Find line 8-24:

```rust
impl SlotRunner {
    /// Lock a project for exclusive code push.
    /// For pre-warmed jobs, the project is already locked.
    /// Returns the locked project_id, or None if all projects are locked.
    pub(crate) async fn lock_project(
        &self,
        project_id: i64,
        skip_if_prewarmed: bool,
        strategy: &str,
        job_name: &str,
        job: &QueueJob,
        db: &Db,
    ) -> Option<i64> {
        if skip_if_prewarmed {
            return Some(project_id);
        }
```

Change the start of the body to:

```rust
    ) -> Option<i64> {
        let lock_start = std::time::Instant::now();
        let record_lock = |session: &Option<std::sync::Arc<crate::server::SessionCounters>>| {
            if let Some(s) = session {
                let ms = lock_start.elapsed().as_millis() as u64;
                s.lock_wait_ms
                    .fetch_add(ms, std::sync::atomic::Ordering::SeqCst);
            }
        };
        if skip_if_prewarmed {
            // pre-warmed path has zero lock wait — still record 0 for consistency
            record_lock(&self.session);
            return Some(project_id);
        }
```

- [ ] **Step 3: Call `record_lock` at every `return Some(...)` exit**

In `lock_project`, every time the function returns `Some(pid)` (the happy path at line ~35, and any alternative-project success paths), insert `record_lock(&self.session);` on the line immediately before the return.

Specifically, at the line currently reading `return Some(project_id);` (there's one at ~line 35 after `tracing::debug!(... "locked project ...")`), change to:

```rust
            record_lock(&self.session);
            return Some(project_id);
```

And at any alternative-project return (e.g. `return Some(*pid);` later in the file — search with `grep -n 'return Some' src/runner/lock.rs`), prefix with the same call.

Do **not** add `record_lock` on `None` returns (we only measure time to successful lock).

- [ ] **Step 4: Verify every successful return has record_lock**

```bash
cd /home/bwg/qc_work && grep -n "return Some\|record_lock" src/runner/lock.rs
```

Every `return Some(...)` line should be immediately preceded by a `record_lock(&self.session);` line.

- [ ] **Step 5: Compile check**

```bash
cd /home/bwg/qc_work && cargo check 2>&1 | tail -5
```

Expected: `Finished`.

- [ ] **Step 6: Commit**

```bash
cd /home/bwg/qc_work
git add src/runner/lock.rs
git commit -m "feat(infra): instrument lock_wait_ms in lock_project"
```

---

## Task 6: Instrument `push_ms`, `compile_ms`, `create_bt_ms`, `bt_run_ms` in `run_backtest`

**Files:**
- Modify: `src/runner/backtest.rs`

- [ ] **Step 1: Locate the variables that already hold the timings**

Read `/home/bwg/qc_work/src/runner/backtest.rs`. The function `run_backtest` already computes:
- `compile_phase_dur` (Duration) — the `compile_ms` to record
- `push_start` → `compile_start` — delta is `push_secs` (f64 seconds)
- `bt_create_start.elapsed()` — the `create_bt_ms`
- `bt_phase_secs` — the `bt_run_ms`

These are currently logged only and then returned. We need to push them into `SessionCounters` as well.

- [ ] **Step 2: Add the increments right before the function returns**

Find this block near the end of `run_backtest` (around line 86-94):

```rust
        let compile_secs = compile_phase_dur.as_secs_f64();
        let cloud_time = compile_secs + bt_phase_secs;
        let push_secs = compile_start.duration_since(push_start).as_secs_f64();
        let create_bt_secs = bt_create_start.elapsed().as_secs_f64();

        tracing::debug!(
            "slot-{slot}: [{job_name}] complete — cloud={cloud_time:.1}s \
             compile={compile_secs:.1}s bt={bt_phase_secs:.1}s polls={poll_count}"
        );

        Ok((
```

Insert, between the `tracing::debug!` and `Ok((`, this block:

```rust

        // Record phase timings into session counters (ms).
        if let Some(s) = &self.session {
            use std::sync::atomic::Ordering;
            s.push_ms.fetch_add(
                (push_secs * 1000.0) as u64,
                Ordering::SeqCst,
            );
            s.compile_ms.fetch_add(
                (compile_secs * 1000.0) as u64,
                Ordering::SeqCst,
            );
            s.create_bt_ms.fetch_add(
                (create_bt_secs * 1000.0) as u64,
                Ordering::SeqCst,
            );
            s.bt_run_ms.fetch_add(
                (bt_phase_secs * 1000.0) as u64,
                Ordering::SeqCst,
            );
        }

```

- [ ] **Step 3: Verify it compiles**

```bash
cd /home/bwg/qc_work && cargo check 2>&1 | tail -5
```

Expected: `Finished`.

- [ ] **Step 4: Commit**

```bash
cd /home/bwg/qc_work
git add src/runner/backtest.rs
git commit -m "feat(infra): instrument push/compile/create_bt/bt_run ms in run_backtest"
```

---

## Task 7: Instrument `idle_ms` in `run_loop` + record per-strategy cycles

**Files:**
- Modify: `src/runner/run_loop.rs`

- [ ] **Step 1: Replace the function body to track idle time and per-strategy overhead**

Open `/home/bwg/qc_work/src/runner/run_loop.rs`. Replace the entire `run` function (lines 15-135) with:

```rust
    /// Main loop: pick job → lock project → run backtest → collect → unlock.
    pub async fn run(mut self) {
        let backoff = Duration::from_secs(1);
        let poll_interval = Duration::from_millis(1500);
        let compile_poll = Duration::from_secs(1);
        let compile_timeout = Duration::from_secs(60);
        let backtest_timeout = Duration::from_secs(900);

        // Stagger slot startup to avoid thundering herd on API
        tokio::time::sleep(
            Duration::from_millis(self.slot_id as u64 * 300),
        )
        .await;
        tracing::debug!("slot-{}: started", self.slot_id);

        // Instant at which the previous cycle *ended* (i.e. became ready to
        // start the next one). First cycle has no previous end, so idle_ms
        // is not recorded.
        let mut prev_cycle_end: Option<Instant> = None;

        loop {
            let cycle_start = Instant::now();

            // Record idle time: the gap between previous cycle end and this
            // cycle start. Zero for the first iteration.
            if let Some(end) = prev_cycle_end {
                let idle_ms = cycle_start.duration_since(end).as_millis() as u64;
                if let Some(s) = &self.session {
                    s.idle_ms.fetch_add(
                        idle_ms,
                        std::sync::atomic::Ordering::SeqCst,
                    );
                }
            }

            // Counters snapshot at cycle start so we can compute per-cycle
            // overhead (excluding bt_run) for the per-strategy record.
            let phase_snapshot_at_start = self.session.as_ref().map(|s| {
                use std::sync::atomic::Ordering;
                (
                    s.pool_wait_ms.load(Ordering::SeqCst),
                    s.lock_wait_ms.load(Ordering::SeqCst),
                    s.push_ms.load(Ordering::SeqCst),
                    s.compile_ms.load(Ordering::SeqCst),
                    s.create_bt_ms.load(Ordering::SeqCst),
                )
            });

            // ── PHASE 1: Acquire a job ──
            let (job, db, project_id, skip_push, pre_compile_id) =
                match self.acquire_job(&backoff).await {
                    Some(result) => result,
                    None => {
                        // Idle path — no cycle completed; do not update
                        // prev_cycle_end so next iteration's idle_ms captures
                        // the full back-to-back gap.
                        continue;
                    }
                };

            let pick_ms = cycle_start.elapsed().as_millis();
            let job_name = job.name.clone();
            let strategy = job.strategy.clone();

            // ── PHASE 2: Lock project ──
            let project_id = match self
                .lock_project(
                    project_id,
                    skip_push,
                    &strategy,
                    &job_name,
                    &job,
                    &db,
                )
                .await
            {
                Some(pid) => pid,
                None => continue,
            };

            tracing::debug!(
                "slot-{}: picked {}/{} project={} pre_compiled={}",
                self.slot_id,
                strategy,
                job_name,
                project_id,
                skip_push
            );

            // ── PHASE 3: Run backtest ──
            let start = Instant::now();

            match self
                .run_backtest(
                    &job,
                    &db,
                    project_id,
                    pre_compile_id,
                    compile_poll,
                    compile_timeout,
                    poll_interval,
                    backtest_timeout,
                )
                .await
            {
                Ok((bt_id, bt_resp, cloud_time, ..)) => {
                    let elapsed = start.elapsed().as_secs_f64();

                    // ── PHASE 4: Non-blocking collect ──
                    self.spawn_collect(
                        job.clone(),
                        db.clone(),
                        project_id,
                        bt_id,
                        cloud_time,
                        bt_resp,
                        elapsed,
                        strategy.clone(),
                        job_name.clone(),
                    );
                }
                Err(e) => {
                    self.handle_backtest_error(
                        e,
                        &strategy,
                        &job_name,
                        &job,
                        &db,
                        start.elapsed().as_secs_f64(),
                    )
                    .await;
                }
            }

            // ── PHASE 5: Unlock project ──
            {
                let mut locked = self.project_lock.lock().await;
                locked.remove(&project_id);
                tracing::debug!(
                    "slot-{}: unlocked project {} (locked_count={})",
                    self.slot_id,
                    project_id,
                    locked.len()
                );
            }

            // Compute per-cycle overhead (excluding bt_run) and bump the
            // per-strategy counters.
            if let (Some(s), Some(snap)) = (&self.session, phase_snapshot_at_start) {
                use std::sync::atomic::Ordering;
                let pool_d = s.pool_wait_ms.load(Ordering::SeqCst) - snap.0;
                let lock_d = s.lock_wait_ms.load(Ordering::SeqCst) - snap.1;
                let push_d = s.push_ms.load(Ordering::SeqCst) - snap.2;
                let comp_d = s.compile_ms.load(Ordering::SeqCst) - snap.3;
                let cbt_d = s.create_bt_ms.load(Ordering::SeqCst) - snap.4;
                let cycle_overhead_ms = pool_d + lock_d + push_d + comp_d + cbt_d;
                let entry = s
                    .per_strategy
                    .entry(strategy.clone())
                    .or_default();
                entry.record(cycle_overhead_ms);
            }

            let cycle_ms = cycle_start.elapsed().as_millis();
            tracing::debug!(
                "slot-{}: cycle done {}ms (pick={}ms) {}/{}",
                self.slot_id,
                cycle_ms,
                pick_ms,
                strategy,
                job_name
            );

            prev_cycle_end = Some(Instant::now());
        }
    }
```

- [ ] **Step 2: Verify compile**

```bash
cd /home/bwg/qc_work && cargo check 2>&1 | tail -5
```

Expected: `Finished` with possible unused-variable warnings resolved. If `AtomicU64` imports are missing, the uses of `Ordering::SeqCst` will fail — the blocks above use fully-qualified `std::sync::atomic::Ordering`, so no import is needed.

- [ ] **Step 3: Commit**

```bash
cd /home/bwg/qc_work
git add src/runner/run_loop.rs
git commit -m "feat(infra): instrument idle_ms + per-strategy cycle overhead in run_loop"
```

---

## Task 8: Add `qc_overhead.log` file layer in `log_setup.rs`

**Files:**
- Modify: `src/log_setup.rs`

- [ ] **Step 1: Insert the overhead file layer**

Open `/home/bwg/qc_work/src/log_setup.rs`. Find the block that creates the `slots_layer` (currently lines 125-153, starting at `// ── {name}_slots.log: ...`). Immediately **after** the `let slots_layer = ...;` block (before `// ── Console:` at line 155), add:

```rust
    // ── {name}_overhead.log: dedicated per-phase overhead breakdown ──
    // Only `qc::overhead` target events land here (debug level). They also
    // land in {name}_full.log via the generic debug filter, but are absent
    // from {name}.log (INFO-only).
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
            EnvFilter::new("off")
                .add_directive("qc::overhead=debug".parse().unwrap()),
        )
        .boxed();
```

- [ ] **Step 2: Register the new layer in the subscriber chain**

Find (currently near the bottom):

```rust
    tracing_subscriber::registry()
        .with(console_layer)
        .with(info_layer)
        .with(debug_layer)
        .with(trace_layer)
        .with(slots_layer)
        .init();
```

Change to:

```rust
    tracing_subscriber::registry()
        .with(console_layer)
        .with(info_layer)
        .with(debug_layer)
        .with(trace_layer)
        .with(slots_layer)
        .with(overhead_layer)
        .init();
```

- [ ] **Step 3: Compile check**

```bash
cd /home/bwg/qc_work && cargo check 2>&1 | tail -5
```

Expected: `Finished`.

- [ ] **Step 4: Commit**

```bash
cd /home/bwg/qc_work
git add src/log_setup.rs
git commit -m "feat(infra): add qc_overhead.log file layer for qc::overhead target"
```

---

## Task 9: Emit overhead delta from `log_status`

**Files:**
- Modify: `src/server_mod/slots.rs`
- Modify: `src/server_mod/status.rs`

- [ ] **Step 1: Pass the full `session` Arc to `log_status` instead of reading only `completed`/`failed` in the caller**

Open `/home/bwg/qc_work/src/server_mod/slots.rs`. Find the status loop (around lines 93-120 — the block starting with `let status_handle = tokio::spawn(async move {`). Inside, locate the call site of `log_status(...)`. Currently it passes `completed` and `failed` as `u64`. We need to also pass the `Arc<SessionCounters>` (already available via the `status_session` clone) and the chosen `wall_secs = 60`.

Replace the call to `log_status(` with one that passes the extra args. Specifically, find:

```rust
            log_status(
                &status_dbs,
                uptime,
                rl_delay,
                completed,
                failed,
```

Add a new argument after `failed` on a new line:

```rust
            log_status(
                &status_dbs,
                uptime,
                rl_delay,
                completed,
                failed,
                Arc::clone(&status_session),
```

Keep the remaining args unchanged. If the closing `).await;` is on a later line, it stays as-is; we've only added one parameter.

- [ ] **Step 2: Update `log_status` signature in `status.rs`**

Open `/home/bwg/qc_work/src/server_mod/status.rs`. Change the signature (currently lines 16-27) from:

```rust
#[allow(clippy::too_many_arguments)]
pub(crate) async fn log_status(
    dbs: &[Db],
    uptime_secs: u64,
    _rl_delay_ms: u64,
    session_completed: u64,
    session_failed: u64,
    num_slots: usize,
    client: &Arc<QcClient>,
    project_id: i64,
) {
```

to:

```rust
#[allow(clippy::too_many_arguments)]
pub(crate) async fn log_status(
    dbs: &[Db],
    uptime_secs: u64,
    _rl_delay_ms: u64,
    session_completed: u64,
    session_failed: u64,
    session: Arc<super::SessionCounters>,
    num_slots: usize,
    client: &Arc<QcClient>,
    project_id: i64,
) {
```

- [ ] **Step 3: Add a module-private snapshot cache and emit delta**

At the top of `status.rs`, below the `use` statements, add a `static` to hold the previous snapshot:

```rust
use std::sync::Mutex;

use super::overhead::{emit_delta, snapshot, OverheadSnapshot};

static PREV_OVERHEAD: Mutex<Option<OverheadSnapshot>> = Mutex::new(None);
```

At the **end** of the `log_status` function body (right before the closing `}` — after `tracing::info!("{report}");`), add:

```rust
    // ── Emit overhead delta on qc::overhead target (debug) ──
    {
        let curr = snapshot(
            &session.pool_wait_ms,
            &session.lock_wait_ms,
            &session.push_ms,
            &session.compile_ms,
            &session.create_bt_ms,
            &session.idle_ms,
            &session.bt_run_ms,
            &session.per_strategy,
        );
        let mut prev_guard = PREV_OVERHEAD.lock().unwrap();
        let prev = prev_guard.clone().unwrap_or_default();
        emit_delta(&prev, &curr, num_slots, 60);
        *prev_guard = Some(curr);
    }
```

- [ ] **Step 4: Verify compile**

```bash
cd /home/bwg/qc_work && cargo check 2>&1 | tail -5
```

Expected: `Finished`. If `Arc` is missing in `status.rs`, it's already used via `use std::sync::Arc;` on line 7.

- [ ] **Step 5: Commit**

```bash
cd /home/bwg/qc_work
git add src/server_mod/status.rs src/server_mod/slots.rs
git commit -m "feat(infra): emit qc::overhead delta every status tick"
```

---

## Task 10: Full build + smoke test

**Files:** None (validation only)

- [ ] **Step 1: Full release build**

```bash
cd /home/bwg/qc_work && cargo build --release 2>&1 | tail -5
```

Expected: `Finished release` with no errors. Warnings acceptable.

- [ ] **Step 2: Run `cargo clippy`**

```bash
cd /home/bwg/qc_work && cargo clippy --release 2>&1 | tail -20
```

Expected: no new errors introduced by these changes. Pre-existing warnings are fine.

- [ ] **Step 3: Start the server (user-driven)**

The server is a long-running process. Rather than starting it in this plan step, confirm the binary was rebuilt:

```bash
ls -lh /home/bwg/qc_work/target/release/qc-backtest-server
```

Expected: binary exists, mtime is recent.

**User action:** restart the running server with the new binary using the existing process:

```bash
ls /home/bwg/qc_work/qc-server.pid && echo "server running — restart required"
```

The normal server start flow (from `USAGE.md`) will pick up the new binary and the new log file will appear after the first 60s tick.

- [ ] **Step 4: Verify the new log file appears**

After restart, wait ~90s, then:

```bash
ls -lh /home/bwg/qc_work/logs/ | grep overhead
```

Expected: `qc_overhead.log.<YYYY-MM-DD>` exists.

- [ ] **Step 5: Verify content of the new log**

```bash
tail -40 /home/bwg/qc_work/logs/qc_overhead.log.*
```

Expected: at least one `overhead summary (last 60s, 10 slots, ...)` block with per-strategy rows and phase breakdown. Numbers are non-negative; `total overhead < 600s * num_slots`; `bt_run` shown but excluded from overhead.

- [ ] **Step 6: Sanity check — overhead + bt_run + idle ≈ wall × slots**

For the first tick after steady state, grab the numbers and confirm:

```
overhead_total + bt_run + (unaccounted) ≈ 60s × num_slots
```

The "unaccounted" gap should be <5%. If larger, one of the phase-increment sites is missing an emission path — inspect.

- [ ] **Step 7: Verify `qc.log` (INFO) is unchanged in format**

```bash
tail -10 /home/bwg/qc_work/logs/qc.log.*
```

Expected: still the familiar status boxes, no `qc::overhead` lines (target-filtered out).

- [ ] **Step 8: Verify `qc_full.log` contains the overhead lines too**

```bash
grep "qc::overhead" /home/bwg/qc_work/logs/qc_full.log.* | tail -5
```

Expected: at least one match per minute after the first tick.

- [ ] **Step 9: Commit the verification log (optional — for archive)**

No source changes in this step. No commit needed unless you captured a sample log file.

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| 7 phase counters (pool_wait, lock_wait, push, compile, create_bt, idle, bt_run) | Tasks 3, 4, 5, 6, 7 |
| Per-strategy `DashMap<String, StrategyCounters>` | Tasks 1, 2, 3, 7 |
| `qc_overhead.log` new file layer, DEBUG, whitelist `qc::overhead` target | Task 8 |
| INFO log (`qc.log`) unchanged | Task 8 (layer filter), Task 10 step 7 verifies |
| 60s status tick emits one debug block with deltas | Task 9 |
| Per-cycle strategy overhead (cycles + overhead_ms) bumped atomically at cycle end | Task 7 |
| Success criteria 1-4 (builds, starts, per-strategy populated, phase sum ≈ wall × slots) | Task 10 steps 1, 4, 5, 6 |

All spec sections have a concrete task.

**Type/name consistency:** `StrategyCounters` is defined in Task 2 and referenced by fully-qualified path `overhead::StrategyCounters` in Task 3's struct and in Task 7's `entry().or_default()`. `OverheadSnapshot`, `snapshot()`, `emit_delta()` names are consistent between Tasks 2 and 9. The tracing target `qc::overhead` is used in Tasks 2, 8, 9, and 10 consistently.

**No placeholders:** every code block shows the actual code; every command shows the exact invocation; no "TBD" / "implement later" present.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-20-infra-overhead-instrumentation.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
