"""Historical sensitivity and walk-forward diagnostics; no OOS inflation."""
import json
import numpy as np
import pandas as pd
from optimize import OUT,OLD,BASES,calendar,data,daily,mask_for,metrics

def main():
 rules=json.loads((OUT/'frozen_rules.json').read_text());dates=np.array(calendar);calyear=np.array([int(d[:4]) for d in calendar]);result={}
 for kind,(_,capital) in BASES.items():
  f=data(kind);r=rules[kind];mask=mask_for(f,r['feature'],r['side'],r['threshold']);base=daily(f,np.ones(len(f),dtype=bool));chosen=daily(f,mask);cases=[]
  for cost in [0,5,10,25]:cases.append(dict(case='extra_package_cost_'+str(cost),**metrics(daily(f,mask,cost),capital,calendar)))
  cases.append(dict(case='double_opening_commission',**metrics(daily(f,mask,4.72 if kind=='condor' else 1.18),capital,calendar)))
  removed=chosen.copy();removed[np.argsort(removed)[-5:]]=0;cases.append(dict(case='remove_five_best_days',**metrics(removed,capital,calendar)))
  stressed=chosen.copy();ix=np.argsort(stressed)[:5];stressed[ix]*=1.5;cases.append(dict(case='five_worst_days_losses_times_1_5',**metrics(stressed,capital,calendar)))
  neighbors=[]
  for q in sorted(set([max(.01,r['quantile']-.05),r['quantile'],min(.99,r['quantile']+.05)])):
   threshold=0 if r['feature']=='none' else float(f.loc[f.year<=2024,r['feature']].quantile(q));m=mask_for(f,r['feature'],r['side'],threshold);counts=f[m].groupby('year').size();neighbors.append(dict(quantile=q,threshold=threshold,min_annual=int(counts.min()),**metrics(daily(f,m),capital,calendar)))
  annual=[]
  for y in range(2022,2027):annual.append(dict(year=y,trades=int(np.sum(mask&(f.year.to_numpy()==y))),**metrics(chosen[calyear==y],capital,dates[calyear==y])))
  benchmark=json.loads((OLD/'frozen_rules.json').read_text())[kind];prior=daily(f,mask_for(f,benchmark['feature'],benchmark['side'],benchmark['threshold']));later=(chosen-prior)[calyear>=2025];rng=np.random.default_rng(20261024);bootstrap=[]
  for block in [5,20,60]:
   means=[]
   for _ in range(2000):
    idx=((rng.integers(0,len(later),size=(len(later)+block-1)//block)[:,None]+np.arange(block))%len(later)).ravel()[:len(later)];means.append(float(later[idx].mean()))
   bootstrap.append(dict(block_days=block,mean_daily_increment=float(later.mean()),interval95=np.quantile(means,[.025,.975]).tolist(),scope='2025–July13 2026; conditional tape; previously inspected'))
  prior_mask=mask_for(f,benchmark['feature'],benchmark['side'],benchmark['threshold']);control_cases=[]
  for cost in [0,5,10,25]:control_cases.append(dict(case='extra_package_cost_'+str(cost),**metrics(daily(f,prior_mask,cost),capital,calendar)))
  control_cases.append(dict(case='double_opening_commission',**metrics(daily(f,prior_mask,4.72 if kind=='condor' else 1.18),capital,calendar)))
  z=prior.copy();z[np.argsort(z)[-5:]]=0;control_cases.append(dict(case='remove_five_best_days',**metrics(z,capital,calendar)))
  z=prior.copy();z[np.argsort(z)[:5]]*=1.5;control_cases.append(dict(case='five_worst_days_losses_times_1_5',**metrics(z,capital,calendar)))
  trials=pd.read_csv(OUT/(kind+'_all_trials.csv'));wf=[];wfmask=np.zeros(len(f),dtype=bool)
  for y in [2023,2024,2025,2026]:
   best=None
   for row in trials.itertuples():
    threshold=0 if row.feature=='none' else float(f.loc[f.year<y,row.feature].quantile(row.quantile));m=mask_for(f,row.feature,row.side,threshold);train=m&(f.year.to_numpy()<y);counts=f[train].groupby('year').size().reindex(range(2022,y),fill_value=0)
    if counts.min()<360:continue
    if y==2023:
     score=metrics(daily(f,train,10)[calyear<y],capital,dates[calyear<y]);rank=(score['calmar'],score['pnl'])
    else:
     inner=[]
     for validation_year in range(2023,y):
      th=0 if row.feature=='none' else float(f.loc[f.year<validation_year,row.feature].quantile(row.quantile));inner_mask=mask_for(f,row.feature,row.side,th)&(f.year.to_numpy()==validation_year)
      inner.append(metrics(daily(f,inner_mask,10)[calyear==validation_year],capital,dates[calyear==validation_year]))
     rank=(min(x['calmar'] for x in inner),sum(x['pnl'] for x in inner))
    if best is None or rank>best[0]:best=(rank,row,threshold,m)
   assert best is not None
   rank,row,threshold,m=best;test=m&(f.year.to_numpy()==y);wfmask|=test
   wf.append(dict(year=y,feature=row.feature,side=row.side,threshold=threshold,historical_selection_score=rank[0],trades=int(test.sum()),**metrics(daily(f,test,10)[calyear==y],capital,dates[calyear==y])))
  # Account for searching many rules in a separate mean-P&L diagnostic.
  evaldays=(calyear==2023)|(calyear==2024);diffs=[]
  for row in trials.itertuples():
   pred=np.zeros(len(f),dtype=bool)
   for y in [2023,2024]:
    threshold=0 if row.feature=='none' else float(f.loc[f.year<y,row.feature].quantile(row.quantile));pred|=mask_for(f,row.feature,row.side,threshold)&(f.year.to_numpy()==y)
   diffs.append((daily(f,pred,10)-daily(f,np.ones(len(f),dtype=bool),10))[evaldays])
  matrix=np.array(diffs).T;observed=float(matrix.mean(axis=0).max());centered=matrix-matrix.mean(axis=0);n=len(matrix);weights=np.zeros((1000,n));block=20
  for i in range(1000):
   ix=((rng.integers(0,n,size=(n+block-1)//block)[:,None]+np.arange(block))%n).ravel()[:n];weights[i]=np.bincount(ix,minlength=n)/n
  nullmax=(weights@centered).max(axis=1);p=float((1+np.sum(nullmax>=observed))/(len(nullmax)+1))
  search=dict(rules=len(trials),block_days=20,replicates=1000,observed_max_mean_increment=observed,centered_max_search_tail_fraction=p,method='Max across all rules of centered block-resampled daily P&L increments versus no filter, using historical 2023/2024 walk-forward predictions. Diagnostic for repeated search; not a formal Calmar significance test or proof of robustness.')
  result[kind]=dict(cost_and_tail_cases=cases,control_cost_and_tail_cases=control_cases,threshold_neighbors=neighbors,annual=annual,later_paired_bootstrap=bootstrap,expanding_walk_forward=wf,walk_forward_aggregate=metrics(daily(f,wfmask,10)[calyear>=2023],capital,dates[calyear>=2023]),search_adjusted_diagnostic=search,rolling63_min_pnl=float(pd.Series(chosen).rolling(63).sum().min()),limitations='Fixed native filled tape; no independent options liquidity/margin paths. Tests are development evidence. Fresh July14–October22 native outcomes evaluated only after rule freeze.')
  print(kind,'robustness complete; search tail fraction',p,flush=True)
 (OUT/'robustness.json').write_text(json.dumps(result,indent=2))
if __name__=='__main__':main()
