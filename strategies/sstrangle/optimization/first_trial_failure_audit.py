#!/usr/bin/env python3
"""Audit genuine first risk-trial fills and retain its unresolved position."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,math,sys
import duckdb,pandas as pd
from zoneinfo import ZoneInfo
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from audit import order_group_id,validate_sequential_close
from qc_contracts import execution_rows,execution_signature
SOURCE=HERE/'results/strangle_basket-calmar_20261019_123602/SSTRANGLE_20261019_123602_cap20_stop1'
BASE=HERE/'results/strangle_basket_20261018_191012/baseline_report'
OUT=Path(__file__).with_name('first_trial_failure_results_20261019')

def metadata(tag):return dict(t.split('=',1)for t in tag.split(';')[1:]if'='in t)
def money(s):return float(str(s).replace('$','').replace(',',''))

def audit():
 OUT.mkdir(exist_ok=True)
 orders=json.loads((SOURCE/'orders.json').read_text());rust=json.loads((SOURCE/'orders.rust.json').read_text())
 full=json.loads((SOURCE/'backtest.json').read_text())['backtest'];fills=execution_rows(orders)
 assert len(orders)==int(full['statistics']['Total Orders'])==762
 assert execution_signature(fills)==execution_signature(execution_rows(rust))
 assert all(o['status']==3 for o in orders)
 assert len({f['event_id']for f in fills})==len(fills)==762
 by_id={o['id']:o for o in orders};groups=defaultdict(list)
 for f in fills:
  o=by_id[f['order_id']];assert sum(float(e.get('fillQuantity',0))for e in o['events'])==float(o['quantity'])
  assert float(f['fee'])>=0 and math.isfinite(float(f['qc_price']))
  assert all(e.get('orderFeeCurrency','USD')=='USD' for e in o['events'])
  groups[f['group_id']].append(f)
 active={};cycles=[];quantities=Counter();closed_cycle_order_ids=set()
 for gid,group in sorted(groups.items(),key=lambda it:min(f['order_id']for f in it[1])):
  assert len(group)==2 and len({f['strategy_key']for f in group})==1 and len({f['reason']for f in group})==1
  validate_sequential_close([by_id[f['order_id']]for f in group])
  key,reason=group[0]['strategy_key'],group[0]['reason']
  if reason=='OPEN':
   assert key not in active
   e=metadata(group[0]['tag']);q=int(e['quantity'])
   active[key]=dict(key=key,entry=min(f['timestamp']for f in group),entry_equity=float(e['allocation_equity']),quantity=q,
    expiry=group[0]['expiry'],opening_credit=sum(-f['quantity']*f['qc_price']*f['multiplier']for f in group),
    gross_cashflow=0.,fees=0.,rolls=0,order_ids=[],inventory=Counter())
  c=active[key]
  for f in group:
   sid=f['symbol_id'];quantities[sid]+=f['quantity'];c['inventory'][sid]+=f['quantity'];c['order_ids'].append(f['order_id'])
   c['gross_cashflow']-=f['quantity']*f['qc_price']*f['multiplier'];c['fees']+=f['fee']
  if reason=='ROLL':c['rolls']+=1
  if reason not in ('OPEN','ROLL'):
   assert all(q==0 for q in c['inventory'].values())
   c.update(exit=max(f['timestamp']for f in group),exit_reason=reason,net_realized_pnl=c['gross_cashflow']-c['fees'])
   closed_cycle_order_ids.update(c['order_ids']);c.pop('inventory');cycles.append(c);del active[key]
  else:
   assert sorted(q for q in c['inventory'].values()if q)==[-c['quantity'],-c['quantity']]
 residual=[dict(symbol_id=s,quantity=q,strategy_key=next(f['strategy_key']for f in fills if f['symbol_id']==s))for s,q in quantities.items()if q]
 assert len(active)==1 and len(residual)==2 and all(r['quantity']==-1 for r in residual)
 fees=sum(f['fee']for f in fills);gross=sum(-f['quantity']*f['qc_price']*f['multiplier']for f in fills)
 cash=60000+gross-fees;closed_pnl=sum(c['net_realized_pnl']for c in cycles)
 unresolved=[]
 for c in active.values():
  c=dict(c);c['inventory']={s:q for s,q in c['inventory'].items()if q}
  c['net_cashflow_not_realized_pnl']=c['gross_cashflow']-c['fees'];unresolved.append(c)
 assert abs(closed_pnl+sum(c['net_cashflow_not_realized_pnl']for c in unresolved)-(cash-60000))<1e-7
 exact_account=money(full['totalPerformance']['portfolioStatistics']['endEquity'])
 stats_account=money(full['statistics']['End Equity']);runtime_account=money(full['runtimeStatistics']['Equity'])
 chart=json.loads((SOURCE/'strategy_equity.json').read_text())['chart']['series']['Equity']['values']
 assert abs(chart[-1][-1]-exact_account)<1e-8
 implied_liability=cash-exact_account
 assert implied_liability>=0 and abs(implied_liability-money(full['runtimeStatistics']['Holdings']))<.011
 assert abs(fees-money(full['statistics']['Total Fees']))<1e-8
 touch_rows=[]
 for f in fills:
  q=f['quantity'];mult=f['multiplier'];o=by_id[f['order_id']];sub=o.get('orderSubmissionData',{})
  bid,ask=sub.get('bidPrice'),sub.get('askPrice')
  valid=bid is not None and ask is not None and math.isfinite(bid)and math.isfinite(ask)and ask>=bid>=0
  mid=(bid+ask)/2 if valid else None;touch=(ask if q>0 else bid)if valid else None
  touch_rows.append(dict(order_id=f['order_id'],strategy_key=f['strategy_key'],timestamp=f['timestamp'],reason=f['reason'],
   quantity=q,multiplier=mult,fee=f['fee'],submission_two_sided_valid=valid,
   submission_spread=ask-bid if valid else None,submission_spread_relative_to_mid=(ask-bid)/mid if valid and mid>0 else None,
   wide_absolute_and_relative=bool(valid and mid>0 and ask-bid>.5 and (ask-bid)/mid>.5),
   put_submission_ask_exceeds_strike=bool(valid and f['security_type']==2 and f['call_put']=='P' and ask>f['strike']),
   filled_equity_put_exceeds_strike=bool(f['security_type']==2 and f['call_put']=='P' and f['qc_price']>f['strike']),
   actual_cashflow=-q*f['qc_price']*mult,
   submission_mid_cashflow=-q*mid*mult if valid else None,
   signed_fill_vs_submission_touch_cost=q*(f['qc_price']-touch)*mult if valid else None,
   signed_fill_vs_submission_mid_cost=q*(f['qc_price']-mid)*mult if valid else None,
   submission_half_spread_cost=abs(q)*(ask-bid)/2*mult if valid else None))
 touch=sum(r['signed_fill_vs_submission_mid_cost']or 0 for r in touch_rows)
 midgross=sum(r['submission_mid_cashflow']or 0 for r in touch_rows)
 assert all(r['submission_two_sided_valid']for r in touch_rows)
 assert abs(midgross-touch-gross)<1e-7
 touch_by_id={r['order_id']:r for r in touch_rows}
 stop_buckets=[]
 for c in cycles:
  et=datetime.fromisoformat(c['exit']).astimezone(ZoneInfo('America/New_York'))
  c['exit_ny_timestamp']=et.isoformat()
  c['exit_first30_ny']=9*60+30<=et.hour*60+et.minute<10*60
  c['net_loss_to_opening_credit']=max(0,-c['net_realized_pnl'])/c['opening_credit']
  c['whole_cycle_submission_mid_cost']=sum(touch_by_id[i]['signed_fill_vs_submission_mid_cost']for i in c['order_ids'])
  closing=[touch_by_id[i]for i in c['order_ids']if touch_by_id[i]['reason']==c['exit_reason']]
  c['closing_submission_mid_cost']=sum(r['signed_fill_vs_submission_mid_cost']for r in closing)
  c['wide_closing_orders']=sum(r['wide_absolute_and_relative']for r in closing)
  c['put_bound_flagged_closing_orders']=sum(r['put_submission_ask_exceeds_strike']for r in closing)
 for early,label in [(True,'09:30–09:59 NY'),(False,'Other NY times')]:
  cs=[c for c in cycles if c['exit_reason']=='STOP' and c['exit_first30_ny']==early]
  stop_buckets.append(dict(bucket=label,cycles=len(cs),actual_net_realized_pnl=sum(c['net_realized_pnl']for c in cs),
   whole_cycle_submission_mid_cost=sum(c['whole_cycle_submission_mid_cost']for c in cs),
   closing_submission_mid_cost=sum(c['closing_submission_mid_cost']for c in cs),
   wide_closing_order_count=sum(c['wide_closing_orders']for c in cs),
   cycles_with_wide_closing_orders=sum(c['wide_closing_orders']>0 for c in cs),
   cycles_with_put_bound_flag=sum(c['put_bound_flagged_closing_orders']>0 for c in cs),
   net_loss_gt_1_25_original_credit=sum(c['net_loss_to_opening_credit']>1.25 for c in cs),
   net_loss_gt_2_original_credit=sum(c['net_loss_to_opening_credit']>2 for c in cs),
   net_loss_gt_5_original_credit=sum(c['net_loss_to_opening_credit']>5 for c in cs),
   max_net_loss_multiple=max((c['net_loss_to_opening_credit']for c in cs),default=0)))
 reasons=[]
 for r in sorted({c['exit_reason']for c in cycles}):
  cs=[c for c in cycles if c['exit_reason']==r]
  reasons.append(dict(exit_reason=r,closed_cycles=len(cs),gross_cashflow=sum(c['gross_cashflow']for c in cs),fees=sum(c['fees']for c in cs),net_realized_pnl=sum(c['net_realized_pnl']for c in cs)))
 baseline=pd.read_csv(BASE/'cycles.csv');cutoff='2019-12-02T23:59:59'
 prior=baseline[baseline.exit<=cutoff]
 summary=dict(created_utc=datetime.now(timezone.utc).isoformat(),classification='Failed partial QC research trial with unresolved short options',
  source=str(SOURCE),backtest_id=full['backtestId'],cloud_error=full['error'],
  orders=len(orders),fills=len(fills),all_fills_rust_python_match=True,all_declared_orders_fully_filled=True,
  initial_cash=60000,closed_cycles=len(cycles),unresolved_cycles=len(unresolved),residual_contracts=len(residual),
  actual_fees=fees,closed_cycle_net_realized_pnl=closed_pnl,all_fills_gross_cashflow=gross,
  account_cash_from_fills=cash,account_equity_exact_portfolio=exact_account,
  account_equity_statistics=stats_account,account_equity_runtime=runtime_account,
  cash_less_reported_equity_implied_short_option_liability=implied_liability,
  individually_independent_residual_option_marks_available=False,
  liability_reconciles_reported_gross_holdings=True,
  qc_reported_partial_drawdown=full['statistics']['Drawdown'],
  valid_full_period_cagr=None,valid_full_period_calmar=None,
  exit_reasons=reasons,unresolved=unresolved,stop_time_buckets=stop_buckets,
  wide_quote_definition='Submission ask-bid>0.50 quote units AND spread/mid>50%; descriptive flag, not promoted trading gate.',
  put_bound_caveat='Ask>strike flags an economically extreme purchase price relative to standard American put maximum payoff under stated100multiplier. An uncompetitive ask does not itself prove arbitrage, incorrect vendor data, or a faulty bid. Adjusted deliverable metadata and independent source accuracy remain unvalidated; no quotes are repaired or rescaled.',
  largest_realized_cycle_losses=sorted(cycles,key=lambda c:c['net_realized_pnl'])[:10],
  execution_arithmetic=dict(orders_with_valid_two_sided_submission_metadata=sum(r['submission_two_sided_valid']for r in touch_rows),
    signed_fill_vs_submission_touch_cost=sum(r['signed_fill_vs_submission_touch_cost']for r in touch_rows),
    signed_fill_vs_submission_mid_cost=touch,submission_half_spread_cost=sum(r['submission_half_spread_cost']for r in touch_rows),
    signed_mid_cost_on_closed_cycles=sum(r['signed_fill_vs_submission_mid_cost']for r in touch_rows if r['order_id']in closed_cycle_order_ids),
    identity_checked='submission_mid_cashflow - signed_mid_cost = actual fill cashflow',
    interpretation='Arithmetic on genuine submission metadata, not independently executable quotes. Mid-price cashflows are not an alternative backtest; quantities, stops and future opportunities would change.'),
  margin_forced_closed_cycles=0,
  baseline_margin_forced_closed_cycles_full_observed=int((baseline.reason=='MARGIN').sum()),
  baseline_margin_forced_closed_cycles_through_trial_failure=int((prior.reason=='MARGIN').sum()),
  comparison_scope='Descriptive actual exit counts only; different entries/sizing/exits and period endpoints prohibit counterfactual performance attribution.',
  limitations=['Failure occurred before the requested endpoint, with two real short options remaining. No fabricated closing fill or closed P&L.',
    'Aggregate liability is implied by exact account equity and genuine fill cash; no per-contract mark invented.',
    'Rounded QC Statistics41229.68 and Runtime41229.69 bracket exact portfolio41229.685.',
    'Submission-touch/mid arithmetic is not evidence of an achievable mid-fill strategy or midpoint Calmar.',
    'Missing mandatory21DTE exit is a concrete engineering failure; all subsequent strategy-performance conclusions remain incomplete.'])
 frames=dict(executions=pd.DataFrame(fills),closed_cycles=pd.DataFrame(cycles).drop(columns=['order_ids']),
  stop_time_buckets=pd.DataFrame(stop_buckets),residual_holdings=pd.DataFrame(residual),touch_mid_arithmetic=pd.DataFrame(touch_rows),exit_reasons=pd.DataFrame(reasons),
  unresolved_cycle_fills=pd.DataFrame([f for f in fills if f['order_id']in unresolved[0]['order_ids']]))
 with duckdb.connect(str(OUT/'failure_audit.duckdb')) as con:
  for t,frame in frames.items():
   con.register('frame',frame);con.execute(f'create or replace table {t} as select * from frame')
   con.execute(f"copy {t} to '{OUT/t}.parquet'(format parquet)");frame.to_csv(OUT/(t+'.csv'),index=False)
   assert con.execute('select count(*) from read_parquet(?)',[str(OUT/t)+'.parquet']).fetchone()[0]==len(frame)
 summary['parquet_counts_verified']=True
 (OUT/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
 (OUT/'manifest.json').write_text(json.dumps(dict(source_sha256={n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest()for n in ['orders.json','orders.rust.json','backtest.json','strategy_equity.json']},
  tables={t:len(f)for t,f in frames.items()}),indent=2))
 print(json.dumps({k:v for k,v in summary.items()if k not in ['unresolved','largest_realized_cycle_losses','limitations']},indent=2))
 return summary
if __name__=='__main__':audit()
