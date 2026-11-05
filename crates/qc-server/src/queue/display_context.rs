//! Full optimizer context display for a strategy.

use std::path::Path;

use anyhow::Result;

use super::display_context_batch::{print_latest_batch, print_recent_failures};
use super::display_context_meta::{print_header, print_params};
use super::display_context_top::print_top10;
use super::display_detail::compute_next_exp_number;
use super::open_db;
use crate::db::Db;

/// Show full optimizer context for a strategy.
///
/// # Errors
/// SQL execution error or strategy DB open failure.
pub async fn context(data_dir: &Path, strategy: &str) -> Result<()> {
    let db = open_db(data_dir, strategy)?;
    print_header(&db, strategy).await?;
    print_params(&db).await?;
    print_queue_section(&db, strategy).await?;
    print_running(&db).await?;
    print_top10(&db).await?;
    print_latest_batch(&db).await?;
    print_recent_failures(&db).await?;
    Ok(())
}

/// Print the queue counts and next experiment number.
async fn print_queue_section(db: &Db, strategy: &str) -> Result<()> {
    let counts = db.queue_counts().await?;
    let exp_count: i64 = db
        .call(|conn| {
            let n: i64 = conn.query_row(
                "SELECT COUNT(*) FROM experiments \
                 WHERE status='success'",
                [],
                |r| r.get(0),
            )?;
            Ok(n)
        })
        .await?;
    let next = compute_next_exp_number(db, strategy).await?;
    let queued_count = counts
        .iter()
        .find(|(s, _)| s == "queued")
        .map_or(0, |(_, c)| *c);
    println!("Queue:");
    for (s, c) in &counts {
        println!("  {s}: {c}");
    }
    println!("  experiments(success): {exp_count}");
    println!("  next_experiment: {next}  queued_count: {queued_count}");
    println!();
    Ok(())
}

/// Print the list of currently running backtests.
async fn print_running(db: &Db) -> Result<()> {
    let running: Vec<(String, Option<String>, Option<String>)> = db
        .call(|conn| {
            let mut stmt = conn.prepare(
                "SELECT name, batch, started_at \
                 FROM backtest_queue \
                 WHERE status='running' \
                 ORDER BY started_at ASC",
            )?;
            let rows = stmt
                .query_map([], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)))?
                .collect::<Result<Vec<_>, _>>()?;
            Ok(rows)
        })
        .await?;
    if !running.is_empty() {
        println!("Running:");
        for (name, batch, started) in &running {
            println!(
                "  {} (batch={}, started={})",
                name,
                batch.as_deref().unwrap_or("-"),
                started.as_deref().unwrap_or("-"),
            );
        }
        println!();
    }
    Ok(())
}

// print_top10 is in display_context_batch.rs
