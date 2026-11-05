//! `batch-stats` — aggregate `runtimeStatistics` across a batch of done backtests.

use std::path::Path;

use anyhow::Result;

use crate::client::QcClient;
use crate::db::Db;
use crate::qc_setup::load_client_and_org;
use crate::queue::open_db;

/// Default metric keys when `--metrics` is omitted.
const DEFAULT_METRICS: &[&str] = &["calmar", "mdd", "ann", "sharpe", "mean_auc"];

pub(super) async fn run(
    data_dir: &Path,
    strategy: &str,
    batch: &str,
    metrics: Option<&str>,
) -> Result<()> {
    let db = open_db(data_dir, strategy)?;
    let rows = fetch_batch_rows(&db, batch).await?;
    if rows.is_empty() {
        println!("no done experiments in {strategy} batch={batch}");
        return Ok(());
    }
    let metric_list: Vec<String> = metrics.map_or_else(
        || DEFAULT_METRICS.iter().map(|s| (*s).to_string()).collect(),
        |s| s.split(',').map(|x| x.trim().to_string()).collect(),
    );
    let (client, _org) = load_client_and_org(data_dir).await?;
    print_header(&metric_list);
    for (name, bt_id, pid) in &rows {
        emit_row(&client, name, bt_id, *pid, &metric_list).await;
    }
    Ok(())
}

async fn fetch_batch_rows(db: &Db, batch: &str) -> Result<Vec<(String, String, i64)>> {
    let b = batch.to_string();
    let rows: Vec<(String, Option<String>, Option<i64>)> = db
        .call(move |conn| {
            let mut stmt = conn.prepare(
                "SELECT name, backtest_id, project_id
                 FROM backtest_queue
                 WHERE batch=?1 AND status='done' AND backtest_id IS NOT NULL
                 ORDER BY id",
            )?;
            let rows = stmt
                .query_map([&b], |r| {
                    Ok((
                        r.get::<_, String>(0)?,
                        r.get::<_, Option<String>>(1)?,
                        r.get::<_, Option<i64>>(2)?,
                    ))
                })?
                .collect::<Result<Vec<_>, _>>()?;
            Ok(rows)
        })
        .await?;
    Ok(rows
        .into_iter()
        .filter_map(|(n, b, p)| Some((n, b?, p?)))
        .collect())
}

fn print_header(metrics: &[String]) {
    print!("{:<18} {:<6}", "name_tail", "ticker");
    for m in metrics {
        print!(" {m:>10}");
    }
    println!();
}

async fn emit_row(client: &QcClient, name: &str, bt_id: &str, pid: i64, metrics: &[String]) {
    let tail = name.split('_').nth_back(0).unwrap_or(name);
    let ticker = name.split('_').nth(2).unwrap_or("?");
    print!("{tail:<18} {ticker:<6}");
    if let Ok(r) = client.read_backtest(pid, bt_id).await
        && r.success
        && let Some(bt) = r.backtest
    {
        for m in metrics {
            let v = bt
                .runtime_statistics
                .get(m)
                .cloned()
                .unwrap_or_else(|| "-".into());
            print!(" {v:>10}");
        }
        println!();
        return;
    }
    for _ in metrics {
        print!(" {:>10}", "ERR");
    }
    println!();
}
