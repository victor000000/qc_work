"""Derived trade-level evidence from native fill receipts only."""
from pathlib import Path
from datetime import date
import json,statistics,collections
P=Path(__file__).parent
out={}
for file in P.glob('*.reconciliation.json'):
 r=json.loads(file.read_text())
 if not r.get('reconciled'):continue
 result=json.loads((P/(r['name']+'.result.json')).read_text())['backtest']
 if result.get('error') or not result.get('completed'):continue
 es=r['episode_summary'];pnls=[e['net_pnl'] for e in es]
 if not es:continue
 wins=[v for v in pnls if v>0];losses=[v for v in pnls if v<0]
 dtes=[d for e in es for d in e['entry_dtes']];hold=[(date.fromisoformat(e['exit_day'])-date.fromisoformat(e['entry_day'])).days for e in es]
 buckets={};reasons=collections.Counter()
 for e in es:
  d=e['entry_dtes'][0];bucket='40–44' if d<45 else '45' if d==45 else '46–50';x=buckets.setdefault(bucket,{'pairs':0,'net_pnl':0});x['pairs']+=1;x['net_pnl']+=e['net_pnl'];reasons.update(e['reasons'])
 orders=json.loads((P/(r['name']+'.orders.json')).read_text());events=[]
 for o in orders:
  ep=o['tag'].split('|')[1]
  for ev in o.get('events',[]):
   q=ev.get('fillQuantity',0)
   if q:events.append((ev['time'],o['id'],ep,q))
 balances=collections.defaultdict(float);peak=0
 for t,order,ep,q in sorted(events):
  balances[ep]+=q;peak=max(peak,sum(abs(v)>1e-9 for v in balances.values()))
 out[r['name']]={'pairs':len(es),'net_pnl':sum(pnls),'mean_trade_net':statistics.mean(pnls),'win_rate':len(wins)/len(es),'winning_net_total':sum(wins),'losing_net_total':sum(losses),'average_win':statistics.mean(wins) if wins else None,'average_loss':statistics.mean(losses) if losses else None,'profit_factor':sum(wins)/-sum(losses) if losses else None,'largest_loss':min(pnls),'entry_dte_min_median_max':[min(dtes),statistics.median(dtes),max(dtes)],'holding_calendar_days_min_median_max':[min(hold),statistics.median(hold),max(hold)],'entry_dte_buckets':buckets,'exit_reasons':dict(reasons),'peak_simultaneous_trade_episodes':peak,'note':'Descriptive selected trades, not independent/causal entry-DTE or exit attribution; simultaneous count includes any partially open episode.'}
(P/'episode_metrics.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out.get('SS45DTE_FUNNEL_FIVE_DAILYIV_V1'),indent=2))
