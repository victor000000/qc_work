//! Per-phase and per-strategy overhead counters.
//!
//! All times are tracked in milliseconds via `AtomicU64::fetch_add`.
//! The status loop reads these counters every 60s, diffs them against
//! the previous snapshot, and emits a DEBUG line on the `qc::overhead`
//! target.

mod delta;

pub use delta::emit_delta;

use std::sync::atomic::{AtomicU64, Ordering};

use dashmap::DashMap;

/// Per-strategy cycle and overhead totals.
///
/// `cycles` counts completed slot cycles for that strategy.
/// `overhead_ms` is the summed overhead (excluding `bt_run`) across those cycles.
#[derive(Default, Debug)]
pub struct StrategyCounters {
    pub cycles: AtomicU64,
    pub overhead_ms: AtomicU64,
}

impl StrategyCounters {
    pub fn record(&self, overhead_ms: u64) {
        self.cycles.fetch_add(1, Ordering::SeqCst);
        self.overhead_ms.fetch_add(overhead_ms, Ordering::SeqCst);
    }
}

/// Snapshot of all overhead counters at a single instant. Used by the
/// status loop to compute deltas between ticks.
#[derive(Default, Debug, Clone)]
pub struct OverheadSnapshot {
    pub pool_wait_ms: u64,
    pub lock_wait_ms: u64,
    pub push_ms: u64,
    pub compile_ms: u64,
    pub create_api_ms: u64,
    pub poll_tail_ms: u64,
    pub idle_ms: u64,
    pub bt_run_ms: u64,
    pub per_strategy: Vec<(String, u64, u64)>, // (name, cycles, overhead_ms)
}

/// Bundled sources for building a snapshot from live counters.
pub struct SnapshotSources<'a> {
    pub pool_wait: &'a AtomicU64,
    pub lock_wait: &'a AtomicU64,
    pub push: &'a AtomicU64,
    pub compile: &'a AtomicU64,
    pub create_api: &'a AtomicU64,
    pub poll_tail: &'a AtomicU64,
    pub idle: &'a AtomicU64,
    pub bt_run: &'a AtomicU64,
    pub per_strategy: &'a DashMap<String, StrategyCounters>,
}

/// Build a fresh snapshot from the live counters (caller owns the
/// reference; this function does not mutate).
#[must_use]
pub fn snapshot(sources: &SnapshotSources<'_>) -> OverheadSnapshot {
    let mut rows: Vec<(String, u64, u64)> = sources
        .per_strategy
        .iter()
        .map(|e| {
            (
                e.key().clone(),
                e.value().cycles.load(Ordering::SeqCst),
                e.value().overhead_ms.load(Ordering::SeqCst),
            )
        })
        .collect();
    rows.sort_by(|a, b| a.0.cmp(&b.0));
    OverheadSnapshot {
        pool_wait_ms: sources.pool_wait.load(Ordering::SeqCst),
        lock_wait_ms: sources.lock_wait.load(Ordering::SeqCst),
        push_ms: sources.push.load(Ordering::SeqCst),
        compile_ms: sources.compile.load(Ordering::SeqCst),
        create_api_ms: sources.create_api.load(Ordering::SeqCst),
        poll_tail_ms: sources.poll_tail.load(Ordering::SeqCst),
        idle_ms: sources.idle.load(Ordering::SeqCst),
        bt_run_ms: sources.bt_run.load(Ordering::SeqCst),
        per_strategy: rows,
    }
}
