//! Node-related types for QC project API.

use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectNodesResponse {
    /// Absent when QC returns an error response (`success: false`).
    /// Callers must check `success` first and inspect `errors` on failure.
    #[serde(default)]
    pub nodes: Option<ProjectNodes>,
    #[serde(default)]
    pub auto_select_node: bool,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectNodes {
    #[serde(default)]
    pub backtest: Vec<Node>,
    #[serde(default)]
    pub live: Vec<Node>,
    #[serde(default)]
    pub research: Vec<Node>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Node {
    #[serde(default)]
    pub speed: f64,
    #[serde(default)]
    pub cpu: i64,
    #[serde(default)]
    pub ram: f64,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub sku: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub id: String,
    #[serde(default)]
    pub busy: bool,
    #[serde(default)]
    pub active: bool,
    #[serde(default)]
    pub has_gpu: i64,
    #[serde(default)]
    pub used_by: Option<String>,
    #[serde(default)]
    pub project_name: Option<String>,
    #[serde(default)]
    pub project_id: Option<i64>,
    #[serde(default)]
    pub assets: Option<i64>,
    #[serde(default)]
    pub host: Option<String>,
    #[serde(default)]
    pub price: Option<NodePrices>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NodePrices {
    #[serde(default)]
    pub monthly: i64,
    #[serde(default)]
    pub yearly: i64,
}
