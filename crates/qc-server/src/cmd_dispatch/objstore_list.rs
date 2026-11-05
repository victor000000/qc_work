//! `obj-list` + `obj-stats` handlers.

use std::collections::BTreeMap;
use std::path::Path;

use anyhow::Result;

use crate::qc_setup::load_client_and_org;

pub(super) async fn list(data_dir: &Path, path: Option<&str>) -> Result<()> {
    let (client, org) = load_client_and_org(data_dir).await?;
    let resp = client.list_objects(&org, path).await?;
    if !resp.success {
        anyhow::bail!("list_objects failed: {:?}", resp.errors);
    }
    println!("{:<10} {:<26} KEY", "SIZE", "MODIFIED");
    for o in &resp.objects {
        let kind = if o.folder { "DIR " } else { "    " };
        println!("{:>8}   {:<24} {kind}{}", o.size, o.modified, o.key);
    }
    println!("{} entries", resp.objects.len());
    Ok(())
}

pub(super) async fn stats(data_dir: &Path, path: Option<&str>) -> Result<()> {
    let (client, org) = load_client_and_org(data_dir).await?;
    let mut totals: BTreeMap<String, (u64, u64)> = BTreeMap::new(); // category -> (count, bytes)
    let keys = super::objstore_meta::walk_leaves(&client, &org, path.unwrap_or("")).await?;
    let mut total_count = 0u64;
    let mut total_bytes = 0u64;
    for (key, size) in keys {
        let entry = totals.entry(categorize(&key)).or_default();
        entry.0 += 1;
        entry.1 += size;
        total_count += 1;
        total_bytes += size;
    }
    println!("{:<24} {:>10} {:>14}", "CATEGORY", "COUNT", "BYTES");
    for (cat, (n, b)) in &totals {
        println!("{cat:<24} {n:>10} {b:>14}");
    }
    println!("{:<24} {:>10} {:>14}", "TOTAL", total_count, total_bytes);
    Ok(())
}

/// Bucket an object-store key into a coarse category matching the Python
/// `qc_objstore.categorize` (see `lb/tools/qc_objstore.py`).
fn categorize(key: &str) -> String {
    if let Some(rest) = key.strip_prefix("bars_") {
        return format!("bars_{}", rest.split('/').next().unwrap_or(""));
    }
    if let Some(rest) = key.strip_prefix("models_") {
        return format!("models_{}", rest.split('/').next().unwrap_or(""));
    }
    if key.starts_with("features_") {
        return "features".into();
    }
    if key.starts_with("oos_") || key.starts_with("series_") {
        return "oos_series".into();
    }
    "other".into()
}
