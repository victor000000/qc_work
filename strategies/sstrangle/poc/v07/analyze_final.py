"""Compare original baselines, local candidates and final native funded runs."""
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from optimize import ROOT,OUT,BASES,cash_metrics

def main():
 rules=json.loads((OUT/'frozen_rules.json').read_text());calendar=json.loads((ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023/calendar_inventory.json').read_text())['session_dates'];rows=[];annual=[];daily={};conclusions={}
 for kind,(key,base,capital) in BASES.items():
  final=OUT/(kind+'_alpha_full_evidence');cons=json.loads((OUT/(kind+'_alpha_full_consistency.json')).read_text());assert cons['funding_differences_explained'] and cons['max_common_pnl_difference']<1e-5 and not cons['common_contract_mismatches']
  for role,folder in [('baseline',base),('final_qc',final)]:
   f=pd.read_parquet(folder/'episodes.parquet');b=json.loads((folder/'backtest.json').read_text())['backtest'];a=json.loads((folder/'audit.json').read_text());assert a['native_cloud_terminal_success'] and a['annual_pass'];s=b['statistics']
   cagr=float(s['Compounding Annual Return'].strip('%'))/100;dd=float(s['Drawdown'].strip('%'))/100
   rows.append(dict(strategy=kind,stage=role,capital=capital,trades=len(f),net_pnl=float(f.pnl.sum()),cagr=cagr,native_mdd=dd,calmar=cagr/dd,min_annual=int(f.groupby('year').size().min()),later_pnl=float(f.loc[f.year>=2025,'pnl'].sum()),max_margin_used=float(b['runtimeStatistics'].get('max_margin_used_1m','nan')),min_margin_remaining=float(b['runtimeStatistics'].get('min_margin_remaining_1m','nan'))))
   for year,g in f.groupby('year'):annual.append(dict(strategy=kind,stage=role,year=int(year),trades=len(g),pnl=float(g.pnl.sum())))
   daily[kind+'_'+role]=f.groupby('day').pnl.sum().reindex(calendar,fill_value=0)
  r=rules[kind];selected=pd.read_parquet(OUT/(kind+'_local_selected.parquet'))
  rows.append(dict(strategy=kind,stage='local_conditional',capital=capital,trades=len(selected),net_pnl=float(selected.pnl.sum()),cagr=None,native_mdd=None,calmar=None,min_annual=int(selected.groupby('year').size().min()),later_pnl=float(selected.loc[selected.year>=2025,'pnl'].sum()),daily_cash_cagr=r['full_local']['cagr'],daily_cash_mdd=r['full_local']['daily_cash_dd'],daily_cash_calmar=r['full_local']['calmar']))
  for year,g in selected.groupby('year'):annual.append(dict(strategy=kind,stage='local_conditional',year=int(year),trades=len(g),pnl=float(g.pnl.sum())))
  native=next(x for x in rows if x['strategy']==kind and x['stage']=='final_qc');baseline=next(x for x in rows if x['strategy']==kind and x['stage']=='baseline')
  diff=(daily[kind+'_final_qc']-daily[kind+'_baseline']);later=diff[diff.index>='2025-01-01'].to_numpy();rng=np.random.default_rng(20261024);samples=[]
  for i in range(2000):
   idx=((rng.integers(0,len(later),size=(len(later)+4)//5)[:,None]+np.arange(5))%len(later)).ravel()[:len(later)];samples.append(float(later[idx].mean()))
  decision=('Reject this filter: final native risk-adjusted performance does not improve the baseline.' if native['calmar']<=baseline['calmar'] else ('Retain only as a fragile research candidate: native Calmar improves, but 2025–2026 profit is nonpositive.' if native['later_pnl']<=0 else 'Retain for further prospective research: native Calmar improves and 2025–2026 profit stays positive; no deployment promotion.'))
  conclusions[kind]=dict(rule={k:r[k] for k in ['feature','quantile','side','threshold','train_calmar','trials','eligible_trials']},native_verification_pass=True,annual_gate=True,research_decision=decision,full_native_calmar_improves=native['calmar']>baseline['calmar'],full_native_pnl_improves=native['net_pnl']>baseline['net_pnl'],later_total_pnl_improves=native['later_pnl']>baseline['later_pnl'],later_daily_increment=float(later.mean()),later_daily_increment_block5_95=np.quantile(samples,[.025,.975]).tolist(),consistency=cons,interpretation='Final funded QC verification is complete; retrospective performance improvement and prospective acceptance are separate decisions. Bootstrap is descriptive, not selection adjusted.')
 pd.DataFrame(rows).to_csv(OUT/'final_comparison.csv',index=False);pd.DataFrame(annual).to_csv(OUT/'final_annual.csv',index=False);pd.DataFrame(daily).rename_axis('day').to_csv(OUT/'final_daily.csv')
 control=json.loads((OUT/'condor_control_full_consistency.json').read_text());assert control['native_episodes']==control['local_expected_episodes'] and control['max_common_pnl_difference']<1e-5 and not control['common_contract_mismatches']
 result=dict(baseline_recheck=json.loads((OUT/'baseline_recheck.json').read_text()),fresh_control=control,strategies=conclusions,scope='Source period2022-05-16–2026-07-13; partial2022/2026; all periods development; no independent vendor option-price or margin reproduction claimed')
 (OUT/'final_findings.json').write_text(json.dumps(result,indent=2));print(pd.DataFrame(rows).to_string(index=False))
if __name__=='__main__':main()
