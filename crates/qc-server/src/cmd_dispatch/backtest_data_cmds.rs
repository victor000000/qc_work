//! Dispatch entry + `backtest-stats` handler (orders handler is in
//! `backtest_orders_cmd.rs`).

use std::path::Path;

use anyhow::Result;
use duckdb::OptionalExt;

use super::backtest_orders_cmd;
use super::batch_stats_cmd;
use crate::cli::Command;
use crate::db::Db;
use crate::qc_setup::load_client_and_org;
use crate::queue::open_db;

pub(super) async fn try_dispatch(command: Command, data_dir: &Path) -> Result<Option<Command>> {
    match command {
        Command::BacktestStats { strategy, name } => {
            stats(data_dir, &strategy, &name).await?;
            Ok(None)
        }
        Command::BacktestOrders {
            strategy,
            name,
            out,
        } => {
            backtest_orders_cmd::orders(data_dir, &strategy, &name, out.as_ref()).await?;
            Ok(None)
        }
        Command::BatchStats {
            strategy,
            batch,
            metrics,
        } => {
            batch_stats_cmd::run(data_dir, &strategy, &batch, metrics.as_deref()).await?;
            Ok(None)
        }
        other => Ok(Some(other)),
    }
}

pub(super) async fn lookup_bt(db: &Db, name: &str) -> Result<(String, i64)> {
    let n = name.to_string();
    let row: Option<(Option<String>, Option<i64>)> = db
        .call(move |conn| {
            conn.query_row(
                "SELECT backtest_id, project_id FROM backtest_queue WHERE name=?1",
                [&n],
                |r| Ok((r.get::<_, Option<String>>(0)?, r.get::<_, Option<i64>>(1)?)),
            )
            .optional()
            .map_err(Into::into)
        })
        .await?;
    let Some((bt, pid)) = row else {
        anyhow::bail!("{name}: not found in queue");
    };
    let bt = bt.ok_or_else(|| anyhow::anyhow!("{name}: no backtest_id"))?;
    let pid = pid.ok_or_else(|| anyhow::anyhow!("{name}: no project_id"))?;
    Ok((bt, pid))
}

async fn stats(data_dir: &Path, strategy: &str, name: &str) -> Result<()> {
    let db = open_db(data_dir, strategy)?;
    let (bt_id, pid) = lookup_bt(&db, name).await?;
    let (client, _org) = load_client_and_org(data_dir).await?;
    let resp = client.read_backtest(pid, &bt_id).await?;
    if !resp.success {
        anyhow::bail!("read_backtest failed: {:?}", resp.errors);
    }
    let Some(bt) = resp.backtest else {
        anyhow::bail!("read_backtest returned no backtest");
    };
    println!("{strategy}/{name}  ({bt_id})");
    println!(
        "  status={}  progress={:.1}%",
        bt.status.as_deref().unwrap_or("?"),
        bt.progress * 100.0
    );
    let mut rs: Vec<(&String, &String)> = bt.runtime_statistics.iter().collect();
    rs.sort_by(|a, b| a.0.cmp(b.0));
    for (k, v) in rs {
        println!("  {k:<28} {v}");
    }
    Ok(())
}
