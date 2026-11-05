//! Remove old done/failed/cancelled queue entries.

use std::path::Path;

use anyhow::Result;

use super::strategy_targets;
use crate::db::Db;

/// Remove old done/failed/cancelled entries from the queue table.
///
/// # Errors
/// Returns `Err` on SQL execution error.
pub async fn clean(
    data_dir: &Path,
    strategy: Option<&str>,
    older_than_days: i64,
    include_cancelled: bool,
    dry_run: bool,
) -> Result<()> {
    let targets = strategy_targets(data_dir, strategy)?;

    for (strat, path) in &targets {
        if !path.exists() {
            continue;
        }
        let db = Db::open(path, strat)?;
        let days = older_than_days;
        let with_cancelled = include_cancelled;

        let (count, deleted): (i64, usize) = db
            .call(move |conn| {
                let statuses = if with_cancelled {
                    "('done','failed','cancelled')"
                } else {
                    "('done','failed')"
                };
                let where_clause = format!(
                    "status IN {statuses} \
                     AND completed_at < \
                     datetime('now', '-{days} days')"
                );
                let count: i64 = conn.query_row(
                    &format!(
                        "SELECT COUNT(*) FROM backtest_queue \
                         WHERE {where_clause}"
                    ),
                    [],
                    |r| r.get(0),
                )?;
                let deleted = if dry_run {
                    0
                } else {
                    conn.execute(
                        &format!(
                            "DELETE FROM backtest_queue \
                             WHERE {where_clause}"
                        ),
                        [],
                    )?
                };
                Ok((count, deleted))
            })
            .await?;

        if dry_run {
            println!(
                "{strat}: would delete {count} entries \
                 (older than {older_than_days}d)"
            );
        } else {
            println!("{strat}: deleted {deleted} entries");
        }
    }
    Ok(())
}
