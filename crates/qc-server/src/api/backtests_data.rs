//! Backtest data: chart + orders. Insights/report live in `backtests_data_ext.rs`.

use anyhow::Result;

use crate::client::QcClient;
use crate::models::backtest_detail::OrdersResponse;
use crate::models::backtest_ext::ChartReadResponse;
use crate::models::backtest_req::{ReadChartReq, ReadOrdersReq};

impl QcClient {
    /// Read chart data for a backtest.
    ///
    /// # Errors
    /// HTTP transport or deserialization failure.
    pub async fn read_backtest_chart(
        &self,
        project_id: i64,
        backtest_id: &str,
        chart_name: &str,
        count: i64,
        start: i64,
        end: i64,
    ) -> Result<ChartReadResponse> {
        self.post(
            "/backtests/chart/read",
            &ReadChartReq {
                project_id,
                backtest_id,
                name: chart_name,
                count,
                start,
                end,
            },
        )
        .await
    }

    /// Read orders from a backtest (end − start must be < 100).
    ///
    /// # Errors
    /// HTTP transport or deserialization failure.
    pub async fn read_backtest_orders(
        &self,
        project_id: i64,
        backtest_id: &str,
        start: i64,
        end: i64,
    ) -> Result<OrdersResponse> {
        anyhow::ensure!(
            start >= 0 && end >= start && end - start < 100,
            "Order page requires 0 <= start <= end and end - start < 100"
        );
        self.post(
            "/backtests/orders/read",
            &ReadOrdersReq {
                project_id,
                backtest_id,
                start,
                end,
            },
        )
        .await
    }
}
