//! Find the next free `bt_pool_<n>` suffix by scanning QC's project list.

/// Query QC for all the user's projects and find the lowest unused
/// numeric suffix on `bt_pool_<n>`. Returns 1 if there are no `bt_pool_*`
/// projects on the account.
pub(super) async fn compute_next_pool_suffix(
    client: &crate::client::QcClient,
) -> anyhow::Result<u64> {
    let resp = client.read_project(None, None, None).await?;
    if !resp.success {
        anyhow::bail!(
            "read_project failed: {}",
            if resp.errors.is_empty() {
                "(no message)".into()
            } else {
                resp.errors.join("; ")
            }
        );
    }
    let mut used: std::collections::BTreeSet<u64> = std::collections::BTreeSet::new();
    for p in &resp.projects {
        if let Some(suffix) = p.name.strip_prefix("bt_pool_")
            && let Ok(n) = suffix.parse::<u64>()
        {
            used.insert(n);
        }
    }
    // First gap (or one-past-max). E.g. used={2,3,4} → 1; used={1,2,4} → 3.
    let mut next = 1u64;
    while used.contains(&next) {
        next += 1;
    }
    Ok(next)
}
