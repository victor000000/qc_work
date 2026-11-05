import fcntl,json,time,traceback,hashlib
from campaign import OUT,P,ROOT,run,rows,read,save
from qc_api_check import credentials
lock=(OUT/'margin_events_controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
plan=json.loads((OUT/'margin_events_execution_plan.json').read_text())
key=plan['key'];cfg=plan['overrides'];path=P/'strategy_margin_events.py'
assert hashlib.sha256(path.read_bytes()).hexdigest()==plan['source_sha256']
assert json.loads((OUT/'margin_runtime_order_parity.json').read_text())['orders_equal']
try:run(key,'condor',overrides=cfg,source_path=path)
except Exception as e:
 row=next((x for x in rows() if x['name'].endswith(key.upper())),None);details={'key':key,'error':str(e),'queue_row':row,'traceback':traceback.format_exc()}
 if row and row['backtest_id']:
  u,t=credentials(ROOT/'data/S001.duckdb');b=read(u,t,'/backtests/read',dict(projectId=row['project_id'],backtestId=row['backtest_id']));save(OUT/(key+'_failed_terminal.json'),b);details['native_error']=b.get('backtest',{}).get('error')
 save(OUT/(key+'_failure.json'),details)
 if not details.get('native_error'):raise
 while not (OUT/(key+'_evidence/audit.json')).exists():time.sleep(10)
print('Separate margin event probe terminal and archived',flush=True)
