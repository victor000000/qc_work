"""Verify source identities, every native payoff, feature decisions and funding deltas."""
import json,sys,hashlib,re,ast
from pathlib import Path
import pandas as pd
from campaign import ROOT,P,OUT,digest,save,ACTIVE_KINDS
from research import features,mask_for,prices,evaluate,select,PRICES
# Keep the archived verifier isolated: its imports bind historical campaign constants.
import importlib.util
spec=importlib.util.spec_from_file_location('v085_payoff',P/'payoff.py');payoff=importlib.util.module_from_spec(spec);spec.loader.exec_module(payoff)

def rejections(folder):
 result={}
 for o in json.loads((folder/'orders.json').read_text()):
  tag=dict(x.split('=',1) for x in o.get('tag','').split(';') if '=' in x)
  if tag.get('r')=='OPEN' and not any(float(e.get('fillQuantity',0)) for e in o.get('events',[])):
   result.setdefault(tag['e'],[]).extend(e.get('message','') for e in o.get('events',[]))
 return result

def audit(key):
 folder=OUT/(key+'_evidence');m=json.loads((OUT/(key+'_manifest.json')).read_text());cfg=m['config']
 a=json.loads((folder/'audit.json').read_text());assert a['native_cloud_terminal_success'] and a['residual_positions']==0
 assert digest(OUT/'experiment_contract.json')==m['contract_sha256']
 cloud={f['name']:f['content'] for f in json.loads((OUT/(key+'_cloud_source_files.json')).read_text())['files']}
 assert set(cloud)==set({'main.py':m['source_sha256'],**m['extra_files_sha256']}),'Unexpected cloud source file'
 for n,h in {'main.py':m['source_sha256'],**m['extra_files_sha256']}.items():assert hashlib.sha256(cloud[n].encode()).hexdigest()==h
 assert digest(folder/'submitted_main.py')==m['source_sha256']
 _,reproduction=payoff.reconstruct(folder)
 ep=pd.read_parquet(folder/'episodes.parquet');assert ((ep.put_delta+.2).abs()<=.02000001).all()
 if cfg['strategy_kind']=='condor':assert ((ep.call_delta-.08).abs()<=.02000001).all()
 if m['alpha']:
  assert m['scope_amendment_sha256']==digest(OUT/'scope_amendment.json')
  assert m['rules_sha256']==digest(OUT/'frozen_rules.json')
  rule=json.loads((OUT/'frozen_rules.json').read_text())[cfg['strategy_kind']]
  assert mask_for(features(ep),rule).all()
  if rule['feature']!='none':
   names=sorted([n for n in cloud if n.startswith('daily_input_')],key=lambda n:int(n.split('_')[-1].split('.')[0]))
   raw=[]
   for n in names:
    node=ast.parse(cloud[n]).body[0];assert isinstance(node,ast.Assign);raw.extend(ast.literal_eval(node.value))
   g=prices[prices.symbol==rule['feature'].split('_')[0].upper()].sort_values('date')
   expected_raw=[[str(r.date),float(r.high),float(r.low),float(r.close),int(r.volume)] for r in g.itertuples()]
   assert raw==expected_raw,'Native raw inputs differ from pinned provider bars'
   f=features(ep).set_index('episode')
   for o in json.loads((folder/'orders.json').read_text()):
    tag=dict(x.split('=',1) for x in o.get('tag','').split(';') if '=' in x)
    if tag.get('r')=='OPEN' and tag['e'] in f.index:
     r=f.loc[tag['e']];assert tag['af']==rule['feature'];assert tag['asof']==r[rule['feature']+'_source_day'];assert abs(float(tag['av'])-r[rule['feature']])<1e-10
 rt=json.loads((folder/'backtest.json').read_text())['backtest']['runtimeStatistics']
 result=dict(key=key,source_verified=True,accounting=reproduction,annual_pass=a['annual_pass'],counts={str(y):int(n) for y,n in ep.groupby('year').size().items()},minimum_margin_remaining=float(rt['min_margin_remaining_1m']),max_margin_used=float(rt['max_margin_used_1m']),feature_decisions_verified=m['alpha'])
 save(OUT/(key+'_verification.json'),result);return result

def compare(kind):
 baseline=OUT/(kind+'_baseline_evidence');final=OUT/(kind+'_final_evidence')
 f=features(pd.read_parquet(baseline/'episodes.parquet'));rule=json.loads((OUT/'frozen_rules.json').read_text())[kind];expected=f[mask_for(f,rule)]
 native=pd.read_parquet(final/'episodes.parquet');common=native.merge(expected,on='episode',suffixes=('_qc','_local'))
 maxdiff=float((common.pnl_qc-common.pnl_local).abs().max()) if len(common) else 0.
 added=native[~native.episode.isin(expected.episode)];missing=expected[~expected.episode.isin(native.episode)]
 def identities(folder):
  legs=pd.read_parquet(folder/'legs.parquet');return {e:tuple(sorted(zip(g.symbol,g.quantity))) for e,g in legs.groupby('episode')}
 a,b=identities(baseline),identities(final);mismatches=[e for e in common.episode if a[e]!=b[e]]
 oldreject,newreject=rejections(baseline),rejections(final)
 reasons={'added':{e:oldreject.get(e,[]) for e in added.episode},'missing':{e:newreject.get(e,[]) for e in missing.episode}}
 unexplained=[(side,e) for side,group in reasons.items() for e,msg in group.items() if not any('Insufficient buying power' in s for s in msg)]
 error=float(native.pnl.sum()-expected.pnl.sum()-added.pnl.sum()+missing.pnl.sum())
 result=dict(common_episodes=len(common),common_max_pnl_error=maxdiff,contract_mismatches=mismatches,added=len(added),missing=len(missing),added_pnl=float(added.pnl.sum()),missing_pnl=float(missing.pnl.sum()),unexplained_differences=unexplained,bridge_error=error,local_trades=len(expected),local_pnl=float(expected.pnl.sum()),native_trades=len(native),native_pnl=float(native.pnl.sum()),passed=maxdiff<1e-5 and not mismatches and not unexplained and abs(error)<.01)
 save(OUT/(kind+'_funding_messages.json'),reasons);save(OUT/(kind+'_local_qc_comparison.json'),result)
 return result

def main():
 provenance=json.loads((OUT/'research_provenance.json').read_text())
 assert provenance['scope_amendment_sha256']==digest(OUT/'scope_amendment.json')
 assert provenance['rules_sha256']==digest(OUT/'frozen_rules.json')
 assert provenance['contract_sha256']==digest(OUT/'experiment_contract.json')
 assert provenance['source_sha256']==digest(P/'research.py')
 assert provenance['provider_sha256']==digest(PRICES)
 frozen=json.loads((OUT/'frozen_rules.json').read_text())
 for kind in ACTIVE_KINDS:
  assert provenance['baseline_hashes'][kind]==digest(OUT/(kind+'_baseline_evidence/episodes.parquet'))
  selected,ledger=select(features(pd.read_parquet(OUT/(kind+'_baseline_evidence/episodes.parquet'))))
  assert selected==frozen[kind]
  assert ledger==json.loads((OUT/(kind+'_trials.json')).read_text())
 results={key:audit(key) for key in ['put_spread_smoke','condor_baseline','condor_final']}
 comparisons={k:compare(k) for k in ACTIVE_KINDS}
 old=ROOT/'strategies/sstrangle/results/qc_final_poc_20261024/condor_control_full_evidence/episodes.parquet'
 before=pd.read_parquet(old);now=pd.read_parquet(OUT/'condor_baseline_evidence/episodes.parquet');now=now[now.day<='2026-07-13'];merge=now.merge(before,on='episode',suffixes=('_new','_old'))
 legacy=dict(old=len(before),new=len(now),common=len(merge),max_pnl_difference=float((merge.pnl_new-merge.pnl_old).abs().max()))
 oldlegs=pd.read_parquet(old.parent/'legs.parquet');newlegs=pd.read_parquet(OUT/'condor_baseline_evidence/legs.parquet')
 oldids={e:tuple(sorted(zip(g.symbol,g.quantity))) for e,g in oldlegs.groupby('episode')};newids={e:tuple(sorted(zip(g.symbol,g.quantity))) for e,g in newlegs.groupby('episode')}
 legacy['contract_mismatches']=[e for e in before.episode if oldids[e]!=newids.get(e)]
 legacy['passed']=len(before)==len(now)==len(merge) and legacy['max_pnl_difference']<1e-5 and not legacy['contract_mismatches']
 result=dict(version='0.8.5',scope='Complete condor pipeline; optional put spread rejected at failed native baseline gate',rejected_addon=json.loads((OUT/'put_spread_failure.json').read_text()),runs=results,comparisons=comparisons,legacy_condor_reproduction=legacy,engineering_pass=all(c['passed'] for c in comparisons.values()) and legacy['passed'],frequency_pass=all(v['annual_pass'] for k,v in results.items() if 'smoke' not in k),margin_headroom_pass=all(v['minimum_margin_remaining']>=0 for k,v in results.items() if 'smoke' not in k),independent_quote_replay_pass=False,robust_alpha_established=False,live_approved=False)
 save(OUT/'final_verification.json',result);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
