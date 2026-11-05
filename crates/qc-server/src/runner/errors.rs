//! Error handling for backtest prep failures.

use tokio::time::{Duration, sleep};

use super::SlotRunner;
use crate::db::{Db, QueueJob};

impl SlotRunner {
    /// Handle backtest errors — requeue transient, mark permanent.
    pub(crate) async fn handle_backtest_error(
        &self,
        error: anyhow::Error,
        strategy: &str,
        job_name: &str,
        job: &QueueJob,
        db: &Db,
        elapsed: f64,
    ) {
        let err_str = format!("{error}");

        let is_transient = err_str.contains("no spare nodes")
            || err_str.contains("No spare nodes")
            || (err_str.contains("rate_limit") && err_str.contains("Too many"));

        if is_transient {
            // 2s backoff: balances QC node-release lag (~2-5s) against
            // visible slot-idle time. 1s was too short (slot churned
            // through next jobs hitting same wall); 5s wasted total
            // ~800s/day of slot time without changing the no-spare rate.
            // Jitter 0-1000ms breaks 8-slot synchronization after burst
            // rate-limit hits — without it slots converge on the same
            // post-cooldown moment and retrigger the storm (126K/day).
            let jitter_ms = fastrand::u64(0..=1000);
            tracing::debug!(
                "slot-{}: {}/{} — transient error, requeuing + 2s backoff \
                 (+{jitter_ms}ms jitter, {elapsed:.1}s): {err_str}",
                self.slot_id,
                strategy,
                job_name
            );
            let jid = job.id;
            let db_clone = db.clone();
            let _ = db_clone
                .call(move |conn| {
                    conn.execute(
                        "UPDATE backtest_queue SET status='queued', \
                         started_at=NULL, project_id=NULL, compile_id=NULL, node_id=NULL, backtest_id=NULL \
                         WHERE id=?1",
                        [jid],
                    )?;
                    Ok(())
                })
                .await;
            sleep(Duration::from_millis(1400 + jitter_ms)).await;
        } else {
            tracing::error!(
                "slot-{}: {}/{} failed after {elapsed:.1}s: {error}",
                self.slot_id,
                strategy,
                job_name
            );
            let _ = db.mark_failed(job.id, &err_str, None).await;
            if let Some(s) = &self.session {
                s.failed.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
            }
        }
    }
}
