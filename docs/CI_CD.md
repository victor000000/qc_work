# Development, testing and CI

The supported offline suites exercise local/mocked behavior. They do not acquire provider data, trade, start production queues or certify native QC account parity. Installing dependencies needs registry/release access; test bodies use synthetic data and temporary databases.

## Reproduce from a clean source checkout

```bash
bash scripts/setup.sh
bash scripts/check.sh
```

Setup uses Rust 1.95.0, Python 3.12, `requirements-dev.lock`, and editable installs for workspace storage and S001/S002/SML01. The local check script runs formatting, native DuckDB bootstrap, strict all-feature/all-target Clippy, all-target Rust tests, debug binary build, workspace tests, isolated strategy tests and explicit custom-axis/design tests. `QC_PYTHON` can select an existing compatible Python interpreter; otherwise `.venv/bin/python` is used.

Strategy suites run in their own directories to preserve their import/configuration boundaries. Do not replace this with one combined pytest collection across all strategy roots: same-named modules and strategy-specific configuration can collide. The custom-axis command is separate:

```bash
.venv/bin/python -m pytest strategies/sstrangle/poc/v088 \
  strategies/sstrangle/poc/v089 strategies/sstrangle/poc/v090 \
  strategies/sstrangle/poc/v091 strategies/sstrangle/poc/v092 \
  strategies/sstrangle/research/design_20261030_v090
```

Older adversarial suites intentionally demonstrate old-version defects and are not part of current green acceptance. Public synthetic fixtures stand in for omitted private historical order data; they do not reproduce that market history.

## Native dependency cache correctness

DuckDB Python is 1.5.6; Rust `duckdb`/`libduckdb-sys` is 1.10506.1. `.cargo/config.toml` enables the dependency's version-specific native download. A restored Cargo fingerprint can outlive its downloaded library. `bash scripts/bootstrap_duckdb.sh` clears only that package's build artifacts and builds it with `--locked`, forcing native setup/copy to run. An existing matching release archive can be reused. `--offline` prevents Cargo registry access, but upstream native setup may still need HTTP if its archive is absent.

Both native CI jobs invoke bootstrap immediately after cache restore. Workspace-tools builds the debug executable and sets the matching runtime library directory before Python tests, so the native-writer regression does not skip simply because no binary was built. For an already installed library, `DUCKDB_LIB_DIR` and the host loader path must point to matching DuckDB 1.5.6. Do not substitute a newer system library to silence linking errors.

## Hosted workflow

`.github/workflows/ci.yml` triggers on push, pull request and explicit dispatch with contents-read permission:

| Job | Checks |
|---|---|
| Rust | Pinned toolchain, cache/bootstrap, fmt, strict Clippy, all-target tests, locked release build |
| Strategy matrix | Locked Python install; isolated S001/S002/SML01/SSTRANGLE suites; v088–v092/design checks in SSTRANGLE |
| Workspace-tools | Locked Python install, native bootstrap/build and storage/tool regressions |
| Audit | cargo-audit 0.22.2 installed locked; audit committed dependency lock without advisory suppression |

No CD target exists. Build artifacts do not deploy a service. The native-cache fix's [seven-job hosted run](https://github.com/victor000000/qc_work/actions/runs/42367520420) passed at exact SHA `8c29672d76968b1bd18c31fb3bc3dc33d75d3c2e`. Those are dated results, not a guarantee for a later documentation commit. Prior local suites recorded 749 Python and 75 Rust passes; two private-credential/cloud Rust tests were intentionally ignored.

## Documentation checks

```bash
.venv/bin/python scripts/check_docs.py
```

The checker validates canonical public local links/anchors and records structural inventory/link findings for all owned Markdown. It does not fetch external URLs, validate private evidence or execute operational examples. CI runs it in workspace-tools; documentation-only changes need that check and safe CLI help verification, not live account exercises.
