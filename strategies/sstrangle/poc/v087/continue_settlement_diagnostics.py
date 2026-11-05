"""Run the preregistered settlement probes only after the existing matrix archives."""
import fcntl,json,time,traceback
from pathlib import Path
from campaign import OUT,P,ROOT,run,rows,read,save,digest
from qc_api_check import credentials
lock=(OUT/'settlement_controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
plan=json.loads((P/'settlement_diagnostic_execution_plan.json').read_text());assert digest(P/'strategy_settlement_diagnostic.py')==plan['adapter_sha256']
prior=json.loads((P/'cloud_test_plan.json').read_text())
while True:
 archived=all((OUT/(x['key']+'_evidence/audit.json')).exists() for x in prior['tests'])
 ended='Validation matrix terminal' in (OUT/'cloud_validation.log').read_text()
 if archived and ended:break
 if 'Traceback (most recent call last)' in (OUT/'cloud_validation.log').read_text():raise RuntimeError('Prior validation controller needs diagnosis')
 time.sleep(25)
save(OUT/'settlement_diagnostic_execution_plan.json',plan)
for item in plan['tests']:
 key=item['key']
 if (OUT/(key+'_failure.json')).exists():continue
 try:run(key,item['kind'],overrides=item['overrides'],source_path=P/'strategy_settlement_diagnostic.py')
 except Exception as e:
  row=next((x for x in rows() if x['name'].endswith(key.upper())),None)
  details={'key':key,'error':str(e),'queue_row':row,'traceback':traceback.format_exc()}
  if row and row['backtest_id']:
   u,t=credentials(ROOT/'data/S001.duckdb');b=read(u,t,'/backtests/read',dict(projectId=row['project_id'],backtestId=row['backtest_id']));save(OUT/(key+'_failed_terminal.json'),b);details['native_error']=b.get('backtest',{}).get('error')
  save(OUT/(key+'_failure.json'),details)
  if not details.get('native_error'):raise
  # Failure archiver owns readback and raw pages; wait before another submission.
  while not (OUT/(key+'_evidence/audit.json')).exists():time.sleep(10)
print('Settlement probes terminal and archived',flush=True)
