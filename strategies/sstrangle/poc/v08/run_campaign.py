"""Serial native campaign. Completed runs are never resubmitted."""
import json,os,subprocess,sys,time
from campaign import ROOT,OUT,P,prepare,launch,rows,read,credentials,save
sys.path.insert(0,str(ROOT/'strategies/sstrangle/poc/v065'));from terminal_state import terminal_ready
u,t=credentials(ROOT/'data/S001.duckdb');env=dict(os.environ,PYTHONPATH=str(ROOT/'scripts'))
trials=[('condor_smoke','condor',False,True),('put_smoke','put',False,True),('condor_control','condor',True,False),('condor_final','condor',False,False),('put_control','put',True,False),('put_final','put',False,False)]
for key,kind,control,smoke in trials:
 if (OUT/(key+'_consistency.json')).exists():print(key,'already verified',flush=True);continue
 manifest=prepare(key,kind,control,smoke)
 identity=OUT/(key+'_launch_identity.json')
 if not identity.exists():launch(key)
 ids=json.loads(identity.read_text());body=dict(projectId=ids['project_id'],backtestId=ids['backtest_id']);terminal=OUT/(key+'_terminal.json')
 while not terminal.exists():
  response=read(u,t,'/backtests/read',body);b=response['backtest'];print(key,b['status'],b['progress'],flush=True)
  if terminal_ready(b):save(terminal.name,response);break
  time.sleep(45)
 b=json.loads(terminal.read_text())['backtest'];assert not b.get('error'),b.get('error')
 # Snapshot source identity again after execution, before reusing the project.
 cloud=read(u,t,'/files/read',{'projectId':ids['project_id']});save(key+'_cloud_source_files.json',cloud)
 folder=OUT/(key+'_evidence');folder.mkdir(exist_ok=True)
 # Bypass the short-timeout CLI's log fetch; only read APIs are retried.
 if not (folder/'cloud.log').exists():
  lines=[];pages=folder/'log_pages';pages.mkdir(exist_ok=True)
  for start in range(0,100000,200):
   path=pages/(str(start).zfill(8)+'.json');r=json.loads(path.read_text()) if path.exists() else read(u,t,'/backtests/read/log',dict(body,start=start,end=start+200,query=''))
   if not path.exists():path.write_text(json.dumps(r))
   chunk=r.get('logs',r.get('log',[]));lines.extend(chunk)
   if len(chunk)<200:break
  (folder/'cloud.log').write_text('\n'.join(lines)+'\n')
 if not (folder/'audit.json').exists():
  cmd=[sys.executable,str(ROOT/'strategies/sstrangle/poc/v06/collect_three.py'),'--name',manifest['name'],'--output',str(folder),'--raw-pages','--terminal-json',str(terminal)]
  if not smoke:cmd+=['--require-annual','--expected-years','2022','2023','2024','2025','2026']
  with (OUT/(key+'_export.log')).open('w') as stream:subprocess.run(cmd,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
  subprocess.run([sys.executable,str(ROOT/'strategies/sstrangle/poc/v06/enrich_evidence.py'),str(folder)],env=env,check=True)
 subprocess.run([sys.executable,str(P/'verify_native.py'),key],check=True)
 print(key,'VERIFIED',flush=True)
print('ALL DRAFT08 NATIVE RUNS VERIFIED',flush=True)
