"""Verify native accounting, source, selected rule and legacy tape differences."""
import json,hashlib,sys
from pathlib import Path
import pandas as pd
from campaign import ROOT,OUT
from optimize import BASES,data,mask_for,OLD
sys.path.insert(0,str(ROOT/'strategies/sstrangle/poc/v07'));from recheck_baselines import reconstruct

def verify(key):
 m=json.loads((OUT/(key+'_manifest.json')).read_text());cfg=m['config'];kind=cfg['strategy_kind'];folder=OUT/(key+'_evidence');audit=json.loads((folder/'audit.json').read_text());assert audit['native_cloud_terminal_success'] and audit['residual_positions']==0
 ep=pd.read_parquet(folder/'episodes.parquet');_,payoff=reconstruct(folder)
 cloud={f['name']:f['content'] for f in json.loads((OUT/(key+'_cloud_source_files.json')).read_text())['files']}
 for n,digest in {'main.py':m['source_sha256'],**m['extra_files_sha256']}.items():assert hashlib.sha256(cloud[n].encode()).hexdigest()==digest,n
 source_rules=OLD if m['control'] else OUT;rule=json.loads((source_rules/'frozen_rules.json').read_text())[kind]
 f=data(kind);mask=mask_for(f,rule['feature'],rule['side'],rule['threshold']);expected=f[mask]
 start='-'.join(map(lambda x:f'{x:02d}',cfg['start']));end='-'.join(map(lambda x:f'{x:02d}',cfg['last_entry']));expected=expected[expected.day.between(start,min(end,'2026-07-13'))]
 legacy=ep[ep.day<='2026-07-13']
 if m['control'] and not m['smoke']:
  prior=pd.read_parquet(OLD/(kind+'_alpha_full_evidence')/'episodes.parquet');assert set(prior.episode)==set(legacy.episode),'0.7 control episode drift'
  check=legacy.merge(prior,on='episode',suffixes=('_new','_old'));assert (check.pnl_new-check.pnl_old).abs().max()<1e-5,'0.7 control P&L drift'
 common=legacy.merge(expected,on='episode',suffixes=('_qc','_local'));added=legacy[~legacy.episode.isin(expected.episode)];missing=expected[~expected.episode.isin(legacy.episode)]
 maxdiff=float((common.pnl_qc-common.pnl_local).abs().max()) if len(common) else 0;assert maxdiff<1e-5
 legs=pd.read_parquet(folder/'legs.parquet');oldlegs=pd.read_parquet(BASES[kind][0]/'legs.parquet')
 def identities(d):return d.groupby('episode').apply(lambda g:tuple(sorted(zip(g.symbol,g.quantity))),include_groups=False).to_dict()
 a,b=identities(legs),identities(oldlegs);assert all(a[e]==b[e] for e in common.episode)
 def rejected(p):
  out={}
  for o in json.loads((p/'orders.json').read_text()):
   tag=dict(x.split('=',1) for x in o.get('tag','').split(';') if '=' in x)
   if tag.get('r')=='OPEN' and not any(float(e.get('fillQuantity',0)) for e in o.get('events',[])):out.setdefault(tag['e'],[]).extend(e.get('message','') for e in o.get('events',[]))
  return out
 oldrej,newrej=rejected(BASES[kind][0]),rejected(folder);reasons={'added':{e:oldrej.get(e,[]) for e in added.episode},'missing':{e:newrej.get(e,[]) for e in missing.episode}}
 explained=all(any('Insufficient buying power' in text for text in r) for group in reasons.values() for r in group.values());assert explained
 # All actual entries, including the new interval, use prior completed raw inputs.
 prices=pd.read_parquet(OUT/'provider/us_prices_full/data.parquet');g=prices[prices.symbol==rule['feature'].split('_')[0].upper()].sort_values('date')
 tags={}
 for o in json.loads((folder/'orders.json').read_text()):
  tag=dict(x.split('=',1) for x in o.get('tag','').split(';') if '=' in x)
  if tag.get('r')=='OPEN':tags[tag['e']]=tag
 maxfeature=0
 if rule['feature']!='none':
  for row in ep.itertuples():
   prior=g[g.date.astype(str)<row.day].iloc[-1];value=(prior.high-prior.low)/prior.close;tag=tags[row.episode]
   assert tag['asof']==str(prior.date) and tag['af']==rule['feature'];error=abs(float(tag['av'])-value);assert error<1e-10;maxfeature=max(maxfeature,error)
   assert (value>rule['threshold']) if rule['side']=='above' else (value<=rule['threshold'])
 counts={str(y):int(n) for y,n in ep.groupby('year').size().items()}
 if not m['smoke']:assert all(counts.get(str(y),0)>=360 for y in range(2022,2027))
 if kind=='condor':assert ((ep.put_delta+.2).abs()<=.02000001).all() and ((ep.call_delta-.08).abs()<=.02000001).all()
 result=dict(key=key,native_episodes=len(ep),native_pnl=float(ep.pnl.sum()),annual_counts=counts,local_expected_legacy=len(expected),local_pnl_legacy=float(expected.pnl.sum()),native_legacy=len(legacy),native_pnl_legacy=float(legacy.pnl.sum()),common_episodes=len(common),max_common_pnl_difference=maxdiff,added=len(added),added_pnl=float(added.pnl.sum()),missing=len(missing),missing_pnl=float(missing.pnl.sum()),funding_explained=explained,feature_max_error=maxfeature,independent_payoff=payoff,holdout_trades=int((ep.day>'2026-07-13').sum()),holdout_pnl=float(ep.loc[ep.day>'2026-07-13','pnl'].sum()))
 assert abs(result['native_pnl_legacy']-result['local_pnl_legacy']-result['added_pnl']+result['missing_pnl'])<.01
 (OUT/(key+'_funding_messages.json')).write_text(json.dumps(reasons,indent=2));(OUT/(key+'_consistency.json')).write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':verify(sys.argv[1])
