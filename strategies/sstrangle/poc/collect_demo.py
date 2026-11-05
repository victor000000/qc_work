#!/usr/bin/env python3
"""Collect native QC demo evidence via Rust, then count/audit whole episodes."""
import argparse
import ast
from collections import defaultdict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import time
import hashlib
import json
import re
import resource
from pathlib import Path
import subprocess
import sys

import pandas as pd
import qc_storage as storage

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'scripts'))
from qc_api_check import credentials, request


def metadata(tag):
    return dict(p.split('=',1) for p in tag.split(';')[1:] if '=' in p)


def parse_contract(value):
    match = re.fullmatch(r'SPXW(\d{6})([CP])(\d{8})', value.replace(' ',''))
    if not match:
        raise ValueError('Unsupported native OCC identity: '+value)
    expiry, right, strike = match.groups()
    return datetime.strptime(expiry,'%y%m%d').date().isoformat(),right,int(strike)/1000


def audit_orders(orders, logs, runtime, require_annual, expected_years=None):
    ids, event_ids, position = set(),set(),defaultdict(float)
    groups, rejected = defaultdict(list),defaultdict(list)
    all_events = []
    for order in orders:
        if order['id'] in ids:
            raise ValueError('Duplicate native order')
        ids.add(order['id'])
        symbol = order['symbol']['id']
        m = metadata(order.get('tag',''))
        fills=[]
        for event in order.get('events',[]):
            event_id = event['id']
            if event_id in event_ids:
                raise ValueError('Duplicate native event')
            event_ids.add(event_id)
            quantity = float(event.get('fillQuantity',0))
            fee = float((event.get('orderFeeAmount') or 0))
            if quantity:
                position[symbol] += quantity
                fills.append(event)
                all_events.append(dict(order_id=order['id'],symbol_id=symbol,
                    symbol=order['symbol']['value'],quantity=quantity,price=float(event['fillPrice']),
                    fee=fee,time=event['time'],order_type=order['type'],tag=order.get('tag','')))
            elif fee:
                raise ValueError('Fee on zero-fill event requires explicit allocation')
        if m.get('r') == 'OPEN':
            (groups if fills else rejected)[m['e']].append(order)
        elif order['type'] != 6: # OptionExercise enum
            raise ValueError('Unexpected non-demo native order type: '+str(order['type']))
    if any(abs(v)>1e-8 for v in position.values()):
        raise ValueError('Residual native contract positions')
    # Settlement spots are observed by the native cash exercise handler; this
    # is attribution of native settled cash, never a substituted market fill.
    settlement, closes, accounts = {},{},[]
    for line in logs.splitlines():
        for token,destination in [('SETTLEMENT_SPOT',settlement),('SESSION_CLOSE',closes)]:
            marker = token+' '
            if marker in line:
                payload=json.loads(line.split(marker,1)[1]);destination[payload['day']]=payload['spot']
        if 'FLAT_ACCOUNT ' in line:
            accounts.append(json.loads(line.split('FLAT_ACCOUNT ',1)[1]))
    # Native exercise events carry the actual settlement underlying, including
    # worthless expirations. These survive even when QC returns no console log.
    for order in orders:
        if order['type'] == 6:
            day,_,_ = parse_contract(order['symbol']['value'])
            for event in order.get('events',[]):
                found = re.search(r'Underlying: ([0-9]+(?:\.[0-9]+)?)', event.get('message') or '')
                if found:
                    spot=float(found.group(1))
                    if day in settlement and abs(settlement[day]-spot)>1e-5:
                        raise ValueError('Native expiry settlement references disagree')
                    settlement[day]=spot
    episodes, legs = [],[]
    for key,group in sorted(groups.items()):
        if len(group)!=4 or len({o['symbol']['id'] for o in group})!=4:
            raise ValueError('Episode does not have four distinct native orders')
        if key in rejected:
            raise ValueError('Partly filled/rejected episode')
        managers=[o.get('groupOrderManager') or {} for o in group]
        combo_ids={m.get('id') for m in managers}
        native_ids={o['id'] for o in group}
        if (len(combo_ids)!=1 or None in combo_ids or any(o['type']!=8 for o in group)
                or any(m.get('count')!=4 or set(m.get('orderIds',[]))!=native_ids for m in managers)):
            raise ValueError('Episode lacks an exact four-order native combo identity')
        entry_cash,fees,payoff = 0.,0.,0.
        day = datetime.strptime(key[:8],'%Y%m%d').date().isoformat()
        spot = settlement.get(day,closes.get(day))
        if spot is None:
            raise ValueError('Missing expiry reference for '+day)
        strikes = {}
        for order in group:
            if order['status'] != 3:
                raise ValueError('Unfilled episode order')
            expiry,right,strike = parse_contract(order['symbol']['value'])
            if expiry != day:
                raise ValueError('Episode is not 0DTE')
            fills = [e for e in order.get('events',[]) if float(e.get('fillQuantity',0))]
            quantity = sum(float(e['fillQuantity']) for e in fills)
            if abs(quantity)!=1:
                raise ValueError('Episode quantity differs from one lot')
            cash = -sum(float(e['fillQuantity'])*float(e['fillPrice'])*100 for e in fills)
            fee = sum(float((e.get('orderFeeAmount') or 0)) for e in fills)
            intrinsic = max(0,spot-strike) if right=='C' else max(0,strike-spot)
            outcome = quantity*intrinsic*100
            entry_cash += cash;fees += fee;payoff += outcome
            strikes[(right,int(quantity))] = strike
            legs.append(dict(episode=key,order_id=order['id'],symbol_id=order['symbol']['id'],
                symbol=order['symbol']['value'],expiry=expiry,right=right,strike=strike,
                quantity=quantity,entry_cash=cash,fees=fee,expiry_attribution=outcome))
        if set(strikes)!={('P',1),('P',-1),('C',-1),('C',1)}:
            raise ValueError('Wrong iron-condor leg signs')
        if (strikes['P',-1]-strikes['P',1]!=20 or strikes['C',1]-strikes['C',-1]!=20
                or strikes['P',-1]>=strikes['C',-1]):
            raise ValueError('Wrong wing widths/strike ordering')
        if runtime.get('fill_convention') == 'oo_midpoint_package':
            package_slip=0.0
            for order in group:
                for event in order.get('events',[]):
                    quantity=float(event.get('fillQuantity',0))
                    if not quantity:
                        continue
                    message=event.get('message') or ''
                    mid=re.search(r'oo_mid=([0-9.]+)',message)
                    slip=re.search(r'oo_slip=([0-9.]+)',message)
                    if not mid or not slip:
                        raise ValueError('Midpoint source model did not round-trip through native fill events')
                    expected=float(mid.group(1))+(float(slip.group(1)) if quantity>0 else -float(slip.group(1)))
                    if abs(expected-float(event['fillPrice']))>1e-7:
                        raise ValueError('Native fill differs from documented midpoint model')
                    package_slip+=abs(quantity)*float(slip.group(1))
            if abs(package_slip-0.05)>1e-7:
                raise ValueError('Slippage is not 0.05 for the complete four-leg package')
        if not 0<entry_cash<2000:
            raise ValueError('Filled condor credit is outside its 20-point payoff bounds')
        m=metadata(group[0]['tag'])
        decision=pd.Timestamp(m['d']).tz_localize('America/New_York').tz_convert('UTC')
        filled_times=[pd.Timestamp(e['time'],unit='s',tz='UTC') for o in group for e in o.get('events',[]) if float(e.get('fillQuantity',0))]
        if min(filled_times)<decision or max(filled_times)>decision+pd.Timedelta(minutes=3):
            raise ValueError('Native entry fill predates decision or exceeds declared execution deadline')
        episodes.append(dict(episode=key,ticker='SPX',day=day,year=int(day[:4]),
            decision_at=m['d'],entry_at=min(filled_times).isoformat(),last_leg_fill_at=max(filled_times).isoformat(),
            fill_delay_seconds=(max(filled_times)-decision).total_seconds(),put_delta=float(m['pd']),call_delta=float(m['cd']),
            entry_spot=float(m['spot']),settlement_spot=spot,entry_credit=entry_cash,
            opening_fees=fees,expiry_cash_attribution=payoff,pnl=entry_cash-fees+payoff))
    frame = pd.DataFrame(episodes)
    if not len(frame) or not frame.episode.is_unique:
        raise ValueError('No unique episodes')
    for key,group in rejected.items():
        if len(group)!=4 or any(o['status'] not in (5,7) for o in group):
            raise ValueError('Rejected episode is not a zero-fill terminal combo')
    if len(frame)!=int(runtime['filled_episodes']):
        raise ValueError('Exported episode count differs from runtime counter')
    annual=frame.groupby('year').agg(trades=('episode','size'),days=('day','nunique'),net_pnl=('pnl','sum')).reset_index()
    if expected_years is not None:
        annual = annual.set_index('year').reindex(expected_years, fill_value=0).rename_axis('year').reset_index()
    annual['minimum']=360;annual['passed']=annual.trades>=360
    for r in annual.itertuples():
        if r.trades!=int(runtime.get('episodes_'+str(r.year),0)):
            raise ValueError('Annual native count differs from runtime')
    net=float(frame.pnl.sum());native=float(runtime['native_net_pnl'])
    if abs(net-native)>0.05:
        raise ValueError('Episode expiry attribution differs from native account: '+str((net,native)))
    if abs(float(runtime['ledger_error']))>0.05:
        raise ValueError('Native cash ledger does not reconcile')
    if require_annual and not expected_years:
        raise ValueError('Annual acceptance requires the expected year inventory')
    return frame,pd.DataFrame(legs),pd.DataFrame(all_events),annual,dict(
        episodes=len(frame),orders=len(orders),fill_events=len(all_events),
        rejected_episodes=len(rejected),native_net_pnl=native,episode_net_pnl=net,
        attribution_error=net-native,residual_positions=0,flat_account_log_checks=len(accounts),
        runtime_max_flat_ledger_error=float(runtime['max_flat_ledger_error']),
        settlement_reference='Native option exercise event messages; console log fallback',
        annual_requirement_applied=require_annual,annual_pass=bool(annual.passed.all()),
        fill_convention=runtime.get('fill_convention','quote_side_per_leg'),
        midpoint_package_fill_audit=runtime.get('fill_convention')=='oo_midpoint_package',
        max_entry_fill_delay_seconds=float(frame.fill_delay_seconds.max()),
        interpretation='Native cash-settled account with attributed whole-episode outcomes; overlapping trades are dependent')


def archive_raw_orders(user, token, ids, expected, out, workers=8):
    """Bounded native API archive; every complete page survives interruption."""
    folder=out/'raw_order_pages';folder.mkdir(exist_ok=True)
    started=time.perf_counter()
    cached_at_start=len(list(folder.glob('*.json')))
    prior=json.loads((out/'raw_order_pages_manifest.json').read_text()).get('files',{}) if (out/'raw_order_pages_manifest.json').exists() else {}
    def fetch(start):
        path=folder/f'{start:08d}.json'
        page=None
        if path.exists():
            if path.name in prior and hashlib.sha256(path.read_bytes()).hexdigest()!=prior[path.name]:
                raise ValueError('Completed raw page checksum differs from its immutable manifest')
            try:page=json.loads(path.read_text())
            except json.JSONDecodeError:
                if path.name in prior:raise
                path.rename(path.with_suffix('.incomplete'))
        if page is None:
            for attempt in range(6):
                try:
                    page=request(user,token,'/backtests/orders/read',dict(ids,start=start,end=min(start+99,expected)))
                    if isinstance(page.get('orders'),(list,dict)):
                        temporary=path.with_suffix('.tmp')
                        temporary.write_text(json.dumps(page,indent=2));temporary.replace(path);break
                    raise ValueError('Native order page not ready')
                except Exception:
                    if attempt==5:raise
                    time.sleep(min(2**attempt,8))
            time.sleep(0.25)
        rows=page['orders'];rows=list(rows.values()) if isinstance(rows,dict) else rows
        if len(rows)!=min(99,expected-start):
            raise ValueError('Native raw page is incomplete')
        return rows
    orders=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i,rows in enumerate(pool.map(fetch,range(0,expected,99)),1):
            orders.extend(rows)
            if i%50==0:print(f'Archived {len(orders):,}/{expected:,} native orders',flush=True)
    if len(orders)!=expected or len({o['id'] for o in orders})!=expected:
        raise ValueError('Raw native order coverage/uniqueness mismatch')
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.glob('*.json'))}
    (out/'raw_order_pages_manifest.json').write_text(json.dumps(dict(identity=ids,orders=expected,
        page_size=99,workers=workers,cached_pages_at_start=cached_at_start,wall_seconds=time.perf_counter()-started,files=files),indent=2)+'\n')
    (out/'orders.json').write_text(json.dumps(orders,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--name',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--require-annual',action='store_true')
    p.add_argument('--expected-years',nargs='+',type=int)
    p.add_argument('--raw-pages',action='store_true',help='Archive complete original native API responses in resumable pages')
    p.add_argument('--export-workers',type=int,default=8,choices=range(1,9))
    p.add_argument('--terminal-json',type=Path,help='Saved full terminal native API response; identity is verified')
    a=p.parse_args();started=time.perf_counter();cpu_started=time.process_time()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    with storage.connect(f'file:{ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as c:
        c.row_factory=storage.Row
        row=dict(c.execute('SELECT name,status,project_id,backtest_id,error_message,code_hash,result_json,code FROM backtest_queue WHERE name=?',(a.name,)).fetchone())
    source=row.pop('code')
    source_sha256=hashlib.sha256(source.encode()).hexdigest()
    cfg=next(ast.literal_eval(node.value) for node in ast.walk(ast.parse(source))
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CONFIG' for t in node.targets))
    period_start=datetime(*cfg['start']).date()
    period_end=datetime(*cfg['last_entry']).date()
    if a.require_annual and a.expected_years!=list(range(period_start.year,period_end.year+1)):
        raise ValueError('Expected-year inventory differs from submitted source period')
    runtime=json.loads(row.pop('result_json') or '{}')
    if (out/'queue_identity.json').exists():
        previous=json.loads((out/'queue_identity.json').read_text())
        if any(previous.get(k)!=row.get(k) for k in ['name','project_id','backtest_id','code_hash']):
            raise ValueError('Cached evidence belongs to a different QC run; use a fresh directory')
    (out/'submitted_main.py').write_text(source)
    row['source_sha256']=source_sha256
    (out/'queue_identity.json').write_text(json.dumps(row,indent=2))
    u,t=credentials(ROOT/'data/S001.duckdb')
    cached=a.terminal_json or (out/'backtest.json')
    full=json.loads(cached.read_text()) if cached.exists() else request(u,t,'/backtests/read',dict(projectId=row['project_id'],backtestId=row['backtest_id']))
    (out/'backtest.json').write_text(json.dumps(full,indent=2))
    b=full['backtest']
    assert b['completed'] and str(b['backtestId'])==row['backtest_id'] and b['projectId']==row['project_id']
    binary=ROOT/'target/release/qc-backtest-server'
    if not (out/'orders.json').exists() and a.raw_pages:
        archive_raw_orders(u,t,dict(projectId=row['project_id'],backtestId=row['backtest_id']),int(str(b['statistics']['Total Orders']).replace(',','')),out,a.export_workers)
    if not (out/'orders.json').exists():
        subprocess.run([str(binary),'--data-dir',str(ROOT/'data'),'backtest-orders','--strategy','sstrangle','--name',a.name,'--out',str(out/'orders.json')],check=True)
    if not (out/'cloud.log').exists():
        with (out/'cloud.log').open('w') as handle:
            subprocess.run([str(binary),'--data-dir',str(ROOT/'data'),'backtest-log','--strategy','sstrangle','--name',a.name],stdout=handle,check=True)
    if not (out/'cloud.log').read_text().strip():
        # The shared CLI's query='log' filters out these actual runtime lines.
        # Keep its empty result and fetch the supported unfiltered response.
        (out/'cloud.rust.log').write_bytes((out/'cloud.log').read_bytes())
        pages=out/'log_pages';pages.mkdir(exist_ok=True)
        lines=[]
        for start in range(0,100000,200):
            cache=pages/f'{start:08d}.json'
            page=json.loads(cache.read_text()) if cache.exists() else request(u,t,'/backtests/read/log',
                dict(projectId=row['project_id'],backtestId=row['backtest_id'],start=start,end=start+200,query=''))
            if not cache.exists():cache.write_text(json.dumps(page,indent=2))
            chunk=page.get('logs',page.get('log',[]));lines.extend(chunk)
            if len(chunk)<200:break
        else:raise ValueError('Console log pagination exceeded safety bound')
        (out/'cloud.log').write_text('\n'.join(lines)+'\n')
    if b.get('error'):
        (out/'audit.json').write_text(json.dumps(dict(status='cloud_failed',error=b.get('error') or row['error_message']),indent=2));return
    native_runtime=b.get('runtimeStatistics') or runtime['runtimeStatistics']
    if cfg.get('fill_convention')=='oo_midpoint_package' and native_runtime.get('fill_convention')!='oo_midpoint_package':
        raise ValueError('Submitted source fill convention did not survive native runtime export')
    frame,legs,events,annual,audit=audit_orders(json.loads((out/'orders.json').read_text()),
        (out/'cloud.log').read_text(),native_runtime,a.require_annual,a.expected_years)
    annual['requested_start']=[str(max(period_start,datetime(int(y),1,1).date())) for y in annual.year]
    annual['requested_end']=[str(min(period_end,datetime(int(y),12,31).date())) for y in annual.year]
    annual['partial_year']=[lo!=f'{int(y)}-01-01' or hi!=f'{int(y)}-12-31'
        for y,lo,hi in zip(annual.year,annual.requested_start,annual.requested_end)]
    audit['local_queue_status']=row['status']
    audit['native_cloud_terminal_success']=bool(b['completed'] and not b.get('error'))
    audit['complete_raw_order_pages_archived']=(out/'raw_order_pages_manifest.json').exists()
    audit['source_sha256']=source_sha256
    audit['source_period']=[str(period_start),str(period_end)]
    stats=b.get('statistics',{})
    ending=float(str(stats['End Equity']).replace(',','').replace('$',''))
    start=float(str(stats['Start Equity']).replace(',','').replace('$',''))
    fees=float(events.fee.sum())
    reported_fees=float(str(stats['Total Fees']).replace(',','').replace('$',''))
    if abs(fees-len(frame)*4*1.18)>0.05:
        raise ValueError('Native fees differ from the declared source per-contract convention')
    if abs(ending-start-audit['native_net_pnl'])>0.05 or abs(fees-reported_fees)>0.05:
        raise ValueError('Exported ledger differs from QC standard account/fee totals')
    audit['standard_account_reconciliation_error']=ending-start-audit['native_net_pnl']
    audit['event_fees']=fees
    audit['episode_statistics']=dict(win_rate=float((frame.pnl>0).mean()),mean_pnl=float(frame.pnl.mean()),
        mean_win=float(frame.loc[frame.pnl>0,'pnl'].mean()),mean_loss=float(frame.loc[frame.pnl<0,'pnl'].mean()),
        max_win=float(frame.pnl.max()),max_loss=float(frame.pnl.min()),
        total_opening_credit=float(frame.entry_credit.sum()),distinct_trading_days=int(frame.day.nunique()),
        max_same_day_episodes=int(frame.groupby('day').size().max()))
    audit['qc_statistics']=stats
    feature_fields=['episode','ticker','decision_at','put_delta','call_delta','entry_spot']
    entry_features=frame[feature_fields].rename(columns={'entry_spot':'decision_spot'}).copy()
    entry_features['decision_at']=pd.to_datetime(entry_features.decision_at).dt.tz_localize('America/New_York').dt.tz_convert('UTC')
    labels=frame[['episode','day','year','settlement_spot','entry_credit','opening_fees','expiry_cash_attribution','pnl']].copy()
    assert entry_features.episode.is_unique and labels.episode.is_unique
    assert set(entry_features.columns).isdisjoint(set(labels.columns)-{'episode'})
    entry_features.to_parquet(out/'entry_features.parquet',compression='zstd',index=False)
    labels.to_parquet(out/'labels.parquet',compression='zstd',index=False)
    registry=dict(version='0.5-audio-poc',scope='SPX native decision metadata only',
        features=['put_delta','call_delta','decision_spot'],
        availability='Computed within the decision event before native order submission; tag timestamp is the decision clock',
        excluded_inputs=['settlement_spot','entry_credit','opening_fees','expiry_cash_attribution','pnl'],
        units=dict(put_delta='dimensionless',call_delta='dimensionless',decision_spot='index_points'),
        provider_features='Not joined here; current quote/provider admission still pending')
    (out/'feature_registry.json').write_text(json.dumps(registry,indent=2)+'\n')
    audit['delta_target_error']=dict(put_max=float((frame.put_delta+0.20).abs().max()),
        call_max=float((frame.call_delta-0.08).abs().max()))
    for name,data in [('episodes',frame),('legs',legs),('fill_events',events),('annual',annual)]:
        data.to_parquet(out/(name+'.parquet'),compression='zstd',index=False)
        data.to_csv(out/(name+'.csv'),index=False)
    audit['collection_cache_state']='resumed_or_cached' if (out/'raw_order_pages_manifest.json').exists() and json.loads((out/'raw_order_pages_manifest.json').read_text()).get('cached_pages_at_start',0) else 'fresh'
    if a.terminal_json:audit['span_since_terminal_response_seconds']=time.time()-a.terminal_json.stat().st_mtime
    audit['collection_wall_seconds']=time.perf_counter()-started
    audit['collection_cpu_seconds']=time.process_time()-cpu_started
    audit['process_peak_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    timing=re.search(r'completed in ([0-9.]+) seconds', (out/'cloud.log').read_text())
    if timing:audit['qc_logged_engine_seconds']=float(timing.group(1))
    (out/'audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    files={str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.iterdir()) if f.is_file() and f.name!='manifest.json'}
    (out/'manifest.json').write_text(json.dumps(dict(files=files),indent=2)+'\n')
    print(json.dumps(audit,indent=2))
    if a.require_annual and not audit['annual_pass']:
        raise SystemExit('Native accounting passed, annual 360-episode acceptance failed; evidence preserved')


if __name__=='__main__':main()
