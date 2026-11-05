"""Run verified 1m bundles through the axis and frozen-decision sidecar.

python -m strategies.sstrangle.poc.v088.pipeline --bundle manifest.json --out NEW_DIR
Bundle paths are manifest-relative, SHA256 pinned. No API requests or cloud creates.
"""
import argparse
import hashlib
import json
from pathlib import Path
from .axis import Axis, utc, stamp
from .shadow import attach_shadow, align_options
from .audit_axis import audit


def normalize(value):
    from datetime import datetime, date
    if isinstance(value, datetime):
        return stamp(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    return value


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_bundle(path):
    path = Path(path)
    manifest = json.loads(path.read_text())
    if manifest.get('version') != '0.8.8' or manifest.get('status') != 'verified':
        raise ValueError('verified 0.8.8 consumer bundle required')
    if manifest.get('frequency_seconds') != 60 or manifest.get('upsampled', True):
        raise ValueError('genuine one-minute delivery required')
    if not manifest.get('release') or not manifest.get('verification_receipt'):
        raise ValueError('release and verification receipt required')
    data = {}
    for key in ('minutes', 'calendar', 'decisions', 'options'):
        item = manifest['files'][key]
        f = (path.parent/item['path']).resolve()
        if file_hash(f) != item['sha256']:
            raise ValueError('delivery hash mismatch: '+key)
        if f.suffix == '.parquet':
            if key == 'options':
                data[key] = f  # Query bounded decision windows instead of loading the full chain history.
            else:
                import pyarrow.parquet as pq
                data[key] = normalize(pq.read_table(f).to_pylist())
        else:
            data[key] = json.loads(f.read_text())
    # The verification receipt itself must also be pinned.
    item = manifest['verification_receipt']
    receipt = path.parent/item['path']
    if hashlib.sha256(receipt.read_bytes()).hexdigest() != item['sha256']:
        raise ValueError('verification receipt hash mismatch')
    return manifest, data


def run(bundle, out, recipe='spx_variation', mode='strict'):
    manifest, data = read_bundle(bundle)
    out = Path(out)
    if out.exists():
        raise ValueError('new output identity required')
    axis = Axis(recipe, mode, manifest['release'])
    summaries, thresholds = [], []
    calendar = data['calendar']
    if [x['session'] for x in calendar] != sorted({x['session'] for x in calendar}):
        raise ValueError('duplicate or unordered calendar')
    grouped = {}
    symbol = 'SPY' if recipe.startswith('spy_') else 'SPX'
    for row in data['minutes']:
        if row['symbol'] == symbol:
            grouped.setdefault(row['session'], []).append(row)
    if set(grouped)-{x['session'] for x in calendar}:
        raise ValueError('unmapped session')
    for session in calendar:
        threshold = axis.begin(session['session'], session['open'], session['close'])
        thresholds.append(dict(session=session['session'], threshold=threshold,
                               source_end=axis.session['threshold_source_end']))
        # Arrival ordering is explicit. Engine refuses late event revisions instead of rewriting history.
        rows = sorted(grouped.get(session['session'], []),
                      key=lambda r: (utc(r.get('available_at') or r['end']), utc(r['end']), r['source_row_id']))
        for row in rows:
            axis.update(row)
        summaries.append(axis.finish())
    decisions = data['decisions']
    sidecar = attach_shadow(decisions, axis.bars)
    aligned = []
    connection = None
    if isinstance(data['options'], Path):
        import duckdb
        connection = duckdb.connect()
        connection.execute('SET threads=2')
        connection.execute("SET TimeZone='UTC'")
    for d in decisions:
        option_rows = data['options']
        if connection is not None:
            from datetime import timedelta
            deadline = utc(d['decision_at'])
            option_rows = normalize(connection.execute(
                'SELECT * FROM read_parquet(?) WHERE observed_at >= ? AND observed_at < ?',
                [str(data['options']), deadline-timedelta(seconds=120), deadline]).to_arrow_table().to_pylist())
        candidates, excluded = align_options(option_rows, d['decision_at'], mode)
        aligned.append(dict(decision_at=d['decision_at'], candidates=candidates, exclusions=excluded))
    if connection is not None:
        connection.close()
    assert [x['decision'] for x in sidecar] == decisions
    completed = [b for b in axis.bars if b['is_complete']]
    report = dict(version='0.8.8', release=manifest['release'], recipe=recipe, mode=mode,
                  input_kind=manifest.get('input_kind', 'provider'), completed_bars=len(completed),
                  complete_sessions=sum(s['complete'] for s in summaries), sessions=len(summaries),
                  shadow_decisions=len(sidecar), original_decisions_unchanged=True,
                  ready_features=sum(s['axis']['status']=='ready' for s in sidecar),
                  aligned_candidates=sum(len(x['candidates']) for x in aligned),
                  economic_acceptance=False, scope='Axis/feature shadow only; no changed orders or model training')
    out.mkdir(parents=True)
    outputs = dict(axis_bars=axis.bars, axis_thresholds=thresholds, session_audit=summaries,
                   axis_state=axis.checkpoint(), decision_shadow=sidecar, aligned_options=aligned,
                   axis_quality=report, axis_diagnostics=audit(axis.bars), input_manifest=manifest)
    for name, value in outputs.items():
        (out/(name+'.json')).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bundle', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--recipe', choices=['spx_variation','spy_dollar','spy_close_volume','time_control'], default='spx_variation')
    p.add_argument('--mode', choices=['strict','sampled'], default='strict')
    a = p.parse_args()
    print(json.dumps(run(a.bundle, a.out, a.recipe, a.mode), indent=2))

if __name__ == '__main__':
    main()
