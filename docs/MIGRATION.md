# Folder migration map

The imported folder names have been replaced with these canonical paths:

| Previous path | Current path |
|---|---|
| `src/`, `tests/` (Rust), `build.rs` | `crates/qc-server/` |
| `SML01/` | `strategies/sml01/` |
| `lb/` | `strategies/wang-ml/` |
| `data/s001/` | `strategies/s001/` |
| `data/s002/` | `strategies/s002/` |
| `data/scripts/` | `strategies/s001/tools/` |
| `data/tests/` | `strategies/s001/tests/` |
| S001 generator helpers from `data/` | `strategies/s001/` |
| S001 JSON/CSV research evidence from `data/` | `strategies/s001/research/` |
| `data/archive/` | `strategies/s001/archive/` |
| `qc_workplace/` imported inside this workspace | `workspaces/lean/` |
| Old baseline backup files | Each strategy's `archive/baselines/` |
| Old server executable and downloaded macOS environment | `.local/legacy-binaries/`, `.local/legacy-environments/` |

The repository root is a Cargo workspace. `data/S*.duckdb` and `data/projects.json`
remain the shared runtime location. The new root `tests/` contains Python workspace
regressions; Rust integration tests live in the server crate.

Temporary folder aliases were removed after auditing active repository source and
verifying the canonical layouts. Dated archive notes can still mention old paths.
Update external shell commands/bookmarks with this table. The separate sibling
`/home/vic/qc_workplace` was not moved or modified.

The Python import package `lb` inside SML01 is retained for model/pickle compatibility;
it is distinct from the former root `lb/` research folder. Existing SQLite experiment
history and research evidence were preserved. The server upgrades generic execution
columns without changing research-owned `user_version` or strategy-specific tables.
