"""Evidence-backed status and reconciliation, safe while native jobs are pending."""
from pathlib import Path
import json,hashlib,sys
import pandas as pd
from payoff import reconstruct
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'strategies/sstrangle/results/qc_poc_20261027_v087'
report={'version':'0.8.7','native':{},'baseline_verification':{},'independent_comparison':{},'strict_replay_ready':False,'full_pipeline_pass':False,'live_ready':False}
def native_identity(frame):
 return {str(ep):tuple(sorted((str(r.right),float(r.strike),float(r.quantity)) for r in g.itertuples())) for ep,g in frame.groupby('episode')}
for stage in ['smoke','baseline','verify']:
 for key in ['c0','c1','p1']:
  name=key+'_'+stage;f=OUT/(name+'_evidence')
  if not (f/'audit.json').exists():report['native'][name]={'status':'pending'};continue
  a=json.loads((f/'audit.json').read_text())
  if not a.get('native_cloud_terminal_success'):report['native'][name]=a;continue
  _,pay=reconstruct(f);b=json.loads((f/'backtest.json').read_text())['backtest'];stats=b['statistics'];runtime=b['runtimeStatistics']
  report['native'][name]={'status':'verified_native_completed','project_id':b.get('projectId'),'backtest_id':b.get('backtestId'),'episodes':a['episodes'],'net_pnl':pay['net_pnl'],'drawdown':stats.get('Drawdown'),'cagr':stats.get('Compounding Annual Return'),'min_margin':runtime.get('min_margin_remaining_1m'),'native_arithmetic':pay,'residual_positions':a['residual_positions']}
for key in ['c0','c1','p1']:
 a=OUT/(key+'_baseline_evidence');b=OUT/(key+'_verify_evidence')
 if not all((x/'episodes.parquet').exists() for x in [a,b]):continue
 x=pd.read_parquet(a/'episodes.parquet').set_index('episode');y=pd.read_parquet(b/'episodes.parquet').set_index('episode');same=set(x.index)==set(y.index);common=x.index.intersection(y.index)
 ia=native_identity(pd.read_parquet(a/'legs.parquet'));ib=native_identity(pd.read_parquet(b/'legs.parquet'))
 report['baseline_verification'][key]={'same_episode_set':same,'common_episodes':len(common),'contracts_equal':ia==ib,'max_pnl_error':float((x.loc[common,'pnl']-y.loc[common,'pnl']).abs().max()) if len(common) else None,'account_net_difference':float(y.pnl.sum()-x.pnl.sum())}
local=pd.read_parquet(OUT/'local_episodes.parquet')
for key in ['c0','c1','p1']:
 f=OUT/(key+'_baseline_evidence')
 if not (f/'episodes.parquet').exists():continue
 n=pd.read_parquet(f/'episodes.parquet');n['episode']=n.episode.astype(str);nl=native_identity(pd.read_parquet(f/'legs.parquet'))
 l=local[(local.strategy==key.upper())&(local['mode']=='equal_time_sensitivity')&(local['fill']=='legacy')].copy();l['episode']=l.day.str.replace('-','')+l.slot.str.replace(':','')
 joined=n.merge(l,on='episode',suffixes=('_qc','_local'));matches=[]
 for r in joined.itertuples():
  ids=json.loads(r.legs);ident=tuple(sorted((s.split(':')[4],float(s.split(':')[5]),float(q)) for s,q in ids));matches.append(ident==nl[r.episode])
 joined['same_contracts']=matches
 joined.to_parquet(OUT/(key+'_native_local_common.parquet'),index=False)
 # Native selection is only used here, after the independent provider run.
 match=joined[joined.same_contracts]
 report['independent_comparison'][key]={'mode':'equal_time_sensitivity_only','local_episodes':len(l),'qc_episodes':len(n),'common_decision_slots':len(joined),'same_contract_slots':int(sum(matches)),'contract_agreement_on_joint_fills':float(sum(matches)/len(matches)) if matches else None,'same_contract_pnl_delta_local_minus_qc':float((match.pnl_local-match.pnl_qc).sum()),'unclassified_difference_count':len(joined)-int(sum(matches)),'acceptance':'not proven; vendor selection/fill/settlement differences require full attribution; primary predecision coverage absent'}
# Legacy native controls are independent from provider parity.
report['legacy_native_control']={}
for key,prior in [('c0','condor_baseline'),('c1','condor_final')]:
 new=OUT/(key+'_baseline_evidence');old=ROOT/'strategies/sstrangle/results/qc_poc_20261026_v085'/(prior+'_evidence')
 if not (new/'episodes.parquet').exists():continue
 a=pd.read_parquet(new/'episodes.parquet').set_index('episode');b=pd.read_parquet(old/'episodes.parquet').set_index('episode');ix=a.index.intersection(b.index)
 report['legacy_native_control'][key]={'same_episode_set':set(a.index)==set(b.index),'contracts_equal':native_identity(pd.read_parquet(new/'legs.parquet'))==native_identity(pd.read_parquet(old/'legs.parquet')),'max_episode_pnl_error':float((a.loc[ix,'pnl']-b.loc[ix,'pnl']).abs().max()),'net_difference':float(a.pnl.sum()-b.pnl.sum())}
report['local_summary']=json.loads((OUT/'local_summary.json').read_text());report['coverage_snapshot']=json.loads((OUT/'coverage_snapshot.json').read_text())
report['native_pipeline_complete']=all(v.get('status')=='verified_native_completed' for v in report['native'].values())
report['verdict']='Native results and equal-time sampled sensitivity are separate evidence. Independent preregistered predecision replay remains blocked by missing synchronized observations; no reproduction or live acceptance.'
(OUT/'results.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ['local_summary','coverage_snapshot']},indent=2))
