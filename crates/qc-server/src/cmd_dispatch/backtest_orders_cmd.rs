//! `backtest-orders` handler — paged fetch + summary or JSON dump.

use std::collections::HashSet;
use std::path::{Path, PathBuf};

use anyhow::Result;

use super::backtest_data_cmds::lookup_bt;
use crate::client::QcClient;
use crate::models::backtest_detail::Order;
use crate::qc_setup::load_client_and_org;
use crate::queue::open_db;

const PAGE: i64 = 99;

async fn fetch_orders(client: &QcClient, pid: i64, bt_id: &str) -> Result<Vec<Order>> {
    let mut all = Vec::new();
    let mut seen = HashSet::new();
    let mut cursor = 0i64;
    loop {
        let resp = client
            .read_backtest_orders(pid, bt_id, cursor, cursor + PAGE)
            .await?;
        anyhow::ensure!(
            resp.success,
            "read_backtest_orders failed: {:?}",
            resp.errors
        );
        let got = resp.orders.len();
        anyhow::ensure!(got <= usize::try_from(PAGE)?, "Oversized order page");
        for order in resp.orders {
            anyhow::ensure!(
                seen.insert(order.id),
                "Duplicate order ID across pages: {}",
                order.id
            );
            all.push(order);
        }
        if i64::try_from(got)? < PAGE {
            break;
        }
        cursor += PAGE;
    }
    Ok(all)
}

pub(super) async fn orders(
    data_dir: &Path,
    strategy: &str,
    name: &str,
    out: Option<&PathBuf>,
) -> Result<()> {
    let db = open_db(data_dir, strategy)?;
    let (bt_id, pid) = lookup_bt(&db, name).await?;
    let (client, _org) = load_client_and_org(data_dir).await?;
    let all = fetch_orders(&client, pid, &bt_id).await?;
    let response = client.read_backtest(pid, &bt_id).await?;
    anyhow::ensure!(
        response.success,
        "Backtest verification failed: {:?}",
        response.errors
    );
    let backtest = response
        .backtest
        .ok_or_else(|| anyhow::anyhow!("Backtest verification returned no backtest"))?;
    if let Some(expected) = backtest.statistics.get("Total Orders") {
        let count: usize = expected.replace(',', "").parse()?;
        anyhow::ensure!(
            all.len() == count,
            "Order coverage mismatch: {} downloaded versus {count} expected",
            all.len()
        );
    }
    if let Some(out_path) = out {
        let json = serde_json::to_string_pretty(&all)?;
        std::fs::write(out_path, json)?;
        println!("wrote {} orders -> {}", all.len(), out_path.display());
    } else {
        println!("{strategy}/{name}: {} orders", all.len());
        for o in all.iter().take(20) {
            let sym = o.symbol.as_ref().map_or("?", |s| s.value.as_str());
            println!(
                "  id={:<6} {sym:<8} qty={:>10.2} price={:>8.2} status={}",
                o.id, o.quantity, o.price, o.status
            );
        }
        if all.len() > 20 {
            println!(
                "  ... +{} more (use --out FILE to dump full JSON)",
                all.len() - 20
            );
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::client::test_support::mock_api;

    #[tokio::test]
    async fn progress_only_response_is_not_an_empty_order_history() {
        let (client, server) = mock_api(vec![(
            "/backtests/orders/read",
            r#"{"progress":0,"status":0,"success":true}"#,
        )])
        .await;
        assert!(fetch_orders(&client, 42, "bid").await.is_err());
        server.await.unwrap();
    }

    #[tokio::test]
    async fn invalid_page_size_is_rejected_before_network_access() {
        let client = QcClient::new("test", "test");
        for (start, end) in [(0, 100), (-1, 98), (99, 98)] {
            assert!(
                client
                    .read_backtest_orders(42, "bid", start, end)
                    .await
                    .is_err()
            );
        }
    }

    #[tokio::test]
    async fn pagination_keeps_every_order_and_rejects_duplicate_pages() {
        let first = serde_json::json!({"success":true,"length":100,"orders":(1..=99).map(|id| serde_json::json!({"id":id})).collect::<Vec<_>>()}).to_string();
        let first: &'static str = Box::leak(first.into_boxed_str());
        let (client, server) = mock_api(vec![
            ("/backtests/orders/read", first),
            (
                "/backtests/orders/read",
                r#"{"success":true,"length":100,"orders":[{"id":100}]}"#,
            ),
        ])
        .await;
        let orders = fetch_orders(&client, 42, "bid").await.unwrap();
        assert_eq!(orders.len(), 100);
        assert_eq!(orders[99].id, 100);
        server.await.unwrap();
        let (client, server) = mock_api(vec![
            ("/backtests/orders/read", first),
            (
                "/backtests/orders/read",
                r#"{"success":true,"orders":[{"id":99}]}"#,
            ),
        ])
        .await;
        assert!(fetch_orders(&client, 42, "bid").await.is_err());
        server.await.unwrap();
    }
}
