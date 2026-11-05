#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
rustup show active-toolchain
uv venv --python 3.12 --allow-existing .venv
uv pip install --index-url https://pypi.org/simple --python .venv/bin/python -r requirements-dev.lock
uv pip install --index-url https://pypi.org/simple --python .venv/bin/python --no-deps -e . -e strategies/s001 -e strategies/s002 -e strategies/sml01
cargo build --release --locked
