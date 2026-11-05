"""Audited native delta experiment comparisons; explicit conditional sensitivities."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'strategies/sstrangle/results/qc_delta_poc_20261024';DEST=OUT/'analysis';DEST.mkdir(exist_ok=True)
folders={'v05':ROOT/'strategies/sstrangle/results/qc_baseline_poc_20261023/full_v5_evidence','v06':ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023/condor_full_v1_evidence'}
for key in ['condor_full_t02','condor_full_t05']:
 p=OUT/(key+'_evidence')
 if (p/'audit.json').exists():folders[key]=p
frames={};rows=[];annual=[];sensitivity=[];overlaps={};groups=[]
for key,p in folders.items():
 a=json.loads((p/'audit.json').read_text());assert a['native_cloud_terminal_success'] and a['annual_pass']
 b=json.loads((p/'backtest.json').read_text())['backtest'];rt=b['runtimeStatistics'];stats=b['statistics'];f=pd.read_parquet(p/'episodes.parquet');frames[key]=f
 row=dict(key=key,trades=len(f),pnl=float(f.pnl.sum()),gap_to_oo=float(f.pnl.sum()-101790),trade_gap=13492-len(f),cagr=float(stats['Compounding Annual Return'].strip('%'))/100,native_mdd=float(stats['Drawdown'].strip('%'))/100,win_rate=float((f.pnl>0).mean()),mean_win=float(f.loc[f.pnl>0,'pnl'].mean()),mean_loss=float(f.loc[f.pnl<=0,'pnl'].mean()),opening_credit=float(f.entry_credit.sum()),fees=float(f.opening_fees.sum()),expiry_cash=float(f.expiry_cash_attribution.sum()),rejections=a['rejected_episodes'],project_id=b['projectId'],backtest_id=b['backtestId'])
 row['min_margin_remaining']=float(rt['min_margin_remaining_1m']) if 'min_margin_remaining_1m' in rt else None;row['max_margin_used']=float(rt['max_margin_used_1m']) if 'max_margin_used_1m' in rt else None
 row['calmar']=row['cagr']/row['native_mdd'];row['eod_cash_mdd']=float((1-(100000+f.groupby('day').pnl.sum().cumsum())/(100000+f.groupby('day').pnl.sum().cumsum()).cummax().clip(lower=100000)).max())
 for field,target in [('put_delta',-.20),('call_delta',.08)]:
  err=(f[field]-target).abs();row[field+'_error_p95']=float(err.quantile(.95));row[field+'_error_max']=float(err.max())
 counts=f.groupby('year').size().reindex(range(2022,2027),fill_value=0);assert counts.ge(360).all();row['min_annual']=int(counts.min());rows.append(row)
 for y,g in f.groupby('year'):annual.append(dict(key=key,year=int(y),trades=len(g),pnl=float(g.pnl.sum())))
 for cost in [0,2.5,5,10]:sensitivity.append(dict(key=key,extra_cost_per_episode=cost,conditional_pnl=float(f.pnl.sum()-cost*len(f)),scope='fixed tape extra package cost, no funding rerun'))
 leg=pd.read_parquet(p/'legs.parquet').merge(f[['episode','settlement_spot']],on='episode',validate='many_to_one')
 for shift in [-1,1]:
  spot=leg.settlement_spot+shift
  intrinsic=np.where(leg.right=='P',np.maximum(leg.strike-spot,0),np.maximum(spot-leg.strike,0))
  cash=float((leg.quantity*intrinsic*100).sum());sensitivity.append(dict(key=key,settlement_shift_points=shift,conditional_pnl=float(f.entry_credit.sum()-f.opening_fees.sum()+cash),scope='hypothetical uniform terminal-reference shift; NOT measured vendor discrepancy'))
 for name,g in [('all',f)]+([('recovered',f[f.recovered]),('original',f[~f.recovered])] if 'recovered' in f else []):
  groups.append(dict(key=key,group=name,trades=len(g),pnl=float(g.pnl.sum()),credit=float(g.entry_credit.sum()),expiry=float(g.expiry_cash_attribution.sum()),fees=float(g.opening_fees.sum())))
base=frames['v06']
for key,f in frames.items():
 if key=='v06':continue
 same=f.merge(base,on='episode',suffixes=('_test','_base'));added=f[~f.episode.isin(base.episode)];removed=base[~base.episode.isin(f.episode)]
 overlaps[key]=dict(common=len(same),common_pnl_change=float((same.pnl_test-same.pnl_base).sum()),max_common_abs_change=float((same.pnl_test-same.pnl_base).abs().max()),added=len(added),added_pnl=float(added.pnl.sum()),removed=len(removed),removed_pnl=float(removed.pnl.sum()),identity_check=float(f.pnl.sum()-base.pnl.sum()-(same.pnl_test-same.pnl_base).sum()-added.pnl.sum()+removed.pnl.sum()))
pd.DataFrame(rows).to_csv(DEST/'comparison.csv',index=False);pd.DataFrame(annual).to_csv(DEST/'annual.csv',index=False);pd.DataFrame(groups).to_csv(DEST/'admission_groups.csv',index=False);pd.DataFrame(sensitivity).to_csv(DEST/'sensitivities.csv',index=False)
(DEST/'findings.json').write_text(json.dumps(dict(comparisons=rows,matched=overlaps,source=dict(pnl=101790,trades=13492,premium=3241715,win_rate=.811,mean_win=229,mean_loss=-942),gap_interpretation='Source is rounded display without trade export. Delta, quote, settlement and fee differences cannot be uniquely identified from aggregate P&L. Sensitivities never modify native results.'),indent=2))
print(pd.DataFrame(rows)[['key','trades','pnl','gap_to_oo','min_annual']].to_string(index=False))
# Supporting gap diagnostics, reproducible from pinned native and feature tapes.
f=frames['v06'];cols=['episode','put_delta','call_delta','entry_credit','pnl','recovered']
f.nlargest(20,'pnl')[cols].to_csv(DEST/'control_largest_wins.csv',index=False)
n0=13492;p0=10941/n0;w0=229;l0=-942;n=len(f);pwin=(f.pnl>0).mean();w=f.loc[f.pnl>0,'pnl'].mean();loss=f.loc[f.pnl<=0,'pnl'].mean();mu0=p0*w0+(1-p0)*l0
bridge=dict(source_rounded_reconstruction=n0*mu0,source_display_rounding_residual=101790-n0*mu0,count_effect=(n-n0)*mu0,win_frequency_effect=n*(pwin-p0)*(w0-l0),mean_winner_effect=n*pwin*(w-w0),mean_loser_effect=n*(1-pwin)*(loss-l0),scope='Sequential algebra on differing populations and rounded source means; NOT causal or matched trade attribution')
(DEST/'rounded_display_bridge.json').write_text(json.dumps(bridge,indent=2))
features=pd.read_parquet(OUT/'local/v06_control_features.parquet');features['t02_pass']=(features.put_delta+.20).abs().le(.02)&(features.call_delta-.08).abs().le(.02);features['rv_bucket']=pd.qcut(features.spy_rv_20,5,labels=False)+1
features.groupby('rv_bucket').agg(episodes=('episode','size'),mean_prior_spy_rv20=('spy_rv_20','mean'),t02_eligible=('t02_pass','sum'),retention=('t02_pass','mean')).to_csv(DEST/'control_delta_retention_by_prior_rv.csv')
features['slot']=features.decision_at.dt.tz_convert('America/New_York').dt.strftime('%H:%M')
features.groupby('slot').agg(episodes=('episode','size'),t02_eligible=('t02_pass','sum'),retention=('t02_pass','mean')).to_csv(DEST/'control_delta_retention_by_slot.csv')
