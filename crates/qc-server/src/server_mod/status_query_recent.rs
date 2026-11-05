//! Recent-failures query, used by the periodic status box.

use crate::db::Db;

use super::status_fmt::RecentFailure;

pub(super) async fn recent_failures(db: &Db) -> Vec<RecentFailure> {
    let rows: Vec<(String, String)> = db
        .call(|conn| {
            let mut stmt = conn.prepare(
                "SELECT name, error_message FROM backtest_queue
                 WHERE status='failed' \
                 AND completed_at > datetime('now', '-5 minutes')
                 ORDER BY completed_at DESC LIMIT 3",
            )?;
            let rows = stmt
                .query_map([], |row| {
                    Ok((
                        row.get::<_, String>(0)?,
                        row.get::<_, Option<String>>(1)?.unwrap_or_default(),
                    ))
                })?
                .collect::<Result<Vec<_>, _>>()?;
            Ok(rows)
        })
        .await
        .unwrap_or_default();
    rows.into_iter()
        .map(|(name, error)| RecentFailure { name, error })
        .collect()
}
