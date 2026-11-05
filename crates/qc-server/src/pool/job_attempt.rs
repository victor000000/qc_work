//! One per-strategy warming attempt — check work, lock a project, claim a
//! job, then push+compile. Returns `Some(WarmEntry)` on success or `None`
//! to fall through to the next strategy.

use std::time::Instant;

use super::WarmEntry;
use super::claim::{ClaimedJob, claim_job, lock_free_project, strategy_has_work};
use super::job::PoolJobParams;
use super::job_steps::execute_warm_steps;

pub(super) async fn try_strategy(
    params: &PoolJobParams<'_>,
    si: usize,
    warm_start: Instant,
) -> Option<WarmEntry> {
    let db = &params.dbs[si];

    if !strategy_has_work(db, params.name_prefix.as_deref()).await {
        tracing::trace!(
            "warm-pool: strategy[{si}]={} has no work",
            params.strategies[si].name
        );
        return None;
    }
    // trace! — fires per-batch when warm-pool finds a strategy with queued
    // work (~10k lines/hr under steady load). Downstream claim/lock logs
    // remain at debug for diagnostic value.
    tracing::trace!(
        "warm-pool: strategy[{si}]={} has work, finding project",
        params.strategies[si].name
    );

    let project_id = lock_free_project(
        params.project_lock,
        &params.strategies[si].project_ids,
        params.counter,
    )
    .await?;
    let (job, project_id) = claim_job(
        db,
        params.project_lock,
        project_id,
        params.name_prefix.as_deref(),
        &params.strategies[si].project_ids,
        params.counter,
    )
    .await?;

    let claimed = ClaimedJob { job, project_id };
    execute_warm_steps(
        params.client,
        params.rl_state.as_ref(),
        params.project_lock,
        db,
        claimed,
        &params.strategies[si],
        warm_start,
    )
    .await
}
