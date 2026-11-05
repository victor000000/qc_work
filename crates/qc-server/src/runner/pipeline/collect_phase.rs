//! Poll-then-collect orchestration spawned per backtest from `run_loop`.

use std::sync::atomic::Ordering;
use std::time::Instant;

use super::ctx::PollCollectCtx;
use super::guard::ActiveCollectsGuard;
use super::handlers::handle_poll_ok;
use super::handlers_err::handle_poll_err;

/// Poll a backtest to completion, collect results, mark queue row done/failed.
/// Spawned from `run_loop` after project is unlocked.
/// Uses `(project_id, backtest_id)` as stable identity — QC's `read_backtest`
/// is stateless w.r.t. project files.
pub(crate) fn spawn_poll_and_collect(ctx: PollCollectCtx) {
    let guard = ActiveCollectsGuard::new(ctx.session.clone());
    tokio::spawn(poll_and_collect(ctx, guard));
}

async fn poll_and_collect(ctx: PollCollectCtx, mut guard: ActiveCollectsGuard) {
    let task_start = Instant::now();
    let active_now = guard.current();

    tracing::debug!(
        target: "qc::pipeline",
        "collect-task: entered slot-{} project={} bt={} strategy={} active_collects={} prep_elapsed={:.2}s",
        ctx.slot_id, ctx.project_id, ctx.backtest_id, ctx.strategy,
        active_now, ctx.prep_elapsed.as_secs_f64()
    );

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
    // Release the QC-node-occupancy counter NOW: poll has returned, which
    // means QC has marked the bt completed (or it failed/timed-out — node
    // freed regardless). Subsequent collect_from_response only hits the
    // results API, which has its own rate-limit handling. This frees slot
    // loops to create the next backtest immediately, eliminating the
    // 90-second idle gap caused by collect-phase pinning the cap.
    guard.release_after_poll();
    tracing::debug!(
        target: "qc::pipeline",
        "collect-task: poll_returned slot-{} project={} bt={} elapsed={:.2}s ok={} active_collects_now={}",
        ctx.slot_id, ctx.project_id, ctx.backtest_id,
        poll_elapsed.as_secs_f64(), poll_result.is_ok(),
        ctx.session.as_ref().map_or(0, |s| s.active_collects.load(Ordering::SeqCst))
    );

    match poll_result {
        Ok((bt_response, bt_phase_secs, poll_count)) => {
            handle_poll_ok(
                &ctx,
                task_start,
                poll_start,
                bt_response,
                bt_phase_secs,
                poll_count,
            )
            .await;
        }
        Err(e) => handle_poll_err(&ctx, &e.to_string()).await,
    }

    drop(guard);
}
