//! Top experiments query: show best by CAR/MDD.

use std::path::Path;

use anyhow::Result;

use super::{ExperimentRow, strategy_targets, truncate_name};
use crate::db::Db;

/// Show top experiments by CAR/MDD.
///
/// # Errors
/// SQL error or strategy DB open failure.
pub async fn top(
    data_dir: &Path,
    strategy: Option<&str>,
    batch_filter: Option<&str>,
    limit: usize,
) -> Result<()> {
    let targets = strategy_targets(data_dir, strategy)?;

    println!(
        "{:<6} {:<35} {:>7} {:>6} {:>8} {:>7} {:>7} BATCH",
        "STRAT", "NAME", "CAGR%", "DD%", "CAR/MDD", "SHARPE", "ORDERS"
    );
    println!("{}", "-".repeat(100));

    for (strat, path) in &targets {
        if !path.exists() {
            continue;
        }
        let db = Db::open(path, strat)?;
        let batch = batch_filter.map(std::string::ToString::to_string);
        let lim = limit;

        let rows: Vec<ExperimentRow> = db
            .call(move |conn| {
                let (sql, params_vec): (String, Vec<Box<dyn duckdb::types::ToSql>>) =
                    if let Some(b) = &batch {
                        (
                            "SELECT name, cagr, dd, car_mdd, sharpe, total_orders, batch
                         FROM experiments WHERE status='success' AND batch=?1
                         ORDER BY car_mdd DESC LIMIT ?2"
                                .to_string(),
                            vec![
                                Box::new(b.clone()) as Box<dyn duckdb::types::ToSql>,
                                Box::new(i64::try_from(lim).unwrap_or(i64::MAX)),
                            ],
                        )
                    } else {
                        (
                            "SELECT name, cagr, dd, car_mdd, sharpe, total_orders, batch
                         FROM experiments WHERE status='success'
                         ORDER BY car_mdd DESC LIMIT ?1"
                                .to_string(),
                            vec![Box::new(i64::try_from(lim).unwrap_or(i64::MAX))
                                as Box<dyn duckdb::types::ToSql>],
                        )
                    };
                let mut stmt = conn.prepare(&sql)?;
                let refs: Vec<&dyn duckdb::types::ToSql> =
                    params_vec.iter().map(std::convert::AsRef::as_ref).collect();
                let rows = stmt
                    .query_map(refs.as_slice(), |row| {
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

        for (name, cagr, dd, car_mdd, sharpe, orders, batch) in &rows {
            println!(
                "{:<6} {:<35} {:>6.1} {:>6.1} {:>8.3} \
                 {:>7.3} {:>7} {}",
                strat,
                truncate_name(name, 35),
                cagr,
                dd,
                car_mdd,
                sharpe,
                orders,
                batch.as_deref().unwrap_or("-"),
            );
        }
    }
    Ok(())
}
