"""Reconcile the failed guarded run without liquidating residual options."""
import sys,json,hashlib,math
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT/'strategies/sstrangle'),str(Path(__file__).parent)]
from qc_contracts import execution_rows,execution_signature
from audit import validate_sequential_close
from report import write_tables
from account_drawdown import chart_drawdown
from datetime import date,datetime,timezone
SOURCE=ROOT/'strategies/sstrangle/results/strangle_basket-calmar_20261019_163122/SSTRANGLE_20261019_163122_cap20_stop1_guard_exit21'
OUT=Path(__file__).with_name('guard21_failure_results_20261019')
def money(v):return float(str(v).replace('$','').replace(',',''))
def main():
 orders=json.loads((SOURCE/'orders.json').read_text());rust=json.loads((SOURCE/'orders.rust.json').read_text());rust=rust['orders'] if isinstance(rust,dict) else rust
 full=json.loads((SOURCE/'backtest.json').read_text())['backtest'];fills=execution_rows(orders)
 assert full['completed'] and full['error'] and len(orders)==int(full['statistics']['Total Orders'])==1080
 assert execution_signature(fills)==execution_signature(execution_rows(rust))
 assert len({f['event_id'] for f in fills})==len(fills)==1080
 assert all(o['status']==3 and abs(sum(float(e.get('fillQuantity',0)) for e in o['events'])-float(o['quantity']))<1e-9 for o in orders)
 by_id={o['id']:o for o in orders};groups=defaultdict(list)
 for f in fills:
  assert math.isfinite(f['qc_price']) and f['fee']>=0
  groups[f['group_id']].append(f)
 active={};closed=[];inventory=Counter()
 for group in sorted(groups.values(),key=lambda g:min(f['order_id'] for f in g)):
  assert len(group)==2 and len({f['strategy_key'] for f in group})==1 and len({f['reason'] for f in group})==1
  validate_sequential_close([by_id[f['order_id']] for f in group]);key=group[0]['strategy_key'];reason=group[0]['reason']
  if reason=='OPEN':
   assert key not in active
   active[key]={'key':key,'entry':min(f['timestamp'] for f in group),'opening_credit':sum(-f['quantity']*f['qc_price']*f['multiplier'] for f in group),'gross_cashflow':0.,'fees':0.,'rolls':0,'inventory':Counter(),'order_ids':[]}
  c=active[key]
  for f in group:
   c['gross_cashflow']-=f['quantity']*f['qc_price']*f['multiplier'];c['fees']+=f['fee'];c['inventory'][f['symbol_id']]+=f['quantity'];inventory[f['symbol_id']]+=f['quantity'];c['order_ids'].append(f['order_id'])
  if reason=='ROLL':c['rolls']+=1
  if reason not in ('OPEN','ROLL'):
   assert all(abs(q)<1e-9 for q in c['inventory'].values())
   c.update(exit=max(f['timestamp'] for f in group),reason=reason,net_pnl=c['gross_cashflow']-c['fees']);c.pop('inventory');c['order_ids']=json.dumps(c['order_ids']);closed.append(c);del active[key]
 residual=[{'symbol_id':s,'quantity':q} for s,q in inventory.items() if abs(q)>1e-9]
 assert len(active)==1 and len(residual)==2 and all(r['quantity']==-1 for r in residual)
 unresolved=[]
 for c in active.values():
  c=dict(c);c['inventory']=json.dumps({s:q for s,q in c['inventory'].items() if abs(q)>1e-9});c['order_ids']=json.dumps(c['order_ids']);c['net_cashflow_not_realized_pnl']=c['gross_cashflow']-c['fees'];unresolved.append(c)
 fees=sum(f['fee'] for f in fills);cash=60000+sum(-f['quantity']*f['qc_price']*f['multiplier']-f['fee'] for f in fills);closed_net=sum(c['net_pnl'] for c in closed)
 assert abs(cash-60000-closed_net-sum(c['net_cashflow_not_realized_pnl'] for c in unresolved))<1e-7
 runtime=full['runtimeStatistics'];equity=money(full['totalPerformance']['portfolioStatistics']['endEquity']);liability=cash-equity
 assert abs(fees-abs(money(runtime['Fees'])))<.0051
 assert abs(liability-abs(money(runtime['Holdings'])))<.0051
 assert abs(equity-money(runtime['Equity']))<.0051
 charts=[]
 for n in ['trading_period.json','strategy_equity.json']:
  p=SOURCE/n
  if p.exists():charts.append(dict(source=n,**chart_drawdown(json.loads(p.read_text()),60000,date(2012,1,3),date(2026,9,30))))
 assert all(datetime.fromisoformat(c['exit']).date()<date(2020,1,1) for c in closed)
 reasons=[]
 for r in sorted({c['reason'] for c in closed}):
  subset=[c for c in closed if c['reason']==r];reasons.append({'reason':r,'cycles':len(subset),'net_pnl':sum(c['net_pnl'] for c in subset),'fees':sum(c['fees'] for c in subset)})
 OUT.mkdir(exist_ok=True);write_tables(OUT,{'executions':fills,'closed_cycles':closed,'residual_holdings':residual,'unresolved_cycles':unresolved,'exit_reasons':reasons})
 result={'scope':'Failed partial guarded21DTE candidate, not a complete performance backtest','backtest_id':full['backtestId'],'cloud_failure':full['error'],'orders':len(orders),'fills':len(fills),'all_rust_python_fills_match':True,'all_actual_orders_fully_filled':True,'closed_cycles':len(closed),'closed_cycle_net_pnl':closed_net,'actual_all_fees':fees,'cash_from_genuine_fills':cash,'exact_account_equity':equity,'residual_short_legs':len(residual),'implied_total_short_liability':liability,'per_leg_marks_invented':False,'actual_cash_account_fees_reconcile':True,'full_period_cagr':None,'full_period_calmar':None,'evaluation_available':False,'target_reached':False,'exit_reasons':reasons,'account_chart_drawdown_audits':charts,'qc_reported_partial_drawdown':full['statistics']['Drawdown'],'parquet_readback_verified':True,'source_sha256':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in ['orders.json','orders.rust.json','backtest.json','strategy_equity.json']},'limitations':['Residual shorts are retained, never liquidated at fabricated prices.','Partial native fills/net loss cannot establish full2012-2026 Calmar or independent source accuracy.','Guard changes the whole basket path; comparison to earlier unguarded candidate is not isolated causal attribution.']}
 (OUT/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False));print(json.dumps(result,indent=2,allow_nan=False))
if __name__=='__main__':main()
