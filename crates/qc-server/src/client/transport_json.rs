//! `json_request` — POST/PUT/DELETE JSON helper with retry + response sniffing.
//!
//! Per-call logs `status` + `bytes`, scans 200-OK bodies for `"success":false`
//! to surface soft-fails that don't trip rate-limit detection.

use anyhow::Result;
use reqwest::Method;
use serde::Serialize;
use serde::de::DeserializeOwned;

use super::QcClient;
use super::retry::with_retry;
use super::trace::traced_call;

impl QcClient {
    /// Generic JSON request helper with retry on transient failures.
    pub(super) async fn json_request<T: DeserializeOwned>(
        &self,
        method: Method,
        path: &str,
        body: Option<&(impl Serialize + Sync)>,
    ) -> Result<T> {
        let url = format!("{}{}", self.base_url, path);
        let mut attempt = 0usize;
        with_retry(path, || {
            attempt += 1;
            let url = url.clone();
            let m = method.clone();
            let m_str: &'static str = match m {
                Method::POST => "POST",
                Method::PUT => "PUT",
                Method::DELETE => "DELETE",
                Method::GET => "GET",
                _ => "?",
            };
            async move {
                traced_call(path, m_str, attempt, || async {
                    let mut req = self.http.request(m, &url).headers(self.headers()?);
                    if let Some(b) = body {
                        req = req.json(b);
                    }
                    let resp = req.send().await?;
                    let status = resp.status();
                    let bytes = resp.bytes().await?;
                    // trace! — paired with qc_api_call (which already logs
                    // elapsed_ms + band); the status/bytes are useful only
                    // for deeper debugging. Was ~6500 lines/hr.
                    tracing::trace!(
                        target: "qc::api",
                        "qc_api_resp path={path} method={m_str} status={} bytes={}",
                        status.as_u16(),
                        bytes.len()
                    );
                    if !status.is_success() {
                        return Err(anyhow::anyhow!(
                            "qc {m_str} {path} HTTP {} body={}",
                            status.as_u16(),
                            String::from_utf8_lossy(&bytes[..bytes.len().min(200)])
                        ));
                    }
                    // 2026-05-07: surface 200-OK + `"success":false` soft-fails
                    // that don't match the rate-limit regex.
                    if bytes.len() < 4096 {
                        let needle = br#""success":false"#;
                        if bytes
                            .windows(needle.len())
                            .any(|w| w.eq_ignore_ascii_case(needle))
                        {
                            tracing::debug!(
                                target: "qc::api",
                                "qc_api_softfail path={path} method={m_str} bytes={} body={}",
                                bytes.len(),
                                String::from_utf8_lossy(&bytes[..bytes.len().min(240)])
                            );
                        }
                    }
                    Ok(serde_json::from_slice(&bytes)?)
                })
                .await
            }
        })
        .await
    }
}
