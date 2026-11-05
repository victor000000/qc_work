//! Query subcommands: errors listing (--detail branch is in `query_results_detail.rs`).

use std::path::Path;

use anyhow::Result;

use super::query_results_detail::show_failure_detail;
use super::{open_db, truncate_name};

/// Show recent errors with QC API messages.
///
/// # Errors
/// Returns `Err` on SQL execution error or if the strategy database fails to open.
pub async fn errors(
    data_dir: &Path,
    strategy: &str,
    limit: usize,
    detail_name: Option<&str>,
) -> Result<()> {
    let db = open_db(data_dir, strategy)?;
    if let Some(name) = detail_name {
        return show_failure_detail(&db, strategy, name).await;
    }

    let lim = limit;
    let rows: Vec<(String, String, Option<String>, Option<String>)> = db
        .call(move |conn| {
            let mut stmt = conn.prepare(
                "SELECT name, status, error_message, completed_at \
                 FROM backtest_queue
                 WHERE status='failed'
                 ORDER BY completed_at DESC LIMIT ?1",
            )?;
            let rows = stmt
                .query_map([i64::try_from(lim).unwrap_or(i64::MAX)], |row| {
                    Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?))
                })?
                .collect::<Result<Vec<_>, _>>()?;
            Ok(rows)
        })
        .await?;

    if rows.is_empty() {
        println!("{strategy}: no failures");
        return Ok(());
    }
    println!("{strategy} recent failures:");
    println!("{:<35} {:<22} ERROR", "NAME", "COMPLETED");
    println!("{}", "-".repeat(100));
    for (name, _status, err, completed) in &rows {
        let err_short = err.as_deref().unwrap_or("");
        let err_display = super::head_chars(err_short, 60);
        println!(
            "{:<35} {:<22} {}",
            truncate_name(name, 35),
            completed.as_deref().unwrap_or("-"),
            err_display,
        );
    }
    println!("\nUse --detail <name> to see full QC API response for a specific failure.");
    Ok(())
}
