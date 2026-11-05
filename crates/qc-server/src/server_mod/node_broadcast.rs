//! Broadcast the discovered node list to every project so QC's scheduler
//! can use any node for any project's backtests.
//!
//! INFRA FIX 2026-05-06: Each QC project has its own node-allowed-set. If a
//! project's allowed-set is a subset of the full N nodes, QC will only
//! schedule that project's backtests on those nodes — leaving other nodes
//! idle even when there's pending work. We were hitting ~70% utilization
//! with 2 nodes chronically idle. Fix: at startup, broadcast the full
//! `bt_nodes` list to every project.

use crate::client::QcClient;
use crate::config::ServerConfig;

pub(super) async fn broadcast_nodes_to_projects(
    client: &QcClient,
    config: &ServerConfig,
    bt_nodes: &[String],
) {
    use futures::stream::{self, StreamExt};
    let all_pids: Vec<i64> = config
        .strategies
        .iter()
        .flat_map(|s| s.project_ids.iter().copied())
        .collect();
    tracing::info!(
        "broadcasting {} nodes to {} projects via update_project_nodes (parallel x8)",
        bt_nodes.len(),
        all_pids.len()
    );
    let started = std::time::Instant::now();
    // 2026-05-07: parallelized 8-wide via futures::buffer_unordered (was ~104s
    // sequential for 74 projects; ~13s parallel). CRITICAL: Send `nodes=None`
    // to enable autoSelectNode=true. QC API quirk: if `nodes` field is
    // present in the request, autoSelectNode is forced to false regardless
    // of the flag's value (verified empirically 2026-05-06).
    let results: Vec<bool> = stream::iter(all_pids.iter().copied())
        .map(|pid| async move {
            match client.update_project_nodes(pid, None, Some(true)).await {
                Ok(r) if r.success => true,
                Ok(r) => {
                    tracing::warn!("update_project_nodes({pid}) success=false: {:?}", r.errors);
                    false
                }
                Err(e) => {
                    tracing::warn!("update_project_nodes({pid}) failed: {e}");
                    false
                }
            }
        })
        .buffer_unordered(8)
        .collect()
        .await;
    let updated = results.iter().filter(|r| **r).count();
    let failed = results.len() - updated;
    let elapsed_ms = started.elapsed().as_millis();
    tracing::info!(
        "node-broadcast done: {updated}/{} projects updated ({failed} failed) elapsed={elapsed_ms}ms",
        all_pids.len()
    );
}
