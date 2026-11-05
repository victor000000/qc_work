"""Read-only native minute-RV collection; no raw prices or strategy claims."""
import argparse,json,sys,re,hashlib,fcntl
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import report as shared
from volatility_coverage_report import ROOTS

def audit(full,orders,rust,log):
 if orders or rust or int(full['statistics']['Total Orders'])!=0:raise ValueError('Minute adapter probe traded')
 rt=full['runtimeStatistics']
 if shared.money(rt['Equity'])!=60000 or any(shared.money(rt[k])!=0 for k in ['Fees','Holdings','Unrealized']):raise ValueError('Minute adapter account changed')
 counts={k:int(rt.get('minute_'+k,'0')) for k in ['requests','ready','unavailable','numpy_matches','source_minutes','missing_sessions','stale_sessions']}
 attempts={r:int(rt.get('minute_root_attempt_'+r,'0')) for r in ROOTS};ready={r:int(rt.get('minute_root_ready_'+r,'0')) for r in ROOTS}
 if counts['requests']!=90 or any(n!=6 for n in attempts.values()) or any(n<0 or n>6 for n in ready.values()):raise ValueError('Incomplete all-root attempt scope')
 if counts['ready']+counts['unavailable']!=90 or counts['numpy_matches']!=counts['ready'] or sum(ready.values())!=counts['ready'] or counts['source_minutes']<=0:raise ValueError('Source outcomes do not reconcile')
 unavailable=[json.loads(s) for s in re.findall(r'MINUTE_SOURCE_UNAVAILABLE (\{[^\n]*\})',log)]
 if len(unavailable)!=counts['unavailable']:raise ValueError('Missing explicit unavailable source outcomes')
 if any(set(x)!={'root','native_id','decision','missing_count','stale_count'} for x in unavailable):raise ValueError('Unexpected logged market values')
 if any(sum(x['root']==r for x in unavailable)+ready[r]!=6 for r in ROOTS):raise ValueError('Silent root omission')
 digests=re.findall(r'MINUTE_SOURCE_CHECKSUM ([0-9a-f]{64})(?![0-9a-z])',log)
 if len(digests)!=1 or (counts['ready']>0 and digests[0]==hashlib.sha256().hexdigest()):raise ValueError('Missing aggregate source checksum')
 if rt.get('minute_no_trades')!='1' or rt.get('minute_iv_input')!='synthetic1.0_not_market_IV':raise ValueError('Missing no-trade/synthetic-IV disclosure')
 return dict(native_adapter_comparisons_verified=counts['ready']>0,full_futures_feature_coverage_verified=all(n>0 for n in ready.values()),strategy_calmar_proven=False,market_iv_gate_validated=False,actual_orders=0,actual_fills=0,actual_fees=0,ending_equity=60000,aggregate_counts=counts,root_attempts=attempts,root_ready=ready,unavailable_outcomes=unavailable,fingerprint=digests[0])

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('campaign',type=Path);a=p.parse_args();c=a.campaign.resolve();m=json.loads((c/'manifest.json').read_text())
 if m['phase']!='basket-volatility-minute' or len(m['jobs'])!=1 or set(m['variants']['vol_minute']['roots'])!=ROOTS:raise ValueError('Wrong minute-adapter campaign')
 lock=(c/'minute_report.lock').open('a')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:print('Another minute collector owns this campaign');return
 name=m['jobs'][0];code=(c/'vol_minute.py').read_text();extra=json.loads((c/'extra_files.json').read_text())
 with shared.storage.connect(f'file:{shared.ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as conn:
  conn.row_factory=shared.storage.Row;row=dict(conn.execute('select * from backtest_queue where name=?',(name,)).fetchone())
 queued=json.loads(row['extra_files']) if isinstance(row['extra_files'],str) else row['extra_files']
 if row['code']!=code or queued!=extra or set(extra)!={'completed_volatility.py','minute_session_closes.py'}:raise ValueError('Frozen native adapter differs from queued source')
 if not row['backtest_id']:print(json.dumps({k:row[k] for k in ['name','status','project_id','backtest_id']}));return
 u,t=shared.credentials(shared.ROOT/'data/S001.duckdb');response=shared.read_research_backtest(u,t,c,name,row);full=response['backtest'];shared.validate_identity(full,row);status=shared.terminal_status(full)
 if status is None:print(json.dumps({k:full.get(k) for k in ['backtestId','status','completed','progress']}));return
 folder=shared.collect_terminal(u,t,c,name,row,response)
 result=dict(status=status,error=full.get('error'),backtest_id=row['backtest_id'],strategy_calmar_proven=False,source_sha256=hashlib.sha256(code.encode()).hexdigest(),helpers_sha256=hashlib.sha256((c/'extra_files.json').read_bytes()).hexdigest())
 if status=='done':
  orders=json.loads((folder/'orders.json').read_text());rust=json.loads((folder/'orders.rust.json').read_text());rust=rust['orders'] if isinstance(rust,dict) else rust
  result.update(audit(full,orders,rust,(folder/'cloud.log').read_text()))
  shared.write_tables(folder/'minute_report',dict(aggregate_counts=[{'metric':k,'value':v} for k,v in result['aggregate_counts'].items()],root_coverage=[dict(root=r,attempts=result['root_attempts'][r],ready=result['root_ready'][r]) for r in sorted(ROOTS)],unavailable_outcomes=result['unavailable_outcomes']))
 shared.atomic_json(c/'minute_summary.json',result);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
