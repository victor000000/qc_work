"""Immutable native jobs, sent once through authenticated QC transport."""
import json,hashlib,sys,subprocess,time
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];P=Path(__file__).parent;OUT=ROOT/'strategies/sstrangle/results/qc_sizing_poc_20261024';PREFIX='SSTRANGLE_OO08_20261024_'
sys.path.insert(0,str(ROOT/'scripts'));import qc_storage as storage
from qc_api_check import credentials
sys.path.insert(0,str(ROOT/'strategies/sstrangle/poc/v06'));from transport import request
BINARY=ROOT/'target/release/qc-backtest-server';PROJECT=31338454

def rows():
 with storage.connect(f'file:{ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as db:
  db.row_factory=storage.Row;return [dict(r) for r in db.execute('SELECT name,status,project_id,backtest_id,error_message,result_json FROM backtest_queue WHERE name LIKE ?',(PREFIX+'%',))]
def read(u,t,path,body):
 for i in range(6):
  try:return request(u,t,path,body)
  except RuntimeError:
   if i==5:raise
   time.sleep(min(2**i,15))
def save(name,value):(OUT/name).write_text(json.dumps(value,indent=2))
def prepare(key,kind,control=False,smoke=False):
 rule=json.loads((ROOT/('strategies/sstrangle/results/qc_final_poc_20261024' if control else 'strategies/sstrangle/results/qc_sizing_poc_20261024')/'frozen_rules.json').read_text())[kind]
 cfg=dict(start=[2024,1,2] if smoke else [2022,5,16],last_entry=[2024,1,12] if smoke else [2026,10,22],strategy_kind=kind,start_capital=100000 if kind=='condor' else 2000000,put_target=.2 if kind=='condor' else .25,call_target=.08 if kind=='condor' else 0,fill_convention='oo_midpoint_package',capital_fraction=1.,verbose=False,wing_policy='paired_exact' if kind=='condor' else 'original',delta_tolerance=.02,alpha_enabled=rule['feature']!='none',alpha_feature=rule['feature'],alpha_threshold=rule['threshold'],alpha_side=rule['side'])
 source=(ROOT/'strategies/sstrangle/poc/v07/three_demos.py').read_text().replace('CONFIG = {}','CONFIG = '+repr(cfg))
 source=source.replace('end = self.last_entry + timedelta(days=4)','end = min(self.last_entry + timedelta(days=4),date(2026,10,24))')
 extras={}
 if cfg['alpha_enabled']:
  assert rule['feature'].endswith('_range_pct'),'Implement and test any other selected formula before native submission'
  prices=pd.read_parquet(OUT/'provider/us_prices_full/data.parquet');f=prices[prices.symbol==rule['feature'].split('_')[0].upper()].sort_values('date');raw=[[str(r.date),float(r.high),float(r.low),float(r.close),int(r.volume)] for r in f.itertuples()]
  for i,start in enumerate(range(0,len(raw),250)):extras[f'daily_input_{i}.py']='ROWS = [\n'+''.join('    '+repr(r)+',\n' for r in raw[start:start+250])+']\n'
  n=len(extras);extras['feature_inputs.py']=''.join(f'from daily_input_{i} import ROWS as ROWS_{i}\n' for i in range(n))+'DAILY_ROWS = '+' + '.join(f'ROWS_{i}' for i in range(n))+'\n'
 assert all(len(x.encode())<32000 for x in [source,*extras.values()])
 manifest=dict(name=PREFIX+key.upper(),config=cfg,control=control,smoke=smoke,source_sha256=hashlib.sha256(source.encode()).hexdigest(),extra_files_sha256={n:hashlib.sha256(v.encode()).hexdigest() for n,v in extras.items()},frozen_rules_sha256=hashlib.sha256((OUT/'frozen_rules.json').read_bytes()).hexdigest())
 for filename,content in [(key+'.py',source),(key+'_extra_files.json',json.dumps(extras,indent=2)),(key+'_manifest.json',json.dumps(manifest,indent=2))]:
  path=OUT/filename;assert not path.exists() or path.read_text()==content;path.write_text(content)
 if not any(r['name']==manifest['name'] for r in rows()):subprocess.run([str(BINARY),'queue','--strategy','sstrangle','--name',manifest['name'],'--code-file',str(OUT/(key+'.py')),'--extra-files',str(OUT/(key+'_extra_files.json')),'--batch','oo08_20261024','--priority','5','--description','Draft0.8 frozen rule; full equity ceiling; native verification'],check=True)
 return manifest

def launch(key):
 m=json.loads((OUT/(key+'_manifest.json')).read_text());name=m['name'];u,t=credentials(ROOT/'data/S001.duckdb');project=PROJECT
 # No server may race this manual native launcher.
 sys.path.insert(0,str(ROOT/'strategies/sstrangle/optimization'));from recover_terminal_research import active_owners
 assert not active_owners(),'A queue worker owns submissions; do not race it'
 def matches():return [b for b in read(u,t,'/backtests/list',{'projectId':project})['backtests'] if b['name']==name]
 def attach(b):
  with storage.connect(str(ROOT/'data/SSTRANGLE.duckdb')) as db:db.execute("UPDATE backtest_queue SET status='running',project_id=?,backtest_id=?,error_message=NULL WHERE name=?",(project,b['backtestId'],name));db.commit()
  save(key+'_launch_identity.json',dict(project_id=project,backtest_id=b['backtestId'],name=name));print(key,'native identity',b['backtestId'],flush=True)
 found=matches();assert len(found)<=1
 if found:attach(found[0]);return
 assert not (OUT/(key+'_create_intent.json')).exists(),'Uncertain prior native create; investigate instead of retrying'
 nodes=read(u,t,'/projects/nodes/read',{'projectId':project});assert all(not n['busy'] for n in nodes['nodes']['backtest'])
 files={'main.py':(OUT/(key+'.py')).read_text(),**json.loads((OUT/(key+'_extra_files.json')).read_text())};remote={f['name']:f['content'] for f in read(u,t,'/files/read',{'projectId':project})['files']}
 for n,content in files.items():
  if remote.get(n)==content:continue
  for attempt in range(3):
   try:request(u,t,'/files/update' if n in remote else '/files/create',{'projectId':project,'name':n,'content':content})
   except RuntimeError:pass
   remote={f['name']:f['content'] for f in read(u,t,'/files/read',{'projectId':project})['files']}
   if remote.get(n)==content:break
   if attempt==2:raise RuntimeError('Unable to establish exact input '+n)
 assert all(remote.get(n)==v for n,v in files.items());save(key+'_cloud_source_files.json',{'files':[{'name':n,'content':v} for n,v in remote.items()]})
 cp=OUT/(key+'_compile_create.json')
 if cp.exists():compiled=json.loads(cp.read_text())
 else:compiled=request(u,t,'/compile/create',{'projectId':project});save(cp.name,compiled)
 cid=compiled['compileId']
 for _ in range(60):
  c=read(u,t,'/compile/read',{'projectId':project,'compileId':cid});save(key+'_compile_final.json',c)
  if c['state']=='BuildSuccess':break
  if c['state']=='BuildError':raise RuntimeError(str(c))
  time.sleep(3)
 else:raise RuntimeError('Compilation not ready')
 found=matches();assert not found
 save(key+'_create_intent.json',dict(projectId=project,compileId=cid,backtestName=name))
 try:r=request(u,t,'/backtests/create',{'projectId':project,'compileId':cid,'backtestName':name});save(key+'_create_response.json',r);attach(r['backtest'])
 except RuntimeError:
  found=matches()
  if len(found)==1:attach(found[0])
  else:raise
if __name__=='__main__':
 import argparse
 a=argparse.ArgumentParser();a.add_argument('key');a.add_argument('kind',choices=['condor','put']);a.add_argument('--control',action='store_true');a.add_argument('--smoke',action='store_true');x=a.parse_args();prepare(x.key,x.kind,x.control,x.smoke);launch(x.key)
