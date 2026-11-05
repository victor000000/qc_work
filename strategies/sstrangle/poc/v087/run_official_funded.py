"""Short integration gate; preserves native account risk and archives before reuse."""
import fcntl,hashlib,json,time
from campaign import OUT,P,ROOT,prepare,rows,read,save
from qc_api_check import credentials
from collect import archive_raw_orders,audit_orders,parse_contract
lock=(OUT/'official_funded_controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
plan=json.loads((OUT/'official_funded_plan.json').read_text());source=P/'strategy_official_funded.py'
assert hashlib.sha256(source.read_bytes()).hexdigest()==plan['source_sha256']
assert all(x['pass'] for x in json.loads((OUT/'accounting_fee_independent_review.json').read_text()).values())
u,t=credentials(ROOT/'data/S001.duckdb')
for test in plan['tests']:
 key=test['key'];folder=OUT/(key+'_funded_archive');folder.mkdir(exist_ok=True)
 if (folder/'audit.json').exists():
  prior=json.loads((folder/'audit.json').read_text())
  assert prior.get('funded_pass') or 'Margin Call' in prior.get('error','');continue
 module=(OUT/'official_funded_values.py').read_text()
 assert hashlib.sha256(module.encode()).hexdigest()==plan['data_module_sha256']
 m=prepare(key,test['kind'],alpha=test['alpha'],overrides=dict(plan['overrides'],start_capital=test['capital']),source_path=source,extra_files={'official_settlement_values.py':module})
 while True:
  row=next(x for x in rows() if x['name']==m['name']);print(row,flush=True)
  if row['backtest_id']:
   ids=dict(projectId=row['project_id'],backtestId=row['backtest_id']);response=read(u,t,'/backtests/read',ids);b=response['backtest'];save(folder/'progress.json',response)
   if b.get('completed'):break
  elif row['status']=='failed':raise RuntimeError('Queue failed without identity; do not retry')
  time.sleep(30)
 save(folder/'backtest.json',response);save(folder/'queue_identity.json',row)
 cloud=read(u,t,'/files/read',{'projectId':row['project_id']});remote={x['name']:x['content'] for x in cloud['files']};assert hashlib.sha256(remote['main.py'].encode()).hexdigest()==m['source_sha256'];save(folder/'cloud_source_files.json',cloud)
 assert all(hashlib.sha256(remote[name].encode()).hexdigest()==h for name,h in m['extra_files_sha256'].items())
 expected=int(str(b.get('statistics',{}).get('Total Orders','0')).replace(',',''))
 if expected:archive_raw_orders(u,t,ids,expected,folder,workers=1)
 logs=read(u,t,'/backtests/read/log',dict(ids,start=0,end=200,query=''));save(folder/'logs.json',logs)
 if b.get('error'):
  save(folder/'audit.json',{'integration_pass':False,'funded_pass':False,'error':b['error'],'source_match':True})
  if 'Margin Call' in b['error']:
   print('ARCHIVED native margin failure',key,flush=True);continue
  raise RuntimeError('Non-margin runtime failure; later jobs not submitted')
 orders=json.loads((folder/'orders.json').read_text());cash=0.;expiry_count=0
 for o in orders:
  for e in o.get('events',[]):
   qty=float(e.get('fillQuantity',0));price=float(e.get('fillPrice',0));fee=float(e.get('orderFeeAmount') or 0);cash-=qty*price*100+fee
   if o['type']==6 and qty:
    day,right,strike=parse_contract(o['symbol']['value']);spot=plan['values'][day];intrinsic=max(0,strike-spot if right=='P' else spot-strike)
    assert abs(price-intrinsic)<1e-7 and fee==0;expiry_count+=1
 runtime=b['runtimeStatistics'];assert runtime['settlement_policy']=='official_intrinsic_generic_portfolio'
 assert abs(cash-float(runtime['native_net_pnl']))<.05
 frame,legs,events,annual,audit=audit_orders(orders,'',runtime,False)
 for name,data in [('episodes',frame),('legs',legs),('events',events),('annual',annual)]:data.to_parquet(folder/(name+'.parquet'),index=False)
 audit.update(integration_pass=True,funded_pass=True,source_match=True,raw_event_net_cash=cash,official_expiry_events=expiry_count,scope='Full-period native-market replay with official expiry cash; independent predecision replay not established')
 save(folder/'audit.json',audit);print('ARCHIVED',key,audit,flush=True)
print('All preregistered official funded accounts archived',flush=True)
