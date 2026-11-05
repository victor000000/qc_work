//! `/backtests/read/log` — runtime console logs for a single backtest.

use anyhow::Result;

use crate::client::QcClient;
use crate::models::backtest_log::{BacktestLogReq, BacktestLogResponse};

impl QcClient {
    /// Read one page of the runtime console log for a backtest.
    ///
    /// `start` / `end` are row indices (inclusive / exclusive). Pages are
    /// typically 200 rows. Page until the returned `log.len() < end - start`.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn read_backtest_log(
        &self,
        project_id: i64,
        backtest_id: &str,
        start: i64,
        end: i64,
    ) -> Result<BacktestLogResponse> {
        self.post(
            "/backtests/read/log",
            &BacktestLogReq {
                project_id,
                backtest_id,
                query: "log",
                start,
                end,
            },
        )
        .await
    }
}
