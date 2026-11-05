"""Native results and decision record; never replace the frozen selected rules."""
import json
import numpy as np
import pandas as pd
from campaign import ROOT,OUT,save,ACTIVE_KINDS
from research import calendar

def main():
 rows=[];annual=[];decisions={};verification=json.loads((OUT/'final_verification.json').read_text());settlement=json.loads((OUT/'official_settlement_audit.json').read_text())
 for kind in ACTIVE_KINDS:
  daily={}
  for stage in ['baseline','final']:
   key=kind+'_'+stage;folder=OUT/(key+'_evidence');ep=pd.read_parquet(folder/'episodes.parquet');b=json.loads((folder/'backtest.json').read_text())['backtest'];stats=b['statistics'];rt=b['runtimeStatistics']
   cagr=float(stats['Compounding Annual Return'].strip('%'))/100;dd=float(stats['Drawdown'].strip('%'))/100
   row=dict(strategy=kind,stage=stage,trades=len(ep),capital=100000,net_pnl=float(ep.pnl.sum()),cagr=cagr,native_mdd=dd,calmar=cagr/dd if dd else None,minimum_annual=int(ep.groupby('year').size().min()),evaluation_pnl=float(ep.loc[ep.year>=2025,'pnl'].sum()),evaluation_trades=int((ep.year>=2025).sum()),minimum_margin_remaining=float(rt['min_margin_remaining_1m']),maximum_margin_used=float(rt['max_margin_used_1m']),project_id=b['projectId'],backtest_id=b['backtestId'],official_settlement_cash_sensitivity=settlement[key]['sum_official_minus_native_expiry'])
   rows.append(row)
   for y,g in ep.groupby('year'):annual.append(dict(strategy=kind,stage=stage,year=int(y),trades=len(g),pnl=float(g.pnl.sum()),partial_year=int(y) in [2022,2026],passed=len(g)>=360))
   daily[stage]=ep.groupby('day').pnl.sum().reindex(calendar,fill_value=0)
  baseline,final=rows[-2:];later=np.array(calendar)>='2025-01-01';delta=(daily['final']-daily['baseline']).to_numpy()[later];rng=np.random.default_rng(85026)
  boots={}
  for block in [5,20,60]:
   starts=rng.integers(0,len(delta),size=(2000,int(np.ceil(len(delta)/block))));ix=((starts[:,:,None]+np.arange(block))%len(delta)).reshape(2000,-1)[:,:len(delta)]
   boots[str(block)]=np.quantile(delta[ix].mean(axis=1),[.025,.975]).tolist()
  economic=final['calmar']>baseline['calmar'] and final['evaluation_pnl']>baseline['evaluation_pnl']
  decisions[kind]=dict(native_calmar_improved=final['calmar']>baseline['calmar'],later_profit_improved=final['evaluation_pnl']>baseline['evaluation_pnl'],later_profit_increment=final['evaluation_pnl']-baseline['evaluation_pnl'],later_daily_increment=float(delta.mean()),native_block_bootstrap95=boots,verdict='Retain candidate as a historical research variant' if economic else 'Retain unfiltered reference; selected filter did not improve both native Calmar and later profit',economic_comparison_pass=economic,frequency_pass=final['minimum_annual']>=360,nonnegative_sampled_margin=final['minimum_margin_remaining']>=0,official_settlement_parity=settlement[kind+'_final']['days_differ_over_001']==0 and not settlement[kind+'_final']['missing_days'],production_ready=False)
 pd.DataFrame(rows).to_csv(OUT/'final_comparison.csv',index=False);pd.DataFrame(annual).to_csv(OUT/'final_annual.csv',index=False)
 save(OUT/'decision_record.json',decisions)
 versions=[]
 for label,folder in [('v0.7 frozen reference extended',ROOT/'strategies/sstrangle/results/qc_sizing_poc_20261024/condor_control_evidence'),('v0.8 frozen candidate',ROOT/'strategies/sstrangle/results/qc_sizing_poc_20261024/condor_final_evidence'),('v0.8.5 frozen candidate',OUT/'condor_final_evidence')]:
  b=json.loads((folder/'backtest.json').read_text())['backtest'];ep=pd.read_parquet(folder/'episodes.parquet');s=b['statistics'];dd=float(s['Drawdown'].strip('%'))/100;cagr=float(s['Compounding Annual Return'].strip('%'))/100
  versions.append(dict(version=label,trades=len(ep),net_pnl=float(ep.pnl.sum()),native_mdd=dd,calmar=cagr/dd,later_2025_2026_pnl=float(ep.loc[ep.year>=2025,'pnl'].sum()),source=str(folder),backtest_id=b['backtestId']))
 pd.DataFrame(versions).to_csv(OUT/'cross_version_condor_comparison.csv',index=False)
 print(pd.DataFrame(rows).to_string(index=False))
if __name__=='__main__':main()
