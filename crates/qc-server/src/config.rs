//! Server configuration types + the `ServerConfig::load` entrypoint.
//!
//! The body of `load` is in `config_load.rs` (top-level sibling module).

use std::path::PathBuf;

/// Per-strategy configuration loaded from the database.
#[derive(Debug, Clone)]
pub struct StrategyConfig {
    pub name: String,
    pub db_path: PathBuf,
    /// QC project IDs -- one per runner slot to avoid code-push conflicts.
    pub project_ids: Vec<i64>,
    /// Scheduler weight (default 1.0). Higher = more likely to be picked.
    pub weight: f64,
}

/// Top-level server configuration.
#[derive(Debug, Clone)]
pub struct ServerConfig {
    pub qc_user_id: String,
    pub qc_api_token: String,
    pub organization_id: String,
    pub strategies: Vec<StrategyConfig>,
    /// Discovered backtest node IDs.
    pub node_ids: Vec<String>,
}
