"""Frozen training-only ranking with explicit full-period count feasibility."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'strategies/sstrangle/results/qc_final_poc_20261024';OLD=ROOT/'strategies/sstrangle/results/qc_delta_poc_20261024'
BASES={'condor':('condor_full_t02',OLD/'condor_full_t02_evidence',100000),'strangle':('strangle_v06',ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023/strangle_full_v2_evidence',2000000),'put':('put_v06',ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023/put_full_v3_evidence',2000000)}

def cash_metrics(d,mask,calendar,capital):
 daily=d.loc[mask].groupby('day').pnl.sum().reindex(calendar,fill_value=0)
 eq=capital+daily.cumsum();peak=eq.cummax().clip(lower=capital);dd=float((1-eq/peak).max());years=(pd.Timestamp(calendar[-1])-pd.Timestamp(calendar[0])).days/365.25
 cagr=float((eq.iloc[-1]/capital)**(1/years)-1) if eq.min()>0 else -1
 return dict(pnl=float(daily.sum()),daily_cash_dd=dd,cagr=cagr,calmar=cagr/dd if dd>0 else -1e9)

def main():
 calendar=json.loads((ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023/calendar_inventory.json').read_text())['session_dates'];traincal=[x for x in calendar if x<'2024-01-01']
 registry=json.loads((OLD/'local/feature_registry.json').read_text());features=[k for k,v in registry.items() if v['screen_eligible']]
 selected={}
 for kind,(key,folder,capital) in BASES.items():
  ep=pd.read_parquet(folder/'episodes.parquet');f=pd.read_parquet(OLD/'local'/(key+'_features.parquet'));d=f.merge(ep[['episode','day','year','pnl']],on='episode',validate='one_to_one');train=d.year<=2023
  rows=[]
  for field in features:
   for quantile in [.25,.5,.75]:
    threshold=float(d.loc[train,field].quantile(quantile))
    for side in ['above','below']:
     mask=d[field].gt(threshold) if side=='above' else d[field].le(threshold)
     counts=d[mask].groupby('year').size().reindex(range(2022,2027),fill_value=0)
     m=cash_metrics(d,mask&train,traincal,capital)
     row=dict(feature=field,quantile=quantile,side=side,threshold=threshold,eligible=bool(counts.ge(400).all() and m['pnl']>0 and m['daily_cash_dd']>0),**{'train_'+k:v for k,v in m.items()},**{f'count_{y}':int(n) for y,n in counts.items()})
     rows.append(row)
  trials=pd.DataFrame(rows);trials.to_csv(OUT/(kind+'_all_trials.csv'),index=False)
  valid=trials[trials.eligible].sort_values(['train_calmar','train_pnl','feature','quantile','side'],ascending=[False,False,True,True,True]);assert len(valid)
  best=valid.iloc[0].to_dict();mask=d[best['feature']].gt(best['threshold']) if best['side']=='above' else d[best['feature']].le(best['threshold'])
  baseline=cash_metrics(d,train,traincal,capital);best['improves_training_calmar']=best['train_calmar']>baseline['calmar']
  best.update(kind=kind,baseline_key=key,baseline_folder=str(folder),capital=capital,baseline_training=baseline,selected_episodes=d.loc[mask,'episode'].tolist(),full_local=cash_metrics(d,mask,calendar,capital),later_local=cash_metrics(d,mask&(d.year>=2025),[x for x in calendar if x>='2025-01-01'],capital),trials=len(trials),eligible_trials=len(valid))
  selected[kind]=best;d.loc[mask,['episode','day','year','pnl']].to_parquet(OUT/(kind+'_local_selected.parquet'),index=False)
  print(kind,{k:best[k] for k in ['feature','quantile','side','threshold','train_calmar','full_local','later_local']},flush=True)
 path=OUT/'frozen_rules.json';payload=json.dumps(selected,indent=2)
 assert not path.exists() or path.read_text()==payload,'Do not overwrite frozen optimizer decisions'
 path.write_text(payload)
 (OUT/'optimizer_provenance.json').write_text(json.dumps({'rules_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'policy':'Training2022-23 ranking; all-year count-only feasibility>=400; no untouched OOS; frozen before native results'},indent=2))
if __name__=='__main__':main()
