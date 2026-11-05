"""Pin a canonical snapshot into a sampled SPY close-volume diagnostic bundle.

Uses actual published 1m SPY bars and one decision day's native1m options.
Never promotes missing historical clocks or unaccepted Greeks to strict readiness.
No requests, acquisitions, provider writes, or trading.
"""
import argparse,json
from pathlib import Path
from datetime import timedelta
import duckdb
import exchange_calendars as xcals
import pyarrow as pa
import pyarrow.parquet as pq
from .axis import stamp
from .pipeline import file_hash


def prepare(snapshot,out,start,end,stage_proof):
    snapshot,out,stage_proof=Path(snapshot),Path(out),Path(stage_proof)
    if out.exists():raise ValueError('fresh bundle identity required')
    m=json.loads(snapshot.read_text());root=snapshot.parents[2]
    stage=json.loads(stage_proof.read_text())
    if stage.get('native_resolution_seconds')!=60 or stage.get('raw_to_normalized_numeric_and_key_mismatches')!=0:
        raise ValueError('stage verification missing')
    tables=m['stores']['history']['tables'];pins={};paths={}
    for name in ('underlying_minutes','option_nbbo','option_intraday_greeks'):
        parts=[p for p in tables[name]['partitions'] if (start[:4]<=str(p['year'])<=end[:4] if name=='underlying_minutes' else '/'+end+'/' in p['path'])]
        if not parts:raise ValueError('requested canonical partitions unavailable')
        paths[name]=[]
        for part in parts:
            path=root/part['path']
            if file_hash(path)!=part['sha256']:raise ValueError('canonical hash mismatch')
            paths[name].append(str(path));pins[str(path)]=part['sha256']
    c=duckdb.connect();c.execute("SET TimeZone='UTC'");c.execute('SET threads=2')
    # Full row comparison ties the new canonical option identity to independently
    # checked native-minute staging evidence. No stage publication flag is inferred.
    for name in ('option_nbbo','option_intraday_greeks'):
        original=stage['artifacts'][name]
        if file_hash(original['path'])!=original['sha256']:raise ValueError('stage hash mismatch')
        pins[original['path']]=original['sha256']
        for left,right in ((paths[name],[original['path']]),([original['path']],paths[name])):
            n=c.execute("SELECT count(*) FROM ((SELECT * FROM read_parquet(?) WHERE source='thetadata_v3_1m') EXCEPT ALL (SELECT * FROM read_parquet(?) WHERE source='thetadata_v3_1m'))",[left,right]).fetchone()[0]
            if n:raise ValueError('canonical/stage row mismatch')
    cal=xcals.get_calendar('XNYS');sessions=cal.sessions_in_range(start,end)
    calendar=[dict(session=str(s.date()),open=stamp(cal.session_open(s)),close=stamp(cal.session_close(s))) for s in sessions]
    if not calendar:raise ValueError('empty calendar interval')
    raw=c.execute("SELECT * FROM read_parquet(?) WHERE symbol='SPY' AND source='alpaca_sip_raw_1m' AND ts_utc>=? AND ts_utc<=? ORDER BY ts_utc",[paths['underlying_minutes'],start,end+' 23:59:59']).to_arrow_table().to_pylist()
    from zoneinfo import ZoneInfo
    from datetime import timezone,datetime
    by_day={r['session']:r for r in calendar};minutes=[]
    for r in raw:
        t=r['ts_utc'].replace(tzinfo=timezone.utc);day=t.astimezone(ZoneInfo('America/New_York')).date().isoformat();calrow=by_day.get(day)
        if not calrow or not datetime.fromisoformat(calrow['open'])<=t<datetime.fromisoformat(calrow['close']):continue
        minutes.append(dict(session=day,symbol='SPY',start=stamp(t),end=stamp(t+timedelta(minutes=1)),available_at=None,
            frequency_seconds=60,open=r['open'],high=r['high'],low=r['low'],close=r['close'],volume=r['volume'],
            source_row_id='alpaca_sip_raw_1m:SPY:'+stamp(t),is_fill_forward=False))
    joined=c.execute("""SELECT q.contract_id,q.interval_ts,q.quote_ts,q.available_at,q.bid,q.ask,
        g.available_at greek_available_at,g.underlying_ts,g.underlying_price,g.delta
        FROM read_parquet(?) q JOIN read_parquet(?) g USING(source,contract_id,interval_ts)
        WHERE q.source='thetadata_v3_1m' AND g.frequency_seconds=60""",[paths['option_nbbo'],paths['option_intraday_greeks']]).to_arrow_table().to_pylist()
    options=[]
    for r in joined:
        _,_,root_symbol,expiry,right,strike=r['contract_id'].split(':')
        options.append(dict(contract_id=r['contract_id'],root=root_symbol,expiry=expiry,right=right,strike=float(strike),
            listed_asof=True,listing_evidence='dated_quoted_inventory_only',source_row_id='thetadata_v3_1m:'+r['contract_id']+'@'+stamp(r['interval_ts']),
            observed_at=r['interval_ts'],quote_ts=r['quote_ts'],available_at=r['available_at'],
            greek_asof=r['interval_ts'],greek_input_at=r['underlying_ts'],greek_available_at=r['greek_available_at'],
            greek_model_accepted=False,frequency_seconds=60,greek_frequency_seconds=60,
            bid=r['bid'],ask=r['ask'],delta=r['delta'],spot=r['underlying_price']))
    c.close()
    out.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(minutes),out/'minutes.parquet')
    pq.write_table(pa.Table.from_pylist(options),out/'options.parquet')
    (out/'calendar.json').write_text(json.dumps(calendar))
    decision_day=by_day[end]
    # Frozen diagnostic times, independent of market outcomes and axis thresholds.
    opened=datetime.fromisoformat(decision_day['open'])
    decisions=[dict(decision_at=stamp(opened+timedelta(minutes=n)),strategy='axis_diagnostic_no_orders') for n in (5,30,60,90,120,150,180,210,240,270,300,330,360) if opened+timedelta(minutes=n)<datetime.fromisoformat(decision_day['close'])]
    (out/'decisions.json').write_text(json.dumps(decisions))
    files={k:dict(path=p,sha256=file_hash(out/p)) for k,p in dict(minutes='minutes.parquet',options='options.parquet',calendar='calendar.json',decisions='decisions.json').items()}
    release=m['release']+':v089-spy-sampled:'+start+':'+end
    receipt=dict(status='verified',release=release,synthetic=False,frequency_seconds=60,
        artifacts={k:v['sha256'] for k,v in files.items()},canonical_publication=True,strict_replay_ready=False,
        calendar_verified=True,calendar_source='exchange_calendars XNYS '+xcals.__version__,
        coverage=dict(underlying_rows=len(minutes),calendar_sessions=len(calendar),option_decision_day=end,option_rows=len(options)),
        snapshot_path=str(snapshot),snapshot_sha256=file_hash(snapshot),stage_proof_sha256=file_hash(stage_proof),source_pins=pins,
        limitations=['Sampled availability; no historical latency proof','SPY close-times-volume approximation, not actual traded notional',
            'Underlying raw bar label interpreted as UTC minute start; no provider availability/fill-forward field',
            'Option dated inventory only; fixed-DTE Greeks unaccepted; no SPX axis','Canonical/stage options exact row parity verified'])
    (out/'verification.json').write_text(json.dumps(receipt,indent=2))
    manifest=dict(version='0.8.9',status='verified',input_kind='provider',data_state='published',release=release,
        frequency_seconds=60,upsampled=False,files=files,verification_receipt=dict(path='verification.json',sha256=file_hash(out/'verification.json')))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2));return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshot',required=True);p.add_argument('--out',required=True)
    p.add_argument('--start',required=True);p.add_argument('--end',required=True);p.add_argument('--stage-proof',required=True)
    a=p.parse_args();print(json.dumps(prepare(a.snapshot,a.out,a.start,a.end,a.stage_proof),indent=2))
