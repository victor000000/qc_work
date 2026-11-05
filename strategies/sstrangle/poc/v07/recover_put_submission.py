"""Recover one frozen pre-launch upload after the task-owned worker stops.
No automatic replay of compile/backtest creation; uncertain launch is looked up.
"""
import hashlib,json,time
from datetime import datetime,timezone
from pathlib import Path
from campaign import ROOT,OUT,PREFIX,rows,storage,credentials,request
assert not Path('/proc/1263025').exists(),'Wait for the owned worker to finish shutdown'
name=PREFIX+'PUT_ALPHA_FULL';row=next(r for r in rows() if r['name']==name);key='put_alpha_full';project=row['project_id'] or 31338454
u,t=credentials(ROOT/'data/S001.duckdb')
def read(path,body):
 for i in range(6):
  try:return request(u,t,path,body)
  except RuntimeError:
   if i==5:raise
   time.sleep(min(2**i,15))
def save(name,value):(OUT/name).write_text(json.dumps(value,indent=2))
def matching():
 r=read('/backtests/list',{'projectId':project});save('put_recovery_backtests_after.json',r)
 return [b for b in r.get('backtests',[]) if b.get('name')==name]
def attach(b):
 bid=b['backtestId']
 with storage.connect(str(ROOT/'data/SSTRANGLE.duckdb')) as db:
  db.execute("UPDATE backtest_queue SET status='running',project_id=?,backtest_id=?,error_message=NULL WHERE name=?",(project,bid,name));db.commit()
 save('put_recovery_receipt.json',dict(project_id=project,backtest_id=bid,frozen_manifest_sha256=hashlib.sha256((OUT/(key+'_manifest.json')).read_bytes()).hexdigest(),duplicate_runs_created=False,worker_stopped=True,transport='existing authenticated Python QC API',utc=datetime.now(timezone.utc).isoformat()))
 print('Attached existing native execution',bid,flush=True)
existing=matching();assert len(existing)<=1
if existing:attach(existing[0]);raise SystemExit(0)
assert not row['backtest_id'],'Local identity exists but native lookup failed; investigate'
nodes=read('/projects/nodes/read',{'projectId':project});save('put_recovery_nodes_after.json',nodes);assert all(not n['busy'] for n in nodes['nodes']['backtest'])
manifest=json.loads((OUT/(key+'_manifest.json')).read_text());files={'main.py':(OUT/(key+'.py')).read_text(),**json.loads((OUT/(key+'_extra_files.json')).read_text())}
for n,digest in {'main.py':manifest['source_sha256'],**manifest['extra_files_sha256']}.items():assert hashlib.sha256(files[n].encode()).hexdigest()==digest
remote={f['name']:f['content'] for f in read('/files/read',{'projectId':project})['files']}
for n,content in files.items():
 if remote.get(n)==content:continue
 # Exact-content updates are checked after any uncertain transport response.
 for attempt in range(3):
  try:request(u,t,'/files/update' if n in remote else '/files/create',{'projectId':project,'name':n,'content':content})
  except RuntimeError:pass
  remote={f['name']:f['content'] for f in read('/files/read',{'projectId':project})['files']}
  if remote.get(n)==content:break
  if attempt==2:raise RuntimeError('Cannot establish exact cloud file: '+n)
 print('Verified upload',n,flush=True)
remote={f['name']:f['content'] for f in read('/files/read',{'projectId':project})['files']};assert all(remote.get(n)==v for n,v in files.items())
compile_file=OUT/'put_recovery_compile_create.json'
if compile_file.exists():compiled=json.loads(compile_file.read_text())
else:
 compiled=request(u,t,'/compile/create',{'projectId':project});save(compile_file.name,compiled)
cid=compiled['compileId']
for _ in range(60):
 c=read('/compile/read',{'projectId':project,'compileId':cid});save('put_recovery_compile_final.json',c)
 if c['state']=='BuildSuccess':break
 if c['state']=='BuildError':raise RuntimeError('Compile failed: '+str(c))
 time.sleep(3)
else:raise RuntimeError('Compile not ready; do not launch')
existing=matching();assert len(existing)<=1
if existing:attach(existing[0]);raise SystemExit(0)
intent=OUT/'put_recovery_create_intent.json'
assert not intent.exists(),'Prior create is uncertain; inspect native list instead of replaying'
save(intent.name,dict(projectId=project,compileId=cid,backtestName=name,utc=datetime.now(timezone.utc).isoformat()))
try:
 result=request(u,t,'/backtests/create',{'projectId':project,'compileId':cid,'backtestName':name});save('put_recovery_create_response.json',result);attach(result['backtest'])
except RuntimeError:
 existing=matching()
 if len(existing)==1:attach(existing[0])
 else:raise
