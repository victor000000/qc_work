//! Bootstrap an isolated strategy without copying another strategy's research tables.

use anyhow::Result;
use std::path::{Path, PathBuf};

/// Create the generic schema, idempotently preserving existing jobs and settings.
///
/// # Errors
/// Returns an error for invalid identifiers, filesystem errors, or incompatible schemas.
pub fn initialize_strategy(data_dir: &Path, strategy: &str) -> Result<PathBuf> {
    validate_strategy_id(strategy)?;
    std::fs::create_dir_all(data_dir)?;
    let path = data_dir.join(format!("{}.duckdb", strategy.to_uppercase()));
    let db = crate::database::Db::open(&path)?;
    db.sync_call(|conn| {
        let tx = conn.transaction()?;
        upgrade(&tx)?;
        tx.execute(
            "INSERT OR IGNORE INTO settings(category,key,value) VALUES ('strategy','name',?1)",
            [strategy],
        )?;
        tx.commit()?;
        Ok(())
    })?;
    Ok(path)
}

/// Upgrade execution columns in older strategy databases without touching
/// strategy-owned tables or research schema-version metadata (used by research migrations).
pub(super) fn upgrade(conn: &duckdb::Connection) -> Result<()> {
    conn.execute_batch(include_str!("../../schema.sql"))?;
    for (table, columns) in [
        (
            "backtest_queue",
            &[
                ("runtime_seconds", "DOUBLE"),
                ("node_id", "TEXT"),
                ("code_hash", "TEXT"),
                ("project_id", "INTEGER"),
                ("requested_project_id", "INTEGER"),
                ("extra_files", "TEXT"),
                ("result_json", "TEXT"),
            ][..],
        ),
        (
            "experiments",
            &[
                ("code_hash", "TEXT"),
                ("runtime_seconds", "DOUBLE"),
                ("project_id", "INTEGER"),
            ][..],
        ),
    ] {
        let mut stmt = conn.prepare(&format!("PRAGMA table_info({table})"))?;
        let existing = stmt
            .query_map([], |row| row.get::<_, String>(1))?
            .collect::<duckdb::Result<Vec<_>>>()?;
        for (column, kind) in columns {
            if !existing.iter().any(|name| name == column) {
                conn.execute_batch(&format!("ALTER TABLE {table} ADD COLUMN {column} {kind}"))?;
            }
        }
    }
    Ok(())
}

/// Validate a canonical strategy ID before constructing a filesystem path.
///
/// # Errors
/// Rejects paths, punctuation and noncanonical identifiers.
pub fn validate_strategy_id(strategy: &str) -> Result<()> {
    anyhow::ensure!(
        strategy.len() > 1
            && strategy.starts_with('s')
            && strategy
                .bytes()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'_'),
        "strategy must start with s and contain only lowercase letters, digits, underscores"
    );
    Ok(())
}
