//! `SessionCounters` — shared atomic counters for per-session metrics.

use std::sync::Mutex;
use std::sync::atomic::{AtomicI64, AtomicU64};

use super::overhead;

/// Shared session counters for the status report.
///
/// Phase counters are all in **milliseconds**. Every slot cycle
/// `fetch_add`s the measured elapsed time into the appropriate field.
/// The status loop reads them every 60s and emits a `qc::overhead`
/// debug line with deltas.
#[derive(Default)]
pub struct SessionCounters {
    pub completed: AtomicU64,
    /// Stop acquiring new work while draining existing tasks.
    pub stopping: std::sync::atomic::AtomicBool,
    /// Includes post-poll `DuckDB` collection; separate from QC node occupancy.
    pub unfinished_collects: AtomicU64,
    pub failed: AtomicU64,

    // Overhead phases (controllable by infra).
    pub pool_wait_ms: AtomicU64,
    pub lock_wait_ms: AtomicU64,
    pub push_ms: AtomicU64,
    pub compile_ms: AtomicU64,
    pub create_api_ms: AtomicU64, // just the create_backtest API call
    pub poll_tail_ms: AtomicU64,  // poll + collect duration (post create)
    pub idle_ms: AtomicU64,

    // Pipeline backpressure counter.
    pub active_collects: AtomicI64,

    // Product phase (logged but excluded from overhead totals).
    pub bt_run_ms: AtomicU64,

    // Per-strategy cycle + overhead tallies.
    pub per_strategy: dashmap::DashMap<String, overhead::StrategyCounters>,

    /// Last-known QC busy slot count, refreshed asynchronously by the
    /// status loop. `usize::MAX` = not yet populated (use local fallback).
    pub qc_busy_slots: std::sync::atomic::AtomicUsize,

    /// Cumulative seconds where queue > 0 AND `busy_slots` < `num_slots`
    /// (i.e. work was waiting but slots were idle). Incremented by the
    /// `snap_handle` 15s loop. Reported in overhead summary.
    pub starvation_secs: AtomicU64,
    /// Cumulative idle slot-seconds during starvation events
    /// (sum of (`num_slots` - `busy_slots`) * 15 per starved snapshot).
    /// Multiply by avg-throughput/60 to estimate backtests missed.
    pub idle_slot_secs: AtomicU64,

    /// Per-minute completion counter that resets at each minute boundary.
    /// Stored as `(minute_bucket, count_in_bucket)` where `minute_bucket` is
    /// `unix_secs / 60`. Used to prefix the completion log with a "this
    /// minute" sequence number rather than session-cumulative count.
    pub minute_counter: Mutex<(u64, u64)>,
}
