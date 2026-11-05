//! `obj-get` / `obj-put` / `obj-delete` handlers.

use std::path::{Path, PathBuf};

use anyhow::Result;

use crate::qc_setup::load_client_and_org;

pub(super) async fn get(data_dir: &Path, key: &str, out: Option<&PathBuf>) -> Result<()> {
    let (client, org) = load_client_and_org(data_dir).await?;
    let resp = client.get_object(&org, key).await?;
    if !resp.success {
        anyhow::bail!("get_object failed: {:?}", resp.errors);
    }
    let Some(url) = resp.url else {
        anyhow::bail!("get_object: server returned no url");
    };
    let Some(out_path) = out else {
        println!("{url}");
        return Ok(());
    };
    let bytes = client
        .http
        .get(&url)
        .timeout(std::time::Duration::from_mins(5))
        .send()
        .await?
        .error_for_status()?
        .bytes()
        .await?;
    let n = bytes.len();
    std::fs::write(out_path, &bytes)?;
    println!("downloaded {n} bytes -> {}", out_path.display());
    Ok(())
}

pub(super) async fn put(data_dir: &Path, key: &str, file: &Path) -> Result<()> {
    let (client, org) = load_client_and_org(data_dir).await?;
    let bytes = std::fs::read(file)?;
    let n = bytes.len();
    let resp = client.upload_object(&org, key, bytes).await?;
    if !resp.success {
        anyhow::bail!("upload_object failed: {:?}", resp.errors);
    }
    println!("uploaded {n} bytes -> {key}");
    Ok(())
}

pub(super) async fn delete(data_dir: &Path, key: &str, yes: bool) -> Result<()> {
    if !yes {
        anyhow::bail!("delete {key}: re-run with --yes to confirm");
    }
    let (client, org) = load_client_and_org(data_dir).await?;
    let resp = client.delete_object(&org, key).await?;
    if !resp.success {
        anyhow::bail!("delete_object failed: {:?}", resp.errors);
    }
    println!("deleted {key}");
    Ok(())
}
