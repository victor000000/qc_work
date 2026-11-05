"""SML01 backtest transport.

The round loop routes backtests through wang's qc-backtest-server queue (the same
Rust engine s001/s002 use) instead of talking to QuantConnect directly. submit ->
INSERT a spec into data/SML01.duckdb (backtest_queue); the server runs it on the shared
QC project pool and writes {status, statistics, runtimeStatistics} back into the
row's result_json; the driver POLLS the DB until the row is terminal.

The 5 functions keep their original signatures so run_round.py is unchanged:
  submit_backtest(code, name, extra_files=None) -> bid  (the queue row id, as str)
  read_backtest_status(bid)                     -> (qc_status_str, runtimeStatistics, logs)
  read_backtest(bid)                            -> {status, statistics, runtimeStatistics}
  delete_backtest(bid)                          -> bool
  is_done(status)                               -> bool

The train->infer dependency needs NO server support: the QC ObjectStore is
org-scoped (same account, user 286064, as s001/s002), so a train cell written by a
backtest on ANY shared project is read by the infer backtest on ANY other — and
run_round already submits infer only AFTER train reaches a terminal state.

The legacy direct-to-QC helpers (_get_creds, _qc_post) are retained below for
champion replay / ObjectStore ops that still hit the QC REST API directly.
"""

import json, subprocess, time, base64, hashlib, os, qc_storage as storage, itertools
from pathlib import Path

def _get_creds():
    """Load QC credentials from QC_CREDS_PATH."""
    from .constants import QC_CREDS_PATH
    with open(QC_CREDS_PATH) as f:
        return json.load(f)

def _qc_post(path, body=None, max_time=120):
    """POST to QC API v2. Returns parsed JSON or {} on failure.
    FORM-ENCODED (2026-06-10): the API stopped parsing JSON bodies mid-session —
    every endpoint returned "Required parameter X is missing" for valid JSON, while
    the identical call form-encoded succeeded. Lists use the key[]= convention.
    Tries Python requests first, falls back to curl."""
    c = _get_creds()
    ts = str(int(time.time()))
    digest = hashlib.sha256(f"{c['token']}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{c['user_id']}:{digest}".encode()).decode()
    url = f"https://www.quantconnect.com/api/v2{path}"
    form = []
    for k, v in (body or {}).items():
        if isinstance(v, (list, tuple)):
            for item in v:
                form.append((f"{k}[]", str(item)))
        elif isinstance(v, bool):
            form.append((k, "true" if v else "false"))
        else:
            form.append((k, str(v)))

    # Try Python requests first, fall back to curl on ANY error (SSL, network, etc.)
    try:
        import requests
        r = requests.post(url,
            headers={"Authorization": f"Basic {auth}", "Timestamp": ts},
            data=form, timeout=max_time)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass  # Fall through to curl

    # Curl fallback
    tmp = f"/tmp/qc_api_{os.getpid()}_{ts}.json"
    cmd = ["curl", "-s", "-w", "%{http_code}",
           "-X", "POST", url,
           "-H", f"Authorization: Basic {auth}",
           "-H", f"Timestamp: {ts}"]
    for k, v in form:
        cmd += ["--data-urlencode", f"{k}={v}"]
    cmd += ["--connect-timeout", "30", "--max-time", str(max_time),
            "-o", tmp]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=max_time + 10)
        try:
            with open(tmp, 'r') as f:
                return json.load(f)
        except:
            return {}
    finally:
        try: os.unlink(tmp)
        except: pass
    return {}

# ===========================================================================
# qc-backtest-server QUEUE transport (data/SML01.duckdb)
# ===========================================================================
_submit_counter = itertools.count(1)


def _connect():
    from .constants import SML01_DB_PATH
    uri = Path(SML01_DB_PATH).resolve().as_uri() + "?mode=rw"
    conn = storage.connect(uri, uri=True, timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")  # tolerate the server writing concurrently
    return conn


def _unique_name(name):
    """backtest_queue.name AND experiments.name are UNIQUE, and the server dedups by
    code_hash. SML01 deliberately re-runs near-identical code (permute control, repeated
    configs), so make every submission's row name unique — otherwise INSERTs collide or
    jobs silently vanish. run_round treats the returned bid (the row id) as opaque, so the
    human-facing label is carried in `description`."""
    suffix = f"__{int(time.time() * 1000)}_{os.getpid()}_{next(_submit_counter)}"
    return str(name)[:240 - len(suffix)] + suffix


def _parse_result(result_json):
    """-> (qc_status_str, statistics, runtimeStatistics) from the server's result_json
    (which it writes as {status, statistics, runtimeStatistics})."""
    try:
        d = json.loads(result_json)
        if not isinstance(d, dict) or not isinstance(d.get("statistics"), dict) or not d["statistics"]:
            raise ValueError("missing final statistics")
        runtime = d.get("runtimeStatistics", {})
        if not isinstance(runtime, dict):
            raise ValueError("invalid runtime statistics")
    except (TypeError, ValueError) as error:
        raise RuntimeError("Completed queue row has an invalid result_json") from error
    return (d.get("status") or "Completed.", d["statistics"], runtime)


def submit_backtest(code, name, extra_files=None):
    """Enqueue a backtest into data/SML01.duckdb; the qc-backtest-server runs it on the
    shared QC project pool. Returns the queue row id (str) as the bid handle. Raises
    RuntimeError on enqueue failure or oversized main.py.

    extra_files: optional {filename: content} of ADDITIONAL project files (bar_builder.py,
    bar_ext.py, ml_ext.py, sizing_ext.py). Carried verbatim in the queue row's extra_files
    column; the server uploads them alongside main.py before compile (QC's per-file
    64,000-char limit is sidestepped by keeping each module its own file). Rendered code is
    uploaded UNCHANGED, so the footer's _PSUF cell key stays byte-identical to the driver's."""
    if len(code) >= 64000:
        raise RuntimeError(f"main.py too large for QC (64k/file): {len(code)}")
    from .constants import SML01_QUEUE_PRIORITY
    uniq = _unique_name(name)
    extra_json = json.dumps(extra_files or {})
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO backtest_queue "
            "(name, code, extra_files, description, priority, status, submitted_by, submitted_at) "
            "VALUES (?,?,?,?,?, 'queued', 'sml01_driver', datetime('now')) RETURNING id",
            (uniq, code, extra_json, name, SML01_QUEUE_PRIORITY))
        conn.commit()
        return str(cur.fetchone()[0])
    finally:
        conn.close()


def _read_row(bid):
    conn = _connect()
    try:
        return conn.execute(
            "SELECT status, result_json, error_message, backtest_id "
            "FROM backtest_queue WHERE id=?", (int(bid),)).fetchone()
    finally:
        conn.close()


def read_backtest(bid):
    """Read the server's stored result for a queue row, as a QC-shaped dict
    {status, statistics, runtimeStatistics}. {} if the row is gone; a Running/error
    stub if not yet successfully completed."""
    row = _read_row(bid)
    if not row:
        return {}
    status, result_json, err, btid = row
    if status == "done":
        qc_status, stats, rt = _parse_result(result_json)
        return {"status": qc_status, "statistics": stats,
                "runtimeStatistics": rt, "backtestId": btid}
    if status in ("failed", "error"):
        return {"status": "RuntimeError", "statistics": {},
                "runtimeStatistics": {}, "logs": err or ""}
    if status in ("cancelled", "canceled"):
        return {"status": "Canceled", "statistics": {}, "runtimeStatistics": {}}
    return {"status": "Running", "statistics": {}, "runtimeStatistics": {}}


def read_backtest_status(bid):
    """Lightweight status check. Returns (qc_status_string, runtimeStatistics, logs).
    The status string is mapped so is_done()/`.startswith('Completed')` behave exactly as
    with the old direct-QC client: done->'Completed.', failed->'RuntimeError' (so
    is_done sees 'Error'), cancelled->'Canceled', queued/running->'Running'."""
    row = _read_row(bid)
    if not row:
        return "?", {}, ""
    status, result_json, err, _btid = row
    if status == "done":
        qc_status, _stats, rt = _parse_result(result_json)
        return qc_status, rt, ""
    if status in ("failed", "error"):
        return "RuntimeError", {}, (err or "")
    if status in ("cancelled", "canceled"):
        return "Canceled", {}, (err or "")
    return "Running", {}, ""


def delete_backtest(bid):
    """Best-effort cancel: mark a still-QUEUED row cancelled so the server skips it.
    A row already running on QC is left alone (the server owns the QC lifecycle and will
    collect it); returns False in that case."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE backtest_queue SET status='cancelled' WHERE id=? AND status='queued'",
            (int(bid),))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def is_done(status):
    """True if backtest is in a terminal state."""
    return status.startswith("Completed") or "Error" in status or status == "Canceled"


def submit_and_wait(code, name, timeout_s=None, extra_files=None):
    """Full lifecycle: enqueue -> poll the DB -> read result. Returns
    (result_dict, status_string) where status is one of 'completed', 'timeout', 'crash'.
    extra_files: optional {filename: content} of separate project modules (see submit_backtest)."""
    from .constants import SML01_JOB_TIMEOUT, QC_POLL_INTERVAL
    if timeout_s is None:
        timeout_s = SML01_JOB_TIMEOUT

    try:
        bid = submit_backtest(code, name, extra_files=extra_files)
    except Exception as e:
        return {"error": str(e)}, "crash"

    t_start = time.time()
    while True:
        elapsed = time.time() - t_start
        status, rt, logs = read_backtest_status(bid)

        if is_done(status):
            if status.startswith("Completed"):
                return read_backtest(bid), "completed"
            return {"status": status, "logs": logs, "runtime": rt}, "crash"

        if elapsed > timeout_s:
            delete_backtest(bid)
            return {"timeout_s": elapsed, "runtime": rt}, "timeout"

        time.sleep(QC_POLL_INTERVAL)
