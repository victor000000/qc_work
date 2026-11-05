use std::collections::HashMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;

// ── Responses ────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BacktestResponse {
    #[serde(default)]
    pub backtest: Option<BacktestResult>,
    #[serde(default)]
    pub debugging: Option<bool>,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BacktestResult {
    #[serde(default)]
    pub backtest_id: String,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub note: Option<String>,
    #[serde(default)]
    pub organization_id: Option<String>,
    #[serde(default)]
    pub project_id: i64,
    #[serde(default)]
    pub completed: bool,
    #[serde(default)]
    pub status: Option<String>,
    #[serde(default)]
    pub error: Option<String>,
    #[serde(default)]
    pub stacktrace: Option<String>,
    #[serde(default)]
    pub progress: f64,
    #[serde(default)]
    pub has_initialize_error: Option<bool>,
    #[serde(default)]
    pub created: Option<String>,
    #[serde(default)]
    pub backtest_start: Option<String>,
    #[serde(default)]
    pub backtest_end: Option<String>,
    #[serde(default)]
    pub tradeable_dates: Option<i64>,
    #[serde(default)]
    pub snapshot_id: Option<i64>,
    #[serde(default)]
    pub optimization_id: Option<String>,
    #[serde(default)]
    pub node_name: Option<String>,
    #[serde(default)]
    pub out_of_sample_max_end_date: Option<String>,
    #[serde(default)]
    pub out_of_sample_days: Option<i64>,
    /// Key statistics.
    #[serde(default)]
    pub statistics: HashMap<String, String>,
    /// Runtime stats.
    #[serde(default)]
    pub runtime_statistics: HashMap<String, String>,
    /// Charts embedded in the full backtest read.
    #[serde(default)]
    pub charts: HashMap<String, Value>,
    #[serde(default)]
    pub parameter_set: Option<Value>,
    #[serde(default)]
    pub rolling_window: Option<Value>,
    #[serde(default)]
    pub total_performance: Option<Value>,
    #[serde(default)]
    pub research_guide: Option<Value>,
}

// List response types are in backtest_list.rs
// Charts, Report, and Request helpers are in backtest_ext.rs
