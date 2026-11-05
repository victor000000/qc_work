"""Read-only native volatility-source probe collection; never trades or submits."""
import argparse,ast,hashlib,json,sys,fcntl,re
from pathlib import Path
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import report as shared

def verify_source(campaign,key,cfg,row):
    code=(campaign/(key+'.py')).read_text();extra=json.loads((campaign/'extra_files.json').read_text())
    queued=json.loads(row['extra_files']) if isinstance(row['extra_files'],str) else row['extra_files']
    if row['code']!=code or queued!=extra:raise ValueError('Frozen native probe source differs from queued source')
    configs=[ast.literal_eval(n.value) for n in ast.walk(ast.parse(code)) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CONFIG' for t in n.targets)]
    expected={'completed_volatility.py'}|({'volatility_original_fixture.py'} if 'roots' in cfg else set())
    if configs!=[cfg] or set(extra)!=expected:raise ValueError('Unexpected native probe CONFIG/dependencies')
    if 'roots' in cfg:
        frozen=HERE.parent/'results/strangle_basket-volatility-source_20261019_174306/vol_futures.py'
        if extra['volatility_original_fixture.py']!=frozen.read_text():raise ValueError('Previously native-verified source adapter changed')
    return dict(queued_source_identical=True,main_sha256=hashlib.sha256(code.encode()).hexdigest(),helper_sha256=hashlib.sha256(extra['completed_volatility.py'].encode()).hexdigest())

def audit(full,orders,rust,chart,probe,log=''):
    if orders or rust:raise ValueError('Source-only probe unexpectedly traded')
    declared=full.get('statistics',{}).get('Total Orders')
    if declared is not None and int(str(declared).replace(',',''))!=0:raise ValueError('Declared native orders differ from empty genuine exports')
    rt=full.get('runtimeStatistics',{});numbers={}
    for key in ['requests','aligned_windows','numpy_matches','sampled_closes']:
        numbers[key]=int(rt['vol_'+key])
    n=numbers['requests']
    if n<=0 or numbers['aligned_windows']!=n or numbers['numpy_matches']!=n or numbers['sampled_closes']!=61*n:raise ValueError('Missing/partial native source comparisons')
    if probe=='equity':
        for key in ['equity_windows','split_basis_verified','actual_split_events']:numbers[key]=int(rt['vol_'+key])
        if numbers['equity_windows']!=n or numbers['split_basis_verified']<=0 or numbers['actual_split_events']<=0:raise ValueError('Missing actual corporate-action controls')
    elif probe=='futures':
        for key in ['futures_windows','native_delivery_resets']:numbers[key]=int(rt['vol_'+key])
        if numbers['futures_windows']!=n or numbers['native_delivery_resets']<=0:raise ValueError('Missing native delivery controls')
    else:raise ValueError('Unexpected native source mode')
    logged=re.findall(r'\bVOLATILITY_SOURCE_CHECKSUM ([0-9a-f]{64})(?![0-9a-z])',log)
    if len(logged)>1:raise ValueError('Duplicate aggregate test checksums')
    fingerprint=rt.get('vol_feature_fingerprint') or (logged[0] if logged else '')
    if logged and rt.get('vol_feature_fingerprint') and logged[0]!=rt['vol_feature_fingerprint']:raise ValueError('Conflicting aggregate checksums')
    if len(fingerprint)!=64 or any(c not in '0123456789abcdef' for c in fingerprint) or fingerprint==hashlib.sha256().hexdigest():raise ValueError('Missing aggregate feature fingerprint')
    if rt.get('vol_no_trades')!='1' or 'synthetic' not in rt.get('vol_synthetic_iv_input','') and 'arithmetic only' not in rt.get('vol_synthetic_iv_input',''):raise ValueError('Missing no-trade/synthetic-IV disclosure')
    if abs(shared.money(rt['Equity'])-60000)>.005 or any(shared.money(rt[k])!=0 for k in ['Fees','Holdings','Unrealized']):raise ValueError('Actual account/fees changed')
    daily=shared.daily_marks(chart)
    if not daily or any(abs(v-60000)>.005 for v in daily.values()):raise ValueError('Native account curve changed')
    return dict(engineering_verified=True,strategy_performance_claim=False,market_iv_gate_validated=False,native_orders=0,actual_fills=0,actual_fees=0,ending_equity=60000,aggregate_counts=numbers,feature_fingerprint=fingerprint,account_chart_observations=len(daily))

def audit_roots(rt,roots,total):
    if len(roots)!=15 or len(set(roots))!=15:raise ValueError('Require all15distinct supported roots')
    counts={root:int(rt['vol_root_'+root]) for root in roots}
    if any(v<=0 for v in counts.values()) or sum(counts.values())!=total:raise ValueError('Native root comparison scope incomplete')
    return {'root_'+root:value for root,value in counts.items()}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('campaign',type=Path);a=p.parse_args();campaign=a.campaign.resolve();m=json.loads((campaign/'manifest.json').read_text())
    if m['phase'] not in ('basket-volatility-source','basket-volatility-roots'):raise ValueError('Wrong source-probe campaign')
    if m['phase']=='basket-volatility-source':
        if len(m['variants'])!=2 or {c.get('probe') for c in m['variants'].values()}!={'equity','futures'}:raise ValueError('Both actual source probes required')
    elif len(m['variants'])!=1 or set(next(iter(m['variants'].values()))['roots'])!={'CL','RB','HO','NG','ZN','ZT','ZB','ZC','ZS','ZW','NQ','ES','HG','GC','SI'}:raise ValueError('Full supported futures source scope required')
    lock=(campaign/'volatility_source_report.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        print('Another source-probe collector owns this campaign');return
    u,t=shared.credentials(shared.ROOT/'data/S001.duckdb');progress=[];results=[];issues=[]
    for name in m['jobs']:
        key,cfg=shared.config_for(name,m)
        with shared.storage.connect('file:'+str(shared.ROOT/'data/SSTRANGLE.duckdb')+'?mode=ro',uri=True) as c:
            c.row_factory=shared.storage.Row;row=dict(c.execute('select * from backtest_queue where name=?',(name,)).fetchone())
        proof=verify_source(campaign,key,cfg,row)
        if not row.get('backtest_id'):progress.append(dict(name=name,status=row['status'],completed=False));continue
        try:
            response=shared.read_research_backtest(u,t,campaign,name,row);full=response['backtest'];shared.validate_identity(full,row);status=shared.terminal_status(full)
            progress.append({k:full.get(k) for k in ['backtestId','status','completed','error','progress']})
            if status is None:continue
            folder=shared.collect_terminal(u,t,campaign,name,row,response)
            receipt=json.loads((folder/'collection_receipt.json').read_text())
            if receipt['issues']:issues.extend(receipt['issues'])
            if status!='done':
                failed=dict(probe=cfg['probe'],backtest_id=row['backtest_id'],engineering_verified=False,actual_cloud_failure=full.get('error'),evidence=str(folder),source_proof=proof)
                shared.write_tables(folder/'feature_report',dict(failed_native_events=[dict(backtest_id=row['backtest_id'],status=full.get('status'),error=full.get('error'))]))
                shared.atomic_json(folder/'feature_report/failed_summary.json',failed);results.append(failed);continue
            orders=json.loads((folder/'orders.json').read_text());rust=json.loads((folder/'orders.rust.json').read_text());rust=rust['orders'] if isinstance(rust,dict) else rust
            result=audit(full,orders,rust,json.loads((folder/'strategy_equity.json').read_text()),cfg['probe'],(folder/'cloud.log').read_text())
            if 'roots' in cfg:result['aggregate_counts'].update(audit_roots(full['runtimeStatistics'],cfg['roots'],result['aggregate_counts']['requests']))
            result.update(probe=cfg['probe'],backtest_id=row['backtest_id'],project_id=row['project_id'],source_proof=proof)
            shared.write_tables(folder/'feature_report',dict(aggregate_counts=[dict(metric=k,value=v) for k,v in result['aggregate_counts'].items()],actual_orders=orders))
            shared.atomic_json(folder/'feature_report/summary.json',result);results.append(result)
        except Exception as e:issues.append(dict(name=name,error=type(e).__name__+': '+str(e),read_only_retry=True))
    verified=len(results)==len(m['variants']) and all(r['engineering_verified'] for r in results) and not issues
    result=dict(engineering_scope_verified=verified,all_roots_verified=verified and m['phase']=='basket-volatility-roots',utc=datetime.now(timezone.utc).isoformat(),engineering_pair_verified=verified and m['phase']=='basket-volatility-source',strategy_calmar_proven=False,progress=progress,results=results,collection_issues=issues)
    shared.atomic_json(campaign/'volatility_source_summary.json',result);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
