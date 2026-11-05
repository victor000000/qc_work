//! Cross-slot create-backtest pacer — converts bursts into a trickle and
//! pushes the whole fleet through a cooldown on rate-limit hits.

use std::time::Instant;

use tokio::time::Duration;

use super::state::RateLimitState;

impl RateLimitState {
    /// Spacing between consecutive `create_backtest` attempts. Restart9
    /// (`sem`=10, no pacer) hit 19.5/min with 151 `prep_failed`/min — slots
    /// bailed-and-retried fast. Restart12 (`sem`=6, 350ms pacer) dropped
    /// to 10.5/min because the pacer serialized submission. With the
    /// sem-rotate fix (commit 5dbafa3) preventing 33s `sem_wait` cascades
    /// during storms, the pacer's role narrows to controlling RATE only.
    /// 2026-05-08: 30ms→20ms per user direction. With backpressure caps
    /// loosened (12× hard, 8× soft) and `sem=num_slots`, tighter spacing
    /// keeps pacer non-binding for steady-state submission. 20ms = 50
    /// req/s burst tolerance experiment.
    /// 2026-05-09: 20ms→10ms per user direction.
    /// 2026-05-10: ×0.7 → 7ms (sleep-budget pass).
    const CREATE_MIN_SPACING_MS: u64 = 7;
    /// On a rate-limit hit, push the global pacer forward this far so the
    /// whole fleet pauses instead of retry-storming.
    const CREATE_BACKOFF_ON_HIT_MS: u64 = 3_500;
    /// Hard cap on future wait above `now` enforced by the pacer. Without
    /// this, successive rate-limit hits each add `CREATE_BACKOFF_ON_HIT_MS`
    /// to the deadline — restart20 observed 42s pacer waits from ~8 hits
    /// in quick succession. 10s gives QC enough recovery time without
    /// stranding slots in long single-cycle waits.
    /// 2026-05-09: 10s→5s→2s→1s→1.5s per user direction.
    /// 2026-05-10: ×0.7 → 1.05s (sleep-budget pass).
    const CREATE_MAX_COOLDOWN_MS: u64 = 1_050;

    /// Atomically read+update the create-pacer slot. Returns the duration
    /// the caller must `sleep` before firing the API call. The slot moves
    /// forward by `CREATE_MIN_SPACING_MS` on every claim — even if the
    /// caller turns out to error.
    pub(crate) fn claim_create_slot(&self) -> Duration {
        let now = Instant::now();
        let spacing = Duration::from_millis(Self::CREATE_MIN_SPACING_MS);
        let mut guard = self
            .create_pacer_until
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let earliest = *guard;
        let wait = earliest.saturating_duration_since(now);
        *guard = earliest.max(now) + spacing;
        wait
    }

    /// Push the global pacer forward when a rate-limit is observed, so
    /// every slot trying to create next must wait through the cooldown.
    /// Capped so that N rapid hits don't compound into 40+s waits — the
    /// pacer should never enforce more than `CREATE_MAX_COOLDOWN_MS` of
    /// future wait above `now`. Restart20 saw 42s pacer waits because
    /// successive hits each added 5s with no upper bound.
    pub(crate) fn record_rate_limit_hit(&self) {
        let backoff = Duration::from_millis(Self::CREATE_BACKOFF_ON_HIT_MS);
        let max_cooldown = Duration::from_millis(Self::CREATE_MAX_COOLDOWN_MS);
        let mut guard = self
            .create_pacer_until
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let now = Instant::now();
        let new_until = (*guard).max(now) + backoff;
        let cap = now + max_cooldown;
        *guard = new_until.min(cap);
    }
}
