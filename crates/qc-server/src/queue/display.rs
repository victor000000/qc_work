use std::path::Path;

use anyhow::Result;

use crate::db::Db;

use super::all_dbs;
use super::display_box::{BoxRenderParams, print_status_box};
use super::display_detect::{detect_server_state, read_rl_delay};
use super::display_gather::gather_strategy_status;
use super::display_overhead::compute_overhead_pct;

/// Show queue status summary in box format matching server's periodic output.
///
/// # Errors
/// Returns `Err` on SQL execution error or if a strategy database fails to open.
pub async fn status(data_dir: &Path) -> Result<()> {
    // Detect server state from PID file
    let pid_path = data_dir.join("qc-server.pid");
    let (state, uptime_h, uptime_m, speed) = detect_server_state(data_dir, &pid_path).await;

    // Read rl_backoff from first DB
    let all = all_dbs(data_dir);
    let _rl_delay: i64 = read_rl_delay(&all).await;

    // Count session ok/fail from all DBs
    let mut session_ok = 0i64;
    let mut session_fail = 0i64;
    let pid_path2 = data_dir.join("qc-server.pid");
    let uptime_secs = if pid_path2.exists() {
        std::fs::metadata(&pid_path2)
            .ok()
            .and_then(|m| m.modified().ok())
            .and_then(|t| std::time::SystemTime::now().duration_since(t).ok())
            .map_or(0, |d| i64::try_from(d.as_secs()).unwrap_or(i64::MAX))
    } else {
        0
    };

    // Gather per-strategy lines and recent errors
    let mut strat_lines = Vec::new();
    let mut error_lines_raw: Vec<(String, String)> = Vec::new();

    for (strategy, path) in &all_dbs(data_dir) {
        if !path.exists() {
            continue;
        }
        let db = Db::open(path, strategy)?;

        let (s_ok, s_fail, line, fails) =
            gather_strategy_status(&db, strategy, uptime_secs).await?;
        session_ok += s_ok;
        session_fail += s_fail;
        strat_lines.push(line);
        error_lines_raw.extend(fails);
    }

    // Compute overhead % from recent jobs
    let overhead_pct = compute_overhead_pct(data_dir).await;

    // Build the box
    print_status_box(&BoxRenderParams {
        state,
        uptime_h,
        uptime_m,
        speed,
        session_ok,
        session_fail,
        overhead_pct,
        strat_lines: &strat_lines,
        error_lines_raw: &error_lines_raw,
    });

    Ok(())
}
