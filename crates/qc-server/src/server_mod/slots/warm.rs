//! Warm pool setup for slot launching.
//!
//! Hosts the rationale-heavy comments for sizing decisions
//! (`slot_reserve`, `max_warm`).

use std::sync::Arc;

use tokio::task::JoinHandle;

use crate::client::QcClient;
use crate::config::ServerConfig;
use crate::db::Db;
use crate::rate_limit::RateLimitState;

/// Warm pool plumbing returned by [`build_warm_pool`].
pub(super) struct WarmPoolBundle {
    pub pool: Arc<crate::pool::WarmPool>,
    pub handle: JoinHandle<()>,
}

/// Build the warm pool and spawn its filler.
///
/// Sizing rationale (preserved from inline history):
/// - `max_warm = (num_projects - num_slots).max(num_slots) * 2` keeps the pool
///   large enough that nodes never starve for pre-compiled work.
/// - `slot_reserve = (num_slots / 3).max(3)` keeps a few projects unlocked so
///   a slot that falls through to direct-claim can always grab one. Tuned
///   through R1359 throughput exploration; lower values caused
///   "all projects locked" cascades, higher values shrank the pool.
pub(super) fn build_warm_pool(
    config: &ServerConfig,
    dbs: &[Db],
    client: &Arc<QcClient>,
    num_slots: usize,
    rl_state: &RateLimitState,
    project_lock: &crate::runner::ProjectLock,
) -> WarmPoolBundle {
    let num_projects = config
        .strategies
        .iter()
        .flat_map(|s| s.project_ids.iter())
        .collect::<std::collections::HashSet<_>>()
        .len();
    let max_warm = (num_projects.saturating_sub(num_slots).max(num_slots)) * 2;
    let pool = Arc::new(crate::pool::WarmPool::new(
        Arc::clone(project_lock),
        max_warm,
    ));
    let slot_reserve = (num_slots / 3)
        .max(3)
        .min(num_projects.saturating_sub(1).max(1));
    let handle = tokio::spawn(crate::pool::warm_pool_filler(
        crate::pool::WarmPoolFillerParams {
            pool: Arc::clone(&pool),
            client: Arc::clone(client),
            dbs: config
                .strategies
                .iter()
                .map(|strategy| {
                    dbs.iter()
                        .find(|db| db.strategy == strategy.name)
                        .expect("active strategy must have a database")
                        .clone()
                })
                .collect(),
            strategies: config.strategies.clone(),
            project_lock: Arc::clone(project_lock),
            name_prefix: None,
            rl_state: Some(rl_state.clone()),
            slot_reserve,
        },
    ));
    tracing::info!("warm pool slot_reserve = {slot_reserve}");
    tracing::info!(
        "warm pool started (max {max_warm} entries, \
         adaptive concurrency up to {} warmers)",
        num_projects.saturating_sub(num_slots)
    );

    WarmPoolBundle { pool, handle }
}
