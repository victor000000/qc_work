//! Per-iteration body of the `SlotRunner` main loop.
//!
//! Phases 1–2 (acquire + lock) live here; phases 3–4 (prep + dispatch) are
//! in `iter_run.rs` so each file stays under 100 lines and the phase comments
//! remain readable.

use std::time::Instant;

use tokio::time::Duration;

use super::{backpressure, cycle, iter_run, prep};
use crate::runner::SlotRunner;

pub(super) struct RunConfig {
    pub backoff: Duration,
    pub timeouts: prep::PrepTimeouts,
    pub compile_poll: Duration,
    pub compile_timeout: Duration,
}

pub(super) async fn run_one(
    runner: &mut SlotRunner,
    cfg: &RunConfig,
    prev_cycle_end: &mut Option<Instant>,
) {
    let cycle_start = Instant::now();
    backpressure::apply(runner.session.as_ref(), runner.slot_id, runner.num_slots).await;

    if let Some(end) = *prev_cycle_end {
        let idle_ms =
            u64::try_from(cycle_start.duration_since(end).as_millis()).unwrap_or(u64::MAX);
        if let Some(s) = &runner.session {
            s.idle_ms
                .fetch_add(idle_ms, std::sync::atomic::Ordering::SeqCst);
        }
    }
    let phase_snapshot = cycle::snapshot_phases(runner.session.as_ref());

    // ── PHASE 1: Acquire a job ──
    let Some((job, db, project_id, skip_push, pre_compile_id)) =
        runner.acquire_job(&cfg.backoff).await
    else {
        // Idle path — no cycle completed; don't update prev_cycle_end.
        return;
    };
    let pick_ms = cycle_start.elapsed().as_millis();
    let job_name = job.name.clone();
    let strategy = job.strategy.clone();

    // ── PHASE 2: Lock project ──
    let Some(project_id) = runner
        .lock_project(project_id, skip_push, &strategy, &job_name, &job, &db)
        .await
    else {
        return;
    };
    tracing::debug!(
        "slot-{}: picked {strategy}/{job_name} project={project_id} pre_compiled={skip_push}",
        runner.slot_id,
    );

    iter_run::run_bt_phase(
        runner,
        cfg,
        iter_run::CycleCtx {
            job: &job,
            db: &db,
            project_id,
            pre_compile_id,
            strategy: &strategy,
            job_name: &job_name,
            cycle_start,
            pick_ms,
            phase_snapshot,
        },
    )
    .await;

    *prev_cycle_end = Some(Instant::now());
}
