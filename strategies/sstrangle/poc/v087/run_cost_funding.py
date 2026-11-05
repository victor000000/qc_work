"""Execute the preregistered combined cost/funding matrix after prior probes."""
import fcntl,json,time,traceback
from campaign import OUT,P,ROOT,run,rows,read,save
from qc_api_check import credentials
lock=(OUT/'cost_funding_controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert 'Settlement probes terminal and archived' in (OUT/'settlement_controller.log').read_text()
plan=json.loads((P/'cloud_cost_funding_plan.json').read_text());save(OUT/'cloud_cost_funding_plan.json',plan)
for item in plan['tests']:
 key=item['key']
 if (OUT/(key+'_failure.json')).exists():continue
 try:run(key,item['kind'],item['alpha'],overrides=item['overrides'])
 except Exception as e:
  row=next((x for x in rows() if x['name'].endswith(key.upper())),None);details={'key':key,'error':str(e),'queue_row':row,'traceback':traceback.format_exc()}
  if row and row['backtest_id']:
   u,t=credentials(ROOT/'data/S001.duckdb');b=read(u,t,'/backtests/read',dict(projectId=row['project_id'],backtestId=row['backtest_id']));save(OUT/(key+'_failed_terminal.json'),b);details['native_error']=b.get('backtest',{}).get('error')
  save(OUT/(key+'_failure.json'),details)
  if not details.get('native_error'):raise
  while not (OUT/(key+'_evidence/audit.json')).exists():time.sleep(10)
print('Combined cost/funding tests terminal and archived',flush=True)
