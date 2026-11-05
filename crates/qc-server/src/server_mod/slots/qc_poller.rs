//! Dedicated QC busy-slot poller: polls `read_project_nodes` every 5s and
//! updates `session.qc_busy_slots` atomic. Status box reads the atomic —
//! never blocks on QC API.

use std::sync::Arc;
use std::sync::atomic::Ordering;

use tokio::task::JoinHandle;
use tokio::time::Duration;

use crate::client::QcClient;
use crate::server::SessionCounters;

pub(super) fn spawn_qc_poller(
    client: Arc<QcClient>,
    session: Arc<SessionCounters>,
    project_id: i64,
) -> JoinHandle<()> {
    tokio::spawn(async move {
        let mut last_idle_ids: Vec<String> = Vec::new();
        loop {
            // Poll every 5s so the cached busy count is at most 5s stale.
            tokio::time::sleep(Duration::from_secs(5)).await;
            match client.read_project_nodes(project_id).await {
                Ok(r) if r.success => {
                    let (busy_count, idle_ids): (usize, Vec<String>) =
                        r.nodes.as_ref().map_or((0, Vec::new()), |n| {
                            let busy = n.backtest.iter().filter(|nd| nd.busy).count();
                            let idle: Vec<String> = n
                                .backtest
                                .iter()
                                .filter(|nd| !nd.busy)
                                .map(|nd| nd.id.clone())
                                .collect();
                            (busy, idle)
                        });
                    session.qc_busy_slots.store(busy_count, Ordering::SeqCst);
                    // Per-poll debug snapshot: which nodes are busy + total. Useful
                    // for cracking QC scheduler bias (heterogeneous SKUs cause
                    // chronic idle on weaker B2-8 nodes vs B4-12; see commit
                    // 1ec7b7f comments). Reminder: node `busy=true` ONLY during
                    // bt-run phase; "idle" here means QC is between bts on that node.
                    if let Some(n) = r.nodes.as_ref() {
                        let busy_ids: Vec<&str> = n
                            .backtest
                            .iter()
                            .filter(|nd| nd.busy)
                            .map(|nd| &nd.id[..15.min(nd.id.len())])
                            .collect();
                        tracing::debug!(
                            target: "qc::nodes",
                            "qc-poller_snapshot busy={} idle={} total={} busy_ids={:?}",
                            busy_count,
                            idle_ids.len(),
                            n.backtest.len(),
                            busy_ids
                        );
                    }
                    // Log idle nodes only when the set CHANGES — avoids spam
                    // but surfaces sustained idle state per-node.
                    if idle_ids != last_idle_ids && !idle_ids.is_empty() {
                        let total_nodes = busy_count + idle_ids.len();
                        tracing::debug!(
                            "qc-poller: {} idle/{} nodes — idle: {}",
                            idle_ids.len(),
                            total_nodes,
                            idle_ids
                                .iter()
                                .map(|s| s.split_at(15.min(s.len())).0)
                                .collect::<Vec<_>>()
                                .join(", ")
                        );
                    }
                    last_idle_ids = idle_ids;
                }
                Ok(r) => tracing::warn!(
                    "qc-poller: read_project_nodes({project_id}) success=false: {:?}",
                    r.errors
                ),
                Err(e) => tracing::warn!("qc-poller: read_project_nodes failed: {e}"),
            }
        }
    })
}
