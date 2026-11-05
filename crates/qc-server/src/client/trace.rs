//! Per-call timing + status tracing for QC API requests.
//!
//! Every request flows through `traced_call`, which logs at debug level:
//! `qc_api_call path=... method=... status=... elapsed_ms=... attempt=...`
//!
//! Enable with `RUST_LOG=qc::api=debug` to crack QC API behavior:
//! - which endpoints are slow (`elapsed_ms`)
//! - which return non-2xx (`status`)
//! - retry pressure (`attempt > 0`)
//! - bucket-band traffic mix (`qc_api_band ...`)
//!
//! Reminder: QC node `busy=true` ONLY during the bt-run phase. All API calls
//! around `create_backtest` / `read_backtest` / `push_files` / `compile` are *node-idle*
//! phases — server-side latency on these calls directly costs node-idle time.

use std::time::Instant;

/// Pick a coarse latency band for a single call. Used in log lines so a
/// quick `grep band=slow` finds the regressed-API events without parsing
/// `elapsed_ms` numerically.
fn latency_band(ms: u128) -> &'static str {
    match ms {
        0..=200 => "fast",        // <=200ms — typical happy path
        201..=1_000 => "ok",      // 200ms-1s — normal QC variance
        1_001..=3_000 => "warn",  // 1-3s — backend pressure or queueing
        3_001..=10_000 => "slow", // 3-10s — investigate
        _ => "veryslow",          // >10s — node-idle penalty
    }
}

/// Trace a single QC API call: log start (trace), measure, log result (debug).
/// Returns the inner Future's output unchanged.
#[inline]
pub(super) async fn traced_call<F, Fut, T>(path: &str, method: &str, attempt: usize, op: F) -> T
where
    F: FnOnce() -> Fut,
    Fut: std::future::Future<Output = T>,
{
    let start = Instant::now();
    tracing::trace!(target: "qc::api", "qc_api_start path={path} method={method} attempt={attempt}");
    let out = op().await;
    let elapsed_ms = start.elapsed().as_millis();
    let band = latency_band(elapsed_ms);
    // Happy-path calls (band fast|ok) fire ~30+/sec and overwhelm qc_full.log;
    // demote those to trace! and keep slow bands at debug so `grep band=slow`
    // still finds the regressed-API events without parsing `elapsed_ms`.
    if matches!(band, "fast" | "ok") {
        tracing::trace!(
            target: "qc::api",
            "qc_api_call path={path} method={method} attempt={attempt} elapsed_ms={elapsed_ms} band={band}"
        );
    } else {
        tracing::debug!(
            target: "qc::api",
            "qc_api_call path={path} method={method} attempt={attempt} elapsed_ms={elapsed_ms} band={band}"
        );
    }
    // 2026-05-07: was INFO. Demoted to debug so debug-disabled runs stay quiet.
    // Operators wanting slow-call alerts should run with `RUST_LOG=qc::api=debug`
    // and `grep band=slow` or `band=veryslow`.
    if elapsed_ms > 5_000 {
        tracing::debug!(
            target: "qc::api",
            "qc_api_slow path={path} method={method} elapsed_ms={elapsed_ms} band={band} (>5000ms)"
        );
    }
    out
}
