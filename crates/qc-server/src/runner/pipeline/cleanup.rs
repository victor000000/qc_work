//! Best-effort cancel of a backtest in the QC cloud after a terminal local
//! failure.

use crate::client::QcClient;

/// Best-effort cancel of a backtest in the QC cloud after a terminal local
/// failure. If the local pipeline gives up (timeout, collect error, etc.)
/// the backtest is often still running in QC, holding a node and burning
/// minutes. Calling `delete_backtest` releases that node so the next job can
/// claim it. Errors here are logged but never propagated — the local row is
/// still marked failed regardless.
pub(crate) async fn cancel_qc_backtest(
    client: &QcClient,
    project_id: i64,
    backtest_id: &str,
    slot_id: usize,
    job_name: &str,
    phase: &str,
) {
    if backtest_id.is_empty() {
        return;
    }
    match client.delete_backtest(project_id, backtest_id).await {
        Ok(resp) if resp.success => {
            tracing::info!(
                "slot-{slot_id}: {phase} cleanup — cancelled QC backtest \
                 {backtest_id} (project={project_id}, job={job_name})"
            );
        }
        Ok(resp) => {
            tracing::warn!(
                "slot-{slot_id}: {phase} cleanup — QC delete_backtest \
                 returned non-success for {backtest_id}: {:?}",
                resp.errors
            );
        }
        Err(e) => {
            tracing::warn!(
                "slot-{slot_id}: {phase} cleanup — QC delete_backtest \
                 failed for {backtest_id}: {e}"
            );
        }
    }
}
