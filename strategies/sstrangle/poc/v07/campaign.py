"""Immutable Draft0.7 native verification experiments."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];P=Path(__file__).parent;OUT=ROOT/'strategies/sstrangle/results/qc_final_poc_20261024'
sys.path.insert(0,str(ROOT/'scripts'))
import qc_storage as storage
from qc_api_check import credentials
sys.path.insert(0,str(ROOT/'strategies/sstrangle/poc/v06'))
from transport import request
BINARY=ROOT/'target/release/qc-backtest-server';PREFIX='SSTRANGLE_OO07_20261024_'
def rows():
 with storage.connect(f'file:{ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as c:
  c.row_factory=storage.Row
  return [dict(r) for r in c.execute('SELECT name,status,project_id,backtest_id,error_message,result_json FROM backtest_queue WHERE name LIKE ? ORDER BY id',(PREFIX+'%',))]
def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['queue','status']);p.add_argument('--key');p.add_argument('--kind',choices=['condor','strangle','put'],default='condor');p.add_argument('--alpha',action='store_true');p.add_argument('--full',action='store_true');a=p.parse_args()
 if a.action=='status':
  for r in rows():r.pop('result_json');print(r)
  return
 rule=json.loads((OUT/'frozen_rules.json').read_text())[a.kind]
 cfg=dict(start=[2022,5,16] if a.full else [2024,1,2],last_entry=[2026,7,13] if a.full else [2024,1,12],strategy_kind=a.kind,start_capital=rule['capital'],put_target={'condor':.20,'strangle':.16,'put':.25}[a.kind],call_target=.08 if a.kind=='condor' else (.16 if a.kind=='strangle' else 0),fill_convention='oo_midpoint_package',capital_fraction=1.,verbose=False,wing_policy='paired_exact' if a.kind=='condor' else 'original',delta_tolerance=.02,alpha_enabled=a.alpha)
 extras={}
 if a.alpha:
  prices=pd.read_parquet(ROOT/'strategies/sstrangle/results/qc_delta_poc_20261024/provider/us_prices/data.parquet');symbol=rule['feature'].split('_')[0].upper();f=prices[prices.symbol==symbol].sort_values('date')
  raw=[[str(r.date),float(r.high),float(r.low),float(r.close),int(r.volume)] for r in f.itertuples()]
  for i,start in enumerate(range(0,len(raw),300)):
   extras[f'daily_input_{i}.py']='# Pinned raw '+symbol+' daily rows: date, high, low, close, volume. No trade labels.\nROWS = [\n'+''.join('    '+repr(r)+',\n' for r in raw[start:start+300])+']\n'
  extras['feature_inputs.py']='# Readable pinned provider input data; evaluated only for completed prior days.\n'+''.join(f'from daily_input_{i} import ROWS as ROWS_{i}\n' for i in range(len(extras)))+'DAILY_ROWS = '+ ' + '.join(f'ROWS_{i}' for i in range(len(extras)))+'\n'
  cfg.update(alpha_feature=rule['feature'],alpha_threshold=rule['threshold'],alpha_side=rule['side'])

 source=(P/'three_demos.py').read_text().replace('CONFIG = {}','CONFIG = '+repr(cfg));path=OUT/(a.key+'.py');assert not path.exists();path.write_text(source)
 manifest=dict(name=PREFIX+a.key.upper(),config=cfg,extra_files_sha256={n:hashlib.sha256(v.encode()).hexdigest() for n,v in extras.items()},source_sha256=hashlib.sha256(source.encode()).hexdigest(),frozen_rules_sha256=hashlib.sha256((OUT/'frozen_rules.json').read_bytes()).hexdigest(),role='filtered funded final verification' if a.alpha else 'unfiltered baseline repeatability control')
 (OUT/(a.key+'_manifest.json')).write_text(json.dumps(manifest,indent=2))
 (OUT/(a.key+'_extra_files.json')).write_text(json.dumps(extras,indent=2))
 subprocess.run([str(BINARY),'queue','--strategy','sstrangle','--name',manifest['name'],'--code-file',str(path),'--batch','oo07_20261024','--priority','5','--description',manifest['role']]+(['--extra-files',str(OUT/(a.key+'_extra_files.json'))] if extras else []),check=True)
 print('source bytes',len(source.encode()),flush=True)
if __name__=='__main__':main()
