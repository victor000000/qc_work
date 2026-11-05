"""Verify native evidence, delta gates, pinned exports and separated feature packs."""
import ast,hashlib,json,subprocess,sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'strategies/sstrangle/results/qc_delta_poc_20261024';checks=[]
def check(value,message):
 assert value,message
 checks.append(message)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for key,tol in [('condor_smoke_t02',.02),('condor_full_t02',.02),('condor_full_t05',.05)]:
 p=OUT/(key+'_evidence');a=json.loads((p/'audit.json').read_text());b=json.loads((p/'backtest.json').read_text())['backtest'];manifest=json.loads((OUT/(key+'_manifest.json')).read_text());ep=pd.read_parquet(p/'episodes.parquet')
 check(b['completed'] and not b.get('error') and a['native_cloud_terminal_success'],key+' native terminal')
 check(sha(p/'submitted_main.py')==sha(OUT/(key+'.py'))==manifest['source_sha256']==a['source_sha256'],key+' frozen source identity')
 check(abs(a['native_net_pnl']-ep.pnl.sum())<.05 and a['residual_positions']==0,key+' native cash and residuals')
 check(((ep.put_delta+.2).abs()<=tol+1e-8).all() and ((ep.call_delta-.08).abs()<=tol+1e-8).all(),key+' actual filled deltas')
 if 'full' in key:check(ep.groupby('year').size().reindex(range(2022,2027),fill_value=0).ge(360).all() and a['annual_pass'],key+' every year>=360')
 for filename,digest in json.loads((p/'manifest.json').read_text())['files'].items():check(sha(p/filename)==digest,key+' '+filename)
 for filename,digest in json.loads((p/'raw_order_pages_manifest.json').read_text())['files'].items():check(sha(p/'raw_order_pages'/filename)==digest,key+' raw '+filename)
 rt=b['runtimeStatistics'];counts={}
 for i in range(1,int(rt['counts_chunks'])+1):counts.update(json.loads(rt['counts_'+str(i).zfill(2)]))
 check(counts.get('skip_delta_tolerance',0)>0,key+' native tolerance rejection counter')
for path in (OUT/'provider').glob('*/manifest.json'):
 m=json.loads(path.read_text());check(sha(path.parent/'data.parquet')==m['sha256'],path.parent.name+' pinned export checksum')
local=json.loads((OUT/'local/summary.json').read_text());reg=json.loads((OUT/'local/feature_registry.json').read_text())
check(len(reg)==211 and sum(v['screen_eligible'] for v in reg.values())==144,'211 fields,144 screened candidates')
for key,item in local['datasets'].items():
 f=pd.read_parquet(OUT/'local'/(key+'_features.parquet'));l=pd.read_parquet(OUT/'local'/(key+'_labels.parquet'))
 check(not set(['pnl','settlement_spot','entry_credit','opening_fees','expiry_cash_attribution']).intersection(f.columns),key+' labels excluded')
 check(f.episode.is_unique and set(f.episode)==set(l.episode),key+' labels identity')
 check((f.available_at<f.decision_at).all() and (f.decision_at-f.available_at).le(pd.Timedelta(days=7)).all(),key+' provider temporal join')
 trials=pd.read_csv(OUT/'local'/(key+'_all_trials.csv'));check(len(trials)==288,key+' complete search ledger')
 selected=trials[trials.train_eligible].sort_values(['train_mean','feature','side'],ascending=[False,True,True]).iloc[0]
 check(selected.feature==item['selected_by_training_only']['feature'] and selected.side==item['selected_by_training_only']['side'],key+' selection uses training only')
 check(not any(reg[x]['family']=='iv_unverified' for x in trials.feature),key+' unknown-clock IV excluded')
report=ROOT/'strategies/sstrangle/research/design_20261024_v065'
for filename,digest in json.loads((report/'manifest.json').read_text())['files'].items():check(sha(report/filename)==digest,'report '+filename)
result=subprocess.run([sys.executable,'-m','pytest','strategies/sstrangle/tests','strategies/sstrangle/poc/test_demo_audit.py','strategies/sstrangle/poc/v06','strategies/sstrangle/poc/v065','-q'],cwd=ROOT,capture_output=True,text=True)
(OUT/'tests.log').write_text(result.stdout+result.stderr);check(result.returncode==0,'regression suite')
(OUT/'final_verification.json').write_text(json.dumps({'status':'passed','checks':len(checks),'invariants':checks,'tests':result.stdout.strip()},indent=2));print(len(checks),'checks passed')
