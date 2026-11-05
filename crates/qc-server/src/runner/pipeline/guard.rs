//! RAII guard for `session.active_collects`.

use std::sync::Arc;
use std::sync::atomic::Ordering;

use crate::server::SessionCounters;

/// RAII guard for `session.active_collects`. Increments on construction,
/// decrements on drop (handles panic, cancellation, early return).
///
/// Semantics: `active_collects` counts backtests *currently executing on a
/// QC node* (= polling phase only). Decremented as soon as the poll loop
/// returns — at that point QC has marked the bt completed and the node is
/// free for the next backtest. Post-poll work (`collect_from_response`,
/// DB writes) does NOT count, since it doesn't hold a QC node.
///
/// Earlier version held the guard for the whole `poll_and_collect` task,
/// which made `active_collects` track total in-flight work (poll+collect).
/// That kept the backpressure cap pinned for ~100s after each bt finished,
/// blocking slot loops from creating new bts and leaving QC nodes idle for
/// 90+ second windows. See `release_after_poll` helper and `run_loop.rs`
/// backpressure block.
pub(crate) struct ActiveCollectsGuard {
    session: Option<Arc<SessionCounters>>,
    released: bool,
}

impl ActiveCollectsGuard {
    pub(crate) fn new(session: Option<Arc<SessionCounters>>) -> Self {
        if let Some(ref s) = session {
            s.active_collects.fetch_add(1, Ordering::SeqCst);
            s.unfinished_collects.fetch_add(1, Ordering::SeqCst);
        }
        Self {
            session,
            released: false,
        }
    }

    pub(crate) fn current(&self) -> i64 {
        self.session
            .as_ref()
            .map_or(0, |s| s.active_collects.load(Ordering::SeqCst))
    }

    /// Decrement the counter early — once the poll loop returns, QC is done
    /// with this backtest and the node is free. Idempotent: subsequent calls
    /// (and Drop) are no-ops once released.
    pub(crate) fn release_after_poll(&mut self) {
        if self.released {
            return;
        }
        if let Some(ref s) = self.session {
            s.active_collects.fetch_sub(1, Ordering::SeqCst);
        }
        self.released = true;
    }
}

impl Drop for ActiveCollectsGuard {
    fn drop(&mut self) {
        self.release_after_poll();
        if let Some(ref s) = self.session {
            s.unfinished_collects.fetch_sub(1, Ordering::SeqCst);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn node_release_keeps_collection_count_until_db_work_finishes() {
        let session = Arc::new(SessionCounters::default());
        let mut guard = ActiveCollectsGuard::new(Some(Arc::clone(&session)));
        assert_eq!(session.active_collects.load(Ordering::SeqCst), 1);
        assert_eq!(session.unfinished_collects.load(Ordering::SeqCst), 1);
        guard.release_after_poll();
        guard.release_after_poll();
        assert_eq!(session.active_collects.load(Ordering::SeqCst), 0);
        assert_eq!(session.unfinished_collects.load(Ordering::SeqCst), 1);
        drop(guard);
        assert_eq!(session.unfinished_collects.load(Ordering::SeqCst), 0);
    }
}
