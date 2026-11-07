#!/usr/bin/env bash
# Cached Cargo fingerprints may outlive the downloaded native library.
# Re-run the locked dependency's own setup; do not substitute a system DuckDB.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
cargo clean -p libduckdb-sys
cargo build -p libduckdb-sys --locked "$@"
