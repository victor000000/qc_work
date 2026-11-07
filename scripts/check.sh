#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo build --workspace --locked
duckdb_lib=$(find target -name libduckdb.so -print -quit)
if [[ -n "$duckdb_lib" ]]; then
    export LD_LIBRARY_PATH="$(dirname "$PWD/$duckdb_lib")${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
python_bin="${QC_PYTHON:-$PWD/.venv/bin/python}"
"$python_bin" -m pytest tests
(cd strategies/s001 && "$python_bin" -m pytest)
(cd strategies/s002 && "$python_bin" -m pytest)
(cd strategies/sml01 && "$python_bin" -m pytest)
"$python_bin" -m pytest strategies/sstrangle/tests
"$python_bin" -m pytest strategies/sstrangle/poc/v088 strategies/sstrangle/poc/v089 strategies/sstrangle/poc/v090 strategies/sstrangle/poc/v091 strategies/sstrangle/poc/v092 strategies/sstrangle/research/design_20261030_v090
