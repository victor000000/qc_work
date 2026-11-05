"""Observe existing runs and collect terminal evidence; never submits/cancels work."""
import json,subprocess,sys,time
from datetime import datetime
from pathlib import Path
from campaign import rows,ROOT,OUT
from transport import request
from qc_api_check import credentials
u,t=credentials(ROOT/'data/S001.duckdb')
keys=['condor_full_v1','strangle_full_v2','put_full_v3']
complete=set();last={};next_read={};errors={}
for key in keys:
 p=OUT/(key+'_evidence')/'audit.json'
 if p.exists():
  a=json.loads(p.read_text())
  if a.get('native_cloud_terminal_success') and a.get('annual_pass'):complete.add(key)

while len(complete)<len(keys):
 records=rows()
 for key in keys:
  if key in complete:continue
  row=next((r for r in records if r['name'].endswith('_'+key.upper())),None)
  if row is None:
   if last.get(key)!='waiting':print(key,'waiting for serialized submission',flush=True);last[key]='waiting'
   continue
  state=(row['status'],row['backtest_id'])
  if state!=last.get(key):print(key,state,flush=True);last[key]=state
  if not row['backtest_id']:continue
  now=time.monotonic()
  terminal=OUT/(key+'_terminal.json')
  if not terminal.exists() and now>=next_read.get(key,0):
   try:
    r=request(u,t,'/backtests/read',dict(projectId=row['project_id'],backtestId=row['backtest_id']))
    b=r['backtest'];next_read[key]=now+180
    snapshot={k:b.get(k) for k in ['completed','status','progress','error','runtimeStatistics']}
    snapshot['observed_at']=datetime.now().isoformat()
    (OUT/(key+'_progress.json')).write_text(json.dumps(snapshot,indent=2))
    print(key,'native progress',b.get('progress'),'status',b.get('status'),flush=True)
    if b['completed']:terminal.write_text(json.dumps(r,indent=2))
   except Exception as exc:
    errors[key]=errors.get(key,0)+1;next_read[key]=now+60
    print(key,'read failed',str(exc)[:240],flush=True)
    if errors[key]>8:raise
  if terminal.exists():
   evidence=OUT/(key+'_evidence')
   cmd=[sys.executable,str(Path(__file__).with_name('collect_three.py')),'--name',row['name'],'--output',str(evidence),'--raw-pages','--terminal-json',str(terminal),'--require-annual','--expected-years','2022','2023','2024','2025','2026']
   print(key,'exporting native archive',flush=True)
   with (OUT/(key+'_export.txt')).open('w') as f: result=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
   if result.returncode:
    print(key,'EXPORT/AUDIT FAILED: see saved export log',flush=True);raise SystemExit(result.returncode)
   audit=json.loads((evidence/'audit.json').read_text())
   if audit.get('status')=='cloud_failed':raise RuntimeError(key+' native runtime failed; evidence preserved')
   subprocess.run([sys.executable,str(Path(__file__).with_name('enrich_evidence.py')),str(evidence)],check=True)
   complete.add(key);print(key,'audited',audit['episodes'],'episodes',audit['native_net_pnl'],'net P&L',flush=True)
 if len(complete)<len(keys):time.sleep(30)
print('ALL THREE FULL BASELINES AUDITED',flush=True)
