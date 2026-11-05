"""13 predeclared rules. Freeze using 2022–24 only; report later years separately."""
import hashlib,json,sys,time,platform
from pathlib import Path
import numpy as np
import pandas as pd
from campaign import ROOT,P,OUT,digest,save,ACTIVE_KINDS
PRICES=ROOT/'strategies/sstrangle/results/qc_sizing_poc_20261024/provider/us_prices_full/data.parquet'
prices=pd.read_parquet(PRICES)
calendar=sorted(prices.loc[(prices.symbol=='SPY') & prices.date.astype(str).between('2022-05-16','2026-10-22'),'date'].astype(str).unique())
def metrics(values,days,capital=100000):
 values=np.asarray(values,dtype=float);eq=capital+np.cumsum(values);peak=np.maximum.accumulate(np.r_[capital,eq])[1:]
 dd=float((1-eq/peak).max()) if len(eq) else 0
 years=(pd.Timestamp(str(days[-1]))-pd.Timestamp(str(days[0]))).days/365.25 if len(days)>1 else 1/365.25
 cagr=float((eq[-1]/capital)**(1/years)-1) if len(eq) and eq.min()>0 else -1
 return dict(pnl=float(values.sum()),cash_mdd=dd,cagr=cagr,calmar=cagr/dd if dd>0 else (1000. if cagr>0 else -1000.))
def features(f):
 f=f.copy();f['day']=f.day.astype(str)
 for feature in ['gld_range_pct','qqq_range_pct']:
  g=prices[prices.symbol==feature.split('_')[0].upper()].sort_values('date');days=g.date.astype(str).to_numpy();idx=np.searchsorted(days,f.day.to_numpy(),side='left')-1
  assert (idx>=0).all();prior=g.iloc[idx];source=prior.date.astype(str).to_numpy();assert (source<f.day.to_numpy()).all()
  value=((prior.high-prior.low)/prior.close).to_numpy();age=(pd.to_datetime(f.day).to_numpy()-pd.to_datetime(source).to_numpy())/np.timedelta64(1,'D')
  f[feature]=np.where(age<8,value,np.nan);f[feature+'_source_day']=source
 assert set(f.day).issubset(set(calendar))
 return f

def mask_for(f,rule):
 if rule['feature']=='none':return np.ones(len(f),dtype=bool)
 v=f[rule['feature']].to_numpy();return np.isfinite(v)&((v>rule['threshold']) if rule['side']=='above' else (v<=rule['threshold']))
def daily(f,mask,cost=0):return f.loc[mask].assign(net=lambda x:x.pnl-cost).groupby('day').net.sum().reindex(calendar,fill_value=0).to_numpy()
def evaluate(f,mask,cost=0,lo='2022-05-16',hi='2026-10-22'):
 dates=np.array(calendar);keep=(dates>=lo)&(dates<=hi);return metrics(daily(f,mask,cost)[keep],dates[keep])
def select(f):
 ledger=[]
 for feature in ['none','gld_range_pct','qqq_range_pct']:
  for q in ([.5] if feature=='none' else [.25,.5,.75]):
   threshold=0. if feature=='none' else float(f.loc[f.year<=2023,['day',feature]].drop_duplicates('day')[feature].quantile(q))
   for side in (['all'] if feature=='none' else ['above','below']):
    rule=dict(feature=feature,quantile=q,side=side,threshold=threshold);mask=mask_for(f,rule)
    counts={str(y):int(np.sum(mask&(f.year.to_numpy()==y))) for y in [2022,2023,2024]}
    m=evaluate(f,mask,10,'2024-01-01','2024-12-31')
    ledger.append(dict(**rule,eligible=min(counts.values())>=400,score=m['calmar'],validation_net=m['pnl'],counts=counts))
 assert len(ledger)==13
 eligible=[r for r in ledger if r['eligible']]
 best=sorted(eligible,key=lambda r:(-r['score'],-r['validation_net'],r['feature'],r['side'],r['quantile']))[0] if eligible else ledger[0]
 return dict(best),ledger

def main():
 assert json.loads((OUT/'scope_amendment.json').read_text())['active_research_strategies']==list(ACTIVE_KINDS)
 started=time.perf_counter()
 rules={};summary={}
 for kind in ACTIVE_KINDS:
  folder=OUT/(kind+'_baseline_evidence');f=features(pd.read_parquet(folder/'episodes.parquet'))
  best,ledger=select(f);rules[kind]=best;save(OUT/(kind+'_trials.json'),ledger)
  pd.DataFrame([{**r,'counts':json.dumps(r['counts'])} for r in ledger]).to_csv(OUT/(kind+'_trials.csv'),index=False)
  f.to_parquet(OUT/(kind+'_trade_features.parquet'),index=False)
  f[['episode','day','gld_range_pct','gld_range_pct_source_day','qqq_range_pct','qqq_range_pct_source_day']].to_parquet(OUT/(kind+'_entry_features.parquet'),index=False)
  f[['episode','day','year','pnl','settlement_spot','entry_credit','opening_fees']].to_parquet(OUT/(kind+'_labels.parquet'),index=False)
  mask=mask_for(f,best);f.loc[mask,['episode','day','year','pnl']].to_parquet(OUT/(kind+'_local_selected.parquet'),index=False)
  annual=[]
  for y in range(2022,2027):
   annual.append(dict(year=y,trades=int(np.sum(mask&(f.year.to_numpy()==y))),**evaluate(f,mask,0,f'{y}-01-01',f'{y}-12-31')))
  rng=np.random.default_rng(85026);dates=np.array(calendar);later=dates>='2025-01-01'
  base=np.ones(len(f),dtype=bool);difference=(daily(f,mask,10)-daily(f,base,10))[later]
  # Contiguous circular day blocks retain all overlapping intraday episodes.
  boot={}
  for block in [5,20,60]:
   starts=rng.integers(0,len(difference),size=(2000,int(np.ceil(len(difference)/block))))
   idx=((starts[:,:,None]+np.arange(block))%len(difference)).reshape(2000,-1)[:,:len(difference)]
   samples=difference[idx].mean(axis=1);boot[str(block)]=dict(mean_daily_uplift=float(difference.mean()),ci95=np.quantile(samples,[.025,.975]).tolist(),bootstrap_positive_fraction=float(np.mean(samples>0)))
  neighbors=[]
  if best['feature']!='none':
   for scale in [.8,.9,1.,1.1,1.2]:
    rule=dict(best,threshold=best['threshold']*scale);m=mask_for(f,rule)
    neighbors.append(dict(scale=scale,trades=int(m.sum()),later=evaluate(f,m,10,'2025-01-01')))
  ds=daily(f,mask,10);top=np.argsort(ds)[-5:];tail=ds.copy();tail[top]=0
  # Exploratory max-across-13-rule diagnostic on 2024; never a selection rerank.
  validation=(dates>='2024-01-01')&(dates<='2024-12-31')
  diffs=np.stack([(daily(f,mask_for(f,r),10)-daily(f,base,10))[validation] for r in ledger])
  observed=float(diffs.mean(axis=1).max());center=diffs-diffs.mean(axis=1,keepdims=True);n=center.shape[1]
  starts=rng.integers(0,n,size=(2000,int(np.ceil(n/20))));idx=((starts[:,:,None]+np.arange(20))%n).reshape(2000,-1)[:,:n]
  maxima=np.stack([center[:,ix].mean(axis=1).max() for ix in idx]);p=float((1+(maxima>=observed).sum())/2001)
  summary[kind]=dict(selected=best,annual=annual,full=evaluate(f,mask),baseline=evaluate(f,base),later=evaluate(f,mask,0,'2025-01-01'),baseline_later=evaluate(f,base,0,'2025-01-01'),cost_stress={str(c):evaluate(f,mask,c) for c in [0,10,25,50]},block_bootstrap_uplift=boot,max_rule_diagnostic=dict(p_value=p,observed_best_daily_uplift=observed,blocks=20,trials=13,interpretation='Exploratory centered resampling; not proof of alpha or fresh OOS'),threshold_neighbors=neighbors,remove_best_five_days=metrics(tail,calendar),independent_days=int(f.loc[mask].day.nunique()))
 payload=json.dumps(rules,indent=2)+'\n';path=OUT/'frozen_rules.json';assert not path.exists() or path.read_text()==payload;path.write_text(payload)
 save(OUT/'local_research.json',summary)
 save(OUT/'feature_registry.json',dict(features={name:dict(formula='(prior session high - low) / close',units='fraction',missing='reject; no history or prior day at least 8 calendar days old',availability='current-vintage raw daily bars; next-session availability assumption, NOT historical publication certification') for name in ['gld_range_pct','qqq_range_pct']},keys=['strategy','episode'],labels_separate=True,joined_research_table='*_trade_features.parquet is analysis only; never cloud input',threshold_weighting='one observation per baseline-filled day in 2022–2023',excluded=['pnl','settlement_spot','entry_credit','opening_fees','future counts','undefined QQQ skew','uncertified option clocks']))
 save(OUT/'research_provenance.json',dict(rules_sha256=digest(path),scope_amendment_sha256=digest(OUT/'scope_amendment.json'),contract_sha256=digest(OUT/'experiment_contract.json'),source_sha256=digest(Path(__file__)),provider_sha256=digest(PRICES),baseline_hashes={k:digest(OUT/(k+'_baseline_evidence/episodes.parquet')) for k in rules},selection_uses_2025_2026=False,python=platform.python_version(),pandas=pd.__version__,numpy=np.__version__,local_wall_seconds=time.perf_counter()-started,local_scope='fixed native tape conditional research; no option-chain or margin simulation'))
 print(json.dumps(rules,indent=2))
if __name__=='__main__':main()
