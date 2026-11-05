"""Resumable queue-only v0.8.5 campaign; the existing worker owns native creates."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[4]; P=Path(__file__).parent
OUT=ROOT/'strategies/sstrangle/results/qc_poc_20261026_v085'
sys.path.insert(0,str(ROOT/'scripts'))
import qc_storage as storage
from qc_api_check import credentials
sys.path.insert(0,str(ROOT/'strategies/sstrangle/poc/v06'))
from transport import request
sys.path.insert(0,str(ROOT/'strategies/sstrangle/poc/v065'))
from terminal_state import terminal_ready
ACTIVE_KINDS=('condor',)  # See immutable scope_amendment.json: rejected add-on baseline.
PREFIX='SSTRANGLE_OO085_20261026_'; BINARY=ROOT/'target/release/qc-backtest-server'
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,obj):
 path=Path(path);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,indent=2)+'\n');tmp.replace(path)
def rows():
 with storage.connect(f'file:{ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as c:
  c.row_factory=storage.Row
  return [dict(r) for r in c.execute('SELECT name,status,project_id,backtest_id,error_message FROM backtest_queue WHERE name LIKE ?',(PREFIX+'%',))]
def read(u,t,path,body):
 for i in range(6):
  try:return request(u,t,path,body)
  except RuntimeError:
   if i==5:raise
   time.sleep(min(2**i,15))
def prepare(key,kind,alpha=False,smoke=False):
 cfg=dict(start=[2024,1,2] if smoke else [2022,5,16],last_entry=[2024,1,12] if smoke else [2026,10,22],strategy_kind=kind,start_capital=100000,put_target=.2,call_target=.08 if kind=='condor' else 0.,fill_convention='oo_midpoint_package',capital_fraction=1.,verbose=False,wing_policy='paired_exact',delta_tolerance=.02,alpha_enabled=False)
 extras={}
 if alpha:
  rule=json.loads((OUT/'frozen_rules.json').read_text())[kind]
  cfg.update(alpha_enabled=rule['feature']!='none',alpha_feature=rule['feature'],alpha_threshold=rule['threshold'],alpha_side=rule['side'])
  if cfg['alpha_enabled']:
   prices=pd.read_parquet(ROOT/'strategies/sstrangle/results/qc_sizing_poc_20261024/provider/us_prices_full/data.parquet')
   f=prices[prices.symbol==rule['feature'].split('_')[0].upper()].sort_values('date')
   raw=[[str(r.date),float(r.high),float(r.low),float(r.close),int(r.volume)] for r in f.itertuples()]
   for i,start in enumerate(range(0,len(raw),250)):extras[f'daily_input_{i}.py']='ROWS = [\n'+''.join('    '+repr(r)+',\n' for r in raw[start:start+250])+']\n'
   n=len(extras);extras['feature_inputs.py']=''.join(f'from daily_input_{i} import ROWS as ROWS_{i}\n' for i in range(n))+'DAILY_ROWS = '+' + '.join(f'ROWS_{i}' for i in range(n))+'\n'
 source=(P/'strategy.py').read_text().replace('CONFIG = {}','CONFIG = '+repr(cfg))
 assert all(len(s.encode())<32000 for s in [source,*extras.values()])
 m=dict(name=PREFIX+key.upper(),config=cfg,alpha=alpha,smoke=smoke,source_sha256=hashlib.sha256(source.encode()).hexdigest(),extra_files_sha256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in extras.items()},contract_sha256=digest(OUT/'experiment_contract.json'))
 if alpha:
  m['rules_sha256']=digest(OUT/'frozen_rules.json');m['scope_amendment_sha256']=digest(OUT/'scope_amendment.json')
 for name,content in [(key+'.py',source),(key+'_extra_files.json',json.dumps(extras,indent=2)),(key+'_manifest.json',json.dumps(m,indent=2))]:
  path=OUT/name
  assert not path.exists() or path.read_text()==content,'Immutable job changed: '+name
  path.write_text(content)
 if not any(r['name']==m['name'] for r in rows()):
  subprocess.run([str(BINARY),'queue','--strategy','sstrangle','--name',m['name'],'--code-file',str(OUT/(key+'.py')),'--extra-files',str(OUT/(key+'_extra_files.json')),'--batch','oo085_20261026','--priority','5','--description','Draft0.8.5 '+('frozen funded verification' if alpha else 'fresh native baseline')],check=True)
 return m

def run(key,kind,alpha=False,smoke=False):
 if (OUT/(key+'_evidence/audit.json')).exists():return
 m=prepare(key,kind,alpha,smoke);u,t=credentials(ROOT/'data/S001.duckdb');terminal=OUT/(key+'_terminal.json')
 while not terminal.exists():
  row=next(r for r in rows() if r['name']==m['name']);print(key,row,flush=True)
  if row['backtest_id']:
   b=read(u,t,'/backtests/read',dict(projectId=row['project_id'],backtestId=row['backtest_id']))
   save(OUT/(key+'_progress.json'),b)
   if b['backtest'].get('error'):raise RuntimeError(b['backtest']['error'])
   if terminal_ready(b['backtest']):save(terminal,b);break
  elif row['status']=='failed':raise RuntimeError('Queue failed; investigate, do not resubmit: '+str(row))
  time.sleep(40)
 row=next(r for r in rows() if r['name']==m['name']);ids=dict(projectId=row['project_id'],backtestId=row['backtest_id'])
 cloud=read(u,t,'/files/read',{'projectId':row['project_id']});remote={f['name']:f['content'] for f in cloud['files']}
 for name,h in {'main.py':m['source_sha256'],**m['extra_files_sha256']}.items():assert hashlib.sha256(remote[name].encode()).hexdigest()==h
 save(OUT/(key+'_cloud_source_files.json'),cloud)
 folder=OUT/(key+'_evidence');folder.mkdir(exist_ok=True)
 if not (folder/'cloud.log').exists():
  pages=folder/'log_pages';pages.mkdir(exist_ok=True);lines=[]
  for start in range(0,100000,200):
   path=pages/(str(start).zfill(8)+'.json');r=json.loads(path.read_text()) if path.exists() else read(u,t,'/backtests/read/log',dict(ids,start=start,end=start+200,query=''))
   if not path.exists():save(path,r)
   chunk=r.get('logs',r.get('log',[]));lines.extend(chunk)
   if len(chunk)<200:break
  (folder/'cloud.log').write_text('\n'.join(lines)+'\n')
 cmd=[sys.executable,str(P/'collect.py'),'--name',m['name'],'--output',str(folder),'--raw-pages','--terminal-json',str(terminal)]
 if not smoke:cmd+=['--require-annual','--expected-years','2022','2023','2024','2025','2026']
 with (OUT/(key+'_export.log')).open('w') as log:
  result=subprocess.run(cmd,env=dict(os.environ,PYTHONPATH=str(ROOT/'scripts')),stdout=log,stderr=subprocess.STDOUT)
 if result.returncode:
  audit=folder/'audit.json'
  if not audit.exists() or not json.loads(audit.read_text()).get('native_cloud_terminal_success'):raise RuntimeError('Collection failed; see '+str(OUT/(key+'_export.log')))
  print('Annual frequency failure retained',key,flush=True)
 print('ARCHIVED',key,flush=True)
if __name__=='__main__':
 stage=sys.argv[1]
 if stage=='baseline':
  run('put_spread_smoke','put_spread',smoke=True)
  for kind in ['condor','put_spread']:run(kind+'_baseline',kind)
 elif stage=='final':
  for kind in ACTIVE_KINDS:run(kind+'_final',kind,alpha=True)
 else:raise ValueError(stage)
