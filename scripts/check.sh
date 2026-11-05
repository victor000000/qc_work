#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
cargo test --workspace --all-targets --locked
python_bin="${QC_PYTHON:-$PWD/.venv/bin/python}"
"$python_bin" -m pytest tests
(cd strategies/s001 && "$python_bin" -m pytest)
(cd strategies/s002 && "$python_bin" -m pytest)
(cd strategies/sml01 && "$python_bin" -m pytest)
"$python_bin" -m pytest strategies/sstrangle/tests
