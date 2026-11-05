//! Request/response shapes for `/backtests/read/log` (runtime console logs).

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BacktestLogReq<'a> {
    pub project_id: i64,
    pub backtest_id: &'a str,
    /// QC requires a `query` discriminator — always "log" for runtime logs.
    pub query: &'a str,
    /// Log row index (0-based, inclusive).
    pub start: i64,
    /// Log row index (exclusive upper bound). Page size = `end - start`.
    pub end: i64,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BacktestLogResponse {
    /// QC returns logs under `log` (singular) for backtests; some older docs
    /// say `logs`. Accept either by aliasing.
    #[serde(default, alias = "logs")]
    pub log: Vec<String>,
    #[serde(default)]
    pub length: i64,
    pub success: bool,
    #[serde(default)]
    pub errors: Vec<String>,
}
