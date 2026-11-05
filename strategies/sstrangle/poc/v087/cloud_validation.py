"""Run preregistered diagnostics after the primary pipeline; preserve failures."""
import json,time,traceback
from pathlib import Path
from campaign import OUT,run,rows,read,save,ROOT
from qc_api_check import credentials
P=Path(__file__).parent
while not all((OUT/(k+'_verify_evidence/audit.json')).exists() for k in ['c0','c1','p1']):
 if (OUT/'pipeline.log').exists() and 'Traceback (most recent call last)' in (OUT/'pipeline.log').read_text():raise RuntimeError('Primary controller needs diagnosis before validation continues')
 time.sleep(30)
plan=json.loads((P/'cloud_test_plan.json').read_text());save(OUT/'cloud_test_plan.json',plan)
for item in plan['tests']:
 failure=OUT/(item['key']+'_failure.json')
 if failure.exists():continue
 try:run(item['key'],item['kind'],item['alpha'],overrides=item['overrides'])
 except Exception as e:
  details={'key':item['key'],'error':str(e),'traceback':traceback.format_exc(),'question':item['question']}
  row=next((r for r in rows() if r['name'].endswith(item['key'].upper())),None)
  details['queue_row']=row
  if row and row['backtest_id']:
   u,t=credentials(ROOT/'data/S001.duckdb');b=read(u,t,'/backtests/read',dict(projectId=row['project_id'],backtestId=row['backtest_id']));save(OUT/(item['key']+'_failed_terminal.json'),b)
   details['native_error']=b.get('backtest',{}).get('error')
  save(failure,details)
  # A transport/unknown state is not a terminal test failure: stop submission.
  if not details.get('native_error') and (not row or row['status']!='failed'):raise
  print('Preserved terminal failure',item['key'],flush=True)
print('Validation matrix terminal; inspect evidence and design next diagnostics',flush=True)
