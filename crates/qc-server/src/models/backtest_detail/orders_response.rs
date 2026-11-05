//! Top-level `read_orders` response wrapper + the embedded `Symbol`.

use serde::{Deserialize, Serialize};

use super::order::Order;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OrdersResponse {
    pub orders: Vec<Order>,
    #[serde(default)]
    pub length: i64,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Symbol {
    #[serde(default)]
    pub value: String,
    #[serde(default)]
    pub id: String,
    #[serde(default)]
    pub permtick: String,
}
