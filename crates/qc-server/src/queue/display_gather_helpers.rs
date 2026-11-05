//! Tiny query helpers for the status display.

use anyhow::Result;

use crate::db::Db;

pub(super) fn count_status(counts: &[(String, i64)], status: &str) -> i64 {
    counts
        .iter()
        .find(|(s, _)| s == status)
        .map_or(0, |(_, c)| *c)
}

pub(super) async fn experiment_count(db: &Db) -> i64 {
    db.call(|conn| {
        conn.query_row(
            "SELECT COUNT(*) FROM experiments WHERE status='success'",
            [],
            |r| r.get(0),
        )
        .map_err(Into::into)
    })
    .await
    .unwrap_or(0)
}

pub(super) async fn session_ok_fail(db: &Db, uptime_secs: i64) -> (i64, i64) {
    db.call(move |conn| {
        let ok: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM backtest_queue \
                 WHERE status='done' \
                 AND completed_at > datetime('now', ?1 || ' seconds')",
                [format!("-{uptime_secs}")],
                |r| r.get(0),
            )
            .unwrap_or(0);
        let fail: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM backtest_queue \
                 WHERE status='failed' \
                 AND completed_at > datetime('now', ?1 || ' seconds')",
                [format!("-{uptime_secs}")],
                |r| r.get(0),
            )
            .unwrap_or(0);
        Ok((ok, fail))
    })
    .await
    .unwrap_or((0, 0))
}

pub(super) fn done_pct(done: i64, total: i64) -> f64 {
    if total <= 0 {
        return 0.0;
    }
    let done_f = f64::from(u32::try_from(done).unwrap_or(u32::MAX));
    let total_f = f64::from(u32::try_from(total).unwrap_or(u32::MAX));
    done_f / total_f * 100.0
}

pub(super) async fn bt_running_count(db: &Db) -> i64 {
    db.call(|conn| {
        conn.query_row(
            "SELECT COUNT(*) FROM backtest_queue \
             WHERE status='running' AND backtest_id IS NOT NULL",
            [],
            |r| r.get(0),
        )
        .map_err(Into::into)
    })
    .await
    .unwrap_or(0)
}

pub(super) async fn recent_failures(db: &Db) -> Vec<(String, String)> {
    db.call(|conn| {
        let mut stmt = conn.prepare(
            "SELECT name, COALESCE(error_message, '') FROM backtest_queue \
             WHERE status='failed' \
             ORDER BY completed_at DESC LIMIT 4",
        )?;
        let rows = stmt
            .query_map([], |row| Ok((row.get(0)?, row.get(1)?)))?
            .collect::<Result<Vec<_>, _>>()?;
        Ok(rows)
    })
    .await
    .unwrap_or_default()
}
