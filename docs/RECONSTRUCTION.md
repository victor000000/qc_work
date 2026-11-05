# Workspace reconstruction

Purpose: shared QuantConnect execution infrastructure and isolated strategy research.

## Target structure

- `crates/qc-server/`: generic Rust API client, queue runner, CLI, regression tests.
- `strategies/s001/`, `strategies/s002/`: independent cross-sectional experiments.
- `strategies/sml01/`: ML autoresearch package, templates, tests and research results.
- `strategies/wang-ml/`: independent historical Wang ML experiments and reference material.
- `data/`: shared runtime configuration and per-strategy DuckDB queues (local, never committed).
- `scripts/`: workspace setup, validation, explicit live API checks.
- `.github/workflows/`: offline regression CI; live checks must be explicit.

Root `Cargo.toml` is the workspace entrypoint. Run Cargo from the repository root.
Imported strategy folders now use canonical paths. The temporary migration aliases
have been removed; see `docs/MIGRATION.md`. Mutable research state has one owner.

## Acceptance checklist

- [x] Separate server crate and primary research workspaces, preserving data.
- [x] Move S001 scripts, tests and datasets out of shared runtime storage.
- [x] Replace active host-specific runtime paths and remove temporary folder aliases.
- [x] Generic schema bootstrap/migrations and a documented new-strategy workflow.
- [x] Review API transport, retry semantics, claims, recovery and shutdown; add bounded polling and shutdown.
- [x] Regression tests for disabled strategies, job isolation, statistics failure outcomes, retry state and execution identity.
- [x] Rust format, strict Clippy, tests and release build pass locally.
- [x] Independent S001, S002 and SML01 Python tests pass.
- [x] CI uses the same commands and locked Python dependencies as local validation.
- [x] Authenticate and run an isolated real QC compile/backtest/result-collection smoke test.
- [x] Finish the full shared-server smoke test, including cleanup and verified graceful shutdown.
- [x] Validate all eight configured production project IDs against QC.
- [x] Validate repaired S001 and S002 baselines on QC.
- [x] Complete SML01 train-to-inference validation after restoring ObjectStore capacity.
- [x] Verify the user-requested complete ObjectStore reset after validation cleanup.
- [x] Clean up all recorded temporary validation projects.
- [x] Run the dependency security audit and update vulnerable dependencies.
- [x] Document run/setup/debug commands and verification evidence.

No completeness claim is made until all acceptance items have current evidence.

## Current verification

The updated shared-server cloud harness passed source isolation, rejection of an
end-of-algorithm runtime error, graceful shutdown and project deletion. All eight pool
projects were confirmed present. S001 and S002 full baselines passed; S001 now handles
retired Morningstar fields and missing-value comparisons while retaining its original
source in the archive. RustSec dependencies were updated and now audit cleanly.

The ObjectStore initially exceeded its current quota. The user explicitly authorized
removing every cloud object after reviewing a complete metadata inventory. API directory
listings became empty before the physical files were gone; native QC ObjectStore
operations then deleted the remaining 15,994 files and reported zero failures and zero
files afterward. The earlier inventory remains a historical pre-reset snapshot.

SML01 now passes real train-to-inference validation: one model saved, 1,109 predictions
loaded and replayed, and 45 orders. Its isolated project and UUID model namespace were
cleaned up. A final native cleanup removed six validation artifacts; a separate fresh
QC process then confirmed zero files. The API also confirmed zero root entries and zero
bytes used, with no active owned temporary projects remaining. Local source,
configs, experiment databases and research history were preserved; earlier cloud models
and caches must be regenerated. Detailed evidence is in `docs/VERIFICATION.md`.

Historical research campaigns have syntax validation and portable path fixes;
their financial/ML behaviour has not been exhaustively rerun on cloud data.
Historical archive notes retain their original paths as dated records; use the migration map for current commands.
