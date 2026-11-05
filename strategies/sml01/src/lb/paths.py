"""Single source of truth for filesystem paths. Derives the repo root from this
file's location; override with LB_ROOT for unusual deployments."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("LB_ROOT", Path(__file__).resolve().parents[2])).resolve()

PKG = ROOT / "src" / "lb"
TEMPLATES_DIR = PKG / "templates"
MODULES_DIR = PKG / "modules"
QC_SCRIPTS_DIR = ROOT / "_autoresearch_scripts"
QC_CREDS_PATH = ROOT / "qc" / ".creds.json"

# qc-backtest-server shared strategy DB. data/SML01.duckdb lives in the PARENT
# qc_work repo (alongside S001.duckdb/S002.duckdb), NOT under the SML01 package — the Rust
# server discovers it there. Override with SML01_DB_PATH for tests.
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = Path(os.environ.get("QC_DATA_DIR", WORKSPACE_ROOT / "data"))
SML01_DB = Path(os.environ.get("SML01_DB_PATH", DATA_DIR / "SML01.duckdb"))

KNOWLEDGE_JSON = ROOT / "knowledge.json"
HYPOTHESES_JSON = ROOT / "hypotheses.json"
RESULTS_DIR = ROOT / "results"
ROUND_RESULTS_CSV = RESULTS_DIR / "round_results.csv"
STATUS_JSON = RESULTS_DIR / "status.json"
