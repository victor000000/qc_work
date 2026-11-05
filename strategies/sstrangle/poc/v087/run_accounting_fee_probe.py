"""Serial native accounting pair; separate audit from frozen strategy ledger."""
import fcntl,hashlib,json,time
from campaign import OUT,P,ROOT,prepare,rows,read,save
from qc_api_check import credentials
from collect import archive_raw_orders
lock=(OUT/'accounting_fee_probe_controller.lock').open('a')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
plan=json.loads((OUT/'accounting_fee_probe_plan.json').read_text())
source=P/'strategy_accounting_fee_probe.py'
assert hashlib.sha256(source.read_bytes()).hexdigest()==plan['source_sha256']
u,t=credentials(ROOT/'data/S001.duckdb')
for test in plan['tests']:
 key=test['key'];folder=OUT/(key+'_accounting_evidence');folder.mkdir(exist_ok=True)
 if (folder/'audit.json').exists():
  assert json.loads((folder/'audit.json').read_text())['accounting_pass']
  continue
 m=prepare(key,'condor',overrides={'accounting_mode':test['mode'],'settlement_reference':test['reference']},source_path=source)
 while True:
  row=next(x for x in rows() if x['name']==m['name'])
  print(row,flush=True)
  if row['backtest_id']:
   ids=dict(projectId=row['project_id'],backtestId=row['backtest_id'])
   response=read(u,t,'/backtests/read',ids);b=response['backtest']
   save(folder/'progress.json',response)
   if b.get('completed'):break
  elif row['status']=='failed':raise RuntimeError('Queue failure without identity; no retry')
  time.sleep(30)
 save(folder/'backtest.json',response);save(folder/'queue_identity.json',row)
 cloud=read(u,t,'/files/read',{'projectId':row['project_id']})
 remote={x['name']:x['content'] for x in cloud['files']}
 assert hashlib.sha256(remote['main.py'].encode()).hexdigest()==m['source_sha256']
 save(folder/'cloud_source_files.json',cloud)
 expected=int(str(b.get('statistics',{}).get('Total Orders','0')).replace(',',''))
 if expected:archive_raw_orders(u,t,ids,expected,folder,workers=1)
 save(folder/'logs.json',read(u,t,'/backtests/read/log',dict(ids,start=0,end=200,query='')))
 s=b.get('runtimeStatistics',{})
 passed=not b.get('error') and all(k in s for k in ['AC_opens','AC_expiries','AC_cash_error','AC_residual']) and int(s['AC_opens'])==8 and int(s['AC_expiries'])==8 and abs(float(s['AC_cash_error']))<.01 and float(s['AC_residual'])==0
 save(folder/'audit.json',{'accounting_pass':passed,'error':b.get('error'),'statistics':s,'source_readback_matches_submitted':True,'scope':'Engineering accounting only; not strategy acceptance'})
 print('ARCHIVED',key,'pass',passed,flush=True)
 if not passed:raise RuntimeError('Accounting probe failed; later stage not submitted')
print('Accounting pair archived; independent cross-account parity review required',flush=True)
