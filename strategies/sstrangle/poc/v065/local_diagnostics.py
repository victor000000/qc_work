"""Daily-cluster diagnostics for training-selected filters; no reselection."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import duckdb
from local_features import OUT,ROOT
P=OUT/'local';summary=json.loads((P/'summary.json').read_text());registry=json.loads((P/'feature_registry.json').read_text())
calendar=json.loads((ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023/calendar_inventory.json').read_text())['session_dates']
results={};db=duckdb.connect(str(P/'research.duckdb'))
for key,item in summary['datasets'].items():
 f=pd.read_parquet(P/(key+'_features.parquet'));labels=pd.read_parquet(P/(key+'_labels.parquet'))
 # Explicit joining for research only. Physical feature files never carry labels.
 assert not {'pnl','settlement_spot','entry_credit','expiry_cash_attribution'}.intersection(f.columns)
 for suffix,frame in [('features',f),('labels',labels)]:
  db.register('tmp',frame);db.execute(f'CREATE OR REPLACE TABLE {key}_{suffix} AS SELECT * FROM tmp');db.unregister('tmp')
 selected=item['selected_by_training_only'];name=selected['feature'];threshold=selected['threshold']
 epfolder=ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023'/({'v06_control':'condor_full_v1','strangle_v06':'strangle_full_v2','put_v06':'put_full_v3'}.get(key,'')+'_evidence') if key in ['v06_control','strangle_v06','put_v06'] else OUT/(key+'_evidence')
 ep=pd.read_parquet(epfolder/'episodes.parquet');d=f.merge(ep[['episode','pnl','day','year']],on='episode',validate='one_to_one')
 mask=d[name]>threshold if selected['side']=='above' else d[name]<=threshold
 daily=pd.DataFrame({'baseline':d.groupby('day').pnl.sum(),'selected':d[mask].groupby('day').pnl.sum()}).fillna(0).reindex(calendar,fill_value=0)
 daily['difference']=daily.selected-daily.baseline;daily.to_csv(P/(key+'_selected_daily.csv'))
 later=daily[daily.index>='2025-01-01'];rng=np.random.default_rng(20261024);means=[];n=len(later)
 for i in range(2000):
  idx=((rng.integers(0,n,size=(n+4)//5)[:,None]+np.arange(5))%n).ravel()[:n]
  means.append(later.iloc[idx][['selected','difference']].mean().to_numpy())
 intervals=np.quantile(means,[.025,.975],axis=0)
 candidates=[k for k,v in registry.items() if v['screen_eligible']]
 corr=d.loc[d.year<=2023,candidates].corr(method='spearman');upper=np.triu(np.ones(corr.shape,dtype=bool),1)
 corr.to_parquet(P/(key+'_training_spearman.parquet'))
 neighborhood=[]
 for quantile in [.4,.5,.6]:
  cut=float(d.loc[d.year<=2023,name].quantile(quantile));keep=d[name]>cut if selected['side']=='above' else d[name]<=cut
  counts=d[keep].groupby('year').size().reindex(range(2022,2027),fill_value=0)
  neighborhood.append(dict(training_quantile=quantile,threshold=cut,later_pnl=float(d.loc[keep&(d.year>=2025),'pnl'].sum()),annual_counts={str(y):int(c) for y,c in counts.items()},annual_pass=bool(counts.ge(360).all()),scope='sensitivity only; no changing chosen threshold'))
 results[key]=dict(selected_feature=name,full_period_selected_pnl=float(d.loc[mask,'pnl'].sum()),later_mean_daily_selected=float(later.selected.mean()),later_mean_daily_increment=float(later.difference.mean()),block5_selected_mean_95=intervals[:,0].tolist(),block5_increment_mean_95=intervals[:,1].tolist(),correlated_candidate_pairs_abs_rho_above_095=int(((corr.abs()>.95)&upper).sum().sum()),candidate_pairs=len(candidates)*(len(candidates)-1)//2,neighborhood=neighborhood,scope='Descriptive daily block bootstrap; not selection-adjusted, no independent OOS or funded filtered account claim')
db.close();(P/'diagnostics.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
