//! Retry failed jobs (`clean` lives in `cmd_clean.rs`).

use std::path::Path;

use anyhow::Result;

use super::open_db;

/// Retry failed jobs by resetting them to queued.
///
/// # Errors
/// Returns `Err` if neither `name` nor `batch` is provided, or on SQL error.
pub async fn retry(
    data_dir: &Path,
    strategy: &str,
    name: Option<&str>,
    batch: Option<&str>,
) -> Result<()> {
    if name.is_none() && batch.is_none() {
        anyhow::bail!("must specify --name or --batch (or both)");
    }
    let db = open_db(data_dir, strategy)?;
    let n = name.map(std::string::ToString::to_string);
    let b = batch.map(std::string::ToString::to_string);

    let changed: usize = db
        .call(move |conn| {
            let c = match (&n, &b) {
                (Some(name), _) => conn.execute(
                    "UPDATE backtest_queue \
                     SET status='queued', error_message=NULL, \
                         retry_count=0, result_json=NULL, started_at=NULL, completed_at=NULL, \
                         backtest_id=NULL, compile_id=NULL, node_id=NULL, project_id=NULL, runtime_seconds=NULL
                     WHERE name=?1 AND status='failed'",
                    [name],
                )?,
                (None, Some(batch)) => conn.execute(
                    "UPDATE backtest_queue \
                     SET status='queued', error_message=NULL, \
                         retry_count=0, result_json=NULL, started_at=NULL, completed_at=NULL, \
                         backtest_id=NULL, compile_id=NULL, node_id=NULL, project_id=NULL, runtime_seconds=NULL
                     WHERE batch=?1 AND status='failed'",
                    [batch],
                )?,
                _ => 0,
            };
            Ok(c)
        })
        .await?;

    let scope = match (name, batch) {
        (Some(n), _) => format!("{strategy}/{n}"),
        (_, Some(b)) => format!("{strategy} batch={b}"),
        _ => strategy.to_string(),
    };
    if changed > 0 {
        println!("retried {changed} failed job(s) in {scope} -> queued");
    } else {
        println!("{scope}: no failed jobs to retry");
    }
    Ok(())
}
