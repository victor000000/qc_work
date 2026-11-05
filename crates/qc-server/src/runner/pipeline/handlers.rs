//! Success-path handlers for poll/collect outcomes.

use std::sync::atomic::Ordering;
use std::time::{Duration, Instant};

use super::ctx::PollCollectCtx;

pub(super) async fn handle_poll_ok(
    ctx: &PollCollectCtx,
    task_start: Instant,
    poll_start: Instant,
    bt_response: crate::models::backtest::BacktestResponse,
    bt_phase_secs: f64,
    poll_count: u32,
) {
    let to_ms = |d: Duration| u64::try_from(d.as_millis()).unwrap_or(u64::MAX);
    let poll_tail_ms = to_ms(poll_start.elapsed());
    if let Some(ref s) = ctx.session {
        let bt_run_dur =
            Duration::try_from_secs_f64(bt_phase_secs.max(0.0)).unwrap_or(Duration::ZERO);
        s.bt_run_ms.fetch_add(to_ms(bt_run_dur), Ordering::SeqCst);
        s.poll_tail_ms.fetch_add(poll_tail_ms, Ordering::SeqCst);
    }
    tracing::debug!(
        target: "qc::pipeline",
        "collect-task: poll_done slot-{} project={} bt={} polls={poll_count} bt_run={bt_phase_secs:.1}s poll_tail={:.2}s",
        ctx.slot_id, ctx.project_id, ctx.backtest_id,
        poll_start.elapsed().as_secs_f64()
    );
    tracing::debug!(
        target: "qc::pipeline",
        "collect-task: collect_starting slot-{} project={} bt={}",
        ctx.slot_id, ctx.project_id, ctx.backtest_id
    );

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
            handle_collect_ok(ctx, task_start, bt_phase_secs, car_mdd.unwrap_or(0.0));
        }
        Err(e) => super::handlers_err::handle_collect_err(ctx, &e.to_string()).await,
    }
}

fn handle_collect_ok(ctx: &PollCollectCtx, task_start: Instant, bt_phase_secs: f64, cm: f64) {
    let total_elapsed_dur = task_start.elapsed();
    let total_elapsed_f = total_elapsed_dur.as_secs_f64();
    let collect_secs = (total_elapsed_f - bt_phase_secs).max(0.0);
    let done_n = ctx.session.as_ref().map_or(0, |s| {
        s.completed.fetch_add(1, Ordering::SeqCst);
        let mut g = s
            .minute_counter
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        g.1 += 1;
        g.1
    });
    tracing::info!(
        "#{:>5} slot-{}: {}/{} bt={:.0}s collect={:.0}s total={:.0}s CAR/MDD={:.3}",
        done_n,
        ctx.slot_id,
        ctx.strategy,
        ctx.job_name,
        bt_phase_secs,
        collect_secs,
        total_elapsed_f,
        cm
    );
    tracing::debug!(
        target: "qc::pipeline",
        "collect-task: result_stored slot-{} project={} bt={} car_mdd={:.3} bt={:.2}s collect={:.2}s task_total={:.2}s done_n={done_n}",
        ctx.slot_id, ctx.project_id, ctx.backtest_id, cm, bt_phase_secs, collect_secs, total_elapsed_f
    );
    if ctx.session.is_some() {
        tracing::debug!(
            target: "qc::pipeline",
            "collect-task: completed_count_bumped slot-{} project={} bt={} completed_total={done_n}",
            ctx.slot_id, ctx.project_id, ctx.backtest_id
        );
    }
}
