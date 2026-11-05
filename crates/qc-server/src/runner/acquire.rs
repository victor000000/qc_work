//! Job acquisition: try warm pool first, then fresh pick.

use std::time::Instant;

use tokio::time::{Duration, sleep};

use super::SlotRunner;
use super::acquire_pool::try_take_from_pool;
use crate::db::{Db, QueueJob};

impl SlotRunner {
    /// Try to get a job from the warm pool, or fall back to `pick_next`.
    /// Returns None if no work is available (already backs off internally).
    pub(crate) async fn acquire_job(
        &mut self,
        backoff: &Duration,
    ) -> Option<(QueueJob, Db, i64, bool, Option<String>)> {
        let acquire_start = Instant::now();
        let record_wait = |session: &Option<std::sync::Arc<crate::server::SessionCounters>>| {
            if let Some(s) = session {
                let ms = u64::try_from(acquire_start.elapsed().as_millis()).unwrap_or(u64::MAX);
                s.pool_wait_ms
                    .fetch_add(ms, std::sync::atomic::Ordering::SeqCst);
            }
        };
        // try_take_from_pool handles the no-warm-pool case (returns None
        // immediately) and the no-work case (sleeps internally). On None,
        // fall through to direct-claim.
        if self.warm_pool.is_some()
            && let Some(found) = try_take_from_pool(self, backoff).await
        {
            record_wait(&self.session);
            return Some(found);
        }

        let picked = self.pick_next().await;
        self.job_counter += 1;
        if let Some((j, d, p)) = picked {
            record_wait(&self.session);
            Some((j, d, p, false, None))
        } else {
            // trace! — redundant with `try_take_from_pool`'s upstream
            // "no queued work" debug; fires per direct-claim cycle.
            tracing::trace!(
                "slot-{}: IDLE — pick_next returned None, backing off {}s",
                self.slot_id,
                backoff.as_secs()
            );
            sleep(*backoff).await;
            None
        }
    }
}
