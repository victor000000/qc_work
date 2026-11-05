//! Warm-pool take helpers used by `acquire_job`.
//!
//! Returns `Some` if we got a warm entry (and rewrote its `node_id`),
//! `None` if the caller should fall through to direct-claim. The "no work
//! anywhere → long backoff" path also returns `None` after sleeping.

use std::time::Instant;

use tokio::time::{Duration, sleep};

use super::SlotRunner;
use crate::db::{Db, QueueJob};
use crate::pool::WarmEntry;

pub(super) async fn try_take_from_pool(
    runner: &SlotRunner,
    backoff: &Duration,
) -> Option<(QueueJob, Db, i64, bool, Option<String>)> {
    let pool = runner.warm_pool.as_ref()?;
    if let Some(we) = pool.take().await {
        return Some(claim_warm_entry(runner, we).await);
    }
    if !runner.any_queued_work().await {
        tracing::debug!(
            "slot-{}: IDLE — no queued work in any DB, backing off {}s",
            runner.slot_id,
            backoff.as_secs()
        );
        sleep(*backoff).await;
        return None;
    }
    // Pool empty but work exists. Brief 1s window for warmer to deliver an
    // entry; then fall through so direct-claim can race in parallel with
    // warmer finishing.
    let wait_start = Instant::now();
    for attempt in 0..4 {
        sleep(Duration::from_millis(175)).await;
        if let Some(we) = pool.take().await {
            tracing::debug!(
                "slot-{}: warm entry arrived after {}ms (attempt {})",
                runner.slot_id,
                wait_start.elapsed().as_millis(),
                attempt + 1
            );
            return Some(claim_warm_entry(runner, we).await);
        }
    }
    tracing::debug!(
        "slot-{}: pool empty after 1s wait (len={}), falling to direct-claim",
        runner.slot_id,
        pool.len().await
    );
    None
}

/// Rewrite the warm entry's `node_id` to `slot-<id>` so status-query
/// counts of `slot-%` running rows correctly attribute pool-launched jobs.
async fn claim_warm_entry(
    runner: &SlotRunner,
    we: WarmEntry,
) -> (QueueJob, Db, i64, bool, Option<String>) {
    let jid = we.job.id;
    let slot_tag = format!("slot-{}", runner.slot_id);
    let _ = we
        .db
        .call(move |conn| {
            conn.execute(
                "UPDATE backtest_queue SET node_id=?1 \
                 WHERE id=?2 AND status='running'",
                duckdb::params![slot_tag, jid],
            )?;
            Ok(())
        })
        .await;
    let cid = we.compile_id.clone();
    (we.job, we.db, we.project_id, true, Some(cid))
}
