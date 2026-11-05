//! Spawn one batch of parallel warmers and absorb their results.

use std::sync::Arc;

use super::filler::WarmPoolFillerParams;

pub(super) async fn fill_one_batch(
    params: &WarmPoolFillerParams,
    room: usize,
    fill_counter: &mut usize,
) {
    let mut set = tokio::task::JoinSet::new();
    for _ in 0..room {
        let c = Arc::clone(&params.client);
        let d = params.dbs.clone();
        let s = params.strategies.clone();
        let pl = Arc::clone(&params.project_lock);
        let np = params.name_prefix.clone();
        let rl = params.rl_state.clone();
        let fc = *fill_counter;
        *fill_counter += 1;

        set.spawn(async move {
            super::job::warm_one_job(super::job::PoolJobParams {
                client: &c,
                dbs: &d,
                strategies: &s,
                project_lock: &pl,
                counter: fc,
                name_prefix: &np,
                rl_state: &rl,
            })
            .await
        });
    }

    let mut warmed = 0;
    while let Some(result) = set.join_next().await {
        if let Ok(Some(entry)) = result {
            tracing::debug!(
                "warm-pool: added {}/{} (project={})",
                entry.strategy,
                entry.job.name,
                entry.project_id,
            );
            params.pool.push(entry).await;
            warmed += 1;
        }
    }

    if warmed > 0 {
        tracing::debug!(
            "warm-pool: batch done, warmed {warmed}, pool={}/{}",
            params.pool.len().await,
            params.pool.max_entries
        );
    }
}
