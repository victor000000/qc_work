//! Context display helpers: latest batch results and recent failures.

use anyhow::Result;
use duckdb::OptionalExt;

use super::truncate_name;
use crate::db::Db;

pub(super) async fn print_latest_batch(db: &Db) -> Result<()> {
    let latest_batch: Option<String> = db
        .call(|conn| {
            conn.query_row(
                "SELECT batch FROM experiments \
                 WHERE status='success' AND batch IS NOT NULL
                 ORDER BY rowid DESC LIMIT 1",
                [],
                |row| row.get(0),
            )
            .optional()
            .map_err(Into::into)
        })
        .await?;
    let Some(lb) = latest_batch else {
        return Ok(());
    };
    let lb2 = lb.clone();
    let batch_results: Vec<(String, f64, f64, f64, i64)> = db
        .call(move |conn| {
            let mut stmt = conn.prepare(
                "SELECT name, cagr, dd, car_mdd, total_orders
                 FROM experiments \
                 WHERE status='success' AND batch=?1
                 ORDER BY car_mdd DESC LIMIT 10",
            )?;
            let rows = stmt
                .query_map([&lb2], |row| {
                    Ok((
                        row.get::<_, String>(0)?,
                        row.get::<_, f64>(1).unwrap_or(0.0),
                        row.get::<_, f64>(2).unwrap_or(0.0),
                        row.get::<_, f64>(3).unwrap_or(0.0),
                        row.get::<_, i64>(4).unwrap_or(0),
                    ))
                })?
                .collect::<Result<Vec<_>, _>>()?;
            Ok(rows)
        })
        .await?;
    if !batch_results.is_empty() {
        println!("Latest batch ({lb}):");
        for (name, cagr, dd, car_mdd, orders) in &batch_results {
            println!(
                "  {:<35} CAGR={:>5.1}% DD={:>5.1}% \
                 CAR/MDD={:>6.3} orders={}",
                truncate_name(name, 35),
                cagr,
                dd,
                car_mdd,
                orders,
            );
        }
        println!();
    }
    Ok(())
}

pub(super) async fn print_recent_failures(db: &Db) -> Result<()> {
    let failures: Vec<(String, Option<String>)> = db
        .call(|conn| {
            let mut stmt = conn.prepare(
                "SELECT name, error_message FROM backtest_queue
                 WHERE status='failed' \
                 ORDER BY completed_at DESC LIMIT 5",
            )?;
            let rows = stmt
                .query_map([], |row| Ok((row.get(0)?, row.get(1)?)))?
                .collect::<Result<Vec<_>, _>>()?;
            Ok(rows)
        })
        .await?;
    if !failures.is_empty() {
        println!("Recent failures:");
        for (name, err) in &failures {
            let e = err.as_deref().unwrap_or("(no message)");
            let e_short = super::head_chars(e, 60);
            println!("  {:<35} {}", truncate_name(name, 35), e_short);
        }
    }
    Ok(())
}
