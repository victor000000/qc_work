//! `Order` — one row from QC's `read_orders` response.

use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::order_event::OrderEvent;
use super::orders_response::Symbol;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Order {
    #[serde(default)]
    pub id: i64,
    #[serde(default)]
    pub contingent_id: Option<i64>,
    #[serde(default)]
    pub broker_id: Vec<String>,
    #[serde(default)]
    pub symbol: Option<Symbol>,
    #[serde(default)]
    pub limit_price: Option<f64>,
    #[serde(default)]
    pub stop_price: Option<f64>,
    #[serde(default)]
    pub stop_triggered: Option<bool>,
    #[serde(default)]
    pub price: f64,
    #[serde(default)]
    pub price_currency: Option<String>,
    #[serde(default)]
    pub time: Option<String>,
    #[serde(default)]
    pub created_time: Option<String>,
    #[serde(default)]
    pub last_fill_time: Option<String>,
    #[serde(default)]
    pub last_update_time: Option<String>,
    #[serde(default)]
    pub canceled_time: Option<String>,
    #[serde(default)]
    pub quantity: f64,
    /// 0=Market,1=Limit,2=StopMarket,3=StopLimit,4=MarketOnOpen,
    /// 5=MarketOnClose,6=OptionExercise,7=LimitIfTouched,
    /// 8=ComboMarket,9=ComboLimit,10=ComboLegLimit,11=TrailingStop
    #[serde(default, rename = "type")]
    pub order_type: i64,
    /// 0=New,1=Submitted,2=PartiallyFilled,3=Filled,5=Canceled,
    /// 6=None,7=Invalid,8=CancelPending,9=UpdateSubmitted
    #[serde(default)]
    pub status: i64,
    #[serde(default)]
    pub tag: Option<String>,
    /// 0=Base,1=Equity,2=Option,3=Commodity,4=Forex,5=Future,6=Cfd,
    /// 7=Crypto,8=FutureOption,9=Index,10=IndexOption,11=CryptoFuture
    #[serde(default)]
    pub security_type: Option<i64>,
    /// 0=Buy, 1=Sell, 2=Hold
    #[serde(default)]
    pub direction: i64,
    #[serde(default)]
    pub value: f64,
    #[serde(default)]
    pub is_marketable: Option<bool>,
    #[serde(default)]
    pub order_submission_data: Option<Value>,
    #[serde(default)]
    pub properties: Option<Value>,
    #[serde(default)]
    pub events: Vec<OrderEvent>,
    #[serde(default)]
    pub trailing_amount: Option<f64>,
    #[serde(default)]
    pub trailing_percentage: Option<bool>,
    #[serde(default)]
    pub trigger_price: Option<f64>,
    #[serde(default)]
    pub trigger_touched: Option<bool>,
    #[serde(default)]
    pub group_order_manager: Option<Value>,
}
