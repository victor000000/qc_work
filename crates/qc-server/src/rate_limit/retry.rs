//! Rate-limit detection + retry-with-backoff wrapper.

use std::future::Future;
use std::time::Instant;

use anyhow::Result;
use tokio::time::{Duration, sleep};

use super::state::RateLimitState;

/// Check if an error looks like a rate limit (HTTP 429 or "rate limit" in message).
pub(crate) fn is_rate_limit(e: &anyhow::Error) -> bool {
    let msg = format!("{e:?}").to_lowercase();
    msg.contains("429")
        || msg.contains("rate limit")
        || msg.contains("rate_limit")
        || msg.contains("too many")
        || msg.contains("slow down")
}

/// Retry an async operation on rate limit, using adaptive backoff from shared state.
/// If `rl_state` is None, uses fixed exponential backoff.
pub(crate) async fn retry_on_rate_limit<F, Fut, T>(
    rl_state: Option<&RateLimitState>,
    max_retries: usize,
    mut f: F,
) -> Result<T>
where
    F: FnMut() -> Fut,
    Fut: Future<Output = Result<T>>,
{
    let mut attempt = 0;
    loop {
        let start = Instant::now();
        match f().await {
            Ok(v) => return Ok(v),
            Err(e) if is_rate_limit(&e) && attempt < max_retries => {
                attempt += 1;
                let delay_ms = rl_state.map_or_else(
                    || 210 * (1 << attempt), // Fixed exponential: 0.42s, 0.84s, 1.68s
                    |rls| (rls.get_delay() * attempt as u64).max(350), // Adaptive: min 350ms
                );
                // Add jitter to avoid thundering herd (10 slots hitting simultaneously)
                let jitter = fastrand::u64(0..=(delay_ms / 3));
                let delay = Duration::from_millis((delay_ms + jitter).min(5_600));
                tracing::debug!(
                    target: "qc::api",
                    "qc_rate_limit_retry attempt={attempt}/{max_retries} delay_ms={} jitter_ms={jitter} cap_5_6s",
                    delay.as_millis()
                );
                sleep(delay).await;
                // Record actual wait when we eventually succeed
                if let Some(rls) = rl_state {
                    rls.record_wait(u64::try_from(start.elapsed().as_millis()).unwrap_or(u64::MAX));
                }
            }
            Err(e) => return Err(e),
        }
    }
}
