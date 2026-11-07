# QC 0.9.1 and 0.9.2 local release review — 2026-11-07

0.9.1 bounded diagnostics and 0.9.2 verified receipts were designed, reviewed, implemented and tested in /home/vic/qc_work. The established publication checkout had a clean main branch and origin victor000000/qc_work. No concurrent writer was observed. Only this task's source, tests and designs are copied here with original SHA256 hashes. Generated probe bundles and historical/private results are excluded.

Operational regression suite: 459 passed in 37.61s. Three pre-existing v090 checkpoint tests absent in this publication checkout are outside this task's commit scope. The new modules are self-contained. Publication validation is recorded below.

Validation command:

```bash
/home/vic/qc_work/.venv/bin/python -m pytest tests strategies/sstrangle/tests strategies/sstrangle/poc/v088 strategies/sstrangle/poc/v089 strategies/sstrangle/poc/v090 strategies/sstrangle/poc/v091 strategies/sstrangle/poc/v092 strategies/sstrangle/research/design_20261030_v090 -q
```

No cloud jobs, protected requests, deployments or service restarts ran. Native group API/runtime capacity, exact cloud parity, margin ordering/cause, historical IV cause, provider/feature parity and economic acceptance remain open. Checksums do not authenticate origin. Dynamic Python mutation remains outside assembly's supported static source contract.

## Final validation and CI preparation

Publication-checkout suites passed: 457 workspace/sstrangle/axis tests, 244 s001 tests (3 existing warnings), 10 s002 tests, 38 sml01 tests: **749 Python tests passed**. Rust `cargo test --workspace --all-targets --locked --offline` passed **75 tests**; two explicitly credentialed/cloud tests stayed ignored. This is the supported offline unit/regression scope, excluding historical intentionally failing adversarial suites. Initial native integration failed to load DuckDB; providing the matching 1.5.6 runtime fixed it. No test was suppressed to obtain the pass.

`cargo fmt --all -- --check`, strict all-target/all-feature Clippy, `bash -n scripts/check.sh`, and CI YAML parsing passed. CI now includes v091/v092 regressions and builds the native writer in workspace-tools so the cross-language storage test cannot silently skip on a clean checkout. The local check script also builds the writer and discovers its runtime library. Existing CI retains locked Python installs, isolated strategy jobs, Rust build/lint/tests and dependency audit. Hosted execution is pending, not assumed successful.

## Remote publication blocker

Verified remote main before committing: `49b39c709a3d6cf423440581bf2102fcf6e312f9`. The coordinating authentication audit reports connector write requests rejected with 403 Resource not accessible by integration, no credentials from the noninteractive helper, and both existing SSH keys rejected with Permission denied(publickey). No keys, permissions or account settings were changed. Local commits are authorized and complete; push and new exact-SHA hosted CI cannot run until an existing authorized write route is restored. No remote commit or hosted pass is claimed.

## Additional maintained QC repositories

All changes stay in the established `/home/vic/github-cleanup-20261105/ci-work/` publication checkouts. Each started clean, retained its existing version sequence, received a pre-implementation design/self-review and final review in REVIEW_20261107.md, and has a focused local main-branch commit. Existing complete CI workflows were inspected and retained.

| Repository | Version | Local commit | Offline validation |
|---|---|---|---|
| qc-backtest-server | 1.1.0 → 1.1.1 | 000db537496751ed8d544b50329153a0b073675c | 2 tests, fmt, strict Clippy |
| rust-backtest | 0.1.0 → 0.1.1 | 96d266b14394b9b12c7d8c101b094511b2e7bbc2 | 4 tests, fmt, strict Clippy |
| quant-autoresearch | 0.1.0 → 0.1.1 | 2b7f90d2dffa3de24403a80848ed8693b89ea4cb | 19 tests, compileall |

The server rejects nonfinite parsed statistics; rust-backtest rejects cache path traversal before I/O; quant-autoresearch validates finite equity/annualization and fixes flat/insolvent Martin ratios. Source/lock versions and regression tests are included. Reviews disclose lexical-only containment, unchanged undefined-ratio sentinels, and lack of external/native acceptance. Push/hosted CI share the authentication blocker above. Remote main bases checked read-only were 42f930b525482d0cef45ae851fbf7dc6a7badf7d, fdb5447c91ee8895a081c3e08dc02a28ca8dea1e, and 53a2d0edb91396317d20998396fc68ba0b0c7385 respectively. Detailed test/Clippy logs remain committed in each repository's review-evidence-20261107 directory.
