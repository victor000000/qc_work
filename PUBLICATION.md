# Publication and research-data boundaries

Current public source is maintained at `victor000000/qc_work`. The separate native operational workspace can lack Git metadata; reviewed changes are committed in the established publication checkout. Never initialize a competing Git history merely to record operational artifacts.

Public source includes the executor, supported strategy modules/templates, synthetic tests, documentation and dependency locks. Private credentials, account databases, provider datasets, logs, cloud result archives, generated charts/bundles, environments, binaries and nested repositories are omitted by publication policy and `.gitignore`. A historical link to such an artifact is a provenance pointer, not evidence that it is public or permission to reconstruct it. Absolute adjacent-project links in retained historical documents may only work on the original workstation.

The documentation audit separates canonical navigation from unavailable historical evidence. Native source/data inventories are recorded separately from the public tracked inventory. Operational-only archives remain private and retain their original dates. Existing source hashes identify copied diagnostic files; CI checks identify exact published commits, not market-data releases.

The November 7 native-cache candidate was published at `8c29672d76968b1bd18c31fb3bc3dc33d75d3c2e`; its complete source tree matched the tested candidate and all seven CI jobs passed. Later documentation commits require their own exact-tree/CI acceptance. No automated deployment or trading action accompanies publication.

## Retained original snapshot record

# Public source snapshot — 2026-11-05

Sanitized qc_work source and documentation prepared for https://github.com/victor000000/qc_work.

Credentials, account databases, logs, cloud result archives, provider datasets, generated charts, local environments, compiled binaries, and nested repositories are excluded. Ordinary source/configuration is not backed up to Drive. The owner keeps credential restoration material separately in private Google Drive.

Credential values are excluded. The initial scanner flag in scripts/gdrive_backup.py was a public OAuth endpoint, not a credential, and the endpoint is preserved. The operational source is unchanged. Some research tools require omitted local datasets and evidence; historical documentation links to those local artifacts are intentionally not evidence of publicly published data. This is a source snapshot, not a complete research-data release.

Local validation: 427 tests pass in the operational workspace. C0 still fails on native margin intervention; the IV early-close replay passes without establishing a solver fix. Full release/economic acceptance is false. The public snapshot itself has not been asserted to pass tests that require omitted private fixtures.
