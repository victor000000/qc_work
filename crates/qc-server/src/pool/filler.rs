//! Background task that fills the warm pool using parallel warmers.

use std::sync::Arc;

use tokio::time::{Duration, sleep};

use super::WarmPool;
use crate::client::QcClient;
use crate::config::StrategyConfig;
use crate::db::Db;
use crate::rate_limit::RateLimitState;
use crate::runner::ProjectLock;

/// Bundled parameters for the warm pool filler task.
pub struct WarmPoolFillerParams {
    pub pool: Arc<WarmPool>,
    pub client: Arc<QcClient>,
    pub dbs: Vec<Db>,
    pub strategies: Vec<StrategyConfig>,
    pub project_lock: ProjectLock,
    pub name_prefix: Option<String>,
    pub rl_state: Option<RateLimitState>,
    pub slot_reserve: usize,
}

/// Background task that fills the warm pool using parallel warmers.
/// Concurrency adapts to available capacity: min(room, `free_projects`).
///
/// `slot_reserve` projects are always kept unlocked so slots that fall
/// back to direct-claim can always get a project. Without this, a full
/// warm pool could lock every project, starving direct-claim slots.
pub async fn warm_pool_filler(params: WarmPoolFillerParams) {
    let num_projects = params
        .strategies
        .iter()
        .flat_map(|s| s.project_ids.iter())
        .collect::<std::collections::HashSet<_>>()
        .len();
    let mut fill_counter: usize = 0;

    loop {
        let locked_count = params.project_lock.lock().await.len();
        let free_total = num_projects.saturating_sub(locked_count);
        let free_for_warm = free_total.saturating_sub(params.slot_reserve);

        let pool_len = params.pool.entries.lock().await.len();
        let room = if pool_len >= params.pool.max_entries || free_for_warm == 0 {
            0
        } else {
            (params.pool.max_entries - pool_len).min(free_for_warm)
        };

        if room == 0 {
            tracing::trace!(
                "warm-pool: throttled (pool={}/{}, free_total={free_total}, \
                 free_for_warm={free_for_warm}, reserve={})",
                pool_len,
                params.pool.max_entries,
                params.slot_reserve,
            );
            // Shorter throttle — slots drain pool in seconds; need to react fast.
            sleep(Duration::from_millis(105)).await;
            continue;
        }

        // trace! — fires per batch (many/sec under steady load); was ~26k
        // lines/hr. Promote back to debug if warm-pool sizing needs tuning.
        tracing::trace!(
            "warm-pool: filling {room} slots \
             (pool={}/{}, free_for_warm={free_for_warm}, reserve={})",
            params.pool.len().await,
            params.pool.max_entries,
            params.slot_reserve,
        );

        super::filler_batch::fill_one_batch(&params, room, &mut fill_counter).await;
        // Short pause between batches — keeps warmer busy when slots drain pool.
        sleep(Duration::from_millis(70)).await;
    }
}
