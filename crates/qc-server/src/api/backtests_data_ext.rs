//! Backtest data — insights + report endpoints.

use anyhow::Result;

use crate::client::QcClient;
use crate::models::backtest_ext::BacktestReportResponse;
use crate::models::backtest_insights::InsightsResponse;
use crate::models::backtest_req::{BacktestIdReq, ReadInsightsReq};

impl QcClient {
    /// Read insights from a backtest (end − start must be < 100).
    ///
    /// # Errors
    /// HTTP transport or deserialization failure.
    pub async fn read_backtest_insights(
        &self,
        project_id: i64,
        backtest_id: &str,
        start: i64,
        end: i64,
    ) -> Result<InsightsResponse> {
        self.post(
            "/backtests/read/insights",
            &ReadInsightsReq {
                project_id,
                backtest_id,
                start,
                end,
            },
        )
        .await
    }

    /// Request a backtest report (HTML with embedded images).
    ///
    /// # Errors
    /// HTTP transport or deserialization failure.
    pub async fn read_backtest_report(
        &self,
        project_id: i64,
        backtest_id: &str,
    ) -> Result<BacktestReportResponse> {
        self.post(
            "/backtests/read/report",
            &BacktestIdReq {
                project_id,
                backtest_id,
            },
        )
        .await
    }
}
