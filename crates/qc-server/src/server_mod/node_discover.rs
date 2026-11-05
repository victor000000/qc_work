//! Node discovery (+ the broadcast step lives in `node_broadcast.rs`).

use anyhow::Result;

use crate::client::QcClient;
use crate::config::ServerConfig;

pub(super) use super::node_broadcast::broadcast_nodes_to_projects;

/// Discover backtest nodes on the QC cloud (uses `strategies[0]` as anchor).
pub(super) async fn discover_nodes(
    client: &QcClient,
    config: &ServerConfig,
) -> Result<Vec<String>> {
    // The empty-strategies bail in serve() guarantees strategies[0] exists;
    // the loader skips strategies with no project IDs.
    let first_project = *config.strategies[0].project_ids.first().ok_or_else(|| {
        anyhow::anyhow!("strategies[0] has no project IDs (should be unreachable)")
    })?;
    let nodes_resp = client.read_project_nodes(first_project).await?;
    if !nodes_resp.success {
        anyhow::bail!(
            "read_project_nodes({first_project}) failed: {}",
            if nodes_resp.errors.is_empty() {
                "no error message returned".to_string()
            } else {
                nodes_resp.errors.join("; ")
            }
        );
    }
    let nodes = nodes_resp.nodes.ok_or_else(|| {
        anyhow::anyhow!("read_project_nodes({first_project}): success=true but no nodes payload")
    })?;
    let bt_nodes: Vec<String> = nodes.backtest.iter().map(|n| n.id.clone()).collect();
    tracing::info!("backtest nodes: {bt_nodes:?}");
    for node in &nodes.backtest {
        tracing::info!(
            "  node {} — sku={} speed={} cpu={} ram={} busy={} active={}",
            node.id,
            node.sku,
            node.speed,
            node.cpu,
            node.ram,
            node.busy,
            node.active
        );
    }
    Ok(bt_nodes)
}
