# CI and deployment boundaries

The public checkout has credential-free Python and Rust CI. Python strategy/workspace tests use synthetic records and temporary databases. The custom-axis v088/v089/v090 and design tests run explicitly; they are not implicitly covered by the strategy's default test directory. Source templates and the S001 baseline source are included. The US exchange-calendar reference is a reduced public LEAN market-hours entry, not a provider price dataset.

The private historical-order regressions were replaced in the public checkout with explicit synthetic native-order/terminal-response shapes. They retain the failure checks for incomplete fills, absent fees, invalid prices, identity mismatches and incomplete remote state. Passing them does not claim that the omitted private history has been replayed. That historical evidence stays in the operational workspace.

Rust is pinned to 1.95.0. CI uses the committed Cargo.lock, formatting checks, Clippy with warnings denied, unit tests and a release build. The audit tool is pinned to cargo-audit 0.22.2 and installed with its lockfile; the project lockfile is audited without suppressing advisories. Registry/build-dependency access is required. No workflow acquires market data or uses account credentials.

Local Python command:

```bash
python -m pytest tests strategies/s001/tests strategies/s002/tests strategies/sml01/tests strategies/sstrangle/tests strategies/sstrangle/poc/v088 strategies/sstrangle/poc/v089 strategies/sstrangle/poc/v090 strategies/sstrangle/research/design_20261030_v090
```

Run Rust checks with `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets --all-features --locked -- -D warnings`, `cargo test --workspace --all-targets --locked`, and `cargo build --workspace --release --locked`. For a local host where automatic DuckDB download is unavailable, set `DUCKDB_LIB_DIR` and `LD_LIBRARY_PATH` to an already installed, matching DuckDB 1.5.6 library. This does not change the pinned dependency version. A binary-dependent workspace smoke test skips explicitly when the native executable has not been built in that job.

QC cloud parity, provider data permissions, actual account funding and live execution are separate integrations. Local/Actions success cannot certify them. C0 margin intervention, historical IV root cause, strict provider readiness and full feature-sidecar parity remain open in 0.9.0.

No deployment target or CD workflow is configured. The CI release binary is a build artifact, not a deployment. No service, account or brokerage action is taken by these checks.
