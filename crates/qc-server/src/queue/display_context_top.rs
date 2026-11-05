//! Context display helper: top 10 experiments table.

use anyhow::Result;

use super::{ExperimentRow, truncate_name};
use crate::db::Db;

pub(super) async fn print_top10(db: &Db) -> Result<()> {
    let top10: Vec<ExperimentRow> = db
        .call(|conn| {
            let mut stmt = conn.prepare(
                "SELECT name, cagr, dd, car_mdd, sharpe, \
                 total_orders, batch
                 FROM experiments WHERE status='success'
                 ORDER BY car_mdd DESC LIMIT 10",
            )?;
            let rows = stmt
                .query_map([], |row| {
                    Ok((
                        row.get::<_, String>(0)?,
                        row.get::<_, f64>(1).unwrap_or(0.0),
                        row.get::<_, f64>(2).unwrap_or(0.0),
                        row.get::<_, f64>(3).unwrap_or(0.0),
                        row.get::<_, f64>(4).unwrap_or(0.0),
                        row.get::<_, i64>(5).unwrap_or(0),
                        row.get::<_, Option<String>>(6)?,
                    ))
                })?
                .collect::<Result<Vec<_>, _>>()?;
            Ok(rows)
        })
        .await?;
    println!(
        "Top 10:\n  {:<35} {:>7} {:>6} {:>8} {:>7} {:>7} BATCH",
        "NAME", "CAGR%", "DD%", "CAR/MDD", "SHARPE", "ORDERS"
    );
    println!("  {}", "-".repeat(90));
    for (name, cagr, dd, car_mdd, sharpe, orders, batch) in &top10 {
        println!(
            "  {:<35} {:>6.1} {:>6.1} {:>8.3} {:>7.3} {:>7} {}",
            truncate_name(name, 35),
            cagr,
            dd,
            car_mdd,
            sharpe,
            orders,
            batch.as_deref().unwrap_or("-"),
        );
    }
    println!();
    Ok(())
}
