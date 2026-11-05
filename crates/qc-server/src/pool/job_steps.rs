//! Warm job steps: push code, compile, poll compile.

use std::time::Instant;

use super::WarmEntry;
use super::claim::ClaimedJob;
use super::claim::requeue_job;
use super::job_validate::pre_push_validate;
use super::push::{compile_code, poll_compile, push_code};
use crate::client::QcClient;
use crate::config::StrategyConfig;
use crate::db::Db;
use crate::rate_limit::RateLimitState;
use crate::runner::ProjectLock;

/// Execute push + compile + poll for a claimed job.
/// Returns `Some(WarmEntry)` on success, `None` on failure
/// (cleans up by unlocking project and requeuing).
pub(crate) async fn execute_warm_steps(
    client: &QcClient,
    rl_state: Option<&RateLimitState>,
    project_lock: &ProjectLock,
    db: &Db,
    claimed: ClaimedJob,
    strategy: &StrategyConfig,
    warm_start: Instant,
) -> Option<WarmEntry> {
    let job_name = claimed.job.name.clone();
    let project_id = claimed.project_id;

    {
        let locked = project_lock.lock().await;
        if !locked.contains(&project_id) {
            tracing::error!(
                "warm-pool: BUG -- project {project_id} not locked \
                 before push for {job_name}!"
            );
            requeue_job(db, claimed.job.id).await;
            return None;
        }
    }

    if !pre_push_validate(&claimed.job, db, project_lock, project_id, &job_name).await {
        return None;
    }

    if push_code(client, rl_state, project_id, &claimed.job, &job_name).await == Err(()) {
        project_lock.lock().await.remove(&project_id);
        requeue_job(db, claimed.job.id).await;
        return None;
    }

    let Some(compile_id) =
        compile_code(client, rl_state, project_id, db, &claimed.job, &job_name).await
    else {
        project_lock.lock().await.remove(&project_id);
        return None;
    };

    if !poll_compile(client, project_id, &compile_id, db, &claimed.job, &job_name).await {
        project_lock.lock().await.remove(&project_id);
        return None;
    }

    let warm_ms = warm_start.elapsed().as_millis();
    tracing::debug!(
        "warm-pool: warmed {}/{job_name} in {warm_ms}ms on project {project_id}",
        strategy.name
    );
    Some(WarmEntry {
        job: claimed.job,
        db: db.clone(),
        project_id,
        compile_id,
        strategy: strategy.name.clone(),
        warmed_at: Instant::now(),
    })
}
