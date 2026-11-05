//! Show full details for a single experiment.

use std::path::Path;

use anyhow::Result;
use duckdb::OptionalExt;

use super::display_show_detail::print_experiment_detail;
use super::display_show_queue::{show_code, show_queue_fallback};
use super::{ExperimentDetail, open_db};
use crate::db::Db;

/// Show full details for a single experiment.
///
/// # Errors
/// Returns `Err` on SQL execution error or if the strategy database fails to open.
pub async fn show(data_dir: &Path, strategy: &str, name: &str, show_code_flag: bool) -> Result<()> {
    let db = open_db(data_dir, strategy)?;
    let n = name.to_string();
    let exp = fetch_experiment(&db, &n).await?;

    if let Some(detail) = exp {
        print_experiment_detail(strategy, name, detail);
    } else {
        let found = show_queue_fallback(&db, strategy, name, &n).await?;
        if !found {
            return Ok(());
        }
    }
    if show_code_flag {
        show_code(&db, &n).await?;
    }
    Ok(())
}

/// Query the experiments table for a single experiment detail row.
async fn fetch_experiment(db: &Db, n: &str) -> Result<Option<ExperimentDetail>> {
    let name = n.to_string();
    let exp: Option<ExperimentDetail> = db
        .call(move |conn| {
            conn.query_row(
                "SELECT status, description, hypothesis,
                        based_on, batch, cagr, dd, car_mdd,
                        sharpe, sortino, total_orders, win_rate,
                        net_profit_pct, probabilistic_sharpe,
                        code_hash, project_id
                 FROM experiments WHERE name=?1",
                [&name],
                |row| {
                    Ok((
                        row.get(0)?,
                        row.get(1)?,
                        row.get(2)?,
                        row.get(3)?,
                        row.get(4)?,
                        row.get(5)?,
                        row.get(6)?,
                        row.get(7)?,
                        row.get(8)?,
                        row.get(9)?,
                        row.get(10)?,
                        row.get(11)?,
                        row.get(12)?,
                        row.get(13)?,
                        row.get(14)?,
                        row.get::<_, Option<i64>>(15)?,
                    ))
                },
            )
            .optional()
            .map_err(Into::into)
        })
        .await?;
    Ok(exp)
}
