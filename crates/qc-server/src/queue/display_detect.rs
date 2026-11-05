//! Server state detection and rate-limit delay reading for CLI status.

use std::path::Path;

use duckdb::OptionalExt;

use crate::db::Db;

use super::all_dbs;

/// Detect whether the server is running from the PID file.
pub(super) async fn detect_server_state(
    data_dir: &Path,
    pid_path: &Path,
) -> (&'static str, u64, u64, f64) {
    if !pid_path.exists() {
        return ("STOPPED", 0, 0, 0.0);
    }
    let pid_str = std::fs::read_to_string(pid_path).unwrap_or_default();
    let pid: u32 = pid_str.trim().parse().unwrap_or(0);
    let alive = pid > 0 && std::path::Path::new(&format!("/proc/{pid}")).exists();
    if !alive {
        return ("STOPPED", 0, 0, 0.0);
    }

    // Uptime from PID file mtime
    let meta = std::fs::metadata(pid_path).ok();
    let uptime_secs = meta
        .and_then(|m| m.modified().ok())
        .and_then(|t| std::time::SystemTime::now().duration_since(t).ok())
        .map_or(0, |d| d.as_secs());
    let h = uptime_secs / 3600;
    let m = (uptime_secs % 3600) / 60;

    // Session throughput
    let mut session_done = 0i64;
    for (_strat, path) in &all_dbs(data_dir) {
        if !path.exists() {
            continue;
        }
        if let Ok(db) = Db::open(path, "tmp") {
            let secs = i64::try_from(uptime_secs).unwrap_or(i64::MAX);
            let n: i64 = db
                .call(move |conn| {
                    conn.query_row(
                        "SELECT COUNT(*) FROM backtest_queue
                         WHERE status IN ('done','failed') \
                         AND completed_at > \
                         datetime('now', ?1 || ' seconds')",
                        [format!("-{secs}")],
                        |r| r.get(0),
                    )
                    .map_err(Into::into)
                })
                .await
                .unwrap_or(0);
            session_done += n;
        }
    }
    let spd = if uptime_secs > 0 {
        let done_f = f64::from(u32::try_from(session_done).unwrap_or(u32::MAX));
        let secs_f = f64::from(u32::try_from(uptime_secs).unwrap_or(u32::MAX));
        done_f / (secs_f / 60.0)
    } else {
        0.0
    };
    ("RUNNING", h, m, spd)
}

/// Read the persisted rate-limit delay from the first DB.
pub(super) async fn read_rl_delay(all: &[(String, std::path::PathBuf)]) -> i64 {
    let Some((_strat, path)) = all.first() else {
        return 0;
    };
    if !path.exists() {
        return 0;
    }
    let Ok(db) = Db::open(path, "tmp") else {
        return 0;
    };
    db.call(|conn| {
        conn.query_row(
            "SELECT CAST(value AS INTEGER) FROM settings \
             WHERE category='server_state' \
             AND key='rate_limit_delay_ms'",
            [],
            |r| r.get(0),
        )
        .optional()
        .map(|o| o.unwrap_or(0))
        .map_err(Into::into)
    })
    .await
    .unwrap_or(0)
}
