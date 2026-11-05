#!/usr/bin/env python3
"""Explicit, read-only QC authentication check. Never prints credentials."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import qc_storage as storage
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def credentials(db):
    user, token = os.getenv('QC_USER_ID'), os.getenv('QC_API_TOKEN')
    if user and token:
        return user, token
    with storage.connect(f'file:{db}?mode=ro', uri=True) as conn:
        values = dict(conn.execute(
            "SELECT key,value FROM settings WHERE category='credentials' "
            "AND key IN ('qc_user_id','qc_api_token')"))
    return values['qc_user_id'], values['qc_api_token']


def request(user, token, path, body=None, method=None):
    timestamp = str(int(time.time()))
    digest = hashlib.sha256(f'{token}:{timestamp}'.encode()).hexdigest()
    auth = base64.b64encode(f'{user}:{digest}'.encode()).decode()
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request('https://www.quantconnect.com/api/v2' + path,
        data=data, method=method or ('GET' if body is None else 'POST'), headers={
            'Authorization': 'Basic ' + auth, 'Timestamp': timestamp,
            'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.load(response)
    if not result.get('success'):
        raise RuntimeError(f"QC {path} rejected request: {result.get('errors', [])}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=ROOT / 'data/S001.duckdb')
    args = parser.parse_args()
    user, token = credentials(args.db.resolve())
    request(user, token, '/authenticate')
    print('QC authenticate: passed')
    projects = request(user, token, '/projects/read')
    print(f"QC projects/read: passed ({len(projects.get('projects', []))} projects)")


if __name__ == '__main__':
    main()
