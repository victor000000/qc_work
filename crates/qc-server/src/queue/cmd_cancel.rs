//! Queue cancel commands: cancel, `cancel_all`.

use std::path::Path;

use anyhow::Result;

use super::open_db;

/// Cancel a single queued job by name.
///
/// # Errors
/// Returns `Err` on SQL execution error.
pub async fn cancel(data_dir: &Path, strategy: &str, name: &str) -> Result<()> {
    let db = open_db(data_dir, strategy)?;
    let n = name.to_string();
    let changed: usize = db
        .call(move |conn| {
            let c = conn.execute(
                "UPDATE backtest_queue SET status='cancelled' \
                 WHERE name=?1 AND status='queued'",
                [&n],
            )?;
            Ok(c)
        })
        .await?;

    if changed > 0 {
        println!("cancelled {strategy}/{name}");
    } else {
        println!(
            "{strategy}/{name}: not found in queued state \
             (may be running/done/already cancelled)"
        );
    }
    Ok(())
}

/// Cancel all queued jobs for a strategy.
///
/// # Errors
/// Returns `Err` on SQL execution error.
pub async fn cancel_all(data_dir: &Path, strategy: &str, batch: Option<&str>) -> Result<()> {
    let db = open_db(data_dir, strategy)?;
    let b = batch.map(std::string::ToString::to_string);
    let changed: usize = db
        .call(move |conn| {
            let c = match &b {
                Some(batch) => conn.execute(
                    "UPDATE backtest_queue \
                     SET status='cancelled' \
                     WHERE status='queued' AND batch=?1",
                    [batch],
                )?,
                None => conn.execute(
                    "UPDATE backtest_queue \
                     SET status='cancelled' \
                     WHERE status='queued'",
                    [],
                )?,
            };
            Ok(c)
        })
        .await?;

    let scope = batch.map(|b| format!(" batch={b}")).unwrap_or_default();
    println!("cancelled {changed} queued jobs in {strategy}{scope}");
    Ok(())
}
