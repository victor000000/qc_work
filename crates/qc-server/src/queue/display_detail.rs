use std::path::Path;

use crate::db::Db;
use anyhow::Result;

use super::open_db;

/// Compute next experiment number from both experiments and `backtest_queue` tables.
pub(super) async fn compute_next_exp_number(db: &Db, strategy: &str) -> Result<i64> {
    let prefix = format!("{}_Exp", strategy.to_uppercase());
    let pfx = prefix.clone();
    let max_num: i64 = db
        .call(move |conn| {
            let mut max_n = 0i64;
            // Parse experiment numbers from names like "S002_Exp525_dw_vx19"
            for table in ["experiments", "backtest_queue"] {
                let sql = format!("SELECT name FROM {table} WHERE name LIKE ?1");
                let mut stmt = conn.prepare(&sql)?;
                let rows = stmt.query_map([format!("{pfx}%")], |row| row.get::<_, String>(0))?;
                for name in rows.flatten() {
                    let after = &name[pfx.len()..];
                    let num_str: String = after.chars().take_while(char::is_ascii_digit).collect();
                    if let Ok(n) = num_str.parse::<i64>() {
                        max_n = max_n.max(n);
                    }
                }
            }
            Ok(max_n)
        })
        .await?;
    Ok(max_num + 1)
}

/// Print the next experiment number for a strategy.
///
/// # Errors
/// Returns `Err` on SQL execution error or if the strategy database fails to open.
pub async fn next_experiment_number(data_dir: &Path, strategy: &str) -> Result<()> {
    let db = open_db(data_dir, strategy)?;
    let next = compute_next_exp_number(&db, strategy).await?;
    println!("{next}");
    Ok(())
}

// show() is in display_show.rs
