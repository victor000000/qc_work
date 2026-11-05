//! Adaptive rate-limit pacer + retry helpers + QC stats parsing.

mod pacer;
mod retry;
mod state;
mod stats;

pub(crate) use retry::{is_rate_limit, retry_on_rate_limit};
pub use state::RateLimitState;
pub(crate) use stats::{stat_f64, stat_i64};
