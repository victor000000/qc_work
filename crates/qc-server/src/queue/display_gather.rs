//! Status display: gather per-strategy counts + recent failures into one row.

use anyhow::Result;

use super::display_fmt::fmt_int;
use super::display_gather_helpers::{
    bt_running_count, count_status, done_pct, experiment_count, recent_failures, session_ok_fail,
};
use crate::db::Db;

/// Gather per-strategy queue counts, session stats, and recent failures.
pub(super) async fn gather_strategy_status(
    db: &Db,
    strategy: &str,
    uptime_secs: i64,
) -> Result<(i64, i64, String, Vec<(String, String)>)> {
    let counts = db.queue_counts().await?;
    let queued = count_status(&counts, "queued");
    let running = count_status(&counts, "running");
    let done = count_status(&counts, "done");
    let failed = count_status(&counts, "failed");

    let exp_count = experiment_count(db).await;
    let (s_ok, s_fail) = session_ok_fail(db, uptime_secs).await;
    let pct = done_pct(done, done + failed);
    let bt_running = bt_running_count(db).await;

    let r_display = if bt_running < running {
        format!("{bt_running}/{running}")
    } else {
        format!("{running}")
    };
    let line = format!(
        "\u{2502}  {strategy:<5}  queued {queued:>4}  running {r_display:<6}  \
         done {done_s:>9}  failed {failed_s:>5}  experiments {exp_s:>8}  {pct:>5.1}%",
        done_s = fmt_int(done),
        failed_s = fmt_int(failed),
        exp_s = fmt_int(exp_count),
    );

    let recent_fails = recent_failures(db).await;
    Ok((s_ok, s_fail, line, recent_fails))
}
