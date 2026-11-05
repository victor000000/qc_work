#!/usr/bin/env python3
"""Request only the baseline's contract/day windows through the shared provider adapter.

Responses are immutable research evidence; this does not merge into live provider stores.
Incomplete responses are retained and retried on a subsequent invocation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode


def validate_cached_response(path, query):
    cached = json.loads(path.read_text())
    if cached.get('query') != query:
        raise ValueError('Cached provider request differs from requested contracts or dates')
    pages = cached.get('pages')
    if not isinstance(pages, list) or not pages or pages[-1].get('next_page_token'):
        raise ValueError('Cached provider response is incomplete')
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get('bars'), dict):
            raise ValueError('Cached provider response lacks a bars object')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder', type=Path)
    p.add_argument('--start', type=date.fromisoformat,
        help='Capture only executions on/after this date; earlier rows remain explicitly uncovered')
    args = p.parse_args()
    out = args.folder.resolve()/'provider_capture'
    out.mkdir(exist_ok=True)
    rows = list(csv.DictReader((args.folder/'qc_executions.csv').open()))
    excluded = 0
    if args.start:
        retained = [r for r in rows if date.fromisoformat(r['timestamp'][:10]) >= args.start]
        excluded = len(rows)-len(retained)
        rows = retained
    from data_providers.credentials import AlpacaHeaders
    from data_providers.providers.alpaca_http import get_json
    groups = {}
    for r in rows:
        groups.setdefault(r['timestamp'][:10], set()).add(r['symbol'])
    jobs = []
    # Entire sessions preserve sparse-trade evidence, rather than silently using
    # an arbitrary later trade as the requested 15:30 execution.
    for day, symbols in sorted(groups.items()):
        jobs.append((f'minute_{day}', dict(symbols=','.join(sorted(symbols)),
            timeframe='1Min', start=day+'T00:00:00Z', end=day+'T23:59:59Z', limit=10000)))
    all_symbols = sorted({r['symbol'] for r in rows})
    for i in range(0, len(all_symbols), 50):
        jobs.append((f'daily_{i//50}', dict(symbols=','.join(all_symbols[i:i+50]),
            timeframe='1Day', start=min(groups)+'T00:00:00Z',
            end=max(groups)+'T23:59:59Z', limit=10000)))

    def fetch(job):
        key, query = job
        path = out/(key+'.json')
        if path.exists():
            validate_cached_response(path, query)
            return key, 'cached'
        pages, token, seen_tokens = [], None, set()
        while True:
            params = dict(query)
            if token:
                params['page_token'] = token
            data = get_json('https://data.alpaca.markets/v1beta1/options/bars?'+urlencode(params),
                            AlpacaHeaders(), tries=3)
            if not isinstance(data.get('bars'), dict):
                raise ValueError('Provider response lacks a bars object')
            pages.append(data)
            token = data.get('next_page_token')
            if not token:
                break
            if token in seen_tokens:
                raise ValueError('Provider pagination repeated a page token')
            seen_tokens.add(token)
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(dict(query=query, received_utc=datetime.now(timezone.utc).isoformat(),
            source='alpaca via data_providers.providers.alpaca_http', pages=pages)))
        temp.replace(path)
        return key, sum(len(b) for page in pages for b in page.get('bars', {}).values())

    failures = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        future_jobs = {pool.submit(fetch, j): j[0] for j in jobs}
        for i, f in enumerate(as_completed(future_jobs), 1):
            try:
                key, count = f.result()
                print(f'{i}/{len(jobs)} {key}: {count}', flush=True)
            except Exception as e:
                # Keep URLs, credentials and request headers out of artifacts.
                failures.append(dict(job=future_jobs[f], error=type(e).__name__))
                print(f'{i}/{len(jobs)} {future_jobs[f]}: {type(e).__name__}', flush=True)
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob('*.json'))
             if p.name != 'manifest.json'}
    (out/'manifest.json').write_text(json.dumps(dict(files=files, failures=failures,
        requested_jobs=len(jobs), completed_jobs=len(jobs)-len(failures),
        requested_start=str(args.start) if args.start else None,
        excluded_earlier_executions=excluded), indent=2))
    if failures:
        raise RuntimeError(f'{len(failures)} provider requests failed; partial captures retained')


if __name__ == '__main__':
    main()
