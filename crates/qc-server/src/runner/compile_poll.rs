//! Shared, bounded compile polling for direct slots and warm-pool workers.
use super::SlotRunner;
use crate::client::QcClient;
use crate::rate_limit::is_rate_limit;
use anyhow::{Result, bail, ensure};
use std::time::Instant;
use tokio::time::{Duration, sleep};

impl SlotRunner {
    pub(super) async fn poll_compile(
        &self,
        project_id: i64,
        compile_id: &str,
        job_name: &str,
        poll_interval: Duration,
        timeout: Duration,
    ) -> Result<Duration> {
        wait_compile(
            &self.client,
            project_id,
            compile_id,
            job_name,
            poll_interval,
            timeout,
        )
        .await
    }
}

pub(crate) async fn wait_compile(
    client: &QcClient,
    project_id: i64,
    compile_id: &str,
    job_name: &str,
    poll_interval: Duration,
    timeout: Duration,
) -> Result<Duration> {
    tokio::time::timeout(timeout, async {
        let start = Instant::now();
        loop {
            let response = match client.read_compile(project_id, compile_id).await {
                Ok(response) => response,
                Err(error) if is_rate_limit(&error) => {
                    sleep(Duration::from_millis(1400)).await;
                    continue;
                }
                Err(error) => return Err(error),
            };
            ensure!(
                response.success,
                "compile_read_failed: {:?}",
                response.errors
            );
            match response.state.as_str() {
                "BuildSuccess" => return Ok(start.elapsed()),
                "BuildError" => bail!("compile_error: {:?}", response.logs),
                "InQueue" => sleep(poll_interval).await,
                other => bail!("compile_unknown_state: {other}"),
            }
        }
    })
    .await
    .map_err(|_| anyhow::anyhow!("compile_timeout: {job_name}"))?
}

#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn compile_budget_includes_waits_between_api_reads() {
        let (client, server) = crate::client::test_support::mock_api(vec![(
            "/compile/read",
            r#"{"success":true,"state":"InQueue"}"#,
        )])
        .await;
        let result = wait_compile(
            &client,
            1,
            "cid",
            "test",
            Duration::from_mins(1),
            Duration::from_millis(250),
        )
        .await;
        server.abort();
        assert!(result.unwrap_err().to_string().contains("compile_timeout"));
    }
}
