//! Backtest read/list endpoints.
//!
//! Write endpoints (create/update/delete/tags) live in `backtests_write.rs`.
//! Bulk data (chart/orders/insights/report) lives in `backtests_data.rs`.

use anyhow::Result;

use crate::client::QcClient;
use crate::models::backtest::BacktestResponse;
use crate::models::backtest_list::BacktestListResponse;
use crate::models::backtest_req::{BacktestIdReq, ListBacktestsReq};

#[derive(Debug)]
pub(crate) struct BacktestIdentityMismatch;

impl std::fmt::Display for BacktestIdentityMismatch {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("backtest read returned an unexpected execution identity")
    }
}

impl std::error::Error for BacktestIdentityMismatch {}

impl QcClient {
    /// Read full backtest results (statistics, charts, etc.).
    ///
    /// # Errors
    /// Returns `Err` on transport failure, invalid JSON or an identity mismatch.
    pub async fn read_backtest(
        &self,
        project_id: i64,
        backtest_id: &str,
    ) -> Result<BacktestResponse> {
        let response: BacktestResponse = self
            .post(
                "/backtests/read",
                &BacktestIdReq {
                    project_id,
                    backtest_id,
                },
            )
            .await?;
        // Older responses may omit one or both identity fields. Any reported
        // identifier must agree with the requested execution before use.
        if response.backtest.as_ref().is_some_and(|backtest| {
            (!backtest.backtest_id.is_empty() && backtest.backtest_id != backtest_id)
                || (backtest.project_id != 0 && backtest.project_id != project_id)
        }) {
            return Err(BacktestIdentityMismatch.into());
        }
        Ok(response)
    }

    /// List all backtests for a project.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn list_backtests(
        &self,
        project_id: i64,
        include_statistics: bool,
    ) -> Result<BacktestListResponse> {
        self.post(
            "/backtests/list",
            &ListBacktestsReq {
                project_id,
                include_statistics: if include_statistics { Some(true) } else { None },
            },
        )
        .await
    }
}
