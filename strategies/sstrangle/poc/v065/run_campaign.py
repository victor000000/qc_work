"""Serialize immutable native trials; stop on any failure, never retry cloud writes."""
import json,subprocess,sys,time,os
from pathlib import Path
from campaign import ROOT,OUT,rows,request,credentials
from terminal_state import terminal_ready
u,t=credentials(ROOT/'data/S001.duckdb')
env=dict(os.environ,PYTHONPATH=str(ROOT/'scripts'))
for key,tol,full in [('condor_smoke_t02',.02,False),('condor_full_t02',.02,True),('condor_full_t05',.05,True)]:
 r=next((r for r in rows() if r['name'].endswith('_'+key.upper())),None)
 if r is None:
  cmd=[sys.executable,str(Path(__file__).with_name('campaign.py')),'queue','--key',key,'--delta-tolerance',str(tol)]
  if full:cmd+=['--full']
  subprocess.run(cmd,check=True)
 path=OUT/(key+'_terminal.json');last=None;errors=0
 while not path.exists():
  r=next(r for r in rows() if r['name'].endswith('_'+key.upper()))
  if r['status']=='failed':raise RuntimeError(str({k:v for k,v in r.items() if k!='result_json'}))
  if r['backtest_id']:
   try:
    result=request(u,t,'/backtests/read',dict(projectId=r['project_id'],backtestId=r['backtest_id']))
    b=result['backtest'];snapshot={k:b.get(k) for k in ['completed','status','progress','error','runtimeStatistics']}
    (OUT/(key+'_progress.json')).write_text(json.dumps(snapshot,indent=2))
    print(key,b.get('status'),b.get('progress'),flush=True)
    if terminal_ready(b):path.write_text(json.dumps(result,indent=2));break
    if b['completed']:(OUT/(key+'_pending_final_statistics.json')).write_text(json.dumps(result,indent=2))
   except Exception as e:
    errors+=1;print(type(e).__name__,str(e)[:250],flush=True)
    if errors>=8:raise
  time.sleep(45)
 b=json.loads(path.read_text())['backtest'];assert b['completed'] and not b.get('error'),b.get('error')
 evidence=OUT/(key+'_evidence')
 cmd=[sys.executable,str(ROOT/'strategies/sstrangle/poc/v06/collect_three.py'),'--name',r['name'],'--output',str(evidence),'--raw-pages','--terminal-json',str(path)]
 if full:cmd+=['--require-annual','--expected-years','2022','2023','2024','2025','2026']
 with (OUT/(key+'_export.log')).open('w') as f:subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
 subprocess.run([sys.executable,str(ROOT/'strategies/sstrangle/poc/v06/enrich_evidence.py'),str(evidence)],env=env,check=True)
 import pandas as pd
 ep=pd.read_parquet(evidence/'episodes.parquet')
 assert ((ep.put_delta+.20).abs()<=tol+1e-8).all() and ((ep.call_delta-.08).abs()<=tol+1e-8).all()
 print(key,'native audit and delta gate PASS',len(ep),flush=True)
print('CAMPAIGN COMPLETE',flush=True)
