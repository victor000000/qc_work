"""Portable S001 paths; shared runtime is separate from this strategy."""
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = ROOT.parents[1]
DATA_DIR = Path(os.environ.get("QC_DATA_DIR", WORKSPACE_ROOT / "data"))
DB_PATH = DATA_DIR / "S001.duckdb"
RESEARCH_DIR = ROOT / "research"
