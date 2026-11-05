"""Version, submit, and inspect explicitly named Draft 0.6 QC experiments."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'scripts'))
import qc_storage as storage
from qc_api_check import credentials
from transport import request
OUT=ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023'
BINARY=ROOT/'target/release/qc-backtest-server'
def rows():
 with storage.connect(f'file:{ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as c:
  c.row_factory=storage.Row
  return [dict(r) for r in c.execute("SELECT name,status,project_id,backtest_id,error_message,runtime_seconds,result_json FROM backtest_queue WHERE name LIKE 'SSTRANGLE_OO06_20261023_%' ORDER BY id")]
def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['queue','status','terminal']);p.add_argument('--key');p.add_argument('--kind',choices=['condor','strangle','put'],default='condor');p.add_argument('--full',action='store_true');p.add_argument('--capital',type=float);p.add_argument('--start',nargs=3,type=int);p.add_argument('--end',nargs=3,type=int);p.add_argument('--priority',type=int,default=5);p.add_argument('--wing-policy',choices=['original','paired_exact']);a=p.parse_args()
 if a.action=='queue':
  cfg=dict(start=[2022,5,16] if a.full else [2024,1,2],last_entry=[2026,7,13] if a.full else [2024,1,12],strategy_kind=a.kind,start_capital=a.capital or (100000 if a.kind=='condor' else 2000000),put_target={'condor':.20,'strangle':.16,'put':.25}[a.kind],call_target=.08 if a.kind=='condor' else (.16 if a.kind=='strangle' else 0),fill_convention='oo_midpoint_package',capital_fraction=1.,verbose=False,wing_policy=a.wing_policy or ('paired_exact' if a.kind=='condor' else 'original'))
  if a.start:cfg['start']=a.start
  if a.end:cfg['last_entry']=a.end
  s=(ROOT/'strategies/sstrangle/poc/v06/three_demos.py').read_text().replace('CONFIG = {}','CONFIG = '+repr(cfg))
  path=OUT/(a.key.lower()+'.py');assert not path.exists(), 'Immutable trial already exists'
  path.write_text(s);name='SSTRANGLE_OO06_20261023_'+a.key.upper()
  manifest=dict(name=name,config=cfg,source_sha256=hashlib.sha256(s.encode()).hexdigest(),role='funded native QC '+('full source interval' if a.full else 'accounting smoke'),source_scope='Audio condor reproduction' if a.kind=='condor' else 'User-authorized Tom-inspired 0DTE adaptation; not Tom 45-DTE source reproduction')
  (OUT/(a.key.lower()+'_manifest.json')).write_text(json.dumps(manifest,indent=2))
  subprocess.run([str(BINARY),'queue','--strategy','sstrangle','--name',name,'--code-file',str(path),'--batch','oo06_20261023','--priority',str(a.priority),'--description',manifest['source_scope']],check=True)
 elif a.action=='status':
  r=rows()
  for x in r:
   result=json.loads(x.pop('result_json') or '{}');x['runtime']=result.get('runtimeStatistics',{})
  (OUT/'queue_snapshot.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
 else:
  r=next(r for r in rows() if r['name'].endswith('_'+a.key.upper()))
  assert r['backtest_id']
  path=OUT/(a.key.lower()+'_terminal.json')
  if path.exists(): result=json.loads(path.read_text())
  else:
   u,t=credentials(ROOT/'data/S001.duckdb');result=request(u,t,'/backtests/read',dict(projectId=r['project_id'],backtestId=r['backtest_id']))
   if result['backtest']['completed']:
    path.write_text(json.dumps(result,indent=2))
  b=result['backtest'];print(json.dumps({k:b.get(k) for k in ['completed','status','progress','error','stacktrace','statistics','runtimeStatistics']},indent=2))
if __name__=='__main__':main()
