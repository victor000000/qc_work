"""Read-only native corporate-warning/source-availability audit; no trading."""
import argparse,ast,fcntl,hashlib,json,re
from datetime import date,timedelta
from pathlib import Path
import report as shared

HERE=Path(__file__).resolve().parent
FROZEN=HERE.parent/'results/strangle_basket-calmar_20261019_182746'


def audit(full,orders,rust,log):
    rt=full['runtimeStatistics']
    if orders or rust or int(full['statistics']['Total Orders'])!=0:
        raise ValueError('Corporate-event source probe traded')
    if shared.money(rt['Equity'])!=60000 or any(shared.money(rt[k])!=0 for k in ['Fees','Holdings','Unrealized']):
        raise ValueError('Corporate-event source account changed')
    if rt.get('twtr_event_no_trades')!='1' or rt.get('twtr_event_performance_claim')!='0':
        raise ValueError('Missing explicit no-trade/performance scope')
    events=[json.loads(s) for s in re.findall(r'TWTR_CORPORATE_EVENT (\{[^\n]*\})',log)]
    days=[json.loads(s) for s in re.findall(r'TWTR_EVENT_DAY (\{[^\n]*\})',log)]
    daily={}
    permitted={'data_slices','strict_pair_minutes','guarded_pair_minutes','underlying_bars',
               'strict_pair_after_warning','guarded_pair_after_warning','strict_at_noon','guarded_at_noon','warning_seen_by_noon'}
    for d in days:
        day=d.pop('day')
        if day in daily or set(d)-permitted or any(type(v) is not int or v<0 for v in d.values()):
            raise ValueError('Duplicate day, unexpected exported field or invalid count')
        daily[day]=d
    calendar=json.loads((HERE.parent/'research/reference/lean_market_hours_20261018.json').read_text())['entries']['Equity-usa-[*]']
    expected={str(date(2022,9,20)+timedelta(days=i)) for i in range(42)
              if shared.noon_open(date(2022,9,20)+timedelta(days=i),calendar)}
    if not expected.issubset(daily) or len(daily)!=int(rt['twtr_event_observed_days']):
        raise ValueError('Incomplete actual source-probe date coverage')
    if any(set(e)!={'sid','type','warning','callback_utc','algorithm_date','source_time'} for e in events):
        raise ValueError('Unexpected corporate-event fields')
    if len(events)!=int(rt['twtr_event_corporate_events']):raise ValueError('Missing native corporate events')
    warnings=[e for e in events if e['sid']=='TWTR VLE97YS7S57P' and e['warning'] is True]
    if int(bool(warnings))!=int(rt['twtr_event_underlying_warning_seen']):
        raise ValueError('Underlying native warning flag disagrees with events')
    bars=sum(d.get('underlying_bars',0) for d in daily.values())
    if bars<=0 or bars!=int(rt['twtr_event_underlying_bars']):raise ValueError('No actual underlying source coverage')
    phases={p:int(rt.get('twtr_event_phase_'+p+'_strict','0')) for p in ['put31','put43','put46']}
    if any(v<=0 for v in phases.values()):raise ValueError('Actual held-pair phases were not observed with fresh quotes')
    totals={k:sum(d.get(k,0) for d in daily.values()) for k in ['strict_pair_after_warning','guarded_pair_after_warning']}
    if not warnings and any(totals.values()):raise ValueError('Post-warning observations reported without a native warning')
    if any(v!=int(rt['twtr_event_'+k]) for k,v in totals.items()):raise ValueError('Post-warning quote counts do not reconcile')
    hashes=re.findall(r'TWTR_EVENT_CHECKSUM ([0-9a-f]{64})(?![0-9a-z])',log)
    expected_hash=hashlib.sha256(json.dumps(dict(events=events,daily=daily),sort_keys=True).encode()).hexdigest()
    if hashes!=[expected_hash]:raise ValueError('Native event/day aggregate fingerprint mismatch')
    return dict(native_source_probe_verified=True,actual_orders=0,actual_fills=0,actual_fees=0,
        ending_equity=60000,underlying_warning_seen=bool(warnings),warnings=warnings,
        strict_quote_opportunity_after_warning_observed=totals['strict_pair_after_warning']>0,
        guarded_quote_opportunity_after_warning_observed=totals['guarded_pair_after_warning']>0,
        post_warning_counts=totals,held_phase_strict_counts=phases,underlying_bars=bars,
        corporate_events=events,daily_availability=[dict(day=d,**c) for d,c in sorted(daily.items())],
        aggregate_sha256=expected_hash,real_exit_execution_verified=False,strategy_calmar_proven=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('campaign',type=Path);c=p.parse_args().campaign.resolve()
    m=json.loads((c/'manifest.json').read_text())
    if m['phase']!='basket-twtr-event-probe' or len(m['jobs'])!=1:raise ValueError('Wrong corporate-event probe campaign')
    lock=(c/'event_report.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:print('Another event collector owns this campaign');return
    name=m['jobs'][0];code=(c/'twtr_events.py').read_text();extras=json.loads((c/'extra_files.json').read_text())
    with shared.storage.connect(f'file:{shared.ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as conn:
        conn.row_factory=shared.storage.Row;row=dict(conn.execute('select * from backtest_queue where name=?',(name,)).fetchone())
    queued=json.loads(row['extra_files']) if isinstance(row['extra_files'],str) else row['extra_files']
    frozen=json.loads((FROZEN/'extra_files.json').read_text())
    if row['code']!=code or queued!=extras or set(extras)!={'rules.py','execution_base.py','voluntary_quote_guard.py'}:
        raise ValueError('Actual queued source/dependencies differ')
    if any(v!=frozen[k] for k,v in extras.items()):raise ValueError('Actual source quote predicates changed')
    configs=[ast.literal_eval(n.value) for n in ast.walk(ast.parse(code)) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CONFIG' for t in n.targets)]
    if configs!=[m['variants']['twtr_events']]:raise ValueError('Rendered probe policy differs')
    if not row['backtest_id']:print(json.dumps({k:row[k] for k in ['name','status','project_id','backtest_id']}));return
    u,t=shared.credentials(shared.ROOT/'data/S001.duckdb');response=shared.read_research_backtest(u,t,c,name,row);full=response['backtest'];shared.validate_identity(full,row)
    status=shared.terminal_status(full)
    if status is None:print(json.dumps({k:full.get(k) for k in ['backtestId','status','completed','progress']}));return
    folder=shared.collect_terminal(u,t,c,name,row,response);result=dict(status=status,error=full.get('error'),backtest_id=row['backtest_id'],strategy_calmar_proven=False)
    if status=='done':
        orders=json.loads((folder/'orders.json').read_text());rust=json.loads((folder/'orders.rust.json').read_text());rust=rust['orders'] if isinstance(rust,dict) else rust
        result.update(audit(full,orders,rust,(folder/'cloud.log').read_text()))
        shared.write_tables(folder/'event_report',dict(daily_availability=result['daily_availability'],corporate_events=result['corporate_events']))
    shared.atomic_json(c/'twtr_event_summary.json',result);print(json.dumps(result,indent=2))


if __name__=='__main__':main()
