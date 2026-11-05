//! Adaptive poll-delay scheduler.

use tokio::time::Duration;

/// Returns the delay to sleep BEFORE the next poll, based on poll count
/// (1-indexed) and current progress. Adaptive tiers + progress-aware tighten.
/// `backoff_factor` multiplier allows per-task 429 elasticity.
///
/// Tightened 2026-05-06: long-tail poll dropped from 2s -> 1s, near-completion
/// threshold lowered 0.80 -> 0.50. Typical s001 spec at 75s × 1s polls = 75 polls
/// vs 38 polls before, but cuts detection lag from ~2s to ~0.5s. With 10 slots
/// at 14 specs/min × 1.5s lag savings = ~30% of node-idle gap eliminated.
///
/// 2026-05-07 PM: `poll_count`=1 sleep 200-1200ms with jitter. Restart25
/// logged 221 `qc_poll_slow` events with p50 `read_ms`=9.3s on poll=1.
/// First fix (uniform 500ms) didn't help — restart26 still saw 50 slow
/// first-polls on 27 BTs. Root cause: slots create BTs in bursts (multiple
/// completing at once), so all first-polls fire synchronized 500ms later
/// and overload QC's backend with a read-burst on fresh BTs. Jitter
/// staggers them across an 800ms window, breaking the convoy.
pub(super) fn tiered_poll_delay(poll_count: u32, progress: f64, backoff_factor: u32) -> Duration {
    // Near-completion: tighten to 0.35s
    if progress >= 0.50 {
        return Duration::from_millis(350).saturating_mul(backoff_factor);
    }
    let base_ms: u64 = if poll_count == 1 {
        // Stagger first polls to break the post-create convoy.
        140 + fastrand::u64(0..700)
    } else if poll_count <= 4 {
        350
    } else {
        700
    };
    let ms = (u128::from(base_ms) * u128::from(backoff_factor)).min(2_100);
    Duration::from_millis(ms as u64)
}
