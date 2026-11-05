//! `Authorization: Basic`-style auth header builder for QC API.

use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result};
use base64::Engine;
use base64::engine::general_purpose::STANDARD as BASE64;
use reqwest::header::{AUTHORIZATION, HeaderMap, HeaderValue};
use sha2::{Digest, Sha256};

/// Build auth headers for a single request.
///
/// 1. `SHA256("{api_token}:{unix_timestamp}")` → hex string
/// 2. Base64-encode `"{user_id}:{hex_hash}"`
/// 3. `Authorization: Basic {base64}` + `Timestamp: {ts}`
pub(super) fn auth_headers(user_id: &str, api_token: &str) -> Result<HeaderMap> {
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .context("system clock before epoch")?
        .as_secs();

    let hash_input = format!("{api_token}:{ts}");
    let hash_hex = hex::encode(Sha256::digest(hash_input.as_bytes()));
    let basic = BASE64.encode(format!("{user_id}:{hash_hex}"));

    let mut headers = HeaderMap::new();
    headers.insert(
        AUTHORIZATION,
        HeaderValue::from_str(&format!("Basic {basic}"))?,
    );
    headers.insert("Timestamp", HeaderValue::from_str(&ts.to_string())?);
    Ok(headers)
}
