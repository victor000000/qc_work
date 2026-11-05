//! Database queries for the status report.

use crate::db::Db;

use super::status_fmt::{RecentFailure, StrategyStatus};

fn lookup(counts: &[(String, i64)], status: &str) -> i64 {
    counts
        .iter()
        .find(|(s, _)| s == status)
        .map_or(0, |(_, c)| *c)
}

/// Gather per-strategy queue counts, experiments, and recent failures.
pub(crate) async fn gather_status(db: &Db) -> Option<(StrategyStatus, Vec<RecentFailure>)> {
    let counts = db.queue_counts().await.ok()?;
    let bt_running: i64 = db
        .call(|conn| {
            conn.query_row(
                "SELECT COUNT(*) FROM backtest_queue \
                 WHERE status='running' AND backtest_id IS NOT NULL",
                [],
                |r| r.get(0),
            )
            .map_err(Into::into)
        })
        .await
        .unwrap_or(0);
    let exp_count: i64 = db
        .call(|conn| {
            conn.query_row(
                "SELECT COUNT(*) FROM experiments WHERE status='success'",
                [],
                |r| r.get(0),
            )
            .map_err(Into::into)
        })
        .await
        .unwrap_or(0);

    let strat = StrategyStatus {
        name: db.strategy.clone(),
        queued: lookup(&counts, "queued"),
        running: lookup(&counts, "running"),
        bt_running,
        done: lookup(&counts, "done"),
        failed: lookup(&counts, "failed"),
        experiments: exp_count,
    };
    let errors = super::status_query_recent::recent_failures(db).await;
    Some((strat, errors))
}

/// Compute overhead % from recent completed jobs across all DBs.
pub(crate) async fn compute_overhead(dbs: &[Db], session_completed: u64) -> f64 {
    let mut total_wall = 0.0f64;
    let mut total_bt = 0.0f64;
    for db in dbs.iter().filter(|_| session_completed > 0) {
        let (wall, bt): (f64, f64) = db
            .call(|conn| {
                conn.query_row(
                    "SELECT
                        COALESCE(SUM(\
                            (julianday(completed_at)\
                             -julianday(started_at))*86400), 0),
                        COALESCE(SUM(runtime_seconds), 0)
                     FROM backtest_queue
                     WHERE status='done' AND runtime_seconds > 0
                       AND completed_at > \
                           datetime('now', '-10 minutes')",
                    [],
                    |r| Ok((r.get(0)?, r.get(1)?)),
                )
                .map_err(Into::into)
            })
            .await
            .unwrap_or((0.0, 0.0));
        total_wall += wall;
        total_bt += bt;
    }
    if total_wall > 0.0 {
        (total_wall - total_bt) / total_wall * 100.0
    } else {
        0.0
    }
}
