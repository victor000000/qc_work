# Pipelined slots implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor slot loop so it releases the project lock immediately after `create_backtest` succeeds and spawns `poll_and_collect` as an async task, lifting steady-state throughput from 11.3 bt/m to ≥18 bt/m.

**Architecture:** Split today's `run_backtest` into `prep_backtest` (push+compile+create, holds lock) and `poll_and_collect` (poll+collect, no lock; tokio-spawned). Introduce `active_collects` counter managed via RAII guard for backpressure. Add adaptive tiered polling + dedicated `qc_pipeline.log` for visibility.

**Tech Stack:** Rust + tokio + tracing-appender (existing). Codebase has no test harness — verification is manual via `cargo check`, `cargo clippy --all-targets --all-features -- -D warnings`, `cargo build --release`, and log inspection during live runs.

**Spec:** `docs/superpowers/specs/2026-04-20-pipelined-slots-design.md`

---

## File Structure

| File | Role | Change |
|---|---|---|
| `src/log_setup.rs` | Tracing layer registration | Add `qc_pipeline.log` layer filtered to `qc::pipeline` target |
| `src/server_mod/mod.rs` | `SessionCounters` struct | Add `active_collects: AtomicI64`; split `create_bt_ms` into `create_api_ms` + `poll_tail_ms` |
| `src/server_mod/overhead.rs` | Overhead counters + snapshot | Replace `create_bt_ms` field with two fields in `OverheadSnapshot`, `SnapshotSources`, `snapshot`, `emit_delta` |
| `src/server_mod/status.rs` | Status tick | Use new counter fields; display `active_collects` in status tick |
| `src/runner/backtest.rs` | Entry-phase orchestrator | Rename `run_backtest` → `prep_backtest`; strip poll+collect; return `(backtest_id, project_id, create_api_secs)`; fix measurement bug |
| `src/runner/pipeline.rs` | **NEW** — async poll+collect | Define `PollCollectCtx`, `ActiveCollectsGuard`, `poll_and_collect()`; emit `qc::pipeline` debug events |
| `src/runner/poll.rs` | Polling loop | Replace fixed 1.5s with tiered delay function; progress-aware tighten; per-task 429 elasticity |
| `src/runner/run_loop.rs` | Main slot loop | Call `prep_backtest`; unlock project; spawn `poll_and_collect`; backpressure check on re-acquire |
| `src/runner/errors.rs` | (existing) `spawn_collect` | Delete or deprecate — replaced by `pipeline::poll_and_collect` |
| `src/runner/mod.rs` | Module exports | Add `pub mod pipeline;` |

---

## Task 1: Add `qc_pipeline.log` layer

**Files:**
- Modify: `src/log_setup.rs` (add layer block + register)

- [ ] **Step 1: Read the current log_setup.rs to confirm location of overhead_layer block**

Run: `grep -n "overhead_layer\|overhead_file\|registry" /home/bwg/qc_work/src/log_setup.rs`

Expected: overhead_layer defined around line 163-176, registered around line 195-197.

- [ ] **Step 2: Add `qc_pipeline.log` layer after the overhead_layer block**

Edit `src/log_setup.rs`. After the existing `let overhead_layer = ...` block (before the `// ── Console` block), add:

```rust
    // ── {name}_pipeline.log: per-slot pipeline event stream ────
    // Slot and collect-task lifecycle events on `qc::pipeline` target.
    // Used to reconstruct pipelined slot trajectories offline.
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

- [ ] **Step 3: Register pipeline_layer in the `.with(...)` chain**

In the `tracing_subscriber::registry()` chain, after `.with(overhead_layer)`, add `.with(pipeline_layer)`:

```rust
    tracing_subscriber::registry()
        .with(console_layer)
        .with(info_layer)
        .with(debug_layer)
        .with(trace_layer)
        .with(slots_layer)
        .with(overhead_layer)
        .with(pipeline_layer)
        .init();
```

- [ ] **Step 4: Verify compile**

Run: `cd /home/bwg/qc_work && cargo check --lib 2>&1 | tail -3`

Expected: `Finished ...` no errors.

- [ ] **Step 5: Commit**

```bash
cd /home/bwg/qc_work
git add src/log_setup.rs
git commit -m "feat(logs): add qc_pipeline.log layer filtered to qc::pipeline target

Prepares dedicated debug log file for the upcoming slot pipeline refactor.
Mirrors the qc_overhead.log pattern; will be populated by events on the
qc::pipeline target once pipeline.rs lands in Task 4."
```

---

## Task 2: Split `create_bt_ms` → `create_api_ms` + `poll_tail_ms` (ALL callers in one commit)

**Atomicity requirement:** This task must leave the crate compilable. Do all edits BEFORE the final `cargo check`, then commit once.

**Files:**
- Modify: `src/server_mod/mod.rs` (SessionCounters struct)
- Modify: `src/server_mod/overhead.rs` (OverheadSnapshot, SnapshotSources, snapshot, emit_delta)
- Modify: `src/runner/backtest.rs` (line ~103-124 — the old counter bump + tuple return)
- Modify: `src/runner/run_loop.rs` (phase_snapshot_at_start read + per-strategy overhead delta)
- Modify: `src/server_mod/status.rs` (SnapshotSources construction)

- [ ] **Step 1: Locate the current create_bt_ms field in SessionCounters**

Run: `grep -n "create_bt_ms\|pub create_bt" /home/bwg/qc_work/src/server_mod/mod.rs`

Expected: one field declaration inside `pub struct SessionCounters`.

- [ ] **Step 2: Replace create_bt_ms with two new fields in SessionCounters**

In `src/server_mod/mod.rs`, find the line:
```rust
    pub create_bt_ms: AtomicU64,
```
and replace with:
```rust
    pub create_api_ms: AtomicU64,   // JUST the create_backtest API call
    pub poll_tail_ms: AtomicU64,    // poll + collect duration (post create)
```

Also add `pub active_collects: AtomicI64,` to the same struct (initialized to 0 — need `std::sync::atomic::AtomicI64` import at top if absent). Initialize in `SessionCounters::default()` or `::new()` to `AtomicI64::new(0)`.

- [ ] **Step 3: Update OverheadSnapshot in overhead.rs**

Edit `src/server_mod/overhead.rs`. Replace in `OverheadSnapshot`:
```rust
    pub create_bt_ms: u64,
```
with:
```rust
    pub create_api_ms: u64,
    pub poll_tail_ms: u64,
```

- [ ] **Step 4: Update SnapshotSources**

Replace in `SnapshotSources<'a>`:
```rust
    pub create_bt: &'a AtomicU64,
```
with:
```rust
    pub create_api: &'a AtomicU64,
    pub poll_tail: &'a AtomicU64,
```

- [ ] **Step 5: Update snapshot() function body**

Replace:
```rust
        create_bt_ms: sources.create_bt.load(Ordering::SeqCst),
```
with:
```rust
        create_api_ms: sources.create_api.load(Ordering::SeqCst),
        poll_tail_ms: sources.poll_tail.load(Ordering::SeqCst),
```

- [ ] **Step 6: Update emit_delta() function to print both**

Find the "phase breakdown" formatter in `emit_delta` (around line 130-170 of overhead.rs). Replace any `create_bt` reference with two entries. For example, if today's format string includes `create_bt={}s({}%)`, expand to:
```rust
"create_api={:.1}s({:.1}%)  poll_tail={:.1}s({:.1}%)"
```

And update the args to include both `create_api_delta_ms` and `poll_tail_delta_ms` (computed the same way as existing `create_bt_delta_ms`).

Also update the percentage-of-overhead calculation: include both in the overhead sum denominator.

- [ ] **Step 7: Fix backtest.rs measurement site (same commit)**

In `src/runner/backtest.rs` find:
```rust
        let (_bt_resp, backtest_id, bt_create_start) = self
            .create_backtest_on_qc(project_id, &compile_id, job)
            .await?;

        let overhead_secs =
            bt_create_start.elapsed().as_secs_f64() + compile_phase_dur.as_secs_f64();
```

Replace with:
```rust
        let (_bt_resp, backtest_id, bt_create_start) = self
            .create_backtest_on_qc(project_id, &compile_id, job)
            .await?;

        // Snapshot create_api duration NOW, before any polling begins.
        // Fixes long-standing bug where create_bt_secs was measured
        // through poll completion (inflating by 20-40s/cycle).
        let create_api_secs = bt_create_start.elapsed().as_secs_f64();

        tracing::debug!(
            target: "qc::pipeline",
            "slot-{slot}: [{job_name}] create_api_measured elapsed={create_api_secs:.2}s"
        );

        let overhead_secs = create_api_secs + compile_phase_dur.as_secs_f64();
```

- [ ] **Step 8: Update the per-phase debug log in backtest.rs**

Find:
```rust
        tracing::debug!(
            "slot-{slot}: [{job_name}] overhead {overhead_secs:.1}s \
             (push+compile={:.1}s create_bt={:.1}s) project={project_id}",
            compile_phase_dur.as_secs_f64(),
            bt_create_start.elapsed().as_secs_f64()
        );
```

Replace with:
```rust
        tracing::debug!(
            "slot-{slot}: [{job_name}] overhead {overhead_secs:.1}s \
             (push+compile={:.1}s create_api={create_api_secs:.1}s) project={project_id}",
            compile_phase_dur.as_secs_f64()
        );
```

- [ ] **Step 9: Update counter fetch_add block in backtest.rs**

Find the counter block at the bottom of `run_backtest`:
```rust
            s.create_bt_ms.fetch_add(
                (create_bt_secs * 1000.0) as u64,
                Ordering::SeqCst,
            );
```

Replace with:
```rust
            s.create_api_ms.fetch_add(
                (create_api_secs * 1000.0) as u64,
                Ordering::SeqCst,
            );
            // poll_tail captures wall time from create return through poll completion
            let poll_tail_secs = (bt_create_start.elapsed().as_secs_f64() - create_api_secs).max(0.0);
            s.poll_tail_ms.fetch_add(
                (poll_tail_secs * 1000.0) as u64,
                Ordering::SeqCst,
            );
            tracing::debug!(
                target: "qc::pipeline",
                "slot-{slot}: [{job_name}] counters_bumped create_api_ms={} poll_tail_ms={}",
                (create_api_secs * 1000.0) as u64,
                (poll_tail_secs * 1000.0) as u64
            );
```

Also find the stale local binding `let create_bt_secs = bt_create_start.elapsed().as_secs_f64();` further up in the function and DELETE it (it was the bogus measurement).

- [ ] **Step 10: Update backtest.rs return tuple**

Find:
```rust
        Ok((
            backtest_id,
            bt_response,
            cloud_time,
            bt_phase_secs,
            push_secs,
            create_bt_secs,
        ))
```

Replace with:
```rust
        Ok((
            backtest_id,
            bt_response,
            cloud_time,
            bt_phase_secs,
            push_secs,
            create_api_secs,
        ))
```

The 6-tuple's trailing informational fields aren't used by callers that match on `Ok((bt_id, bt_resp, cloud_time, ..))` — this is purely a name clean-up.

- [ ] **Step 11: Update run_loop.rs phase_snapshot to read create_api_ms**

Run: `grep -n "create_bt_ms\|phase_snapshot_at_start" /home/bwg/qc_work/src/runner/run_loop.rs`

Find:
```rust
                    s.create_bt_ms.load(Ordering::SeqCst),
```

Replace with:
```rust
                    s.create_api_ms.load(Ordering::SeqCst),
```

And in the delta block below:
```rust
                let cbt_d = s.create_bt_ms.load(Ordering::SeqCst) - snap.4;
                let cycle_overhead_ms = pool_d + lock_d + push_d + comp_d + cbt_d;
```

Replace with:
```rust
                let cap_d = s.create_api_ms.load(Ordering::SeqCst) - snap.4;
                let cycle_overhead_ms = pool_d + lock_d + push_d + comp_d + cap_d;
```

(Renaming `cbt_d` → `cap_d` for clarity — "create_api delta".)

- [ ] **Step 12: Update status.rs SnapshotSources construction**

Run: `grep -n "create_bt\|SnapshotSources" /home/bwg/qc_work/src/server_mod/status.rs`

Find:
```rust
            create_bt: &session.create_bt_ms,
```

Replace with:
```rust
            create_api: &session.create_api_ms,
            poll_tail: &session.poll_tail_ms,
```

- [ ] **Step 13: Verify full-crate compile NOW (must pass)**

Run: `cd /home/bwg/qc_work && cargo check --lib 2>&1 | tail -5`

Expected: `Finished ...` no errors. If errors remain, they are likely in overhead.rs's `emit_delta` formatter (Step 6) — audit and fix before committing.

- [ ] **Step 14: Verify clippy**

Run: `cd /home/bwg/qc_work && cargo clippy --all-targets --all-features -- -D warnings 2>&1 | tail -3`

Expected: `Finished`.

- [ ] **Step 15: Commit (atomic — all callers updated in one commit)**

```bash
cd /home/bwg/qc_work
git add src/server_mod/mod.rs src/server_mod/overhead.rs src/runner/backtest.rs src/runner/run_loop.rs src/server_mod/status.rs
git commit -m "refactor(counters): split create_bt_ms into create_api_ms + poll_tail_ms

Fixes long-standing instrumentation bug: old create_bt_secs was computed
as bt_create_start.elapsed() AFTER poll_backtest() completed, capturing
20-40s per backtest instead of the true 1-2s create_backtest API call.
This made create_bt dominate overhead reports (80-97%), masking the real
polling cost.

Now:
- create_api_ms: just the create_backtest API call duration
- poll_tail_ms: residual (poll + DB write + collect)

Also add active_collects: AtomicI64 for the upcoming pipeline backpressure.
qc_overhead.log summary now shows create_api + poll_tail as separate fields.
All callers (backtest.rs, run_loop.rs, status.rs) updated atomically."
```

---

## Task 4: Introduce `ActiveCollectsGuard` + `PollCollectCtx` in new `pipeline.rs`

**Files:**
- Create: `src/runner/pipeline.rs`
- Modify: `src/runner/mod.rs` (add `pub mod pipeline;`)

- [ ] **Step 1: Confirm runner/mod.rs current module list**

Run: `grep -n "pub mod\|mod " /home/bwg/qc_work/src/runner/mod.rs | head -15`

- [ ] **Step 2: Create src/runner/pipeline.rs scaffold with types only**

Write new file `src/runner/pipeline.rs`:

```rust
//! Async poll+collect task launched by run_loop after prep_backtest.
//!
//! Responsibilities:
//! - Poll QC until backtest completes (or timeout)
//! - Parse results and store via collect_from_response
//! - mark_done / mark_failed on the queue row
//! - Emit `qc::pipeline` debug events capturing the lifecycle
//! - Manage `active_collects` counter via RAII guard
//!
//! Does NOT hold the project lock. Uses (project_id, backtest_id) only.

#![expect(
    clippy::cast_possible_truncation,
    clippy::cast_sign_loss,
    reason = "phase timings non-negative; seconds-to-ms conversions bounded"
)]

use std::sync::Arc;
use std::sync::atomic::{AtomicI64, Ordering};
use std::time::Instant;

use tokio::time::Duration;

use crate::client::QcClient;
use crate::db::{Db, QueueJob};
use crate::server::SessionCounters;

/// RAII guard for `session.active_collects`. Increments on construction,
/// decrements on drop (handles panic, cancellation, early return).
pub(crate) struct ActiveCollectsGuard {
    session: Option<Arc<SessionCounters>>,
}

impl ActiveCollectsGuard {
    pub(crate) fn new(session: Option<Arc<SessionCounters>>) -> Self {
        if let Some(ref s) = session {
            s.active_collects.fetch_add(1, Ordering::SeqCst);
        }
        Self { session }
    }

    pub(crate) fn current(&self) -> i64 {
        self.session
            .as_ref()
            .map_or(0, |s| s.active_collects.load(Ordering::SeqCst))
    }
}

impl Drop for ActiveCollectsGuard {
    fn drop(&mut self) {
        if let Some(ref s) = self.session {
            s.active_collects.fetch_sub(1, Ordering::SeqCst);
        }
    }
}

/// All context needed by poll_and_collect. Owned values — moved into
/// the tokio-spawned task.
pub(crate) struct PollCollectCtx {
    pub slot_id: usize,
    pub client: Arc<QcClient>,
    pub session: Option<Arc<SessionCounters>>,
    pub db: Db,
    pub job: QueueJob,
    pub project_id: i64,
    pub backtest_id: String,
    pub strategy: String,
    pub job_name: String,
    pub prep_elapsed: Duration,   // time spent in prep_backtest (for cycle accounting)
    pub bt_poll: Duration,        // tiered inside poll; this is initial hint
    pub bt_timeout: Duration,
}

/// Poll a backtest to completion, collect results, mark queue row done/failed.
/// Spawned from run_loop after project is unlocked. Uses (project_id, backtest_id)
/// as stable identity — QC's read_backtest is stateless w.r.t. project files.
pub(crate) async fn poll_and_collect(ctx: PollCollectCtx) {
    let _guard = ActiveCollectsGuard::new(ctx.session.clone());
    let task_start = Instant::now();
    let active_now = _guard.current();

    tracing::debug!(
        target: "qc::pipeline",
        "collect-task: entered slot-{} project={} bt={} strategy={} active_collects={} prep_elapsed={:.2}s",
        ctx.slot_id, ctx.project_id, ctx.backtest_id, ctx.strategy,
        active_now, ctx.prep_elapsed.as_secs_f64()
    );

    // TODO(Task 5): call poll_backtest_tiered + collect_from_response here
    // Placeholder: log and return so the scaffold compiles.
    tracing::debug!(
        target: "qc::pipeline",
        "collect-task: scaffold_exit slot-{} project={} bt={} (Task 5 will implement)",
        ctx.slot_id, ctx.project_id, ctx.backtest_id
    );
    let _ = (ctx.client, ctx.db, ctx.job, ctx.bt_poll, ctx.bt_timeout, task_start);
}
```

(The `TODO` marker is explicit — Task 5 fills in the body; this task just establishes types.)

- [ ] **Step 3: Add module export in runner/mod.rs**

Edit `src/runner/mod.rs`. In the module list, add:

```rust
pub mod pipeline;
```

(Place alphabetically or after `pub mod poll_create;` — consistent with existing style.)

- [ ] **Step 4: Verify compile**

Run: `cd /home/bwg/qc_work && cargo check --lib 2>&1 | tail -5`

Expected: `Finished ...`. There will be a `dead_code` warning on `poll_and_collect` because nothing calls it yet — that's OK, it gets called in Task 6.

- [ ] **Step 5: Verify clippy**

Run: `cd /home/bwg/qc_work && cargo clippy --all-targets --all-features -- -D warnings 2>&1 | tail -5`

Expected: `Finished ...`. Note: `dead_code` is a lint in a separate category from pedantic, not `-D warnings` by default. If it trips the gate, add `#[allow(dead_code)]` temporarily above `poll_and_collect` for this task only — Task 6 removes the need.

- [ ] **Step 6: Commit**

```bash
cd /home/bwg/qc_work
git add src/runner/pipeline.rs src/runner/mod.rs
git commit -m "feat(pipeline): add ActiveCollectsGuard + PollCollectCtx scaffolding

Empty poll_and_collect skeleton with RAII guard for session.active_collects.
Callers wired in next commits."
```

---

## Task 5: Implement `poll_and_collect` body (move logic from run_backtest poll path)

**Files:**
- Modify: `src/runner/pipeline.rs` (fill in the TODO)
- Modify: `src/runner/errors.rs` (deprecate `spawn_collect` — mark unused or delete; see step 5)

- [ ] **Step 1: Read current run_backtest poll path for reference**

Run: `sed -n '95,135p' /home/bwg/qc_work/src/runner/backtest.rs` — shows the poll_backtest call + counter bumps that need to move.

- [ ] **Step 2: Replace the TODO block in pipeline.rs**

Edit `src/runner/pipeline.rs`. Replace the `TODO(Task 5)` section at end of `poll_and_collect` with:

```rust
    // ── Poll until complete (uses a free-function poll variant; no lock needed) ──
    let poll_start = Instant::now();

    tracing::debug!(
        target: "qc::pipeline",
        "collect-task: poll_starting slot-{} project={} bt={} timeout={}s",
        ctx.slot_id, ctx.project_id, ctx.backtest_id, ctx.bt_timeout.as_secs()
    );

    let poll_result = crate::runner::poll::poll_backtest_unlocked(
        &ctx.client,
        ctx.project_id,
        &ctx.backtest_id,
        &ctx.job_name,
        ctx.bt_poll,
        ctx.bt_timeout,
    )
    .await;

    let poll_elapsed = poll_start.elapsed();
    tracing::debug!(
        target: "qc::pipeline",
        "collect-task: poll_returned slot-{} project={} bt={} elapsed={:.2}s ok={}",
        ctx.slot_id, ctx.project_id, ctx.backtest_id,
        poll_elapsed.as_secs_f64(), poll_result.is_ok()
    );

    match poll_result {
        Ok((bt_response, bt_phase_secs, poll_count)) => {
            let poll_tail_ms = (poll_start.elapsed().as_secs_f64() * 1000.0) as u64;
            if let Some(ref s) = ctx.session {
                s.bt_run_ms.fetch_add(
                    (bt_phase_secs * 1000.0) as u64,
                    Ordering::SeqCst,
                );
                s.poll_tail_ms.fetch_add(poll_tail_ms, Ordering::SeqCst);
            }
            tracing::debug!(
                target: "qc::pipeline",
                "collect-task: poll_done slot-{} project={} bt={} polls={poll_count} bt_run={bt_phase_secs:.1}s poll_tail={:.2}s",
                ctx.slot_id, ctx.project_id, ctx.backtest_id,
                poll_elapsed.as_secs_f64()
            );
            tracing::debug!(
                target: "qc::pipeline",
                "collect-task: collect_starting slot-{} project={} bt={}",
                ctx.slot_id, ctx.project_id, ctx.backtest_id
            );

            // Collect results via existing collect_from_response (fast-path; uses poll response)
            let collect_result = crate::runner::collect::collect_from_response(
                &ctx.client,
                &ctx.job,
                &ctx.db,
                ctx.project_id,
                &ctx.backtest_id,
                ctx.prep_elapsed.as_secs_f64() + bt_phase_secs,
                bt_response,
            )
            .await;

            match collect_result {
                Ok(car_mdd) => {
                    let cm = car_mdd.unwrap_or(0.0);
                    let total_elapsed = task_start.elapsed().as_secs_f64();
                    tracing::info!(
                        "slot-{}: {}/{} {}s CAR/MDD={:.3}",
                        ctx.slot_id, ctx.strategy, ctx.job_name,
                        total_elapsed as u64, cm
                    );
                    tracing::debug!(
                        target: "qc::pipeline",
                        "collect-task: result_stored slot-{} project={} bt={} car_mdd={:.3} task_total={:.2}s",
                        ctx.slot_id, ctx.project_id, ctx.backtest_id, cm, total_elapsed
                    );
                    if let Some(ref s) = ctx.session {
                        s.completed.fetch_add(1, Ordering::SeqCst);
                        tracing::debug!(
                            target: "qc::pipeline",
                            "collect-task: completed_count_bumped slot-{} project={} bt={} completed_total={}",
                            ctx.slot_id, ctx.project_id, ctx.backtest_id,
                            s.completed.load(Ordering::SeqCst)
                        );
                    }
                }
                Err(e) => {
                    tracing::error!(
                        "slot-{}: collect failed for {}: {e}",
                        ctx.slot_id, ctx.job_name
                    );
                    tracing::debug!(
                        target: "qc::pipeline",
                        "collect-task: collect_failed slot-{} project={} bt={} error={e}",
                        ctx.slot_id, ctx.project_id, ctx.backtest_id
                    );
                    let _ = ctx.db
                        .mark_failed(ctx.job.id, &format!("collect: {e}"), None)
                        .await;
                    if let Some(ref s) = ctx.session {
                        s.failed.fetch_add(1, Ordering::SeqCst);
                    }
                }
            }
        }
        Err(e) => {
            tracing::error!(
                "slot-{}: poll failed for {}: {e}",
                ctx.slot_id, ctx.job_name
            );
            tracing::debug!(
                target: "qc::pipeline",
                "collect-task: poll_failed slot-{} project={} bt={} error={e}",
                ctx.slot_id, ctx.project_id, ctx.backtest_id
            );
            let _ = ctx.db
                .mark_failed(ctx.job.id, &format!("poll: {e}"), None)
                .await;
            if let Some(ref s) = ctx.session {
                s.failed.fetch_add(1, Ordering::SeqCst);
            }
        }
    }
```

Remove the placeholder `let _ = (ctx.client, ctx.db, ...)` line — all those are now consumed.

- [ ] **Step 3: Add a free-function variant of poll_backtest in poll.rs**

The current `poll_backtest` is `impl SlotRunner`. We need a free function that doesn't need `&self`. Edit `src/runner/poll.rs` and add this free function (below the existing impl block):

```rust
/// Free-function variant of poll_backtest for use in spawned pipeline tasks
/// (no `&self` needed; takes the `client` directly). Same polling logic.
pub(crate) async fn poll_backtest_unlocked(
    client: &crate::client::QcClient,
    project_id: i64,
    backtest_id: &str,
    job_name: &str,
    bt_poll: Duration,
    bt_timeout: Duration,
) -> Result<(crate::models::backtest::BacktestResponse, f64, u32)> {
    tracing::debug!(
        "[{job_name}] polling backtest {backtest_id} (unlocked)"
    );
    let bt_run_start = Instant::now();
    let deadline = Instant::now() + bt_timeout;
    let mut poll_count = 0u32;

    loop {
        poll_count += 1;

        let r = match client.read_backtest(project_id, backtest_id).await {
            Ok(r) => r,
            Err(e) if is_rate_limit(&e) => {
                sleep(Duration::from_secs(3)).await;
                continue;
            }
            Err(e) => return Err(e),
        };

        if let Some(bt_result) = r.backtest.as_ref() {
            if bt_result.completed {
                if let Some(err) = &bt_result.error
                    && !err.is_empty()
                {
                    bail!("runtime_error: {err}");
                }
                let bt_phase_secs = bt_run_start.elapsed().as_secs_f64();
                return Ok((r, bt_phase_secs, poll_count));
            }
        }

        if Instant::now() > deadline {
            bail!(
                "backtest_timeout after {}s ({poll_count} polls)",
                bt_timeout.as_secs()
            );
        }
        sleep(bt_poll).await;
    }
}
```

(Task 8 will rewrite the sleep to use tiered delays. For now, keep the fixed `bt_poll` interval so this task is independently shippable.)

- [ ] **Step 4: Verify compile**

Run: `cd /home/bwg/qc_work && cargo check --lib 2>&1 | tail -5`

Expected: `Finished ...`. Still `dead_code` on `poll_and_collect` and `poll_backtest_unlocked` — resolved in Task 6.

- [ ] **Step 5: Verify clippy**

Run: `cd /home/bwg/qc_work && cargo clippy --all-targets --all-features -- -D warnings 2>&1 | tail -5`

Expected: `Finished`. If `dead_code` trips, add `#[allow(dead_code)]` above the two new functions — removed in Task 6.

- [ ] **Step 6: Commit**

```bash
cd /home/bwg/qc_work
git add src/runner/pipeline.rs src/runner/poll.rs
git commit -m "feat(pipeline): implement poll_and_collect body + free-fn poll_backtest_unlocked

poll_and_collect runs in tokio::spawn; does not hold project lock; uses
(project_id, backtest_id) to identify work. Records bt_run_ms + poll_tail_ms
counters, completed/failed tally, and emits qc::pipeline debug events on
every phase transition."
```

---

## Task 6: Refactor `run_backtest` → `prep_backtest` (strip poll path)

**Files:**
- Modify: `src/runner/backtest.rs` (entire impl block)

- [ ] **Step 1: Read current run_backtest signature + body**

Run: `sed -n '25,140p' /home/bwg/qc_work/src/runner/backtest.rs`

- [ ] **Step 2: Rename function and strip poll+collect logic**

Replace the `impl SlotRunner { pub(crate) async fn run_backtest(...) }` block with:

```rust
impl SlotRunner {
    /// Prep a backtest: push code (or skip if pre-compiled), compile,
    /// create_backtest on QC. Writes `backtest_id` to queue row.
    ///
    /// Holds the project lock throughout; caller must release after this returns.
    /// Does NOT poll or collect — those happen async in `pipeline::poll_and_collect`.
    ///
    /// Returns `(backtest_id, project_id, create_api_secs)`.
    pub(crate) async fn prep_backtest(
        &self,
        params: BacktestParams<'_>,
    ) -> Result<(String, i64, f64)> {
        let BacktestParams {
            job,
            db,
            project_id,
            pre_compile_id,
            compile_poll,
            compile_timeout,
            bt_poll: _,
            bt_timeout: _,
        } = params;
        let slot = self.slot_id;
        let job_name = &job.name;

        tracing::debug!(
            target: "qc::pipeline",
            "slot-{slot}: prep_started project={project_id} job={job_name}"
        );

        // ── Step 1+2: Push code and compile (or skip if pre-compiled) ──
        let (compile_id, compile_phase_dur, push_start, compile_start) = self
            .push_and_compile(
                job,
                project_id,
                pre_compile_id,
                compile_poll,
                compile_timeout,
            )
            .await?;

        let push_secs = compile_start.duration_since(push_start).as_secs_f64();

        tracing::debug!(
            target: "qc::pipeline",
            "slot-{slot}: push_done project={project_id} elapsed={push_secs:.1}s"
        );
        tracing::debug!(
            target: "qc::pipeline",
            "slot-{slot}: compile_done project={project_id} compile_id={compile_id} elapsed={:.1}s",
            compile_phase_dur.as_secs_f64()
        );

        // ── Step 3: Create backtest ──
        let (_bt_resp, backtest_id, bt_create_start) = self
            .create_backtest_on_qc(project_id, &compile_id, job)
            .await?;

        let create_api_secs = bt_create_start.elapsed().as_secs_f64();

        tracing::debug!(
            target: "qc::pipeline",
            "slot-{slot}: create_bt_done project={project_id} backtest_id={backtest_id} elapsed={create_api_secs:.1}s"
        );

        // Persist backtest_id on the queue row while we still hold the lock.
        {
            let bid = backtest_id.clone();
            let jid = job.id;
            let _ = db
                .call(move |conn| {
                    conn.execute(
                        "UPDATE backtest_queue SET backtest_id=?1 \
                         WHERE id=?2 AND status='running'",
                        rusqlite::params![bid, jid],
                    )?;
                    Ok(())
                })
                .await;
        }

        // Record push / compile / create_api counters now (poll/bt_run
        // happen in pipeline::poll_and_collect).
        if let Some(s) = &self.session {
            use std::sync::atomic::Ordering;
            s.push_ms.fetch_add((push_secs * 1000.0) as u64, Ordering::SeqCst);
            s.compile_ms.fetch_add(
                (compile_phase_dur.as_secs_f64() * 1000.0) as u64,
                Ordering::SeqCst,
            );
            s.create_api_ms.fetch_add(
                (create_api_secs * 1000.0) as u64,
                Ordering::SeqCst,
            );
        }

        Ok((backtest_id, project_id, create_api_secs))
    }
}
```

Also remove the unused local `push_start` duplicate (the inner `push_and_compile` call returns its own).

- [ ] **Step 3: Verify compile fails at run_loop.rs (expected — we fix in Task 7)**

Run: `cd /home/bwg/qc_work && cargo check --lib 2>&1 | grep -E "error|run_backtest" | head -10`

Expected: errors in `run_loop.rs:113` and possibly `errors.rs` about `run_backtest`. Also errors about unused `BacktestResponse` import if anywhere. We fix those in Task 7.

- [ ] **Step 4: Commit (broken-intermediate state accepted; rebuild after Task 7)**

Do **not** commit yet. Proceed directly to Task 7 — the refactor is split across backtest.rs + run_loop.rs and must land together for the crate to build.

---

## Task 7: Rewire `run_loop.rs` to use `prep_backtest` + spawn `poll_and_collect`

**Files:**
- Modify: `src/runner/run_loop.rs` (main loop body)
- Modify: `src/runner/errors.rs` (remove `spawn_collect`)

- [ ] **Step 1: Read current run_loop main loop**

Run: `sed -n '60,190p' /home/bwg/qc_work/src/runner/run_loop.rs`

- [ ] **Step 2: Replace the `run_backtest` match arm + spawn_collect with prep+spawn**

Edit `src/runner/run_loop.rs`. Find the block starting at `// ── PHASE 3: Run backtest ──` and ending at `// ── PHASE 5: Unlock project ──` (inclusive of the match arms). Replace with:

```rust
            // ── PHASE 3: Prep backtest (push+compile+create) ──
            let prep_start = Instant::now();
            tracing::debug!(
                target: "qc::pipeline",
                "slot-{}: lock_acquired project={project_id} strategy={strategy} job={job_name}",
                self.slot_id
            );
            let prep_result = self
                .prep_backtest(super::backtest::BacktestParams {
                    job: &job,
                    db: &db,
                    project_id,
                    pre_compile_id,
                    compile_poll,
                    compile_timeout,
                    bt_poll: poll_interval,
                    bt_timeout: backtest_timeout,
                })
                .await;
            let prep_elapsed = prep_start.elapsed();
            tracing::debug!(
                target: "qc::pipeline",
                "slot-{}: prep_returned project={project_id} elapsed={:.2}s ok={}",
                self.slot_id, prep_elapsed.as_secs_f64(), prep_result.is_ok()
            );

            // ── PHASE 4: Unlock project EARLY (before poll+collect) ──
            //    poll_and_collect only needs (project_id, backtest_id) —
            //    QC holds the compiled binary snapshot at create time
            //    (confirmed by QC docs: response carries snapshotId).
            {
                let mut locked = self.project_lock.lock().await;
                let existed = locked.remove(&project_id);
                tracing::debug!(
                    target: "qc::pipeline",
                    "slot-{}: project_released project={} was_locked={} remaining_locks={} (pipeline handoff)",
                    self.slot_id, project_id, existed, locked.len()
                );
            }

            match prep_result {
                Ok((backtest_id, pid, create_api_secs)) => {
                    let ctx = super::pipeline::PollCollectCtx {
                        slot_id: self.slot_id,
                        client: std::sync::Arc::clone(&self.client),
                        session: self.session.clone(),
                        db: db.clone(),
                        job: job.clone(),
                        project_id: pid,
                        backtest_id: backtest_id.clone(),
                        strategy: strategy.clone(),
                        job_name: job_name.clone(),
                        prep_elapsed,
                        bt_poll: poll_interval,
                        bt_timeout: backtest_timeout,
                    };
                    tracing::debug!(
                        target: "qc::pipeline",
                        "slot-{}: spawn_collect project={pid} bt={backtest_id} create_api={create_api_secs:.2}s prep={:.2}s",
                        self.slot_id, prep_elapsed.as_secs_f64()
                    );
                    tokio::spawn(super::pipeline::poll_and_collect(ctx));
                    tracing::debug!(
                        target: "qc::pipeline",
                        "slot-{}: next_acquire_starting (slot freed after {:.2}s cycle)",
                        self.slot_id, prep_start.elapsed().as_secs_f64()
                    );
                }
                Err(e) => {
                    tracing::debug!(
                        target: "qc::pipeline",
                        "slot-{}: prep_failed project={project_id} elapsed={:.2}s error={e}",
                        self.slot_id, prep_elapsed.as_secs_f64()
                    );
                    self.handle_backtest_error(
                        e,
                        &strategy,
                        &job_name,
                        &job,
                        &db,
                        prep_elapsed.as_secs_f64(),
                    )
                    .await;
                }
            }
```

Note the structural changes:
- The old "PHASE 5: Unlock project" block is now folded into the new "PHASE 4" right after `prep_result`.
- Unlock happens regardless of prep success/failure (error path benefits too).
- `spawn_collect` is no longer called; replaced by `pipeline::poll_and_collect`.

- [ ] **Step 3: Remove the phase_snapshot_at_start / per-strategy overhead block (moved semantics)**

The tail of the old loop computed per-cycle overhead and bumped `per_strategy` counters. Update the counter fields used:

Find:
```rust
            if let (Some(s), Some(snap)) = (&self.session, phase_snapshot_at_start) {
                use std::sync::atomic::Ordering;
                let pool_d = s.pool_wait_ms.load(Ordering::SeqCst) - snap.0;
                let lock_d = s.lock_wait_ms.load(Ordering::SeqCst) - snap.1;
                let push_d = s.push_ms.load(Ordering::SeqCst) - snap.2;
                let comp_d = s.compile_ms.load(Ordering::SeqCst) - snap.3;
                let cbt_d = s.create_bt_ms.load(Ordering::SeqCst) - snap.4;
                let cycle_overhead_ms = pool_d + lock_d + push_d + comp_d + cbt_d;
                ...
            }
```

Replace `s.create_bt_ms.load(...)` with `s.create_api_ms.load(...)` and rename `cbt_d` → `cap_d`:
```rust
                let cap_d = s.create_api_ms.load(Ordering::SeqCst) - snap.4;
                let cycle_overhead_ms = pool_d + lock_d + push_d + comp_d + cap_d;
```

And update the snapshot construction earlier in the loop (`phase_snapshot_at_start`) to read `s.create_api_ms.load(Ordering::SeqCst)` instead of `s.create_bt_ms.load(...)`.

- [ ] **Step 4: Remove spawn_collect method from errors.rs**

Edit `src/runner/errors.rs`. Delete the entire `pub(crate) fn spawn_collect(&self, params: SpawnCollectParams)` method + the `SpawnCollectParams` struct. Keep `handle_backtest_error` since run_loop still calls it.

If other files imported `SpawnCollectParams` / `spawn_collect` (they shouldn't after Task 7), the compiler will point them out.

- [ ] **Step 5: Verify compile clean**

Run: `cd /home/bwg/qc_work && cargo check --lib 2>&1 | tail -5`

Expected: `Finished ...` no errors.

- [ ] **Step 6: Verify clippy**

Run: `cd /home/bwg/qc_work && cargo clippy --all-targets --all-features -- -D warnings 2>&1 | tail -5`

Expected: `Finished ...`.

- [ ] **Step 7: Verify release build**

Run: `cd /home/bwg/qc_work && cargo build --release 2>&1 | tail -3`

Expected: `Finished `release` profile ...` under 30s.

- [ ] **Step 8: Commit (combines Task 6 + Task 7 — refactor is atomic)**

```bash
cd /home/bwg/qc_work
git add src/runner/backtest.rs src/runner/run_loop.rs src/runner/errors.rs
git commit -m "refactor(slot): split into prep_backtest + async poll_and_collect

Slot now releases the project lock immediately after create_backtest and
spawns poll_and_collect as a tokio task. Polling and result collection no
longer block the slot's hot path.

- run_backtest → prep_backtest (push+compile+create+DB write, holds lock)
- pipeline::poll_and_collect (poll+collect, no lock)
- run_loop unlocks project right after prep returns (success OR error)
- errors.rs::spawn_collect removed (replaced by pipeline path)

Collection safety preserved: QC stores the compiled binary at create time,
so subsequent pushes to the same project do not affect in-flight backtests.
read_backtest(project_id, backtest_id) is stateless w.r.t. project files."
```

---

## Task 8: Adaptive tiered polling in `poll_backtest_unlocked`

**Files:**
- Modify: `src/runner/poll.rs` (tiered delay)

- [ ] **Step 1: Add a tiered-delay helper function**

Edit `src/runner/poll.rs`. Above `poll_backtest_unlocked`, add:

```rust
/// Returns the delay to sleep BEFORE the next poll, based on poll count
/// (1-indexed) and current progress. Adaptive tiers plus progress-aware
/// tighten near completion.
fn tiered_poll_delay(poll_count: u32, progress: f64, backoff_factor: u32) -> Duration {
    // Near-completion: tighten to 0.5s regardless of poll count
    if progress >= 0.80 {
        return Duration::from_millis(500) * backoff_factor;
    }
    let base_ms: u64 = match poll_count {
        1 => 0,        // immediate first poll
        2..=4 => 500,  // 0.5s early phase
        5..=15 => 1000, // 1.0s typical s002
        _ => 2000,     // 2.0s long-tail
    };
    let ms = (base_ms as u128 * backoff_factor as u128).min(3_000);
    Duration::from_millis(ms as u64)
}
```

- [ ] **Step 2: Thread progress + backoff_factor through the polling loop**

Replace `poll_backtest_unlocked`'s loop body with the tiered version:

```rust
pub(crate) async fn poll_backtest_unlocked(
    client: &crate::client::QcClient,
    project_id: i64,
    backtest_id: &str,
    job_name: &str,
    _bt_poll_hint: Duration,  // ignored — tiers chosen internally
    bt_timeout: Duration,
) -> Result<(crate::models::backtest::BacktestResponse, f64, u32)> {
    tracing::debug!(
        "[{job_name}] polling backtest {backtest_id} (tiered)"
    );
    let bt_run_start = Instant::now();
    let deadline = Instant::now() + bt_timeout;
    let mut poll_count: u32 = 0;
    let mut progress: f64 = 0.0;
    let mut backoff_factor: u32 = 1;  // doubles on 429; resets on success

    // Sleep tier BEFORE the poll (first tier = 0ms so first poll is immediate)
    loop {
        let delay = tiered_poll_delay(poll_count + 1, progress, backoff_factor);
        if !delay.is_zero() {
            sleep(delay).await;
        }
        poll_count += 1;

        tracing::debug!(
            target: "qc::pipeline",
            "[{job_name}] poll_attempt #{poll_count} delay_before={:.3}s progress={progress:.2} backoff={backoff_factor}x",
            delay.as_secs_f64()
        );

        let r = match client.read_backtest(project_id, backtest_id).await {
            Ok(r) => {
                if backoff_factor > 1 {
                    tracing::debug!(
                        target: "qc::pipeline",
                        "[{job_name}] backoff_reset poll={poll_count} (was {backoff_factor}x)"
                    );
                }
                backoff_factor = 1;  // reset on success
                r
            }
            Err(e) if is_rate_limit(&e) => {
                // Per-task elasticity: double current tier for next 3 polls.
                backoff_factor = (backoff_factor * 2).min(4);
                tracing::debug!(
                    target: "qc::pipeline",
                    "[{job_name}] rate_limit on poll {poll_count} — backoff_factor={backoff_factor}"
                );
                continue;
            }
            Err(e) => {
                tracing::debug!(
                    target: "qc::pipeline",
                    "[{job_name}] poll_error poll={poll_count} error={e}"
                );
                return Err(e);
            }
        };

        if let Some(bt_result) = r.backtest.as_ref() {
            let new_progress = bt_result.progress;
            if (new_progress - progress).abs() > 0.01 {
                tracing::debug!(
                    target: "qc::pipeline",
                    "[{job_name}] progress_update poll={poll_count} progress={new_progress:.2} status={:?}",
                    bt_result.status.as_deref().unwrap_or("?")
                );
            }
            progress = new_progress;
            if bt_result.completed {
                if let Some(err) = &bt_result.error
                    && !err.is_empty()
                {
                    tracing::debug!(
                        target: "qc::pipeline",
                        "[{job_name}] runtime_error_detected poll={poll_count} error={err}"
                    );
                    bail!("runtime_error: {err}");
                }
                let bt_phase_secs = bt_run_start.elapsed().as_secs_f64();
                tracing::debug!(
                    target: "qc::pipeline",
                    "[{job_name}] tier_summary polls={poll_count} bt_run={bt_phase_secs:.1}s final_progress={progress:.2}"
                );
                return Ok((r, bt_phase_secs, poll_count));
            }
        }

        if Instant::now() > deadline {
            bail!(
                "backtest_timeout after {}s ({poll_count} polls)",
                bt_timeout.as_secs()
            );
        }
    }
}
```

- [ ] **Step 3: Verify compile**

Run: `cd /home/bwg/qc_work && cargo check --lib 2>&1 | tail -5`

Expected: `Finished ...` no errors.

- [ ] **Step 4: Verify clippy**

Run: `cd /home/bwg/qc_work && cargo clippy --all-targets --all-features -- -D warnings 2>&1 | tail -5`

Expected: `Finished`.

- [ ] **Step 5: Commit**

```bash
cd /home/bwg/qc_work
git add src/runner/poll.rs
git commit -m "feat(polling): adaptive tiered delays + per-task 429 elasticity

Replaces the fixed 1.5s poll interval with:
- Poll 1: immediate (0ms) — catch already-complete backtests
- Polls 2-4: 0.5s — catch ≤3s backtests
- Polls 5-15: 1.0s — typical s002 range
- Polls 16+: 2.0s — slow path
- Progress ≥0.80: force 0.5s (near-complete tighten)
- On 429: double current tier for next N polls in this task only"
```

---

## Task 9: Backpressure check in run_loop + status tick `active_collects` display

**Files:**
- Modify: `src/runner/run_loop.rs` (top of loop — backpressure gate)
- Modify: `src/server_mod/status.rs` (emit active_collects in status tick)

- [ ] **Step 1: Add backpressure gate at the top of the loop in run_loop.rs**

Edit `src/runner/run_loop.rs`. Inside the `loop { ... }` body, BEFORE the `// Record idle time` block, add:

**Critical context:** `self.dbs.len()` is the strategy DB count (2: S001 + S002), NOT slot count. Using it as proxy would trigger backpressure at `active_collects > 4` — way too aggressive. We need the real slot count. Check if `SlotRunner` has a `num_slots` field:

```bash
grep -n "pub.*num_slots\|num_slots:" /home/bwg/qc_work/src/runner/mod.rs
```

If no `num_slots` field exists on `SlotRunner`, add one first:

Edit `src/runner/mod.rs`. Inside `pub struct SlotRunner`:
```rust
    pub(crate) num_slots: usize,   // total slots in deployment (for backpressure)
```

Edit `src/runner/mod.rs` `SlotRunnerNew` builder struct — add the same field. Then in `src/server_mod/slots.rs` where `SlotRunner::new(SlotRunnerNew { ... })` is constructed (around line 80-90), pass `num_slots` from the existing `num_slots` variable in scope.

Now the backpressure block in run_loop.rs:

```rust
            // Backpressure: avoid unbounded poll_and_collect tasks.
            // Thresholds scale with slot count. At 2x slots = soft 500ms; 3x = hard 2s.
            if let Some(ref s) = self.session {
                use std::sync::atomic::Ordering;
                let active = s.active_collects.load(Ordering::SeqCst);
                let slots = self.num_slots as i64;
                if active > slots * 3 {
                    tracing::debug!(
                        target: "qc::pipeline",
                        "slot-{}: backpressure_hard active_collects={active} threshold={}x slots={}",
                        self.slot_id, 3, slots
                    );
                    tokio::time::sleep(std::time::Duration::from_secs(2)).await;
                } else if active > slots * 2 {
                    tracing::debug!(
                        target: "qc::pipeline",
                        "slot-{}: backpressure_soft active_collects={active} threshold={}x slots={}",
                        self.slot_id, 2, slots
                    );
                    tokio::time::sleep(std::time::Duration::from_millis(500)).await;
                }
            }
```

- [ ] **Step 2: Emit active_collects in status tick**

Edit `src/server_mod/status.rs`. In `log_status`, find where the status line is constructed. Add a read of `active_collects`:

```rust
    let active_collects = session.active_collects.load(std::sync::atomic::Ordering::SeqCst);
```

Then add to the formatted status report string (append to the end of the existing status line, or include in the overhead summary). For example in `format_status_report` params or as a trailing field:

```rust
    // Append to the boxed status line (non-breaking):
    tracing::info!("  pipeline: active_collects={active_collects}");
```

(Placement: log this on a separate INFO line right after the main status box so the existing box format isn't disturbed.)

- [ ] **Step 3: Verify compile**

Run: `cd /home/bwg/qc_work && cargo check --lib 2>&1 | tail -5`

Expected: `Finished ...`.

- [ ] **Step 4: Verify clippy**

Run: `cd /home/bwg/qc_work && cargo clippy --all-targets --all-features -- -D warnings 2>&1 | tail -5`

Expected: `Finished`.

- [ ] **Step 5: Commit**

```bash
cd /home/bwg/qc_work
git add src/runner/run_loop.rs src/server_mod/status.rs
git commit -m "feat(pipeline): backpressure + active_collects visibility

- Slot loop checks active_collects before acquire; 500ms soft pause at 2x,
  2s hard pause at 3x slot count.
- Status tick logs 'pipeline: active_collects=N' for operator visibility.

RAII guard in pipeline.rs ensures the counter can't leak (already in
Task 4). This task adds the producer-side backoff."
```

---

## Task 10: Rebuild release binary + restart server + zombie cleanup + soak

**Files:** (no code changes — operational)

- [ ] **Step 1: Rebuild release**

Run: `cd /home/bwg/qc_work && cargo build --release 2>&1 | tail -3`

Expected: `Finished `release` profile [optimized] target(s) in Ns`.

- [ ] **Step 2: Stop the running server gracefully**

Run: `OLDPID=$(cat /home/bwg/qc_work/qc-server.pid); kill -TERM $OLDPID; for i in 1 2 3 4 5 6 7 8 9 10; do ps -p $OLDPID > /dev/null 2>&1 || { echo "stopped after ${i}s"; break; }; sleep 1; done`

Expected: "stopped after Ns" within 10s. If not, `kill -KILL $OLDPID`.

- [ ] **Step 3: Clean up any zombie running rows (pipelined semantics may orphan collects mid-restart)**

Run:
```bash
sqlite3 /home/bwg/qc_work/data/S001.db "UPDATE backtest_queue SET status='queued', started_at=NULL, node_id=NULL, backtest_id=NULL, compile_id=NULL WHERE status='running'; SELECT changes() AS s001_cleaned"
sqlite3 /home/bwg/qc_work/data/S002.db "UPDATE backtest_queue SET status='queued', started_at=NULL, node_id=NULL, backtest_id=NULL, compile_id=NULL WHERE status='running'; SELECT changes() AS s002_cleaned"
```

Expected: integer counts of zombies cleared.

- [ ] **Step 4: Start new server**

Run:
```bash
cd /home/bwg/qc_work
nohup ./target/release/qc-backtest-server serve > /home/bwg/qc_work/data/logs/qc.stdout.log 2>&1 &
NEWPID=$!
echo "$NEWPID" > /home/bwg/qc_work/qc-server.pid
echo "Started PID=$NEWPID"
sleep 5
ps -p $NEWPID -o pid,pcpu,etime
```

Expected: process visible with ~20-30% CPU after warmup.

- [ ] **Step 5: Verify pipeline log is being written**

Wait 60s, then:
```bash
tail -20 /home/bwg/qc_work/data/logs/qc_pipeline.log.$(date +%Y-%m-%d)
```

Expected: lines with `slot-N: lock_acquired`, `push_done`, `compile_done`, `create_bt_done`, `project_released`, `collect_spawned`, `poll_started`, `poll_done`, `result_stored`. Should see multiple slots active.

- [ ] **Step 6: Soak-test 30 min — measure throughput**

Leave server running 30 min. Then:
```bash
tail -40 /home/bwg/qc_work/data/logs/qc.log.$(date +%Y-%m-%d) | grep "bt/m"
```

Expected: steady-state `bt/m` ≥ **18**. Baseline was 11.3.

- [ ] **Step 7: Verify create_api_secs averages 1-3s**

```bash
grep "create_api=" /home/bwg/qc_work/data/logs/qc_overhead.log.$(date +%Y-%m-%d) | tail -10
```

Expected: each tick's `create_api=N.Ns` reports ~10-30s aggregate (10 slots × 1-3s per cycle × ~10 cycles/min = 10-30s per 60s window).

- [ ] **Step 8: Verify active_collects stays bounded**

```bash
grep "active_collects" /home/bwg/qc_work/data/logs/qc_pipeline.log.$(date +%Y-%m-%d) | tail -20
```

Expected: values mostly ≤ 15, occasional spikes to 18-20, never sustained above 20.

- [ ] **Step 9: If throughput < 18 bt/m or active_collects runaway, roll back**

Decision gate. If success criteria not met:
```bash
cd /home/bwg/qc_work
git log --oneline -8  # identify commit SHAs from Tasks 1-9
git revert <bad-commit-sha>
cargo build --release
# restart server
```

If success criteria met, proceed to Step 10.

- [ ] **Step 10: Capture final metrics + commit operational notes**

Create/update `docs/superpowers/plans/2026-04-20-pipelined-slots.md` appendix with observed throughput, save to `project_infra_throughput.md` memory. (Text-only update — no code commit needed.)

Update `~/.claude/projects/-home-bwg-qc-work/memory/project_infra_throughput.md` by hand with the post-deploy numbers.

---

## Self-Review

### Spec coverage

| Spec section | Task |
|---|---|
| Dedicated pipeline log | Task 1 |
| Measurement fix (split create_bt_ms) | Tasks 2, 3 |
| `active_collects` + RAII guard | Tasks 2, 4 |
| `PollCollectCtx` + `poll_and_collect` | Tasks 4, 5 |
| `prep_backtest` split | Task 6 |
| Early project release + spawn | Task 7 |
| Adaptive tiered polling + 429 elasticity | Task 8 |
| Backpressure (2x/3x thresholds) | Task 9 |
| Status tick `active_collects` display | Task 9 |
| Rebuild + restart + soak | Task 10 |

All 9 items in File Inventory of the spec map to tasks.

### Placeholder scan

No "TBD", "TODO implement later", or vague "add error handling" placeholders. Task 4's `TODO(Task 5)` is an explicit commit-ship marker (intentional intermediate state), removed in Task 5.

### Type consistency

- `prep_backtest` returns `(String, i64, f64)` throughout (Tasks 6, 7 use the same signature).
- `PollCollectCtx` fields defined in Task 4, populated in Task 7 — field names match exactly.
- `create_api_ms` / `poll_tail_ms` names consistent across Tasks 2, 3, 5, 7, 8, 9, 10.
- `ActiveCollectsGuard` defined in Task 4, constructed in Task 5 (`ActiveCollectsGuard::new(ctx.session.clone())`), dropped automatically.
- `tiered_poll_delay` defined in Task 8 with explicit `u32, f64, u32 → Duration` signature used at its single call site.

### Scope check

Focused single-plan scope. All tasks contribute to one coherent refactor. No cross-feature bleeding.

### Ambiguity fixes applied

- Explicit `backoff_factor` cap at 4 in Task 8 to prevent runaway.
- Explicit decision point in Task 10 step 9 (roll-back gate) with success criteria.
- Explicit file-path line-ranges removed where they'd drift; replaced with grep-based location discovery.

---

Plan complete and saved to `docs/superpowers/plans/2026-04-20-pipelined-slots.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
