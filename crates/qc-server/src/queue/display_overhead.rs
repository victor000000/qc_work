//! Compute overhead percentage from recent completed jobs.

use std::path::Path;

use crate::db::Db;

use super::all_dbs;

/// Compute overhead percentage from recent completed jobs.
pub(super) async fn compute_overhead_pct(data_dir: &Path) -> f64 {
    let Some((_strat, path)) = all_dbs(data_dir).first().cloned() else {
        return 0.0;
    };
    if !path.exists() {
        return 0.0;
    }
    let Ok(db) = Db::open(&path, "tmp") else {
        return 0.0;
    };
    db.call(|conn| {
        conn.query_row(
            "SELECT COALESCE(
                (SELECT ROUND(
                    AVG((julianday(completed_at)\
                         -julianday(started_at))*86400 \
                         - runtime_seconds)
                    / NULLIF(AVG((julianday(completed_at)\
                                  -julianday(started_at))*86400), 0) \
                    * 100, 1)
                 FROM backtest_queue
                 WHERE status='done' AND runtime_seconds > 0
                   AND completed_at > datetime('now', '-10 minutes')),
                0.0)",
            [],
            |r| r.get(0),
        )
        .map_err(Into::into)
    })
    .await
    .unwrap_or(0.0)
}
