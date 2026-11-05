//! Side-effects of a status tick: starvation log + overhead delta emit.

use std::sync::Arc;
use std::sync::Mutex;
use std::sync::atomic::Ordering;

use super::SessionCounters;
use super::overhead::{OverheadSnapshot, SnapshotSources, emit_delta, snapshot};

#[expect(
    clippy::cast_precision_loss,
    reason = "uptime/starv ratios; values stay below 2^53"
)]
pub(super) fn log_starvation(session: &Arc<SessionCounters>, uptime_secs: u64) {
    let starv_secs = session.starvation_secs.load(Ordering::SeqCst);
    let idle_slot_secs = session.idle_slot_secs.load(Ordering::SeqCst);
    if starv_secs == 0 {
        return;
    }
    let starv_pct = if uptime_secs > 0 {
        starv_secs as f64 * 100.0 / uptime_secs as f64
    } else {
        0.0
    };
    // Approx backtests missed: each idle slot-second is ~1/avg_runtime_s of a missed backtest
    let bts_missed = idle_slot_secs / 75;
    tracing::info!(
        "  starvation: {starv_secs}s ({starv_pct:.1}% of uptime), \
         idle_slot_secs={idle_slot_secs}, ~{bts_missed} bts missed"
    );
}

static PREV_OVERHEAD: Mutex<Option<OverheadSnapshot>> = Mutex::new(None);

pub(super) fn emit_overhead_delta(session: &Arc<SessionCounters>, num_slots: usize) {
    let curr = snapshot(&SnapshotSources {
        pool_wait: &session.pool_wait_ms,
        lock_wait: &session.lock_wait_ms,
        push: &session.push_ms,
        compile: &session.compile_ms,
        create_api: &session.create_api_ms,
        poll_tail: &session.poll_tail_ms,
        idle: &session.idle_ms,
        bt_run: &session.bt_run_ms,
        per_strategy: &session.per_strategy,
    });
    let mut prev_guard = PREV_OVERHEAD
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    let prev = prev_guard.clone().unwrap_or_default();
    emit_delta(&prev, &curr, num_slots, 60);
    *prev_guard = Some(curr);
}
