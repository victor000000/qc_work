# Native DuckDB cache repair — 2026-11-07

Hosted run 42366860229, Rust job 128386628635 at published SHA 64348d10c7659f82f3561bee0ccbcef64334d3d5 restored a full Swatinem cache hit. Formatting and strict Clippy passed; test linking failed with `rust-lld: error: unable to find library -lduckdb`. The cached link-search path points into target/duckdb-download/x86_64-unknown-linux-gnu/1.5.6, but native downloads are not guaranteed to survive cache pruning.

## Design and self-review before implementation

After cache restore, invalidate only libduckdb-sys package build artifacts and build that package using Cargo.lock. This forces its existing version-specific downloader/extractor and runtime-copy setup to rerun. The bootstrap script does not change package versions, bypass registry integrity checks, replace DuckDB with a system library, or touch databases/services. Use it in both native CI jobs and the local check entrypoint. Release-profile builds retain the dependency's own separate runtime-copy setup. Rebuilding this small external-library wrapper is preferable to relying on cache internals for correctness. The pre-existing upstream native archive download mechanism is retained; no new authenticity guarantee for release ZIPs is claimed.

Acceptance: simulate missing native download and debug runtime copies with warm Cargo metadata, establish the failure, run bootstrap, then full Rust tests and strict Clippy. Native storage integration must pass without private credentials. Preserve/restore the test's original native files. Python strategy source is unchanged; previously passing suites need no repetition. Hosted revalidation requires the sole publisher to apply this focused commit; no remote mutation is performed by this writer.

## Local adversarial validation

With warm fingerprints intact, temporarily moved both target/duckdb-download/x86_64-unknown-linux-gnu/1.5.6/libduckdb.so and target/debug/deps/libduckdb.so aside, and touched the package build-script timestamp to force application relinking without invalidating the dependency. `cargo test --workspace --all-targets --locked --offline --no-run` failed with exit 101 and missing -lduckdb. Original native files and timestamp were restored in a finally block after recovery validation.

`bash scripts/bootstrap_duckdb.sh --offline` regenerated the missing library from the existing pinned archive. `cargo test --workspace --all-targets --locked --offline` then passed 75 tests; two credentialed/cloud tests stayed ignored. No external LD_LIBRARY_PATH was supplied. Strict all-feature/all-target Clippy and fmt passed. `python -m pytest tests/test_duckdb_storage.py -q` passed all 3 native storage tests. Bash syntax and YAML parsing passed, including verification that bootstrap immediately follows cache restore in both native CI jobs. No trading/strategy source changed.

The earlier authentication-blocked report is historical: the sole browser publisher subsequently published the candidate under SHA 64348d10c7659f82f3561bee0ccbcef64334d3d5. That run's six non-Rust jobs passed, including all four strategy suites, workspace/native integration and dependency audit. This source writer makes no remote mutations. Apply the focused local fix through the same publisher, then require a new exact-SHA hosted run before claiming CI success.

`cargo build --workspace --release --locked --offline` passed in 22.16s; the release binary `--help` smoke passed without an external loader path. Final review retained Cargo.lock unchanged and scoped cleanup to the dependency build artifacts. The new shell script uses Git mode 100644 and explicit bash invocation.
