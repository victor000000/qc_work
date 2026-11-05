//! QC API request/response shapes. Each submodule mirrors one
//! `/api/v2/<endpoint>` family. Callers reach into a submodule by name
//! (`crate::models::backtest::BacktestResponse`); the flat `pub use *`
//! re-exports were dead — every internal use is `crate::models::sub::T`.

pub mod account;
pub mod backtest;
pub mod backtest_detail;
pub mod backtest_ext;
pub mod backtest_insights;
pub mod backtest_list;
pub mod backtest_log;
pub mod backtest_req;
pub mod common;
pub mod compile;
pub mod file;
pub mod object_store;
pub mod project;
pub mod project_node;
pub mod project_req;
