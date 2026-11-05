//! Candidate scanning: find non-conflicting job from candidates.

/// Result of scanning candidates for a claimable job.
pub(crate) struct ScanResult {
    pub job_id: Option<i64>,
    pub effective_project_id: i64,
    pub skipped: usize,
}

/// Scan candidates and find the first non-conflicting job.
pub(crate) fn scan_candidates(
    candidates: &[(i64, Option<i64>)],
    running_projects: &[i64],
    default_project_id: i64,
    pool: &[i64],
) -> ScanResult {
    let mut job_id: Option<i64> = None;
    let mut effective_project_id = default_project_id;
    let mut skipped = 0usize;

    for (cid, stored_pid) in candidates {
        if let Some(sp) = stored_pid {
            // Job has a pinned project -- check if it conflicts
            if running_projects.contains(sp) {
                skipped += 1;
                continue;
            }
            job_id = Some(*cid);
            effective_project_id = *sp;
            break;
        }
        // No pinned project -- try default first, then scan pool
        if !running_projects.contains(&default_project_id) {
            job_id = Some(*cid);
            effective_project_id = default_project_id;
            break;
        }
        // Default busy -- find any free project from pool
        let mut found_alt = false;
        for alt in pool {
            if !running_projects.contains(alt) {
                job_id = Some(*cid);
                effective_project_id = *alt;
                found_alt = true;
                break;
            }
        }
        if found_alt {
            break;
        }
        // All projects busy -- skip this candidate
        skipped += 1;
    }

    ScanResult {
        job_id,
        effective_project_id,
        skipped,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pinned_candidate_claims_on_its_project() {
        let r = scan_candidates(&[(7, Some(42))], &[], 1, &[1, 2, 3]);
        assert_eq!(r.job_id, Some(7));
        assert_eq!(r.effective_project_id, 42);
    }

    #[test]
    fn pinned_candidate_skipped_when_its_project_is_running() {
        let r = scan_candidates(&[(7, Some(42)), (8, None)], &[42], 1, &[1]);
        assert_eq!(r.job_id, Some(8)); // unpinned next candidate took it
        assert_eq!(r.effective_project_id, 1);
        assert_eq!(r.skipped, 1);
    }

    #[test]
    fn unpinned_uses_default_when_free_then_pool_fallback() {
        let r = scan_candidates(&[(7, None)], &[], 5, &[1, 2]);
        assert_eq!(r.effective_project_id, 5);
        let r2 = scan_candidates(&[(7, None)], &[5], 5, &[1, 2]);
        assert_eq!(r2.effective_project_id, 1); // default busy → first free in pool
    }
}
