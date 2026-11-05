use std::path::Path;

use anyhow::{Result, ensure};

use crate::client::QcClient;
use crate::config::ServerConfig;

/// Smoke-test the QC API: auth, list nodes for each strategy, read account.
///
/// # Errors
/// Returns `Err` on config load failure or any QC HTTP call failure.
pub async fn test_api(data_dir: &Path) -> Result<()> {
    let (config, _dbs) = ServerConfig::load(data_dir).await?;
    let client = QcClient::new(&config.qc_user_id, &config.qc_api_token);

    check_client(&client, &config).await
}

async fn check_client(client: &QcClient, config: &ServerConfig) -> Result<()> {
    // Auth
    let auth = client.authenticate().await?;
    ensure!(
        auth.success,
        "QC authentication rejected: {:?}",
        auth.errors
    );
    println!("auth: passed");

    // Nodes
    for strat in &config.strategies {
        let Some(&pid) = strat.project_ids.first() else {
            println!("{}: no project IDs, skipping nodes check", strat.name);
            continue;
        };
        let resp = client.read_project_nodes(pid).await?;
        ensure!(
            resp.success,
            "{} node check rejected: {:?}",
            strat.name,
            resp.errors
        );
        let nodes = resp
            .nodes
            .ok_or_else(|| anyhow::anyhow!("{}: node response has no payload", strat.name))?;
        ensure!(
            !nodes.backtest.is_empty(),
            "{}: no backtest nodes available",
            strat.name
        );
        println!(
            "{} nodes ({pid}): {} backtest, autoSelect={}",
            strat.name,
            nodes.backtest.len(),
            resp.auto_select_node,
        );
        for n in &nodes.backtest {
            println!("  {} sku={} busy={}", n.id, n.sku, n.busy);
        }
    }

    // Account
    let acct = client.read_account().await?;
    ensure!(acct.success, "QC account read rejected: {:?}", acct.errors);
    println!("account: passed");

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn rejected_authentication_is_a_failed_diagnostic() {
        let (client, server) = crate::client::test_support::mock_api(vec![(
            "/authenticate",
            r#"{"success":false,"errors":["invalid credentials"]}"#,
        )])
        .await;
        let config = ServerConfig {
            qc_user_id: "unused".into(),
            qc_api_token: "unused".into(),
            organization_id: "unused".into(),
            strategies: vec![],
            node_ids: vec![],
        };
        let error = check_client(&client, &config).await.unwrap_err();
        assert!(error.to_string().contains("authentication rejected"));
        server.await.unwrap();
    }
}
