//! Spawn `num_slots` `SlotRunner` tasks. Each gets its own clone of the
//! shared state and a reference to the warm pool.

use std::sync::Arc;

use crate::client::QcClient;
use crate::config::ServerConfig;
use crate::db::Db;
use crate::rate_limit::RateLimitState;
use crate::runner::{SlotRunner, SlotRunnerNew};
use crate::server::SessionCounters;

pub(super) struct SpawnSlotsArgs<'a> {
    pub client: &'a Arc<QcClient>,
    pub dbs: &'a [Db],
    pub config: &'a ServerConfig,
    pub rl_state: &'a RateLimitState,
    pub session: &'a Arc<SessionCounters>,
    pub project_lock: &'a crate::runner::ProjectLock,
    pub warm_pool: &'a Arc<crate::pool::WarmPool>,
    pub num_slots: usize,
    pub bt_nodes: &'a [String],
}

pub(super) fn spawn_slot_runners(a: &SpawnSlotsArgs<'_>) -> Vec<tokio::task::JoinHandle<()>> {
    let mut handles = Vec::new();
    for slot_id in 0..a.num_slots {
        let mut runner = SlotRunner::new(SlotRunnerNew {
            slot_id,
            client: Arc::clone(a.client),
            dbs: a.dbs.to_vec(),
            strategies: a.config.strategies.clone(),
            name_prefix: None,
            rl_state: Some(a.rl_state.clone()),
            session: Some(Arc::clone(a.session)),
            project_lock: Arc::clone(a.project_lock),
            num_slots: a.num_slots,
        });
        runner.warm_pool = Some(Arc::clone(a.warm_pool));
        tracing::info!(
            "starting slot-{slot_id} (node={})",
            a.bt_nodes.get(slot_id).map_or("auto", String::as_str)
        );
        handles.push(tokio::spawn(async move { runner.run().await }));
    }
    handles
}
