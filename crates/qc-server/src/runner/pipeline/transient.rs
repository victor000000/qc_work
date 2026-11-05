//! Classify whether a QC poll-time error is a transient infra issue worth
//! requeuing, vs a permanent (user-code) error that should `mark_failed`.

/// Smoking gun for these patterns: multiple unrelated strategies hit them
/// in the same minute. The "Unable to import python module" error has
/// been observed across 4+ ETF strategies in a ~90s window — QC's
/// worker-cache miss, not anything in user code.
pub(super) fn is_qc_transient_poll_error(err: &str) -> bool {
    err.contains("Unable to import python module")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn transient_qc_cache_miss_classified() {
        assert!(is_qc_transient_poll_error(
            "Algorithm.Initialize() Error: Loader.TryCreatePythonAlgorithm(): \
             Unable to import python module ./cache/foo"
        ));
    }

    #[test]
    fn user_code_errors_are_not_transient() {
        // These are real failures we've seen on s003. None should be
        // mis-classified as transient — that would cause infinite retry.
        for err in [
            "Runtime Error: name 'delta' is not defined",
            "Runtime Error: boolean index did not match indexed array along dimension 0",
            "Runtime Error: ZNorm_DD_Builder.update() got an unexpected keyword argument 'close'",
            "Runtime Error: base_score must be in (0,1) for logistic loss, got: 0",
        ] {
            assert!(!is_qc_transient_poll_error(err), "should not match: {err}");
        }
    }
}
