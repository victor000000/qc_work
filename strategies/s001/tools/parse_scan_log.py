"""Parse the universe scanner backtest log into field_universe_stats.

Reads `PCT,fid,p10,p25,p50,p75,p90,n` log lines emitted by the scanner spec
(percentiles already computed in-process by the algorithm to keep log volume
and spec size under QC's limits). Writes one field_universe_stats row per
PCT line.

Usage:
    python -m scripts.parse_scan_log --bake-hash <md5> [--db S001.duckdb]

If --bake-hash matches a queued/done scan spec named S001_SCAN_FUNDAMENTALS_<bake_hash>,
reads its log payload from backtest_queue.result_json. Otherwise reads from stdin.
"""

from s001.paths import WORKSPACE_ROOT, DATA_DIR

import argparse
import json
import qc_storage as storage
import sys
from datetime import datetime, timezone


SAMPLE_SIZE_THRESHOLD = 50


def _scanned_at_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def parse_scan_log(db_path, log_lines, bake_hash, scanned_at=None):
    """Parse PCT log lines into field_universe_stats rows.

    log_lines: iterable of strings (one per log line).
    bake_hash: the bake hash to associate with these stats.
    scanned_at: ISO-8601 timestamp; defaults to now.

    Each PCT line has the form 'PCT,<field_id>,<p10>,<p25>,<p50>,<p75>,<p90>,<sample_size>'.
    Lines with sample_size < SAMPLE_SIZE_THRESHOLD are skipped.
    Non-PCT lines are silently ignored.
    """
    if scanned_at is None:
        scanned_at = _scanned_at_now()

    rows_to_insert = []
    for line in log_lines:
        line = line.strip()
        if not line.startswith('PCT,'):
            continue
        parts = line.split(',')
        if len(parts) != 8:
            continue
        try:
            field_id = int(parts[1])
            p10 = float(parts[2])
            p25 = float(parts[3])
            p50 = float(parts[4])
            p75 = float(parts[5])
            p90 = float(parts[6])
            sample_size = int(parts[7])
        except (ValueError, TypeError):
            continue
        if sample_size < SAMPLE_SIZE_THRESHOLD:
            continue
        rows_to_insert.append(
            (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at))

    if not rows_to_insert:
        return 0

    with storage.connect(db_path) as con:
        cur = con.cursor()
        cur.executemany(
            """INSERT OR REPLACE INTO field_universe_stats
               (field_id, bake_hash, p10, p25, p50, p75, p90, sample_size, scanned_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows_to_insert)
        con.commit()
    return len(rows_to_insert)


def _read_log_from_db(db_path, bake_hash):
    spec_name = f'S001_SCAN_FUNDAMENTALS_{bake_hash}'
    with storage.connect(db_path) as con:
        cur = con.cursor()
        row = cur.execute(
            "SELECT result_json FROM backtest_queue WHERE name = ?",
            (spec_name,)).fetchone()
    if not row or not row[0]:
        raise SystemExit(f'No completed scan spec named {spec_name}')
    payload = json.loads(row[0])
    return payload.get('logs', [])


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bake-hash', required=True)
    p.add_argument('--db', default=str(DATA_DIR / 'S001.duckdb'))
    p.add_argument('--from-stdin', action='store_true',
                   help='Read log lines from stdin instead of from backtest_queue')
    args = p.parse_args()
    if args.from_stdin:
        lines = sys.stdin.read().splitlines()
    else:
        lines = _read_log_from_db(args.db, args.bake_hash)
    n = parse_scan_log(args.db, lines, args.bake_hash)
    print(f'Persisted {n} field_universe_stats rows.')


if __name__ == '__main__':
    main()
