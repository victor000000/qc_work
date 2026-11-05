//! Header + params printing for `context` command.

use anyhow::Result;
use duckdb::OptionalExt;

use crate::db::Db;

/// Print the header with strategy name and optimizer description.
pub(super) async fn print_header(db: &Db, strategy: &str) -> Result<()> {
    let desc: Option<String> = db
        .call(|conn| {
            conn.query_row(
                "SELECT value FROM settings \
                 WHERE category='strategy' \
                 AND key='optimizer_description'",
                [],
                |row| row.get(0),
            )
            .optional()
            .map_err(Into::into)
        })
        .await?;
    println!("=== {strategy} optimizer ===");
    if let Some(d) = &desc {
        println!("{d}");
    }
    println!();
    Ok(())
}

/// Print the strategy parameters line.
pub(super) async fn print_params(db: &Db) -> Result<()> {
    let params: Vec<(String, String)> = db
        .call(|conn| {
            let mut stmt = conn.prepare(
                "SELECT key, value FROM settings \
                 WHERE category='strategy'
                 AND key IN ('universe','start_date','end_date',\
                             'start_cash','leverage','resolution')
                 ORDER BY key",
            )?;
            let rows = stmt
                .query_map([], |row| Ok((row.get(0)?, row.get(1)?)))?
                .collect::<Result<Vec<_>, _>>()?;
            Ok(rows)
        })
        .await?;
    if !params.is_empty() {
        let param_str: Vec<String> = params.iter().map(|(k, v)| format!("{k}={v}")).collect();
        println!("Params: {}", param_str.join("  "));
        println!();
    }
    Ok(())
}
