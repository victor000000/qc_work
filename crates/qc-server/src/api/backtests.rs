//! Backtest read/list endpoints.
//!
//! Write endpoints (create/update/delete/tags) live in `backtests_write.rs`.
//! Bulk data (chart/orders/insights/report) lives in `backtests_data.rs`.

use anyhow::Result;

use crate::client::QcClient;
use crate::models::backtest::BacktestResponse;
use crate::models::backtest_list::BacktestListResponse;
use crate::models::backtest_req::{BacktestIdReq, ListBacktestsReq};

impl QcClient {
    /// Read full backtest results (statistics, charts, etc.).
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn read_backtest(
        &self,
        project_id: i64,
        backtest_id: &str,
    ) -> Result<BacktestResponse> {
        self.post(
            "/backtests/read",
            &BacktestIdReq {
                project_id,
                backtest_id,
            },
        )
        .await
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
