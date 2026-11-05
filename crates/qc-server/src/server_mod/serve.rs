//! `serve` — the server entrypoint that owns the PID lock and orchestrates
//! config → auth → node discovery → slot launch.

use std::path::PathBuf;
use std::sync::Arc;

use anyhow::Result;

use super::SessionCounters;
use super::log_helpers::{log_queue_counts, log_strategies};
use super::node_discover::{broadcast_nodes_to_projects, discover_nodes};
use super::pid;
use super::slots::{LaunchSlotsParams, launch_slots};
use super::status::recover_running_jobs;
use crate::client::QcClient;
use crate::config::ServerConfig;

const PID_FILE: &str = "qc-server.pid";

/// Start the backtest server: acquire PID lock, load config, discover nodes,
/// launch runner slots.
///
/// # Errors
/// Returns `Err` if the PID lock cannot be acquired, config loading fails,
/// QC authentication fails, or no backtest nodes are available.
pub async fn serve(data_dir: PathBuf) -> Result<()> {
    let pid_path = data_dir.join(PID_FILE);
    let _pid_guard = pid::try_acquire_pid_lock(&pid_path)?;

    tracing::info!("loading config from {}", data_dir.display());
    let (mut config, dbs) = ServerConfig::load(&data_dir).await?;

    if config.strategies.is_empty() {
        anyhow::bail!(
            "no strategies with project IDs found. Add IDs to projects.json \
             (or run `create-projects --count N`) before serving."
        );
    }

    log_strategies(&config);

    let client = Arc::new(QcClient::new(&config.qc_user_id, &config.qc_api_token));
    let auth = client.authenticate().await?;
    if !auth.success {
        anyhow::bail!("QC auth failed: {:?}", auth.errors);
    }
    tracing::info!("QC authentication OK");

    let bt_nodes = discover_nodes(&client, &config).await?;
    config.node_ids = bt_nodes.clone();
    broadcast_nodes_to_projects(&client, &config, &bt_nodes).await;

    let num_projects = config
        .strategies
        .iter()
        .flat_map(|s| s.project_ids.iter())
        .collect::<std::collections::HashSet<_>>()
        .len();
    let num_slots = bt_nodes.len();
    if num_slots == 0 {
        anyhow::bail!("no backtest nodes available");
    }
    if num_projects == 0 {
        anyhow::bail!("no project IDs configured");
    }
    tracing::info!(
        "launching {num_slots} slot(s) for {} node(s), {num_projects} project(s) \
         (slots independent of project count)",
        bt_nodes.len()
    );

    recover_running_jobs(&dbs, &client).await?;
    let rl_state = crate::rate_limit::RateLimitState::load(&dbs[0]).await;
    log_queue_counts(&dbs).await?;

    let session = Arc::new(SessionCounters::default());
    // Sentinel: usize::MAX means "QC busy poll has not run yet — use local fallback"
    session
        .qc_busy_slots
        .store(usize::MAX, std::sync::atomic::Ordering::SeqCst);
    let project_lock = crate::runner::ProjectLock::default();

    launch_slots(LaunchSlotsParams {
        config: &mut config,
        dbs: &dbs,
        client,
        bt_nodes: &bt_nodes,
        num_slots,
        rl_state,
        session,
        project_lock,
    })
    .await?;

    Ok(())
}
