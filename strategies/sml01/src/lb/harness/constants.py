import os
from datetime import datetime

from lb.paths import (
    TEMPLATES_DIR, MODULES_DIR, QC_SCRIPTS_DIR, QC_CREDS_PATH,
    KNOWLEDGE_JSON, HYPOTHESES_JSON,
    RESULTS_DIR, ROUND_RESULTS_CSV, STATUS_JSON, SML01_DB,
)

# === ETF Universe ===
CORE_7_ETFS = ["QQQ", "IWM", "EEM", "XLE", "HYG", "TLT", "GLD"]

# === Time Splits ===
TRAIN_END = datetime(2021, 8, 1)
VAL_END = datetime(2023, 8, 1)
TEST_END = datetime(2026, 7, 1)    # advanced 2026-06-12 (user: OOS real-trading backtest end -> 2026-07-01)

# === QC Cloud ===
# 32883446 = autoresearch-2026-06 (created 2026-06-14 per user; fresh node availability for the
# spread/trend-gate work). Prior project 31338454 holds the campaign's ObjectStore cells; the QC
# cloud ObjectStore is org-scoped so saved cells remain reachable from the new project.
# NOTE: QC_PROJECT_ID is only used by the LEGACY direct-QC helpers (_qc_post, champion replay,
# objectstore ops). The round loop now routes backtests through the qc-backtest-server queue
# (see SML01_DB below), which runs them on the SHARED project pool (data/projects.json). The
# QC ObjectStore is org-scoped (same account, user 286064) so train->infer cells written on any
# shared project are read from any other — no dependence on this single project id.
QC_PROJECT_ID = 32883446
QC_POLL_INTERVAL = 30  # seconds between status checks
TIME_BUDGET = 300       # legacy: 5 min QC execution cap (used by direct-QC submit_and_wait)

# === qc-backtest-server queue transport ===
# SML01 enqueues specs into this shared strategy DB; the Rust server (the same engine
# s001/s002 use) runs them and writes results back into result_json. The driver polls
# the DB for completion. See lb.harness.qc_client.
SML01_DB_PATH = str(SML01_DB)
# Within-strategy queue ordering (lower = higher priority). 5 = neutral, matching
# s001/s002 manual probes. Override with SML01_QUEUE_PRIORITY.
SML01_QUEUE_PRIORITY = int(os.environ.get("SML01_QUEUE_PRIORITY", "5"))
# Max wall-clock the driver waits for one queued job to finish (queue wait under
# contention with s001/s002 + the ~5min QC run). Generous: the server, not this
# timeout, enforces real execution caps; this is just a backstop. Override with
# SML01_JOB_TIMEOUT.
SML01_JOB_TIMEOUT = int(os.environ.get("SML01_JOB_TIMEOUT", "2400"))

# === Gate Thresholds ===
GATE_CALMAR_MIN = 3.0       # OOS Calmar must exceed this
GATE_TRADES_MIN = 80        # OOS trade count must exceed this
GATE_AUC_DIVERGENCE_MAX = 0.05  # |train_AUC - val_AUC| must be below this

# === Rendering ===
# TEMPLATES_DIR / MODULES_DIR / QC_SCRIPTS_DIR / QC_CREDS_PATH now come from
# lb.paths (single source of truth); imported above as pathlib.Path objects.
# lean_workspace is archived on this machine; use the standalone scripts dir instead.

# === Asset Fingerprinting (for ETF selection) ===
ASSET_AFFINITY = {
    "trend_following": ["QQQ", "IWM", "XLE", "GLD"],
    "mean_reversion": ["HYG", "TLT", "EEM"],
    "volatility_regime": ["GLD", "XLE", "EEM"],
}

# Target bars per 17-year history (2009-2026) at minute granularity
TARGET_BARS = 15000
