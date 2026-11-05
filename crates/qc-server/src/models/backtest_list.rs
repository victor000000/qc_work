//! Backtest list response and summary types.

use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BacktestListResponse {
    #[serde(default)]
    pub backtests: Vec<BacktestSummary>,
    #[serde(default)]
    pub count: i64,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BacktestSummary {
    pub backtest_id: String,
    #[serde(default)]
    pub status: String,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub created: String,
    #[serde(default)]
    pub progress: f64,
    #[serde(default)]
    pub tradeable_dates: Option<i64>,
    #[serde(default)]
    pub snapshot_id: Option<i64>,
    #[serde(default)]
    pub optimization_id: Option<String>,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub parameter_set: Option<Value>,
    // Optional statistics (only present when includeStatistics=true)
    #[serde(default)]
    pub sharpe_ratio: Option<f64>,
    #[serde(default)]
    pub alpha: Option<f64>,
    #[serde(default)]
    pub beta: Option<f64>,
    #[serde(default)]
    pub compounding_annual_return: Option<f64>,
    #[serde(default)]
    pub drawdown: Option<f64>,
    #[serde(default)]
    pub loss_rate: Option<f64>,
    #[serde(default)]
    pub net_profit: Option<f64>,
    #[serde(default)]
    pub psr: Option<f64>,
    #[serde(default)]
    pub sortino_ratio: Option<f64>,
    #[serde(default)]
    pub trades: Option<i64>,
    #[serde(default)]
    pub treynor_ratio: Option<f64>,
    #[serde(default)]
    pub win_rate: Option<f64>,
}
