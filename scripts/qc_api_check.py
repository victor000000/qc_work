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


def credentials(db=None):
    """Read environment/private JSON only; db is a compatibility path hint."""
    path = Path(os.environ.get('QC_CREDENTIALS_FILE', ROOT / '.local/credentials.json'))
    values = {}
    if not (os.getenv('QC_USER_ID') and os.getenv('QC_API_TOKEN')) and path.exists():
        if path.stat().st_mode & 0o077:
            raise RuntimeError('QC credential file must have mode 0600')
        try:
            values = json.loads(path.read_text())
        except (ValueError, OSError):
            raise RuntimeError('Cannot read QC credential file') from None
    user = os.getenv('QC_USER_ID', values.get('qc_user_id', ''))
    token = os.getenv('QC_API_TOKEN', values.get('qc_api_token', ''))
    if not user.strip() or not token.strip():
        raise RuntimeError('Set QC_USER_ID/QC_API_TOKEN or QC_CREDENTIALS_FILE; database credentials are unsupported')
    return user, token


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
