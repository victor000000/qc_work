"""Complete the frozen local-to-QC loop; never repeat uncertain native writes."""
import json,os,subprocess,sys,time
from pathlib import Path
from campaign import ROOT,OUT,P,rows,request,credentials
sys.path.insert(0,str(ROOT/'strategies/sstrangle/poc/v065'))
from terminal_state import terminal_ready
u,t=credentials(ROOT/'data/S001.duckdb');env=dict(os.environ,PYTHONPATH=str(ROOT/'scripts'))
trials=[('condor_alpha_smoke_readable','condor',True,False),('condor_control_full','condor',False,True),('condor_alpha_full','condor',True,True),('strangle_alpha_full','strangle',True,True),('put_alpha_full','put',True,True)]
for key,kind,alpha,full in trials:
 # Completed evidence is immutable; its cloud project may already be reused.
 proof=OUT/(key+'_consistency.json')
 if proof.exists():
  saved=json.loads(proof.read_text())
  assert saved['max_common_pnl_difference']<1e-5 and not saved['common_contract_mismatches'] and saved['funding_differences_explained']
  assert terminal_ready(json.loads((OUT/(key+'_terminal.json')).read_text())['backtest'])
  assert (OUT/(key+'_cloud_source_files.json')).exists()
  print(key,'already archived and verified; retaining original cloud source snapshot',flush=True)
  continue
 existing=next((r for r in rows() if r['name'].endswith('_'+key.upper())),None)
 if existing is None:
  cmd=[sys.executable,str(P/'campaign.py'),'queue','--key',key,'--kind',kind]
  if alpha:cmd+=['--alpha']
  if full:cmd+=['--full']
  subprocess.run(cmd,check=True)
 terminal=OUT/(key+'_terminal.json');errors=0
 while not terminal.exists():
  row=next(r for r in rows() if r['name'].endswith('_'+key.upper()))
  if row['status']=='failed':raise RuntimeError(str({k:v for k,v in row.items() if k!='result_json'}))
  if row['backtest_id']:
   try:
    r=request(u,t,'/backtests/read',dict(projectId=row['project_id'],backtestId=row['backtest_id']));b=r['backtest'];errors=0
    (OUT/(key+'_progress.json')).write_text(json.dumps({k:b.get(k) for k in ['completed','progress','status','error','runtimeStatistics']},indent=2));print(key,b['status'],b['progress'],flush=True)
    if terminal_ready(b):terminal.write_text(json.dumps(r,indent=2));break
    if b.get('completed'):(OUT/(key+'_pending_statistics.json')).write_text(json.dumps(r,indent=2))
   except Exception as e:
    errors+=1;print('read error',str(e)[:200],flush=True)
    if errors>=8:raise
  time.sleep(45)
 b=json.loads(terminal.read_text())['backtest'];assert terminal_ready(b) and not b.get('error'),b.get('error')
 row=next(r for r in rows() if r['name'].endswith('_'+key.upper()));folder=OUT/(key+'_evidence')
 if not (folder/'audit.json').exists():
  cmd=[sys.executable,str(ROOT/'strategies/sstrangle/poc/v06/collect_three.py'),'--name',row['name'],'--output',str(folder),'--raw-pages','--terminal-json',str(terminal)]
  if full:cmd+=['--require-annual','--expected-years','2022','2023','2024','2025','2026']
  with (OUT/(key+'_export.log')).open('w') as stream:subprocess.run(cmd,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
  subprocess.run([sys.executable,str(ROOT/'strategies/sstrangle/poc/v06/enrich_evidence.py'),str(folder)],env=env,check=True)
 subprocess.run([sys.executable,str(P/'verify_native.py'),key],check=True)
 print(key,'AUDIT AND CONSISTENCY REVIEW COMPLETE',flush=True)
print('ALL FINAL QC RUNS VERIFIED',flush=True)
