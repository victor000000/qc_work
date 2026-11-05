//! QC `read_orders` response shapes — orders, order events, and symbols.
//!
//! Re-exports the structs at this level so they're reachable as
//! `crate::models::backtest_detail::{Order, OrderEvent, OrdersResponse,
//! Symbol}` without the submodule path. (Order/OrderEvent/Symbol are
//! embedded in `OrdersResponse`, so callers that touch the response need
//! to name them.)

mod order;
mod order_event;
mod orders_response;

pub use order::Order;
pub use order_event::OrderEvent;
pub use orders_response::{OrdersResponse, Symbol};
