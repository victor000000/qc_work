//! Phases 3–4 of the slot main loop: prep the backtest (push+compile+create),
//! release the project lock early, then dispatch the prep result for
//! poll+collect.

use std::time::Instant;

use super::cycle;
use super::iter::RunConfig;
use super::prep;
use crate::db::{Db, QueueJob};
use crate::runner::SlotRunner;

pub(super) struct CycleCtx<'a> {
    pub job: &'a QueueJob,
    pub db: &'a Db,
    pub project_id: i64,
    pub pre_compile_id: Option<String>,
    pub strategy: &'a str,
    pub job_name: &'a str,
    pub cycle_start: Instant,
    pub pick_ms: u128,
    pub phase_snapshot: Option<cycle::PhaseSnapshot>,
}

pub(super) async fn run_bt_phase(runner: &SlotRunner, cfg: &RunConfig, ctx: CycleCtx<'_>) {
    // ── PHASE 3: Prep backtest (push+compile+create) ──
    let prep_start = Instant::now();
    tracing::debug!(
        target: "qc::pipeline",
        "slot-{}: lock_acquired project={} strategy={} job={}",
        runner.slot_id, ctx.project_id, ctx.strategy, ctx.job_name
    );
    let prep_result = runner
        .prep_backtest(crate::runner::backtest::BacktestParams {
            job: ctx.job,
            db: ctx.db,
            project_id: ctx.project_id,
            pre_compile_id: ctx.pre_compile_id,
            compile_poll: cfg.compile_poll,
            compile_timeout: cfg.compile_timeout,
        })
        .await;
    let prep_elapsed = prep_start.elapsed();
    tracing::debug!(
        target: "qc::pipeline",
        "slot-{}: prep_returned project={} elapsed={:.2}s ok={}",
        runner.slot_id, ctx.project_id, prep_elapsed.as_secs_f64(), prep_result.is_ok()
    );

    // ── PHASE 4: Unlock project EARLY (before poll+collect) ──
    //    poll_and_collect only needs (project_id, backtest_id); QC holds the
    //    compiled binary snapshot at create time.
    cycle::release_project_lock(&runner.project_lock, runner.slot_id, ctx.project_id).await;

    prep::dispatch_prep_result(
        runner,
        prep::DispatchArgs {
            prep_result,
            db: ctx.db,
            job: ctx.job,
            project_id: ctx.project_id,
            strategy: ctx.strategy,
            job_name: ctx.job_name,
            prep_elapsed,
            prep_start,
            timeouts: &cfg.timeouts,
        },
    )
    .await;

    cycle::record_strategy_cycle(runner.session.as_ref(), ctx.phase_snapshot, ctx.strategy);
    cycle::log_cycle_done(
        runner.slot_id,
        ctx.cycle_start.elapsed().as_millis(),
        ctx.pick_ms,
        prep_elapsed.as_millis(),
        ctx.strategy,
        ctx.job_name,
    );
}
