//! Project locking — ensure exclusive code push per project.

use tokio::time::{Duration, sleep};

use super::SlotRunner;
use super::lock_alt::try_alternative_project;
use crate::db::{Db, QueueJob};

impl SlotRunner {
    /// Lock a project for exclusive code push.
    /// For pre-warmed jobs, the project is already locked.
    /// Returns the locked `project_id`, or None if all projects are locked.
    pub(crate) async fn lock_project(
        &self,
        project_id: i64,
        skip_if_prewarmed: bool,
        strategy: &str,
        job_name: &str,
        job: &QueueJob,
        db: &Db,
    ) -> Option<i64> {
        let lock_start = std::time::Instant::now();
        let record_lock = |session: &Option<std::sync::Arc<crate::server::SessionCounters>>| {
            if let Some(s) = session {
                let ms = u64::try_from(lock_start.elapsed().as_millis()).unwrap_or(u64::MAX);
                s.lock_wait_ms
                    .fetch_add(ms, std::sync::atomic::Ordering::SeqCst);
            }
        };
        if skip_if_prewarmed {
            record_lock(&self.session);
            return Some(project_id);
        }

        let mut locked = self.project_lock.lock().await;
        if !locked.contains(&project_id) {
            locked.insert(project_id);
            tracing::debug!(
                "slot-{}: locked project {project_id} (total locked={})",
                self.slot_id,
                locked.len()
            );
            record_lock(&self.session);
            return Some(project_id);
        }

        if let Some(alt) =
            try_alternative_project(self, &mut locked, project_id, strategy, job_name, job, db)
                .await
        {
            record_lock(&self.session);
            return Some(alt);
        }

        let pool_len = if let Some(ref p) = self.warm_pool {
            p.len().await
        } else {
            0
        };
        tracing::warn!(
            "slot-{}: IDLE — all projects locked (pool_len={pool_len}), releasing {strategy}/{job_name}; \
             likely warmer over-reserved or slot_reserve too small",
            self.slot_id,
        );
        let jid = job.id;
        let db_clone = db.clone();
        drop(locked);
        let _ = db_clone
            .call(move |conn| {
                conn.execute(
                    "UPDATE backtest_queue SET status='queued', \
                     started_at=NULL, project_id=NULL, node_id=NULL \
                     WHERE id=?1 AND status='running'",
                    [jid],
                )?;
                Ok(())
            })
            .await;
        sleep(Duration::from_millis(3500)).await;
        None
    }
}
