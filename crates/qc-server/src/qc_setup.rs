//! Shared credentials-loading prelude for CLI commands that talk to QC.
//!
//! Every CLI handler that needs a `QcClient` previously repeated the
//! same prelude: load `ServerConfig`, pull `qc_user_id`/`qc_api_token`
//! from it, hand them to `QcClient::new`. This module collapses that to
//! one call so credential loading stays consistent and any future
//! change (e.g. encrypted secrets) happens in one place.

use std::path::Path;

use anyhow::Result;

use crate::client::QcClient;
use crate::config::ServerConfig;

/// Build a QC client from `data_dir`'s strategy DBs (strategy settings live in
/// the `settings` table of the first DB found).
///
/// # Errors
/// Returns `Err` if config loading or any DB-open fails.
pub(crate) async fn load_client(data_dir: &Path) -> Result<QcClient> {
    let (config, _dbs) = ServerConfig::load(data_dir).await?;
    Ok(QcClient::new(&config.qc_user_id, &config.qc_api_token))
}

/// Same as `load_client` but also returns `organization_id` — needed by
/// the object-store API endpoints.
///
/// # Errors
/// Returns `Err` if config loading or any DB-open fails.
pub(crate) async fn load_client_and_org(data_dir: &Path) -> Result<(QcClient, String)> {
    let (config, _dbs) = ServerConfig::load(data_dir).await?;
    let client = QcClient::new(&config.qc_user_id, &config.qc_api_token);
    Ok((client, config.organization_id))
}
