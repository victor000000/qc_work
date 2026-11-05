//! `obj-props` + `obj-bulk-delete` handlers.

use std::collections::{BTreeMap, HashSet};
use std::path::Path;

use anyhow::Result;

use crate::client::QcClient;
use crate::qc_setup::load_client_and_org;

pub(super) async fn props(data_dir: &Path, key: &str) -> Result<()> {
    let (client, org) = load_client_and_org(data_dir).await?;
    let resp = client.get_object_properties(&org, key).await?;
    if !resp.success {
        anyhow::bail!("get_object_properties failed: {:?}", resp.errors);
    }
    let Some(m) = resp.metadata else {
        println!("no metadata returned for {key}");
        return Ok(());
    };
    println!("key:       {}", m.key);
    println!("size:      {}", m.size);
    println!("modified:  {}", m.modified);
    println!("created:   {}", m.created);
    if let Some(md) = &m.md5 {
        println!("md5:       {md}");
    }
    if let Some(mime) = &m.mime {
        println!("mime:      {mime}");
    }
    if let Some(p) = &m.preview {
        println!("preview:   {p}");
    }
    Ok(())
}

pub(super) async fn bulk_delete(data_dir: &Path, prefix: &str, yes: bool) -> Result<()> {
    if prefix.trim_matches('/').is_empty() {
        anyhow::bail!(
            "obj-bulk-delete: --prefix is empty or root; refusing to walk the entire object store"
        );
    }
    let (client, org) = load_client_and_org(data_dir).await?;
    let keys = walk_leaves(&client, &org, prefix).await?;
    let n = keys.len();
    let bytes: u64 = keys.iter().map(|(_, s)| *s).sum();
    if !yes {
        println!("dry-run: would delete {n} keys / {bytes} bytes under {prefix}");
        for (k, s) in keys.iter().take(10) {
            println!("  {s:>10}  {k}");
        }
        if n > 10 {
            println!("  ...");
        }
        println!("re-run with --yes to delete.");
        return Ok(());
    }
    let mut deleted = 0u64;
    let mut failed = 0u64;
    // Don't bail on first network error — keep going so partial cleanup is
    // visible and remaining keys still get tried.
    for (k, _) in &keys {
        match client.delete_object(&org, k).await {
            Ok(resp) if resp.success => deleted += 1,
            Ok(resp) => {
                failed += 1;
                eprintln!("delete failed: {k}: {:?}", resp.errors);
            }
            Err(e) => {
                failed += 1;
                eprintln!("delete error: {k}: {e}");
            }
        }
    }
    println!("deleted {deleted}/{n} keys ({failed} failed) under {prefix}");
    anyhow::ensure!(
        failed == 0,
        "{failed} ObjectStore deletions failed under {prefix}"
    );
    Ok(())
}

/// Recursive walk that returns leaf keys (`(key, size)`).
pub(super) async fn walk_leaves(
    client: &QcClient,
    org: &str,
    prefix: &str,
) -> Result<Vec<(String, u64)>> {
    let prefix = prefix.trim_start_matches('/');
    let mut out = BTreeMap::new();
    let mut visited = HashSet::new();
    let mut stack: Vec<String> = vec![prefix.to_string()];
    while let Some(p) = stack.pop() {
        if !visited.insert(p.clone()) {
            continue;
        }
        let p_opt = if p.is_empty() { None } else { Some(p.as_str()) };
        let resp = client.list_objects(org, p_opt).await?;
        if !resp.success {
            anyhow::bail!("list failed at {p:?}: {:?}", resp.errors);
        }
        anyhow::ensure!(
            resp.total_pages.unwrap_or(1) <= 1,
            "ObjectStore listing at {p:?} has multiple pages; traversal aborted"
        );
        for o in &resp.objects {
            let key = o.key.trim_start_matches('/');
            anyhow::ensure!(
                key.starts_with(prefix),
                "ObjectStore returned key outside requested prefix: {:?}",
                o.key
            );
            if o.folder || o.key.ends_with('/') {
                stack.push(key.to_owned());
            } else {
                out.insert(key.to_owned(), u64::try_from(o.size).unwrap_or(0));
            }
        }
    }
    Ok(out.into_iter().collect())
}

#[cfg(test)]
mod tests {
    use super::walk_leaves;
    use crate::client::test_support::mock_api;

    #[tokio::test]
    async fn root_prefix_is_rejected_before_loading_credentials() {
        for prefix in ["", "/", "///"] {
            let error = super::bulk_delete(
                std::path::Path::new("/missing-inventory-test"),
                prefix,
                true,
            )
            .await
            .unwrap_err();
            assert!(error.to_string().contains("empty or root"));
        }
    }

    #[tokio::test]
    async fn rejected_listing_aborts_deletion_plan() {
        let (client, server) = mock_api(vec![(
            "/object/list",
            r#"{"success":false,"errors":["denied"]}"#,
        )])
        .await;
        assert!(walk_leaves(&client, "org", "owned/").await.is_err());
        server.await.unwrap();
    }

    #[tokio::test]
    async fn unrelated_key_aborts_deletion_plan() {
        let (client, server) = mock_api(vec![(
            "/object/list",
            r#"{"success":true,"objects":[{"key":"production/model"}]}"#,
        )])
        .await;
        let error = walk_leaves(&client, "org", "owned/").await.unwrap_err();
        assert!(error.to_string().contains("outside requested prefix"));
        server.await.unwrap();
    }

    #[tokio::test]
    async fn folder_cycle_is_visited_once() {
        let (client, server) = mock_api(vec![("/object/list", r#"{"success":true,"totalPages":null,"objects":[{"key":"/owned/","folder":true},{"key":"/owned/model","size":42}]}"#)]).await;
        assert_eq!(
            walk_leaves(&client, "org", "owned/").await.unwrap(),
            vec![("owned/model".into(), 42)]
        );
        server.await.unwrap();
    }
}
