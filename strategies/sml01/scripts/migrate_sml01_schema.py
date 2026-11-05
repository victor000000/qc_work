#!/usr/bin/env python3
"""Idempotent schema migration for the generic multi-strategy qc-server.

Two jobs, both safe to re-run:

  1. ADD COLUMN backtest_queue.extra_files TEXT  to every existing strategy DB
     (S001.duckdb, S002.duckdb). This is a metadata-only DuckDB operation and is INVISIBLE to
     the currently-running old binary (its SELECTs name explicit columns, never
     `extra_files`), so it is safe to run while `serve` is live. Run this BEFORE
     deploying the new binary (which DOES select extra_files).

  2. Stand up data/SML01.duckdb as a first-class strategy DB the server auto-discovers
     (filename SML01.duckdb matches the S*.duckdb glob -> strategy 'sml01'). It gets the
     4 core tables (backtest_queue WITH extra_files, experiments, code_blobs,
     settings) using the generic DuckDB schema.duckdb's schema, plus organization ID copied from
     S002 (so sml01 is self-contained, not dependent on dbs[0] ordering) and a
     scheduler_weight. No cloud_project_id is set -> sml01 inherits the 8 shared
     QC projects from data/projects.json, exactly like s001/s002.

Never prints credential VALUES. data/*.duckdb is gitignored, so SML01.duckdb (which holds
creds) is never committed.
"""
import os
import qc_storage as storage
import sys
from pathlib import Path

DATA = os.environ.get("QC_DATA_DIR", str(Path(__file__).resolve().parents[3] / "data"))
S001 = os.path.join(DATA, "S001.duckdb")
S002 = os.path.join(DATA, "S002.duckdb")
SML01 = os.path.join(DATA, "SML01.duckdb")

CORE_TABLES = ["backtest_queue", "experiments", "code_blobs", "settings"]


def connect(path, read_only=False):
    location = Path(path).resolve().as_uri() + "?mode=ro" if read_only else path
    c = storage.connect(location, timeout=60, uri=read_only)
    c.execute("PRAGMA busy_timeout=60000")
    return c


def has_column(conn, table, col):
    return any(r[1] == col for r in conn.execute(f"PRAGMA table_info({table})"))


def table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def add_extra_files(path):
    """ADD COLUMN extra_files TEXT to backtest_queue if absent. Idempotent."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        print(f"  SKIP {os.path.basename(path)} (missing/empty)")
        return
    c = connect(path)
    try:
        if not table_exists(c, "backtest_queue"):
            print(f"  SKIP {os.path.basename(path)} (no backtest_queue table)")
            return
        if has_column(c, "backtest_queue", "extra_files"):
            print(f"  {os.path.basename(path)}: extra_files already present ✓")
        else:
            c.execute("ALTER TABLE backtest_queue ADD COLUMN extra_files TEXT")
            c.commit()
            print(f"  {os.path.basename(path)}: ADDED extra_files ✓")
    finally:
        c.close()


def get_setting(conn, cat, key):
    r = conn.execute(
        "SELECT value FROM settings WHERE category=? AND key=?", (cat, key)
    ).fetchone()
    return r[0] if r else None


def standup_sml01():
    """Create data/SML01.duckdb with the 4 core tables + settings, using the generic DuckDB schema."""
    src = connect(S002, read_only=True)
    creds = {
        ("project", "organization_id"): get_setting(src, "project", "organization_id"),
    }
    src.close()

    missing = [k for k, v in creds.items() if not v]
    if missing:
        print(f"  ERROR: missing organization settings in S002.duckdb: {missing}", file=sys.stderr)
        sys.exit(1)

    db = connect(SML01)
    try:
        schema = Path(__file__).resolve().parents[3] / "crates/qc-server/schema.sql"
        db.executescript(schema.read_text())
        db.commit()
        print("  SML01.duckdb: generic DuckDB schema initialized")

        # Guarantee the extra_files column on the new DB too.
        if not has_column(db, "backtest_queue", "extra_files"):
            db.execute("ALTER TABLE backtest_queue ADD COLUMN extra_files TEXT")
            db.commit()
            print("  SML01.duckdb: ADDED extra_files ✓")
        else:
            print("  SML01.duckdb: extra_files present ✓")

        # Settings: organization ID (copied) + strategy identity. INSERT OR REPLACE is
        # idempotent on the (category,key) primary key.
        rows = [
            ("project", "organization_id", creds[("project", "organization_id")]),
            ("strategy", "name", "sml01"),
            ("strategy", "db_path", "SML01.duckdb"),
            ("strategy", "type", "ml_autoresearch"),
            ("strategy", "asset_class", "etf"),
            ("strategy", "scheduler_weight", "1.0"),
            ("strategy", "optimizer_description",
             "SML01 ML autoresearch (de Prado / Wang pipeline) single-ticker ETF "
             "edge hunter; train->infer cells, OOS Calmar + honesty stack."),
        ]
        db.executemany(
            "INSERT OR REPLACE INTO settings(category,key,value) VALUES(?,?,?)", rows
        )
        db.commit()
        print(f"  SML01.duckdb: settings written ({len(rows)} rows; no credentials)")
    finally:
        db.close()


def verify():
    print("== verify ==")
    for p in (S001, S002, SML01):
        if not os.path.exists(p):
            print(f"  {os.path.basename(p)}: MISSING")
            continue
        c = connect(p)
        try:
            ef = has_column(c, "backtest_queue", "extra_files") if table_exists(c, "backtest_queue") else None
            print(f"  {os.path.basename(p)}: backtest_queue.extra_files = {ef}")
            if p == SML01:
                tabs = sorted(r[0] for r in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"))
                print(f"    tables: {tabs}")
                got = {f"{cat}/{key}" for cat, key in c.execute(
                    "SELECT category,key FROM settings")}
                need = {"project/organization_id", "strategy/name",
                        "strategy/scheduler_weight"}
                print(f"    settings present: {sorted(need & got)}")
                print(f"    settings missing: {sorted(need - got)}")
                qc = c.execute("SELECT COUNT(*) FROM backtest_queue").fetchone()[0]
                print(f"    backtest_queue rows: {qc}")
        finally:
            c.close()


if __name__ == "__main__":
    print("== step 1: ADD COLUMN extra_files to existing strategy DBs ==")
    add_extra_files(S001)
    add_extra_files(S002)
    print("== step 2: stand up SML01.duckdb ==")
    standup_sml01()
    verify()
    print("done.")
