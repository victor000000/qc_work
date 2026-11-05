"""Bounded walk-forward rule selection; preserve trials and freeze before QC."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'strategies/sstrangle/results/qc_sizing_poc_20261024';OLD=ROOT/'strategies/sstrangle/results/qc_final_poc_20261024'
BASES={'condor':(OLD/'condor_control_full_evidence',100000),'put':(ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023/put_full_v3_evidence',2000000)}
calendar=json.loads((ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023/calendar_inventory.json').read_text())['session_dates']

def metrics(daily,capital,dates):
 eq=capital+np.cumsum(daily);dd=float(np.max(1-eq/np.maximum.accumulate(np.r_[capital,eq])[1:]));years=(pd.Timestamp(str(dates[-1]))-pd.Timestamp(str(dates[0]))).days/365.25
 cagr=float((eq[-1]/capital)**(1/years)-1) if np.min(eq)>0 else -1.
 return dict(pnl=float(np.sum(daily)),cash_dd=dd,cagr=cagr,calmar=cagr/dd if dd>0 else (-1000 if cagr<=0 else 1000))

def data(kind):
 f=pd.read_parquet(BASES[kind][0]/'episodes.parquet').sort_values('episode').reset_index(drop=True);panel=pd.read_parquet(OUT/'daily_features.parquet');days=np.array(list(panel.index));idx=np.searchsorted(days,f.day.to_numpy(),side='left')-1
 assert (idx>=0).all();x=panel.iloc[idx].reset_index(drop=True)
 f=pd.concat([f,x[list(json.loads((OUT/'feature_registry.json').read_text()))]],axis=1)
 f['day_index']=pd.Index(calendar).get_indexer(f.day);return f

def daily(f,mask,cost=0):return np.bincount(f.day_index.to_numpy()[mask],weights=(f.pnl.to_numpy()[mask]-cost),minlength=len(calendar))
def mask_for(f,feature,side,threshold):return np.ones(len(f),dtype=bool) if feature=='none' else ((f[feature].to_numpy()>threshold) if side=='above' else (f[feature].to_numpy()<=threshold))

def main():
 features=list(json.loads((OUT/'feature_registry.json').read_text()));rules={};calyear=np.array([int(d[:4]) for d in calendar])
 for kind,(_,capital) in BASES.items():
  f=data(kind);year=f.year.to_numpy();ledger=[]
  for feature in ['none']+features:
   for quantile in ([.5] if feature=='none' else [.25,.5,.75]):
    for side in (['all'] if feature=='none' else ['above','below']):
     rec=dict(feature=feature,quantile=quantile,side=side);scores=[];validation_profit=0
     for testyear in [2023,2024]:
      threshold=0 if feature=='none' else float(f.loc[f.year<testyear,feature].quantile(quantile));mask=mask_for(f,feature,side,threshold)&(year==testyear);ds=daily(f,mask,10)[calyear==testyear];dates=np.array(calendar)[calyear==testyear];m=metrics(ds,capital,dates);rec[f'fold_{testyear}_calmar']=m['calmar'];rec[f'fold_{testyear}_trades']=int(mask.sum());scores.append(m['calmar']);validation_profit+=m['pnl']
     threshold=0 if feature=='none' else float(f.loc[f.year<=2024,feature].quantile(quantile));mask=mask_for(f,feature,side,threshold);counts={str(y):int(np.sum(mask&(year==y))) for y in range(2022,2027)}
     rec.update(threshold=threshold,score=min(scores),validation_pnl=validation_profit,eligible=bool(min(counts.values())>=400 and rec['fold_2023_trades']>=400 and rec['fold_2024_trades']>=400),**{'count_'+y:n for y,n in counts.items()});ledger.append(rec)
  trials=pd.DataFrame(ledger);assert len(trials)==901;trials.to_csv(OUT/(kind+'_all_trials.csv'),index=False)
  valid=trials[trials.eligible].sort_values(['score','validation_pnl','feature','quantile','side'],ascending=[False,False,True,True,True]);assert len(valid)
  best=valid.iloc[0].to_dict();mask=mask_for(f,best['feature'],best['side'],best['threshold']);best.update(capital=capital,trials=len(trials),eligible_trials=len(valid),full_local=metrics(daily(f,mask),capital,calendar),selected_episodes=list(f.loc[mask,'episode']))
  f.loc[mask,['episode','day','year','pnl']].to_parquet(OUT/(kind+'_local_selected.parquet'),index=False);rules[kind]=best;print(kind,{k:best[k] for k in ['feature','side','threshold','score','full_local']},flush=True)
 payload=json.dumps(rules,indent=2);path=OUT/'frozen_rules.json';assert not path.exists() or path.read_text()==payload;path.write_text(payload)
 (OUT/'optimizer_provenance.json').write_text(json.dumps(dict(rules_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),contract_sha256=hashlib.sha256((OUT/'EXPERIMENT_CONTRACT.txt').read_bytes()).hexdigest(),policy='Historical 2023/2024 walk-forward validation, $10 extra package cost; final threshold fit through2024; all-year count-only feasibility. July14-October22 native outcomes not viewed before freeze.'),indent=2))
if __name__=='__main__':main()
