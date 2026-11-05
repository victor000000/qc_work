import json,statistics
from pathlib import Path
from datetime import date,timedelta
P=Path(__file__).parent;old=P.parent/'automatic_20261025';name='SS45DTE_AUTO_ONEPAIR_COST_V6'
r=json.loads((old/(name+'.reconciliation.json')).read_text());orders=json.loads((old/(name+'.orders.json')).read_text());es=r['episode_summary'];p=[e['net_pnl'] for e in es];wins=[v for v in p if v>0];losses=[v for v in p if v<0]
active=set();position_days=0
for e in es:
 a=date.fromisoformat(e['entry_day']);b=date.fromisoformat(e['exit_day']);position_days+=(b-a).days
 for i in range((b-a).days):active.add(a+timedelta(days=i))
spread=sum((o['orderSubmissionData']['askPrice']-o['orderSubmissionData']['bidPrice'])/2*100*abs(o['quantity']) for o in orders)
result={'episodes':len(es),'net_pnl':sum(p),'mean_net_per_pair':statistics.mean(p),'median_net_per_pair':statistics.median(p),'winning_net_total':sum(wins),'losing_net_total':sum(losses),'mean_win':statistics.mean(wins),'mean_loss':statistics.mean(losses),'profit_factor':sum(wins)/-sum(losses),'largest_loss':min(p),'fees':r['fees'],'modeled_absolute_slippage':sum(abs(o['quantity'])*100*.01 for o in orders),'half_spread_cost_vs_submission_midpoint':spread,'hypothetical_midpoint_pnl_before_fees_and_slippage':sum(p)+r['fees']+100+spread,'calendar_position_days':position_days,'calendar_days_with_any_position':len(active),'sample_calendar_days':(date(2026,10,23)-date(2024,1,2)).days,'by_name':r['by_name'],'notes':['Calendar occupancy is approximate from entry/exit dates, not minute-weighted margin deployment.','Midpoint comparison is arithmetic execution attribution, not an executable alternate backtest.','Winning/losing amounts include fees. No valid loss excluded.']}
(P/'pnl_attribution.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
