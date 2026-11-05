"""Reconcile native order-event fills into whole strangle episodes, not leg win rates."""
import json,re,sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
ROOT=Path(__file__).parent
names=sys.argv[1:] or [p.name.removesuffix('.orders.json') for p in ROOT.glob('*.orders.json')]
for name in names:
 orders=json.loads((ROOT/(name+'.orders.json')).read_text())
 groups={};positions=defaultdict(float);unmatched=[];seen=set();fees=0;cash=0
 for order in orders:
  tag=order.get('tag','');parts=tag.split('|');valid=len(parts)>=4 and parts[0]=='SS45'
  for event in order.get('events',[]):
   qty=float(event.get('fillQuantity') or 0)
   if not qty:continue
   eventid=(order['id'],event['id'])
   if eventid in seen:continue
   seen.add(eventid)
   text=order['symbol']['value'];symbolid=order['symbol']['id']
   contract=re.fullmatch(r'(.+?)\s+(\d{6})([PC])(\d{8})',text)
   # These research contracts are standard US options; reject unknown identity rather than infer.
   if not contract:unmatched.append({'order_id':order['id'],'reason':'nonstandard identity','symbol':text});continue
   mult=100;fee=float(event.get('orderFeeAmount') or 0);price=float(event['fillPrice']);flow=-qty*price*mult
   fees+=fee;cash+=flow;positions[symbolid]+=qty
   if not valid:unmatched.append({'order_id':order['id'],'reason':'missing episode tag'});continue
   episode=groups.setdefault(parts[1],{'id':int(parts[1]),'name':contract[1].strip(),'cashflow':0.,'fees':0.,'fills':[]})
   episode['cashflow']+=flow;episode['fees']+=fee
   day=datetime.fromtimestamp(event['time'],timezone.utc).astimezone(ZoneInfo('America/New_York')).date()
   expiry=datetime.strptime(contract[2],'%y%m%d').date()
   episode['fills'].append({'symbol':text,'quantity':qty,'price':price,'fee':fee,'day':str(day),'expiry':str(expiry),'dte':(expiry-day).days,'action':parts[2],'reason':parts[3]})
 summary=[]
 for episode in groups.values():
  fs=episode['fills'];opens=[f for f in fs if f['action']=='OPEN'];closes=[f for f in fs if f['action']!='OPEN']
  balances=defaultdict(float)
  for f in fs:balances[f['symbol']]+=f['quantity']
  episode.update(net_pnl=episode['cashflow']-episode['fees'],flat=all(abs(v)<1e-9 for v in balances.values()),entry_day=min((f['day'] for f in opens),default=None),exit_day=max((f['day'] for f in closes),default=None),entry_dtes=sorted(set(f['dte'] for f in opens)),exit_dtes=sorted(set(f['dte'] for f in closes)),reasons=sorted(set(f['reason'] for f in closes)))
  summary.append({k:v for k,v in episode.items() if k!='fills'})
 result=json.loads((ROOT/(name+'.result.json')).read_text())['backtest'];stats=result.get('statistics',{});runtime=result.get('runtimeStatistics',{})
 navchange=float(stats.get('End Equity',0))-float(stats.get('Start Equity',0))
 byname={}
 for symbol in sorted(set(e['name'] for e in groups.values())):
  es=[e for e in groups.values() if e['name']==symbol]
  byname[symbol]={'episodes':len(es),'wins':sum(e['net_pnl']>0 for e in es),'net_pnl':sum(e['net_pnl'] for e in es)}
 out={'name':name,'native_orders':len(orders),'fill_events':len(seen),'episodes':len(groups),'flat_episodes':sum(e['flat'] for e in groups.values()),'wins':sum(e['net_pnl']>0 for e in groups.values()),'net_pnl':cash-fees,'fees':fees,'nav_change':navchange,'cashflow_equity_difference':cash-fees-navchange,'residual_contracts':{k:v for k,v in positions.items() if abs(v)>1e-9},'unmatched':unmatched,'runtime_closed':runtime.get('ss_closed'),'runtime_net_closed':runtime.get('ss_net_closed'),'native_win_rate_leg_level':stats.get('Win Rate'),'by_name':byname,'episode_summary':summary,'method':'Native fill events; one standard US option contract multiplier=100; assignments/nonstandard identities flagged rather than inferred.'}
 out['reconciled']=not unmatched and not out['residual_contracts'] and abs(out['cashflow_equity_difference'])<.02 and out['flat_episodes']==len(groups)
 (ROOT/(name+'.reconciliation.json')).write_text(json.dumps(out,indent=2)+'\n')
 print(json.dumps({k:v for k,v in out.items() if k not in ['episode_summary','by_name']}))
