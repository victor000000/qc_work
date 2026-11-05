//! Duplicate-name + duplicate-hash checks for the enqueue command.

use anyhow::Result;
use duckdb::OptionalExt;

use crate::db::Db;

pub(super) async fn check_no_duplicate_name(db: &Db, strategy: &str, name: &str) -> Result<()> {
    let name_check = name.to_string();
    let exists: Option<String> = db
        .call(move |conn| {
            conn.query_row(
                "SELECT status FROM backtest_queue WHERE name=?1",
                [&name_check],
                |row| row.get(0),
            )
            .optional()
            .map_err(Into::into)
        })
        .await?;
    if let Some(status) = exists {
        anyhow::bail!(
            "{strategy}/{name} already exists in queue \
             (status={status}). Use a different name."
        );
    }
    Ok(())
}

pub(super) async fn warn_on_duplicate_hash(db: &Db, hash: &str) -> Result<()> {
    let hash_check = hash.to_string();
    let dup_names: Vec<(String, String)> = db
        .call(move |conn| {
            let mut stmt = conn.prepare(
                "SELECT name, 'experiment' FROM experiments \
                 WHERE code_hash=?1
                 UNION ALL
                 SELECT name, 'queued' FROM backtest_queue \
                 WHERE code_hash=?1 \
                 AND status IN ('queued','running')
                 LIMIT 5",
            )?;
            let rows = stmt
                .query_map([&hash_check], |row| Ok((row.get(0)?, row.get(1)?)))?
                .collect::<Result<Vec<_>, _>>()?;
            Ok(rows)
        })
        .await?;
    if !dup_names.is_empty() {
        eprintln!("warning: code hash {hash} matches existing entries:");
        for (dup_name, source) in &dup_names {
            eprintln!("  {source}: {dup_name}");
        }
    }
    Ok(())
}
