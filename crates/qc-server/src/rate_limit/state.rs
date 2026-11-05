//! Adaptive rate-limit state: persisted EMA backoff + cross-slot pacer.

use std::sync::{Arc, Mutex};
use std::time::Instant;

use crate::db::Db;

/// Shared adaptive rate-limit state for the real server.
/// Persisted to the first strategy DB on update so restarts don't start cold.
#[derive(Clone)]
pub struct RateLimitState {
    /// Learned backoff delay in ms (exponential moving average).
    pub estimated_delay_ms: Arc<std::sync::atomic::AtomicU64>,
    /// Earliest instant any slot is allowed to fire its NEXT
    /// `create_backtest`. Acts as a global pacer to convert bursts into a
    /// trickle. Bumped forward by the spacing on each successful gate, and
    /// pushed further forward when a rate-limit error is observed (so the
    /// entire fleet backs off, not just the failing slot).
    pub create_pacer_until: Arc<Mutex<Instant>>,
}

impl RateLimitState {
    /// Load from DB or use default.
    pub async fn load(db: &Db) -> Self {
        let saved = db
            .get_setting("server_state", "rate_limit_delay_ms")
            .await
            .ok()
            .flatten()
            .and_then(|v| v.parse::<u64>().ok())
            .unwrap_or(1000); // default 1s
        tracing::info!("rate limit backoff loaded: {saved}ms");
        Self {
            estimated_delay_ms: Arc::new(std::sync::atomic::AtomicU64::new(saved)),
            create_pacer_until: Arc::new(Mutex::new(Instant::now())),
        }
    }

    /// Save current state to DB.
    pub async fn save(&self, db: &Db) {
        let val = self
            .estimated_delay_ms
            .load(std::sync::atomic::Ordering::Relaxed);
        let _ = db
            .set_setting("server_state", "rate_limit_delay_ms", &val.to_string())
            .await;
    }

    pub(crate) fn get_delay(&self) -> u64 {
        self.estimated_delay_ms
            .load(std::sync::atomic::Ordering::Relaxed)
    }

    /// Update estimate after a rate-limit + successful retry.
    pub(crate) fn record_wait(&self, actual_ms: u64) {
        let old = self
            .estimated_delay_ms
            .load(std::sync::atomic::Ordering::Relaxed);
        // EMA: 70% old, 30% new
        let new = (old * 7 + actual_ms * 3) / 10;
        self.estimated_delay_ms
            .store(new.max(100), std::sync::atomic::Ordering::Relaxed);
    }
}
