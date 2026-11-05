"""Run verified 1m bundles through the axis and frozen-decision sidecar.

python -m strategies.sstrangle.poc.v090.pipeline --bundle manifest.json --out NEW_DIR
Bundle paths are manifest-relative, SHA256 pinned. No API requests or cloud creates.
"""
import argparse
import hashlib
import json
from pathlib import Path
from .axis import Axis, utc, stamp, digest
from .shadow import attach_shadow, align_options
from .audit_axis import audit
from .contracts import validate_calendar, validate_receipt, validate_strict_provider
from zoneinfo import ZoneInfo


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
    if manifest.get('version') not in ('0.8.9','0.9.0') or manifest.get('status') != 'verified':
        raise ValueError('verified 0.8.9/0.9.0 consumer bundle required')
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
            if key in ('options','minutes'):
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
    attestation = json.loads(receipt.read_text())
    validate_receipt(manifest, attestation)
    data['receipt'] = attestation
    return manifest, data


def run(bundle, out, recipe='spx_variation', mode='strict', control_symbol='SPX'):
    """Replay per session and decision; JSONL sidecars have a final completion manifest.

    Provider large tables must be Parquet. Fixture JSON is intentionally small/in-memory.
    Historical decisions are evaluated at their deadline, not after final state is known.
    """
    from contextlib import ExitStack
    from datetime import timedelta
    import duckdb
    manifest,data=read_bundle(bundle)
    validate_strict_provider(manifest,data['receipt'],mode)
    calendar=data['calendar'];by_day=validate_calendar(calendar)
    if manifest.get('input_kind')!='synthetic_fixture' and any(not isinstance(data[k],Path) for k in ('minutes','options')):
        raise ValueError('provider minute/option tables must be bounded Parquet inputs')
    decisions={day:[] for day in by_day}
    for i,d in enumerate(data['decisions']):
        deadline=utc(d['decision_at']);day=deadline.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        c=by_day.get(day)
        if c is None or not utc(c['open'])<=deadline<=utc(c['close']):raise ValueError('decision outside calendar')
        decisions[day].append((i,d))
    out=Path(out)
    if out.exists():raise ValueError('new output identity required')
    axis=Axis(recipe,mode,manifest['release'],retention=128,calendar_hash=digest(calendar),control_symbol=control_symbol)
    symbol=control_symbol if recipe=='time_control' else 'SPY' if recipe.startswith('spy_') else 'SPX'
    connection=duckdb.connect();connection.execute('SET threads=2');connection.execute("SET TimeZone='UTC'")
    # Reject undeclared sessions, even if they would otherwise be skipped by session queries.
    if isinstance(data['minutes'],Path):
        days={str(x[0]) for x in connection.execute('SELECT DISTINCT session FROM read_parquet(?) WHERE symbol=?',[str(data['minutes']),symbol]).fetchall()}
    else:days={r['session'] for r in data['minutes'] if r['symbol']==symbol}
    if days-set(by_day):
        connection.close();raise ValueError('unmapped session')
    report=dict(version='0.9.0',release=manifest['release'],recipe=recipe,mode=mode,
        underlying=symbol,calendar_hash=digest(calendar),input_files={k:v['sha256'] for k,v in manifest['files'].items()},
        input_kind=manifest.get('input_kind','provider'),completed_bars=0,complete_sessions=0,sessions=len(calendar),
        shadow_decisions=0,original_decisions_unchanged=True,ready_features=0,aligned_candidates=0,
        economic_acceptance=False,scope='Axis/feature shadow only; no changed orders or model training')
    out.mkdir(parents=True)
    try:
        with ExitStack() as stack:
            streams={k:stack.enter_context((out/(k+'.jsonl')).open('w')) for k in
                ('axis_bars','axis_thresholds','session_audit','quality_events','decision_shadow','aligned_options','axis_diagnostics')}
            def emit(name,row):streams[name].write(json.dumps(row,allow_nan=False)+'\n')
            for session in calendar:
                day=session['session'];session_bars=[]
                threshold=axis.begin(day,session['open'],session['close'])
                emit('axis_thresholds',dict(session=day,threshold=threshold,source_end=axis.session['threshold_source_end']))
                if isinstance(data['minutes'],Path):
                    rows=normalize(connection.execute('SELECT * FROM read_parquet(?) WHERE session=? AND symbol=?',
                        [str(data['minutes']),day,symbol]).to_arrow_table().to_pylist())
                else:rows=[r for r in data['minutes'] if r['session']==day and r['symbol']==symbol]
                rows.sort(key=lambda r:(utc(r.get('available_at') or r['end']),utc(r['end']),r['source_row_id']))
                cursor=0
                def collect(before_seq,before_segment):
                    new=[b for b in axis.bars if b['session']==day and b['sequence']>before_seq]
                    for b in new:
                        emit('axis_bars',b);session_bars.append(b);report['completed_bars']+=int(b['is_complete'])
                    for event in axis.events:
                        if event['session']==day and event['segment_id']>before_segment:emit('quality_events',event)
                def consume(row):
                    seq,seg=axis.session['sequence'],axis.session['segment']
                    axis.update(row);collect(seq,seg)
                for index,d in sorted(decisions[day],key=lambda pair:(utc(pair[1]['decision_at']),pair[0])):
                    deadline=utc(d['decision_at'])
                    while cursor<len(rows) and utc(rows[cursor].get('available_at') or rows[cursor]['end'])<deadline:
                        consume(rows[cursor]);cursor+=1
                    feature=attach_shadow([d],axis)[0];feature['decision_index']=index
                    emit('decision_shadow',feature)
                    report['shadow_decisions']+=1;report['ready_features']+=int(feature['axis']['status']=='ready')
                    option_rows=data['options']
                    if isinstance(option_rows,Path):
                        option_rows=normalize(connection.execute('SELECT * FROM read_parquet(?) WHERE observed_at >= ? AND observed_at < ?',
                            [str(option_rows),deadline-timedelta(seconds=120),deadline]).to_arrow_table().to_pylist())
                    candidates,excluded=align_options(option_rows,deadline,mode)
                    emit('aligned_options',dict(decision_index=index,decision_at=d['decision_at'],candidates=candidates,exclusions=excluded))
                    report['aligned_candidates']+=len(candidates)
                for row in rows[cursor:]:consume(row)
                seq,seg=axis.session['sequence'],axis.session['segment']
                summary=axis.finish();collect(seq,seg)
                emit('session_audit',summary);emit('axis_diagnostics',dict(session=day,diagnostics=audit(session_bars)))
                report['complete_sessions']+=int(summary['complete'])
            for name,value in dict(axis_state=axis.checkpoint(),axis_quality=report,input_manifest=manifest).items():
                (out/(name+'.json')).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
        completion=dict(version='0.9.0',complete=True,files={p.name:file_hash(p) for p in sorted(out.iterdir()) if p.is_file()})
        (out/'COMPLETE.json').write_text(json.dumps(completion,indent=2)+'\n')
    finally:connection.close()
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bundle', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--recipe', choices=['spx_variation','spy_dollar','spy_close_volume','time_control'], default='spx_variation')
    p.add_argument('--mode', choices=['strict','sampled'], default='strict')
    p.add_argument('--control-symbol',choices=['SPX','SPY'],default='SPX')
    a = p.parse_args()
    print(json.dumps(run(a.bundle, a.out, a.recipe, a.mode, a.control_symbol), indent=2))

if __name__ == '__main__':
    main()
