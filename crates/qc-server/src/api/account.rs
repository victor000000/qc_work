use anyhow::Result;

use crate::client::QcClient;
use crate::models::account::{AccountResponse, LeanVersionsResponse};
use crate::models::common::RestResponse;

impl QcClient {
    /// Verify authentication is valid.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or non-2xx response.
    pub async fn authenticate(&self) -> Result<RestResponse> {
        self.post("/authenticate", &serde_json::json!({})).await
    }

    /// Read account info (organization, balance, card).
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn read_account(&self) -> Result<AccountResponse> {
        self.get("/account/read", &()).await
    }

    /// List available LEAN engine versions.
    ///
    /// # Errors
    /// Returns `Err` on HTTP transport failure or deserialization failure.
    pub async fn read_lean_versions(&self) -> Result<LeanVersionsResponse> {
        self.get("/lean/versions/read", &()).await
    }
}
