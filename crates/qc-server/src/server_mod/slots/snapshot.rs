//! Lightweight pool/lock-state snapshot loop (15s cadence) for
//! fast diagnosis of slot starvation.

use std::sync::Arc;
use std::sync::atomic::Ordering;

use tokio::task::JoinHandle;
use tokio::time::Duration;

use super::snapshot_scan::scan_dbs;
use crate::db::Db;
use crate::server::SessionCounters;

pub(super) fn spawn_snapshot_loop(
    pool: Arc<crate::pool::WarmPool>,
    lock: crate::runner::ProjectLock,
    dbs: Vec<Db>,
    session: Arc<SessionCounters>,
    num_slots: usize,
) -> JoinHandle<()> {
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(15)).await;
            let pool_len = pool.len().await;
            let locked_count = lock.lock().await.len();
            let (queued, prewarm, bt_running, busy) = scan_dbs(&dbs).await;
            // Track starvation — queue has work but slots idle.
            if queued > 0 && busy < num_slots {
                // External bottleneck: when QC reports >= num_slots busy nodes
                // already, our idle slots can't create new backtests no matter
                // what — every `create_backtest` call comes back "no spare
                // nodes". Skip the counter increments (they feed the
                // "% of uptime" status line, which is meant to measure *our*
                // scheduling inefficiency) and log at info so the event stays
                // auditable. `usize::MAX` sentinel = poller not started.
                let qc_busy = session.qc_busy_slots.load(Ordering::SeqCst);
                let qc_capped = qc_busy != usize::MAX && qc_busy >= num_slots;
                if qc_capped {
                    tracing::info!(
                        "starvation (QC-bottlenecked): queued={queued} busy={busy}/{num_slots} \
                         qc_busy_nodes={qc_busy} (pool={pool_len} prewarm={prewarm})"
                    );
                } else {
                    let idle = (num_slots - busy) as u64;
                    session.starvation_secs.fetch_add(15, Ordering::SeqCst);
                    session
                        .idle_slot_secs
                        .fetch_add(idle * 15, Ordering::SeqCst);
                    if busy == 0 {
                        tracing::warn!(
                            "FULL STARVATION: queued={queued} but 0/{num_slots} slots busy \
                             (pool={pool_len} prewarm={prewarm} bt_running={bt_running})"
                        );
                    } else if num_slots - busy >= num_slots / 2 {
                        tracing::warn!(
                            "starvation: queued={queued} busy={busy}/{num_slots} \
                             (pool={pool_len} prewarm={prewarm})"
                        );
                    }
                }
            }
            tracing::debug!(
                "snapshot: pool={pool_len} locked_projects={locked_count} \
                 bt_running={bt_running} prewarm={prewarm} \
                 busy_slots={busy}/{num_slots} queued={queued}"
            );
        }
    })
}
