//! Backtest detail models: insights.

use serde::{Deserialize, Serialize};

// ── Insights ─────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct InsightsResponse {
    #[serde(default)]
    pub insights: Vec<Insight>,
    #[serde(default)]
    pub length: i64,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Insight {
    #[serde(default)]
    pub id: String,
    #[serde(default)]
    pub group_id: Option<String>,
    #[serde(default)]
    pub source_model: Option<String>,
    #[serde(default)]
    pub generated_time: i64,
    #[serde(default)]
    pub close_time: i64,
    #[serde(default)]
    pub symbol: String,
    #[serde(default)]
    pub ticker: String,
    /// "price" | "volatility"
    #[serde(default, rename = "type")]
    pub insight_type: String,
    #[serde(default)]
    pub reference: f64,
    #[serde(default)]
    pub reference_final: Option<f64>,
    /// "down" | "flat" | "up"
    #[serde(default)]
    pub direction: String,
    #[serde(default)]
    pub period: i64,
    #[serde(default)]
    pub magnitude: Option<f64>,
    #[serde(default)]
    pub confidence: Option<f64>,
    #[serde(default)]
    pub weight: Option<f64>,
    #[serde(default)]
    pub score_final: Option<bool>,
    #[serde(default)]
    pub score_direction: Option<f64>,
    #[serde(default)]
    pub score_magnitude: Option<f64>,
    #[serde(default)]
    pub estimated_value: Option<f64>,
    #[serde(default)]
    pub tag: Option<String>,
}
