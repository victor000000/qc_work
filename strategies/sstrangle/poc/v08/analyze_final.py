"""Compare like-for-like full native runs and the frozen incremental interval."""
import json
import pandas as pd
import numpy as np
from optimize import OUT,BASES

def main():
 rows=[];annual=[];decisions={};held_daily={}
 for kind,(_,capital) in BASES.items():
  for stage in ['control','final']:
   key=kind+'_'+stage;p=OUT/(key+'_evidence');ep=pd.read_parquet(p/'episodes.parquet');b=json.loads((p/'backtest.json').read_text())['backtest'];s=b['statistics'];rt=b['runtimeStatistics'];c=json.loads((OUT/(key+'_consistency.json')).read_text());assert c['funding_explained'] and c['max_common_pnl_difference']<1e-5
   cagr=float(s['Compounding Annual Return'].strip('%'))/100;dd=float(s['Drawdown'].strip('%'))/100
   row=dict(strategy=kind,stage=stage,capital=capital,trades=len(ep),net_pnl=float(ep.pnl.sum()),cagr=cagr,native_mdd=dd,calmar=cagr/dd,minimum_annual=int(ep.groupby('year').size().min()),legacy_pnl=float(ep.loc[ep.day<='2026-07-13','pnl'].sum()),held_interval_pnl=float(ep.loc[ep.day>'2026-07-13','pnl'].sum()),held_interval_trades=int((ep.day>'2026-07-13').sum()),min_margin_remaining=float(rt['min_margin_remaining_1m']),max_margin_used=float(rt['max_margin_used_1m']))
   prices=pd.read_parquet(OUT/'provider/us_prices_full/data.parquet');sessions=sorted(prices.loc[(prices.symbol=='SPY')&(prices.date.astype(str)>'2026-07-13'),'date'].astype(str));held_daily[kind+'_'+stage]=ep.groupby('day').pnl.sum().reindex(sessions,fill_value=0)
   assert row['minimum_annual']>=360;rows.append(row)
   for year,g in ep.groupby('year'):annual.append(dict(strategy=kind,stage=stage,year=int(year),trades=len(g),pnl=float(g.pnl.sum())))
  old,new=rows[-2:];delta=(held_daily[kind+'_final']-held_daily[kind+'_control']).to_numpy();rng=np.random.default_rng(20261024);samples=[]
  for _ in range(2000):
   ix=((rng.integers(0,len(delta),size=(len(delta)+4)//5)[:,None]+np.arange(5))%len(delta)).ravel()[:len(delta)];samples.append(float(delta[ix].mean()))
  verdict=('Candidate improves full native Calmar and reserved-interval total profit; retain for research, with robustness still unproven.' if new['calmar']>old['calmar'] and new['held_interval_pnl']>old['held_interval_pnl'] else 'Retain Draft 0.7 as the preferred reference: the new candidate does not improve both native Calmar and reserved-interval profit.')
  decisions[kind]=dict(verdict=verdict,held_daily_increment=float(delta.mean()),held_block5_interval95=np.quantile(samples,[.025,.975]).tolist(),native_verified=True,annual_gate=True,full_profit_improved=new['net_pnl']>old['net_pnl'],native_calmar_improved=new['calmar']>old['calmar'],held_interval_profit_improved=new['held_interval_pnl']>old['held_interval_pnl'],held_interval_increment=new['held_interval_pnl']-old['held_interval_pnl'],robust_alpha_proven=False,interpretation='Technical verification is separate from economic preference. Historical bootstrap intervals include zero and adaptive annual selection fails some frequency gates. No robust or production-ready alpha claim.')
 pd.DataFrame(rows).to_csv(OUT/'final_comparison.csv',index=False);pd.DataFrame(annual).to_csv(OUT/'final_annual.csv',index=False)
 (OUT/'final_findings.json').write_text(json.dumps(dict(decisions=decisions,robustness=json.loads((OUT/'robustness.json').read_text()),scope='Native May16 2022–October22 2026 plus settlement tail throughOctober24. July14–October22 interval reserved before new native outcome inspection. Original period repeatedly inspected; one short held historical interval is not prospective live proof.'),indent=2));print(pd.DataFrame(rows).to_string(index=False))
if __name__=='__main__':main()
