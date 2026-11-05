//! Backtest write endpoints: create / update / delete / tags.

use std::collections::HashMap;

use anyhow::Result;
use serde_json::Value;

use crate::client::QcClient;
use crate::models::backtest::BacktestResponse;
use crate::models::backtest_req::{
    BacktestIdReq, CreateBacktestReq, UpdateBacktestReq, UpdateBacktestTagsReq,
};
use crate::models::common::RestResponse;

impl QcClient {
    /// Create and launch a new cloud backtest.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn create_backtest(
        &self,
        project_id: i64,
        compile_id: &str,
        backtest_name: &str,
        parameters: Option<&HashMap<String, Value>>,
    ) -> Result<BacktestResponse> {
        let req = CreateBacktestReq {
            project_id,
            compile_id,
            backtest_name,
            parameters,
        };
        self.post("/backtests/create", &req).await
    }

    /// Update backtest name / note.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or non-2xx response.
    pub async fn update_backtest(
        &self,
        project_id: i64,
        backtest_id: &str,
        name: Option<&str>,
        note: Option<&str>,
    ) -> Result<RestResponse> {
        self.post(
            "/backtests/update",
            &UpdateBacktestReq {
                project_id,
                backtest_id,
                name,
                note,
            },
        )
        .await
    }

    /// Delete a backtest.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or non-2xx response.
    pub async fn delete_backtest(
        &self,
        project_id: i64,
        backtest_id: &str,
    ) -> Result<RestResponse> {
        self.post(
            "/backtests/delete",
            &BacktestIdReq {
                project_id,
                backtest_id,
            },
        )
        .await
    }

    /// Update tags on a backtest.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or non-2xx response.
    pub async fn update_backtest_tags(
        &self,
        project_id: i64,
        backtest_id: &str,
        tags: &[String],
    ) -> Result<RestResponse> {
        self.post(
            "/backtests/tags/update",
            &UpdateBacktestTagsReq {
                project_id,
                backtest_id,
                tags,
            },
        )
        .await
    }
}
