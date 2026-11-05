"""Payoff-envelope diagnostic from genuine condor openings, not a new margin model."""
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd

def evaluate(folder):
 e=pd.read_parquet(folder/'episodes.parquet');legs=pd.read_parquet(folder/'legs.parquet')
 b=json.loads((folder/'backtest.json').read_text())['backtest'];rt=b['runtimeStatistics']
 if rt.get('strategy_kind','condor')!='condor':raise ValueError('Only bounded condor fixture')
 out=[]
 grouped_legs={key:g for key,g in legs.groupby("episode")}
 for day,df in e.groupby('day'):
  accumulated=[];credit=0;fees=0
  for row in df.sort_values('decision_at').itertuples():
   current=grouped_legs[row.episode];accumulated.append(current);credit+=row.entry_credit;fees+=row.opening_fees
   all_legs=pd.concat(accumulated,ignore_index=True);strikes=sorted(all_legs.strike.unique());spots=np.array([0,*strikes,max(strikes)+1])
   pnl=np.full(len(spots),credit-fees,dtype=float)
   for leg in all_legs.itertuples():pnl+=leg.quantity*100*np.maximum(0,spots-leg.strike if leg.right=='C' else leg.strike-spots)
   # Equal call tails make this a bounded piecewise-linear terminal payoff.
   assert int(all_legs.loc[all_legs.right=='C','quantity'].sum())==0
   out.append(dict(day=day,episode=row.episode,opened_episodes=len(accumulated),terminal_worst_net_pnl=float(pnl.min()),initial_capital_at_risk=max(0,float(-pnl.min()))))
 frame=pd.DataFrame(out);frame.to_parquet(folder/'terminal_payoff_envelope.parquet',index=False)
 summary=dict(max_terminal_net_loss_envelope=float(frame.initial_capital_at_risk.max()),native_max_margin_used_1m=float(rt['max_margin_used_1m']) if 'max_margin_used_1m' in rt else None,
 interpretation='Static terminal payoff envelope of accumulated actual openings; costs included. This is not intraday marked drawdown, a replacement margin model, or proof of available buying power. Maxima need not occur at the same time.')
 (folder/'terminal_payoff_envelope.json').write_text(json.dumps(summary,indent=2)+'\n');print(summary)
 return frame,summary
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('folder',type=Path);evaluate(p.parse_args().folder)
