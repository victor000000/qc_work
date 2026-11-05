//! Slot runner launch entrypoint.

use futures::StreamExt;
use std::sync::Arc;

use crate::client::QcClient;
use crate::config::ServerConfig;
use crate::db::Db;
use crate::rate_limit::RateLimitState;
use crate::server::SessionCounters;

use super::launch_spawn::{SpawnSlotsArgs, spawn_slot_runners};
use super::qc_poller::spawn_qc_poller;
use super::snapshot::spawn_snapshot_loop;
use super::status_loop::spawn_status_loop;
use super::warm::build_warm_pool;

/// Bundled parameters for `launch_slots`.
pub(crate) struct LaunchSlotsParams<'a> {
    pub config: &'a mut ServerConfig,
    pub dbs: &'a [Db],
    pub client: Arc<QcClient>,
    pub bt_nodes: &'a [String],
    pub num_slots: usize,
    pub rl_state: RateLimitState,
    pub session: Arc<SessionCounters>,
    pub project_lock: crate::runner::ProjectLock,
}

/// Launch slot runners and the warm pool, then wait forever.
pub(crate) async fn launch_slots(params: LaunchSlotsParams<'_>) -> anyhow::Result<()> {
    let LaunchSlotsParams {
        config,
        dbs,
        client,
        bt_nodes,
        num_slots,
        rl_state,
        session,
        project_lock,
    } = params;

    let warm = build_warm_pool(config, dbs, &client, num_slots, &rl_state, &project_lock);
    let handles = spawn_slot_runners(&SpawnSlotsArgs {
        client: &client,
        dbs,
        config,
        rl_state: &rl_state,
        session: &session,
        project_lock: &project_lock,
        warm_pool: &warm.pool,
        num_slots,
        bt_nodes,
    });

    tracing::info!("server running with {num_slots} slots");

    let status_project = config
        .strategies
        .first()
        .and_then(|s| s.project_ids.first().copied())
        .unwrap_or(0);
    let status_handle = spawn_status_loop(
        dbs.to_vec(),
        rl_state.clone(),
        Arc::clone(&session),
        Arc::clone(&client),
        num_slots,
        status_project,
    );
    let snap_handle = spawn_snapshot_loop(
        Arc::clone(&warm.pool),
        Arc::clone(&project_lock),
        dbs.to_vec(),
        Arc::clone(&session),
        num_slots,
    );

    let qc_handle = spawn_qc_poller(Arc::clone(&client), Arc::clone(&session), status_project);

    let mut pending: futures::stream::FuturesUnordered<_> = handles.into_iter().collect();
    let unexpected_exit = tokio::select! {
        () = super::shutdown::wait_for_signal() => false,
        result = pending.next() => {
            tracing::error!("runner slot exited unexpectedly: {result:?}");
            true
        }
    };
    session
        .stopping
        .store(true, std::sync::atomic::Ordering::SeqCst);
    warm.handle.abort();
    super::shutdown::drain_slots(&mut pending, &session).await;
    status_handle.abort();
    snap_handle.abort();
    qc_handle.abort();
    rl_state.save(&dbs[0]).await;
    anyhow::ensure!(!unexpected_exit, "runner slot stopped unexpectedly");
    Ok(())
}
