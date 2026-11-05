//! Per-cycle phase-counter snapshot + per-strategy overhead recording.
//!
//! Note 2026-05-07: per-cycle phase breakdown is now logged directly from
//! `prep_backtest` using locally-measured durations. The global atomic
//! counters here remain — they back the periodic overhead summary in
//! `server_mod::overhead` which is correct at long-run scope.

use std::sync::Arc;
use std::sync::atomic::Ordering;

use crate::server::SessionCounters;

/// Snapshot of monotonic phase counters at cycle start.
pub(super) type PhaseSnapshot = (u64, u64, u64, u64, u64);

pub(super) fn snapshot_phases(session: Option<&Arc<SessionCounters>>) -> Option<PhaseSnapshot> {
    session.map(|s| {
        (
            s.pool_wait_ms.load(Ordering::SeqCst),
            s.lock_wait_ms.load(Ordering::SeqCst),
            s.push_ms.load(Ordering::SeqCst),
            s.compile_ms.load(Ordering::SeqCst),
            s.create_api_ms.load(Ordering::SeqCst),
        )
    })
}

/// Release a project lock and emit the pipeline-handoff debug log.
pub(super) async fn release_project_lock(
    project_lock: &crate::runner::ProjectLock,
    slot_id: usize,
    project_id: i64,
) {
    // Snapshot under the lock, then drop before formatting + emitting
    // the debug line. Otherwise the lock is held across the entire
    // tracing macro expansion (format_args + subscriber I/O on the
    // `qc::pipeline` target), serializing all slot release events.
    let (existed, remaining) = {
        let mut locked = project_lock.lock().await;
        let existed = locked.remove(&project_id);
        (existed, locked.len())
    };
    tracing::debug!(
        target: "qc::pipeline",
        "slot-{slot_id}: project_released project={project_id} was_locked={existed} remaining_locks={remaining} (pipeline handoff)"
    );
}

/// Log the cycle-completion summary line.
pub(super) fn log_cycle_done(
    slot_id: usize,
    cycle_ms: u128,
    pick_ms: u128,
    prep_ms: u128,
    strategy: &str,
    job_name: &str,
) {
    let bt_plus_collect_ms = cycle_ms.saturating_sub(pick_ms).saturating_sub(prep_ms);
    tracing::debug!(
        target: "qc::pipeline",
        "slot-{slot_id}: cycle_done total={cycle_ms}ms pick={pick_ms}ms prep={prep_ms}ms bt_plus_collect={bt_plus_collect_ms}ms (node-busy ≈ bt_plus_collect minus collect lag) {strategy}/{job_name}"
    );
}

/// Bump the per-strategy global counter (still used by the periodic overhead
/// summary). Phase deltas read from atomics — accurate at the long-run summary
/// scope, NOT at per-cycle scope.
pub(super) fn record_strategy_cycle(
    session: Option<&Arc<SessionCounters>>,
    snap: Option<PhaseSnapshot>,
    strategy: &str,
) {
    let (Some(s), Some(snap)) = (session, snap) else {
        return;
    };
    let pool_d = s.pool_wait_ms.load(Ordering::SeqCst) - snap.0;
    let lock_d = s.lock_wait_ms.load(Ordering::SeqCst) - snap.1;
    let push_d = s.push_ms.load(Ordering::SeqCst) - snap.2;
    let comp_d = s.compile_ms.load(Ordering::SeqCst) - snap.3;
    let cap_d = s.create_api_ms.load(Ordering::SeqCst) - snap.4;
    let cycle_overhead_ms = pool_d + lock_d + push_d + comp_d + cap_d;
    let entry = s.per_strategy.entry(strategy.to_string()).or_default();
    entry.record(cycle_overhead_ms);
}
