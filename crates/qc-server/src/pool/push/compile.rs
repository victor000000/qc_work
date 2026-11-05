//! Warm-pool compile + compile-poll helpers.

use tokio::time::Duration;

use crate::client::QcClient;
use crate::db::{Db, QueueJob};
use crate::pool::claim::requeue_job;
use crate::rate_limit::{RateLimitState, retry_on_rate_limit};

pub(crate) async fn compile_code(
    client: &QcClient,
    rl_state: Option<&RateLimitState>,
    project_id: i64,
    db: &Db,
    job: &QueueJob,
    job_name: &str,
) -> Option<String> {
    let compile_result =
        retry_on_rate_limit(rl_state, 3, || client.create_compile(project_id)).await;

    match compile_result {
        Ok(c) if c.success => {
            tracing::debug!(
                "warm-pool: compile created for {job_name}: {}",
                c.compile_id
            );
            Some(c.compile_id)
        }
        Ok(c) => {
            tracing::warn!(
                "warm-pool: compile create failed for {job_name}: {:?}",
                c.errors
            );
            let _ = db
                .mark_failed(job.id, &format!("warmpool_compile: {:?}", c.errors), None)
                .await;
            None
        }
        Err(e) => {
            tracing::warn!("warm-pool: compile error for {job_name}: {e}");
            requeue_job(db, job.id).await;
            None
        }
    }
}

pub(crate) async fn poll_compile(
    client: &QcClient,
    project_id: i64,
    compile_id: &str,
    db: &Db,
    job: &QueueJob,
    job_name: &str,
) -> bool {
    match crate::runner::compile_poll::wait_compile(
        client,
        project_id,
        compile_id,
        job_name,
        Duration::from_millis(1050),
        Duration::from_mins(1),
    )
    .await
    {
        Ok(_) => true,
        Err(error) => {
            let message = error.to_string();
            if message.starts_with("compile_error:") {
                let _ = db.mark_failed(job.id, &message, None).await;
            } else {
                tracing::warn!("warm-pool: compile failed for {job_name}: {error}");
                requeue_job(db, job.id).await;
            }
            false
        }
    }
}
