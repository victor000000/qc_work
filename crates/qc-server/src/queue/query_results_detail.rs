//! `errors --detail NAME` — pretty-print the stored failure for one job.

use anyhow::Result;

use crate::db::Db;

pub(super) async fn show_failure_detail(db: &Db, strategy: &str, name: &str) -> Result<()> {
    let n = name.to_string();
    let row: Option<(String, Option<String>, Option<String>)> = db
        .call(move |conn| {
            conn.query_row(
                "SELECT status, error_message, result_json \
                 FROM backtest_queue WHERE name=?1",
                [&n],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .map(Some)
            .or_else(|e| match e {
                duckdb::Error::QueryReturnedNoRows => Ok(None),
                _ => Err(e.into()),
            })
        })
        .await?;
    let Some((status, err, json)) = row else {
        println!("{strategy}/{name}: not found");
        return Ok(());
    };
    println!("{strategy}/{name}  status={status}");
    if let Some(e) = &err {
        println!("\nerror_message:\n  {e}");
    }
    if let Some(j) = &json {
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(j) {
            println!("\nresult_json:");
            println!(
                "{}",
                serde_json::to_string_pretty(&v).unwrap_or_else(|_| j.clone())
            );
        } else {
            println!("\nresult_json (raw):\n{j}");
        }
    } else {
        println!("\n(no result_json saved)");
    }
    Ok(())
}
