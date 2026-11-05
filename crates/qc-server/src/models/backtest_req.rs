//! Backtest API request helpers.

use std::collections::HashMap;

use serde::Serialize;
use serde_json::Value;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct CreateBacktestReq<'a> {
    pub project_id: i64,
    pub compile_id: &'a str,
    pub backtest_name: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parameters: Option<&'a HashMap<String, Value>>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct BacktestIdReq<'a> {
    pub project_id: i64,
    pub backtest_id: &'a str,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ListBacktestsReq {
    pub project_id: i64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub include_statistics: Option<bool>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct UpdateBacktestReq<'a> {
    pub project_id: i64,
    pub backtest_id: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub note: Option<&'a str>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct UpdateBacktestTagsReq<'a> {
    pub project_id: i64,
    pub backtest_id: &'a str,
    pub tags: &'a [String],
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ReadChartReq<'a> {
    pub project_id: i64,
    pub backtest_id: &'a str,
    pub name: &'a str,
    pub count: i64,
    pub start: i64,
    pub end: i64,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ReadOrdersReq<'a> {
    pub project_id: i64,
    pub backtest_id: &'a str,
    pub start: i64,
    pub end: i64,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ReadInsightsReq<'a> {
    pub project_id: i64,
    pub backtest_id: &'a str,
    pub start: i64,
    pub end: i64,
}
