//! Warm pool helpers: check for work, lock projects, claim jobs, requeue.

use crate::db::{Db, QueueJob};
use crate::runner::ProjectLock;

/// A successfully claimed job with its effective project ID.
pub(crate) struct ClaimedJob {
    pub job: QueueJob,
    pub project_id: i64,
}

pub(crate) async fn strategy_has_work(db: &Db, name_prefix: Option<&str>) -> bool {
    let prefix = name_prefix.map(str::to_owned);
    db.call(move |conn| {
        let n: i64 = match &prefix {
            Some(p) => conn.query_row(
                "SELECT COUNT(*) FROM backtest_queue \
                 WHERE status='queued' AND name LIKE ?1 LIMIT 1",
                [format!("{p}%")],
                |r| r.get(0),
            )?,
            None => conn.query_row(
                "SELECT COUNT(*) FROM backtest_queue \
                 WHERE status='queued' LIMIT 1",
                [],
                |r| r.get(0),
            )?,
        };
        Ok(n > 0)
    })
    .await
    .unwrap_or(false)
}

pub(crate) async fn lock_free_project(
    project_lock: &ProjectLock,
    project_ids: &[i64],
    counter: usize,
) -> Option<i64> {
    let mut locked = project_lock.lock().await;
    for offset in 0..project_ids.len() {
        let idx = (counter + offset) % project_ids.len();
        let candidate = project_ids[idx];
        if !locked.contains(&candidate) {
            locked.insert(candidate);
            return Some(candidate);
        }
    }
    None
}

pub(crate) async fn claim_job(
    db: &Db,
    project_lock: &ProjectLock,
    project_id: i64,
    name_prefix: Option<&str>,
    project_ids: &[i64],
    counter: usize,
) -> Option<(QueueJob, i64)> {
    let node_tag = format!("warm-pool-{counter}");
    let pids = project_ids.to_vec();
    let claim = db
        .claim_next_job_with_pool(&node_tag, project_id, name_prefix, &pids)
        .await;

    let Ok(Some((job, effective_pid))) = claim else {
        project_lock.lock().await.remove(&project_id);
        return None;
    };

    // Handle effective_pid mismatch
    if effective_pid == project_id {
        Some((job, project_id))
    } else {
        // Decide outcome under the lock, then drop it before any async
        // work (requeue_job hits DuckDB). Holding the project_lock across
        // a DB roundtrip would block other warmers/slots needlessly.
        let needs_requeue = {
            let mut locked = project_lock.lock().await;
            locked.remove(&project_id);
            if locked.contains(&effective_pid) {
                true
            } else {
                locked.insert(effective_pid);
                false
            }
        };
        if needs_requeue {
            requeue_job(db, job.id).await;
            return None;
        }
        Some((job, effective_pid))
    }
}

pub(crate) async fn requeue_job(db: &Db, job_id: i64) {
    let _ = db
        .call(move |conn| {
            conn.execute(
                "UPDATE backtest_queue SET status='queued', \
                 started_at=NULL, project_id=NULL, node_id=NULL WHERE id=?1",
                [job_id],
            )?;
            Ok(())
        })
        .await;
}
