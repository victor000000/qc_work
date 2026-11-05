//! Prep-result handling: spawn collect on success, log on failure.

use std::time::Instant;

use tokio::time::Duration;

use crate::db::{Db, QueueJob};

use super::super::SlotRunner;

/// Constants/timeouts wrapping `prep_backtest` invocation.
pub(super) struct PrepTimeouts {
    pub poll_interval: Duration,
    pub backtest_timeout: Duration,
}

/// Bundle of cycle-context args for `dispatch_prep_result` — replaces what
/// would otherwise be ~10 positional parameters and silences `too_many_arguments`.
pub(super) struct DispatchArgs<'a> {
    pub prep_result: anyhow::Result<(String, i64, f64)>,
    pub db: &'a Db,
    pub job: &'a QueueJob,
    pub project_id: i64,
    pub strategy: &'a str,
    pub job_name: &'a str,
    pub prep_elapsed: Duration,
    pub prep_start: Instant,
    pub timeouts: &'a PrepTimeouts,
}

/// Hand the prep result off to the pipeline (spawn collect) or to the
/// error path. `prep_start` is used to log the slot-free latency.
pub(super) async fn dispatch_prep_result(runner: &SlotRunner, args: DispatchArgs<'_>) {
    let DispatchArgs {
        prep_result,
        db,
        job,
        project_id,
        strategy,
        job_name,
        prep_elapsed,
        prep_start,
        timeouts,
    } = args;
    match prep_result {
        Ok((backtest_id, pid, create_api_secs)) => {
            let ctx = crate::runner::pipeline::PollCollectCtx {
                slot_id: runner.slot_id,
                client: std::sync::Arc::clone(&runner.client),
                session: runner.session.clone(),
                db: db.clone(),
                job: job.clone(),
                project_id: pid,
                backtest_id: backtest_id.clone(),
                strategy: strategy.to_string(),
                job_name: job_name.to_string(),
                prep_elapsed,
                bt_poll: timeouts.poll_interval,
                bt_timeout: timeouts.backtest_timeout,
            };
            tracing::debug!(
                target: "qc::pipeline",
                "slot-{}: spawn_collect project={pid} bt={backtest_id} create_api={create_api_secs:.2}s prep={:.2}s",
                runner.slot_id, prep_elapsed.as_secs_f64()
            );
            crate::runner::pipeline::spawn_poll_and_collect(ctx);
            tracing::debug!(
                target: "qc::pipeline",
                "slot-{}: next_acquire_starting (slot freed after {:.2}s cycle)",
                runner.slot_id, prep_start.elapsed().as_secs_f64()
            );
        }
        Err(e) => {
            tracing::debug!(
                target: "qc::pipeline",
                "slot-{}: prep_failed project={project_id} elapsed={:.2}s error={e}",
                runner.slot_id, prep_elapsed.as_secs_f64()
            );
            runner
                .handle_backtest_error(e, strategy, job_name, job, db, prep_elapsed.as_secs_f64())
                .await;
        }
    }
}
