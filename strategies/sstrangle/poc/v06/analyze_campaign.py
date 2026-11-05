"""Compare funded baselines and conditional matched episode sets without rerunning QC."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[4]
BASE=ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023'
OLD=ROOT/'strategies/sstrangle/results/qc_baseline_poc_20261023/full_v5_evidence'

def pct(s):return float(str(s).strip('%'))/100

def describe(f):
 daily=f.groupby('day').pnl.sum()
 return dict(worst_day=float(daily.min()) if len(daily) else None,worst_day_date=str(daily.idxmin()) if len(daily) else None,episodes=len(f),net_pnl=float(f.pnl.sum()),win_rate=float((f.pnl>0).mean()) if len(f) else None,
 mean_pnl=float(f.pnl.mean()) if len(f) else None,days=int(f.day.nunique()),
 worst_episode=float(f.pnl.min()) if len(f) else None,best_episode=float(f.pnl.max()) if len(f) else None)

def main():
 p=argparse.ArgumentParser();p.add_argument('--condor',default='condor_full_v1');p.add_argument('--strangle',default='strangle_full_v2');p.add_argument('--put',default='put_full_v3');a=p.parse_args()
 output=BASE/'analysis';output.mkdir(exist_ok=True)
 folders={'condor_v05':OLD,**{k:BASE/(getattr(a,k)+'_evidence') for k in ['condor','strangle','put']}}
 frames={};summaries=[];annuals=[];hours=[];days={};identities={}
 for name,folder in folders.items():
  f=pd.read_parquet(folder/'episodes.parquet');audit=json.loads((folder/'audit.json').read_text());b=json.loads((folder/'backtest.json').read_text())['backtest'];rt=b['runtimeStatistics'];stats=b['statistics']
  assert audit['native_cloud_terminal_success'] and audit['annual_pass']
  frames[name]=f;identities[name]=dict(project_id=b['projectId'],backtest_id=b['backtestId'],source_sha256=audit['source_sha256'])
  row=dict(strategy=name,**describe(f),capital=float(stats['Start Equity']),ending_equity=float(stats['End Equity']),cagr=pct(stats['Compounding Annual Return']),native_mdd=pct(stats['Drawdown']),fees=audit['event_fees'],orders=audit['orders'],fills=audit['fill_events'],rejections=audit['rejected_episodes'],max_margin_used_1m=float(rt['max_margin_used_1m']) if 'max_margin_used_1m' in rt else None,minimum_margin_remaining_1m=float(rt['min_margin_remaining_1m']) if 'min_margin_remaining_1m' in rt else None)
  row['calmar']=row['cagr']/row['native_mdd'] if row['native_mdd'] else None
  row['return_on_initial']=row['net_pnl']/row['capital'];row['margin_peak_over_initial']=row['max_margin_used_1m']/row['capital'] if row['max_margin_used_1m'] is not None else None
  summaries.append(row)
  yearly=pd.read_csv(folder/'annual.csv');yearly.insert(0,'strategy',name);annuals.append(yearly)
  daily=f.groupby('day').pnl.sum();days[name]=daily
  byhour=f.assign(slot=pd.to_datetime(f.decision_at).dt.strftime('%H:%M')).groupby('slot').agg(episodes=('episode','size'),net_pnl=('pnl','sum'),mean_pnl=('pnl','mean'));byhour.insert(0,'strategy',name);hours.append(byhour.reset_index())
  # Daily realized outcomes are attribution, not intraday marked drawdown.
  daily.rename('pnl').to_csv(output/(name+'_daily.csv'))
 pd.DataFrame(summaries).to_csv(output/'comparison.csv',index=False)
 pd.concat(annuals,ignore_index=True).to_csv(output/'annual.csv',index=False)
 pd.concat(hours,ignore_index=True).to_csv(output/'entry_slot.csv',index=False)
 calendar=json.loads((BASE/'calendar_inventory.json').read_text())
 daily_table=pd.DataFrame(days).fillna(0)
 assert set(daily_table.index).issubset(calendar['session_dates'])
 daily_table=daily_table.reindex(calendar['session_dates'],fill_value=0)
 daily_table.index.name='day';daily_table.to_csv(output/'daily_pnl.csv')
 daily_table.corr().to_csv(output/'daily_pnl_correlation.csv')
 old,new=frames['condor_v05'],frames['condor']
 same=new.merge(old,on='episode',suffixes=('_new','_old'))
 added=new[~new.episode.isin(old.episode)];lost=old[~old.episode.isin(new.episode)]
 overlap=dict(common_episodes=len(same),added=describe(added),lost=describe(lost),common_pnl_difference=float((same.pnl_new-same.pnl_old).sum()),common_max_abs_pnl_difference=float((same.pnl_new-same.pnl_old).abs().max()))
 added.to_parquet(output/'condor_added.parquet',index=False);lost.to_parquet(output/'condor_lost.parquet',index=False)
 common_keys=set.intersection(*(set(frames[k].episode) for k in ['condor','strangle','put']))
 common={k:describe(frames[k][frames[k].episode.isin(common_keys)]) for k in ['condor','strangle','put']}
 rt=json.loads((folders['condor']/'backtest.json').read_text())['backtest']['runtimeStatistics']
 funded_reasons={k:int(v) for k,v in rt.items() if k!='wing_policy' and k.startswith(('wing_','original_wing_','recovered_','skip_'))}
 admission=json.loads((BASE/'admission_diagnostic.json').read_text())
 reasons=admission['counts']
 assert reasons['skip_missing_20point_wing']==int(rt['original_wing_skips'])==3606
 delta_audit={}
 for label,subset in [('all',new),('recovered',new[new.recovered]),('original_admissible',new[~new.recovered])]:
  delta_audit[label]={'episodes':len(subset)}
  for field,target,anchor in [('put_delta',-.20,'anchor_pd'),('call_delta',.08,'anchor_cd')]:
   error=(subset[field]-target).abs()
   delta_audit[label][field+'_target_error']=dict(median=float(error.median()),p95=float(error.quantile(.95)),maximum=float(error.max()))
   shift=(subset[field]-subset[anchor]).abs()
   delta_audit[label][field+'_anchor_shift']=dict(median=float(shift.median()),p95=float(shift.quantile(.95)),maximum=float(shift.max()))
 tolerance_rows=[]
 for limit in [.02,.05,.10,None]:
  keep=new if limit is None else new[(new.put_delta+.20).abs().le(limit)&(new.call_delta-.08).abs().le(limit)]
  row=dict(max_absolute_delta_error=limit,episodes=len(keep),scope='Conditional count on realized funded tape; not a rerun or funded filtered portfolio')
  row.update({str(year):int((keep.year==year).sum()) for year in range(2022,2027)})
  tolerance_rows.append(row)
 pd.DataFrame(tolerance_rows).to_csv(output/'conditional_delta_tolerance_counts.csv',index=False)
 diag=dict(conditional_delta_tolerance_counts=tolerance_rows,admission_replay=admission,funded_runtime_counters=funded_reasons,recovered_delta_audit=delta_audit,original_3606_reproduced=int(rt.get('original_wing_skips',-1))==3606,reasons=reasons,overlap=overlap,
 source_trade_count=13492,old_count=len(old),new_count=len(new),old_gap=13492-len(old),new_gap=13492-len(new))
 combined={k:v for k,v in reasons.items() if k.startswith('wing_reason_')}
 diag['reason_summary']=dict(slots_with_age_rejection=sum(v for k,v in combined.items() if '_age' in k),slots_with_crossed_rejection=sum(v for k,v in combined.items() if '_crossed' in k),slots_with_absent_chain_wing=sum(v for k,v in combined.items() if '_absent_chain' in k),scope='Categories can overlap; each combined wing_reason key is mutually exclusive')
 diag['admission_funnel']=dict(scheduled_attempts=reasons['scheduled_slots'],missing_chain=reasons['skip_no_chain'],missing_short_delta_or_quotes=reasons['skip_missing_delta_or_quotes'],original_admitted=reasons['diag_admitted_original'],original_wing_skips=3606,recoverable_exact_pair_slots=reasons['wing_recoverable_pair_search'],no_admissible_pair=3606-reasons['wing_recoverable_pair_search'],native_submitted=int(rt['submitted_episodes']),native_rejected=int(rt['skip_native_rejected_zero_fill']),native_completed=len(new),calendar_close_boundary_attempts=9)
 funnel=diag['admission_funnel']
 assert funnel['original_admitted']+funnel['recoverable_exact_pair_slots']==funnel['native_submitted']
 assert funnel['native_submitted']-funnel['native_rejected']==len(new)
 assert funnel['scheduled_attempts']-funnel['missing_chain']-funnel['missing_short_delta_or_quotes']-funnel['no_admissible_pair']==funnel['native_submitted']
 diag['source_display']=dict(net_pnl=101790,ending_capital=201790,cagr=.184,mdd=.611,episodes=13492,scope='Saved audio/demo display, not an independently audited trade export')
 diag['pnl_difference_from_source_display']=dict(old=float(old.pnl.sum()-101790),revised=float(new.pnl.sum()-101790))
 diag['gap_closed_fraction']=(len(new)-len(old))/(13492-len(old))
 (output/'wing_diagnosis.json').write_text(json.dumps(diag,indent=2)+'\n')
 # Realized daily block bootstrap of unconditional mean; descriptive, no model selection.
 rng=np.random.default_rng(20261023);boot={}
 for k in ['condor','strangle','put']:
  values=daily_table[k].to_numpy();n=len(values);means=[]
  for i in range(2000):
   starts=rng.integers(0,n,size=(n+4)//5);idx=(starts[:,None]+np.arange(5))%n
   means.append(float(values[idx.ravel()[:n]].mean()))
  boot[k]=dict(mean_daily_pnl=float(values.mean()),block5_95_percentile_interval=np.quantile(means,[.025,.975]).tolist(),replicates=2000,seed=20261023)
 coverage={k:dict(zero_entry_days=sorted(set(calendar['session_dates'])-set(f.day)),eligible_calendar_slots=13492,completed_episodes=len(f)) for k,f in frames.items()}
 results=dict(coverage=coverage,summaries=summaries,identities=identities,wing_diagnosis=diag,
 matched_slot_comparison=common,matched_slot_scope='Conditional P&L comparison only; no funded filtered or combined portfolio result',
 block_bootstrap=boot,bootstrap_scope='Descriptive circular five-trading-day resampling; overlapping episodes grouped by day; not untouched OOS or proof of independent stationarity')
 (output/'findings.json').write_text(json.dumps(results,indent=2)+'\n')
 (output/'manifest.json').write_text(json.dumps({'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file() and p.name!='manifest.json'}},indent=2)+'\n')
 print(json.dumps(results,indent=2))
if __name__=='__main__':main()
