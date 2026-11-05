//! Retry policy + transient-error classification for QC API calls.

use anyhow::Result;

/// Retry transient QC API failures (502/503/504, connection errors, timeouts).
/// BOUNDED: 6 retries with back-off [1, 2, 3, 5, 8, 13]s → ~32s max total.
/// Was [2,5,10,15,20,30,45,60,90,120]=397s — too long for hot-path polls
/// (slot cycles appeared stuck for 3+ min while retrying fresh-backtest 502s).
/// Client errors (4xx other than 408/429) fail fast without retry.
pub(crate) async fn with_retry<T, F, Fut>(path: &str, mut op: F) -> Result<T>
where
    F: FnMut() -> Fut,
    Fut: std::future::Future<Output = Result<T>>,
{
    let delays = [1u64, 2, 3, 5, 8, 13];
    let mut last_err: Option<anyhow::Error> = None;
    for (attempt, delay) in std::iter::once(&0u64).chain(delays.iter()).enumerate() {
        if *delay > 0 {
            tokio::time::sleep(std::time::Duration::from_secs(*delay)).await;
        }
        match op().await {
            Ok(v) => {
                if attempt > 0 {
                    tracing::info!("qc_api {path} recovered on attempt {attempt}");
                }
                return Ok(v);
            }
            Err(e) => {
                // A gateway error or lost response can follow a successful create.
                // Replaying such requests can launch duplicate paid backtests.
                if matches!(path, "/projects/create" | "/backtests/create")
                    && !e.chain().any(|cause| {
                        cause
                            .downcast_ref::<reqwest::Error>()
                            .is_some_and(reqwest::Error::is_connect)
                    })
                {
                    return Err(
                        e.context("remote create outcome is uncertain; request was not replayed")
                    );
                }
                if !is_transient(&e) {
                    return Err(e);
                }
                if attempt < delays.len() {
                    tracing::warn!(
                        "qc_api {path} transient error (attempt {}/{}): {e}",
                        attempt + 1,
                        delays.len() + 1
                    );
                }
                last_err = Some(e);
            }
        }
    }
    Err(last_err.unwrap_or_else(|| anyhow::anyhow!("with_retry: unknown failure")))
}

/// Classify an anyhow error as transient (retriable) vs permanent (fail fast).
/// Transient: 502, 503, 504, connection errors, timeouts, decode errors on partial responses.
pub(crate) fn is_transient(e: &anyhow::Error) -> bool {
    // Walk the error chain looking for a reqwest error we recognize.
    for cause in e.chain() {
        if let Some(re) = cause.downcast_ref::<reqwest::Error>() {
            if let Some(status) = re.status() {
                return matches!(status.as_u16(), 500 | 502 | 503 | 504 | 408 | 429);
            }
            if re.is_timeout() || re.is_connect() || re.is_request() || re.is_body() {
                return true;
            }
        }
    }
    // Also treat raw "502 Bad Gateway" / "Bad Gateway" / "Gateway Time-out" strings as transient
    // in case reqwest has already been unwrapped into a display string upstream.
    let s = e.to_string();
    s.contains("502")
        || s.contains("503")
        || s.contains("504")
        || s.contains("Bad Gateway")
        || s.contains("Gateway Time")
        || s.contains("timed out")
        || s.contains("connection reset")
        || s.contains("connection closed")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn typed_connection_failure_is_transient_after_context_wrapping() {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        drop(listener);
        let client = reqwest::Client::builder()
            .no_proxy()
            .connect_timeout(std::time::Duration::from_millis(100))
            .timeout(std::time::Duration::from_secs(1))
            .build()
            .unwrap();
        let error = client
            .post(format!("http://{address}/backtests/read"))
            .send()
            .await
            .unwrap_err();
        assert!(is_transient(
            &anyhow::Error::new(error).context("read observation")
        ));
    }

    #[tokio::test]
    async fn ambiguous_create_is_never_automatically_replayed() {
        let mut calls = 0;
        let result = with_retry::<(), _, _>("/backtests/create", || {
            calls += 1;
            async { anyhow::bail!("HTTP 503: gateway lost response") }
        })
        .await;
        assert!(result.is_err());
        assert_eq!(calls, 1);
    }
    #[tokio::test]
    async fn read_request_recovers_from_transient_gateway_failure() {
        let mut calls = 0;
        let result = with_retry("/backtests/read", || {
            calls += 1;
            let current = calls;
            async move {
                if current == 1 {
                    anyhow::bail!("HTTP 503")
                }
                Ok(42)
            }
        })
        .await
        .unwrap();
        assert_eq!(result, 42);
        assert_eq!(calls, 2);
    }
}
