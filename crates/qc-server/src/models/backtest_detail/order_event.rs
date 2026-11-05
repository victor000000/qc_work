//! `OrderEvent` — fill/cancel/etc lifecycle event for an `Order`.

use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OrderEvent {
    #[serde(default)]
    pub algorithm_id: Option<String>,
    #[serde(default)]
    pub symbol: Option<String>,
    #[serde(default)]
    pub symbol_value: Option<String>,
    #[serde(default)]
    pub symbol_permtick: Option<String>,
    #[serde(default)]
    pub order_id: i64,
    #[serde(default)]
    pub order_event_id: i64,
    #[serde(default)]
    pub id: Option<String>,
    #[serde(default)]
    pub status: Option<String>,
    #[serde(default)]
    pub order_fee_amount: Option<f64>,
    #[serde(default)]
    pub order_fee_currency: Option<String>,
    #[serde(default)]
    pub fill_price: f64,
    #[serde(default)]
    pub fill_price_currency: Option<String>,
    #[serde(default)]
    pub fill_quantity: f64,
    #[serde(default)]
    pub direction: Option<String>,
    #[serde(default)]
    pub message: Option<String>,
    #[serde(default)]
    pub is_assignment: Option<bool>,
    #[serde(default)]
    pub stop_price: Option<f64>,
    #[serde(default)]
    pub limit_price: Option<f64>,
    #[serde(default)]
    pub quantity: f64,
    #[serde(default)]
    pub time: Option<Value>, // can be datetime string or unix int
    #[serde(default)]
    pub is_in_the_money: Option<bool>,
}
