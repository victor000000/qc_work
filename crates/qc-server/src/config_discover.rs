//! Strategy DB discovery and shared project pool loading.

use std::path::{Path, PathBuf};

use anyhow::Result;

use crate::projects_json;

/// Auto-discover strategy DBs: any file matching S*.duckdb in `data_dir`.
/// Only includes DBs that have a `backtest_queue` table.
pub(crate) fn discover_strategy_dbs(data_dir: &Path) -> Vec<(String, PathBuf)> {
    let mut found = Vec::new();
    if let Ok(entries) = std::fs::read_dir(data_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if let Some(name) = path.file_name().and_then(|n| n.to_str())
                && name.starts_with('S')
                && path
                    .extension()
                    .is_some_and(|e| e.eq_ignore_ascii_case("duckdb"))
                && !name.ends_with(".duckdb.bak")
            {
                // Check that this DB has a backtest_queue table
                if let Ok(db) = crate::database::Db::open(&path) {
                    let has_queue = db.sync_call(|conn| {
                    let has_queue: bool = conn
                            .query_row(
                                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='backtest_queue'",
                                [],
                                |r| r.get::<_, i64>(0),
                            )
                            .is_ok_and(|n| n > 0);
                    Ok(has_queue)
                    }).unwrap_or(false);
                    if !has_queue {
                        continue;
                    }
                } else {
                    tracing::warn!("skipping unreadable strategy database {}", path.display());
                    continue;
                }
                // S001.duckdb -> s001
                let strategy = path
                    .file_stem()
                    .and_then(|s| s.to_str())
                    .unwrap_or(name)
                    .to_lowercase();
                found.push((strategy, path));
            }
        }
    }
    found.sort_by(|a, b| a.0.cmp(&b.0));
    found
}

/// Load shared project IDs from `projects.json` if present; empty if absent.
pub(crate) fn load_shared_projects(data_dir: &Path) -> Result<Vec<i64>> {
    let path = projects_json::path_in(data_dir);
    if !path.exists() {
        tracing::warn!("no projects.json found, falling back to per-strategy DB config");
        return Ok(Vec::new());
    }
    let projects = projects_json::read(&path)?;
    tracing::info!(
        "loaded {} shared project IDs from projects.json: {:?}",
        projects.len(),
        projects
    );
    Ok(projects)
}
