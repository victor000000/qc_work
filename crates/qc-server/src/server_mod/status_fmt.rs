//! Status report data types + the small `fmt_int` helper.
//!
//! The renderer lives in `status_fmt_render.rs`. Re-exported here so external
//! callers can still write `use server_mod::status_fmt::format_status_report`.

pub use super::status_fmt_render::format_status_report;

pub struct StrategyStatus {
    pub name: String,
    pub queued: i64,
    pub running: i64,
    /// Jobs in backtest phase (has `backtest_id`). Pre-warm jobs are running - `bt_running`.
    pub bt_running: i64,
    pub done: i64,
    pub failed: i64,
    pub experiments: i64,
}

pub struct RecentFailure {
    pub name: String,
    pub error: String,
}

pub struct StatusReport {
    pub state: &'static str,
    pub uptime_secs: u64,
    pub throughput: f64,
    pub session_completed: u64,
    pub session_failed: u64,
    pub overhead_pct: f64,
    pub strategies: Vec<StrategyStatus>,
    pub recent_errors: Vec<RecentFailure>,
    /// Distinct slot `node_ids` holding any 'running' job — true slot occupancy.
    pub busy_slots: usize,
    /// Total slot count (so display can read X/N busy).
    pub total_slots: usize,
}

pub(super) fn fmt_int(n: i64) -> String {
    let neg = n < 0;
    let s = n.unsigned_abs().to_string();
    let bytes = s.as_bytes();
    let len = bytes.len();
    let mut out = String::with_capacity(len + len / 3 + 1);
    if neg {
        out.push('-');
    }
    for (i, &b) in bytes.iter().enumerate() {
        if i > 0 && (len - i).is_multiple_of(3) {
            out.push(',');
        }
        out.push(b as char);
    }
    out
}
