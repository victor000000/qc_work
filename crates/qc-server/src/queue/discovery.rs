//! Locate strategy databases (`S<NAME>.duckdb`) on disk.

use std::path::{Path, PathBuf};

use anyhow::Result;

use crate::db::Db;

pub(crate) fn open_db(data_dir: &Path, strategy: &str) -> Result<Db> {
    crate::db::validate_strategy_id(strategy)?;
    let db_file = format!("{}.duckdb", strategy.to_uppercase());
    let path = data_dir.join(&db_file);
    if !path.exists() {
        anyhow::bail!(
            "unknown strategy: {strategy} (no {db_file} in {})",
            data_dir.display()
        );
    }
    Db::open(&path, strategy)
}

pub(crate) fn all_dbs(data_dir: &Path) -> Vec<(String, PathBuf)> {
    crate::config_discover::discover_strategy_dbs(data_dir)
}

pub(crate) fn strategy_targets(
    data_dir: &Path,
    strategy: Option<&str>,
) -> Result<Vec<(String, PathBuf)>> {
    match strategy {
        Some(s) => {
            crate::db::validate_strategy_id(s)?;
            let db_file = format!("{}.duckdb", s.to_uppercase());
            let path = data_dir.join(&db_file);
            if !path.exists() {
                anyhow::bail!("unknown strategy: {s} (no {db_file})");
            }
            Ok(vec![(s.to_string(), path)])
        }
        None => Ok(all_dbs(data_dir)),
    }
}
