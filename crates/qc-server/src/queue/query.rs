//! Queue listing subcommand.

use std::path::Path;

use anyhow::Result;

use super::query_sql::{ListFilters, build_list_sql};
use super::{QueueRow, strategy_targets, truncate_name};
use crate::db::Db;

/// List jobs in the queue with optional filters.
///
/// # Errors
/// Returns `Err` on SQL execution error or if a strategy database fails to open.
pub async fn list(
    data_dir: &Path,
    strategy: Option<&str>,
    status_filter: &str,
    batch_filter: Option<&str>,
    name_like: Option<&str>,
    limit: usize,
) -> Result<()> {
    let statuses: Vec<String> = status_filter
        .split(',')
        .map(|s| s.trim().to_string())
        .collect();
    let targets = strategy_targets(data_dir, strategy)?;

    println!(
        "{:<6} {:<35} {:<10} {:<6} {:<12} SUBMITTED",
        "STRAT", "NAME", "STATUS", "PRI", "BATCH"
    );
    println!("{}", "-".repeat(90));

    for (strat, path) in &targets {
        if !path.exists() {
            continue;
        }
        let db = Db::open(path, strat)?;
        let (sql, params_vec) = build_list_sql(&ListFilters {
            statuses: &statuses,
            batch: batch_filter,
            name_like,
            limit,
        });

        let rows: Vec<QueueRow> = db
            .call(move |conn| {
                let mut stmt = conn.prepare(&sql)?;
                let params_ref: Vec<Box<dyn duckdb::types::ToSql>> = params_vec
                    .iter()
                    .map(|s| -> Box<dyn duckdb::types::ToSql> { Box::new(s.clone()) })
                    .collect();
                let refs: Vec<&dyn duckdb::types::ToSql> =
                    params_ref.iter().map(std::convert::AsRef::as_ref).collect();
                let rows = stmt
                    .query_map(refs.as_slice(), |row| {
                        Ok((
                            row.get(0)?,
                            row.get(1)?,
                            row.get(2)?,
                            row.get(3)?,
                            row.get(4)?,
                        ))
                    })?
                    .collect::<Result<Vec<_>, _>>()?;
                Ok(rows)
            })
            .await?;

        for (name, status, pri, batch, submitted) in &rows {
            println!(
                "{:<6} {:<35} {:<10} {:<6} {:<12} {}",
                strat,
                truncate_name(name, 35),
                status,
                pri,
                batch.as_deref().unwrap_or("-"),
                submitted.as_deref().unwrap_or("-"),
            );
        }
    }
    Ok(())
}
