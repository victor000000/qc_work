# Public source snapshot — 2026-11-05

Sanitized qc_work source and documentation prepared for https://github.com/victor000000/qc_work.

Credentials, account databases, logs, cloud result archives, provider datasets, generated charts, local environments, compiled binaries, and nested repositories are excluded. Ordinary source/configuration is not backed up to Drive. The owner keeps credential restoration material separately in private Google Drive.

Credential values are excluded. The initial scanner flag in scripts/gdrive_backup.py was a public OAuth endpoint, not a credential, and the endpoint is preserved. The operational source is unchanged. Some research tools require omitted local datasets and evidence; historical documentation links to those local artifacts are intentionally not evidence of publicly published data. This is a source snapshot, not a complete research-data release.

Local validation: 427 tests pass in the operational workspace. C0 still fails on native margin intervention; the IV early-close replay passes without establishing a solver fix. Full release/economic acceptance is false. The public snapshot itself has not been asserted to pass tests that require omitted private fixtures.
