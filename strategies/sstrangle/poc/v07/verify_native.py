"""Reconcile final native entries against frozen local rules and baseline tapes."""
from pathlib import Path
import json,re
import pandas as pd
from feature_rule import feature_value,rule_pass
from optimize import ROOT,OUT,OLD,BASES

def verify(key):
 p=OUT/(key+'_evidence');manifest=json.loads((OUT/(key+'_manifest.json')).read_text());cfg=manifest['config'];kind=cfg['strategy_kind'];rule=json.loads((OUT/'frozen_rules.json').read_text())[kind]
 ep=pd.read_parquet(p/'episodes.parquet');base=pd.read_parquet(BASES[kind][1]/'episodes.parquet');audit=json.loads((p/'audit.json').read_text());full=cfg['start']==[2022,5,16]
 assert audit['native_cloud_terminal_success'] and audit['residual_positions']==0
 if full:assert ep.groupby('year').size().reindex(range(2022,2027),fill_value=0).ge(360).all()
 if kind=='condor':assert ((ep.put_delta+.2).abs()<=.02+1e-8).all() and ((ep.call_delta-.08).abs()<=.02+1e-8).all()
 if cfg['alpha_enabled']:
  prices=pd.read_parquet(OLD/'provider/us_prices/data.parquet');g=prices[prices.symbol==rule['feature'].split('_')[0].upper()].sort_values('date');raw=[[str(r.date),float(r.high),float(r.low),float(r.close),int(r.volume)] for r in g.itertuples()]
  orders=json.loads((p/'orders.json').read_text());tags={}
  for o in orders:
   tag=dict(x.split('=',1) for x in o.get('tag','').split(';') if '=' in x)
   if tag.get('r')=='OPEN':tags[tag['e']]=tag
  feature_error=0
  for row in ep.itertuples():
   value,day=feature_value(raw,row.day,rule['feature']);tag=tags[row.episode]
   assert tag['af']==rule['feature'] and tag['asof']==day and rule_pass(value,rule['threshold'],rule['side'])
   error=abs(float(tag['av'])-value);assert error<1e-10;feature_error=max(feature_error,error)
  expected=base[base.episode.isin(rule['selected_episodes'])]
 else:expected=base;feature_error=0
 start='-'.join(f'{x:02d}' if i else str(x) for i,x in enumerate(cfg['start']));end='-'.join(f'{x:02d}' if i else str(x) for i,x in enumerate(cfg['last_entry']))
 expected=expected[expected.day.between(start,end)]
 common=ep.merge(expected,on='episode',suffixes=('_native','_local'));added=ep[~ep.episode.isin(expected.episode)];missing=expected[~expected.episode.isin(ep.episode)]
 delta=float((common.pnl_native-common.pnl_local).sum());max_delta=float((common.pnl_native-common.pnl_local).abs().max()) if len(common) else 0
 legs=pd.read_parquet(p/'legs.parquet');baselegs=pd.read_parquet(BASES[kind][1]/'legs.parquet')
 def identities(frame):return frame.groupby('episode').apply(lambda g:tuple(sorted(zip(g.symbol,g.quantity))),include_groups=False).to_dict()
 li,bi=identities(legs),identities(baselegs);mismatched_contracts=[x for x in common.episode if li[x]!=bi[x]]
 def zero_fill_reasons(source):
  result={}
  for order in json.loads((source/'orders.json').read_text()):
   tag=dict(x.split('=',1) for x in order.get('tag','').split(';') if '=' in x)
   if tag.get('r')=='OPEN' and not any(float(e.get('fillQuantity',0)) for e in order.get('events',[])):
    result.setdefault(tag['e'],[]).extend(e.get('message','') for e in order.get('events',[]) if e.get('message'))
  return result
 old_rejections=zero_fill_reasons(BASES[kind][1]);new_rejections=zero_fill_reasons(p)
 added_reasons={e:old_rejections.get(e,[]) for e in added.episode};missing_reasons={e:new_rejections.get(e,[]) for e in missing.episode}
 funding_explained=all(any('Insufficient buying power' in text for text in messages) for messages in list(added_reasons.values())+list(missing_reasons.values()))
 (OUT/(key+'_funding_messages.json')).write_text(json.dumps({'added':added_reasons,'missing':missing_reasons,'all_differences_explained_by_native_buying_power':funding_explained},indent=2))
 # Archive every readable cloud input module before the project can be reused.
 from campaign import request,credentials,rows
 row=next(r for r in rows() if r['name']==manifest['name']);u,t=credentials(ROOT/'data/S001.duckdb')
 import time
 for attempt in range(6):
  try:
   response=request(u,t,'/files/read',{'projectId':row['project_id']});break
  except RuntimeError:
   if attempt==5:raise
   time.sleep(min(2**(attempt+1),30))

 cloud={x['name']:x['content'] for x in response['files']}
 import hashlib
 cloud_expected={'main.py':manifest['source_sha256'],**manifest.get('extra_files_sha256',{})}
 for name,digest in cloud_expected.items():assert hashlib.sha256(cloud[name].encode()).hexdigest()==digest,'Cloud source/input mismatch: '+name
 (OUT/(key+'_cloud_source_files.json')).write_text(json.dumps(response,indent=2))
 result=dict(key=key,kind=kind,alpha_enabled=cfg['alpha_enabled'],full=full,native_episodes=len(ep),local_expected_episodes=len(expected),native_pnl=float(ep.pnl.sum()),local_expected_pnl=float(expected.pnl.sum()),common_episodes=len(common),common_pnl_difference=delta,max_common_pnl_difference=max_delta,common_contract_mismatches=mismatched_contracts,added_episodes=len(added),added_pnl=float(added.pnl.sum()),missing_episodes=len(missing),missing_pnl=float(missing.pnl.sum()),feature_max_error=feature_error,funding_differences_explained=funding_explained,cloud_modules_verified=len(cloud_expected),annual_counts={str(y):int(n) for y,n in ep.groupby('year').size().items()},native_rejected_episodes=audit['rejected_episodes'])
 assert abs(result['native_pnl']-result['local_expected_pnl']-delta-result['added_pnl']+result['missing_pnl'])<.01
 # Full unfiltered control must reproduce the baseline, not merely a rounded total.
 if full and not cfg['alpha_enabled']:assert not len(added) and not len(missing) and not mismatched_contracts and max_delta<1e-5
 # Preserve evidence for changed entries/funding; quantify instead of asserting false filtered tape equivalence.
 added.to_csv(OUT/(key+'_added.csv'),index=False);missing.to_csv(OUT/(key+'_missing.csv'),index=False)
 (OUT/(key+'_consistency.json')).write_text(json.dumps(result,indent=2))
 if full and cfg['alpha_enabled']:assert not mismatched_contracts and max_delta<1e-5 and funding_explained,'Investigate unexplained local/native differences before acceptance'
 print(json.dumps(result,indent=2),flush=True)
 return result
if __name__=='__main__':
 import sys
 verify(sys.argv[1])
