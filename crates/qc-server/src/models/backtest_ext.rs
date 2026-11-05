//! Backtest models: charts and report types.

use std::collections::HashMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;

// ── Charts ───────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ChartReadResponse {
    #[serde(default)]
    pub chart: Option<Chart>,
    #[serde(default)]
    pub progress: Option<f64>,
    #[serde(default)]
    pub status: Option<String>,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Chart {
    #[serde(default)]
    pub name: String,
    /// 0 = Overlayed, 1 = Stacked
    #[serde(default)]
    pub chart_type: i64,
    #[serde(default)]
    pub series: HashMap<String, Series>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Series {
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub unit: Option<String>,
    #[serde(default)]
    pub index: i64,
    #[serde(default)]
    pub values: Value,
    /// 0=Line, 1=Scatter, 2=Candle, 3=Bar, 4=Flag,
    /// 5=StackedArea, 6=Pie, 7=Treemap, 9=Heatmap
    #[serde(default)]
    pub series_type: i64,
    #[serde(default)]
    pub color: Option<String>,
    #[serde(default)]
    pub scatter_marker_symbol: Option<String>,
}

// ── Report ───────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BacktestReportResponse {
    #[serde(default)]
    pub report: Option<String>,
    #[serde(default)]
    pub generating: Option<bool>,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}

// Request helpers are in backtest_req.rs
