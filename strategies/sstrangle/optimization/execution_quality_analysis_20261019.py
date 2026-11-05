"""Read-only arithmetic diagnosis of genuine baseline order submission snapshots.
Never modifies fills, source strategy, cloud jobs, or economic results.
"""
import csv,hashlib,json,math,sys
from collections import defaultdict
from pathlib import Path
import duckdb
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'strategies/sstrangle'))
from qc_contracts import execution_rows
BASE=ROOT/'strategies/sstrangle/results/strangle_basket_20261018_191012'
SRC=BASE/'SSTRANGLE_20261018_191012_basket'
OUT=ROOT/'strategies/sstrangle/optimization/execution_quality_20261019'
OUT.mkdir(exist_ok=True)
orders=json.loads((SRC/'orders.json').read_text())
by_order={r['id']:r for r in orders}
cycles=list(csv.DictReader((BASE/'baseline_report/cycles.csv').open()))
for i,c in enumerate(cycles):
 c['cycle_id']=i+1
 c['pnl']=float(c['pnl']); c['fees']=float(c['fees'])
 c['entry']=c['entry'].replace('Z','+00:00');c['exit']=c['exit'].replace('Z','+00:00')
logs=(SRC/'cloud.log').read_text().splitlines()
alias={}
for l in logs:
 if ' ENTRY ' in l:
  r=json.loads(l.split(' ENTRY ',1)[1]);alias[(r['key'],r['date'])]=r['ticker']
rows=execution_rows(orders)
for r in rows:
 o=by_order[r['order_id']];q=o.get('orderSubmissionData',{});bid=q.get('bidPrice');ask=q.get('askPrice')
 good=bid is not None and ask is not None and math.isfinite(bid) and math.isfinite(ask) and bid>0 and ask>=bid
 cs=[c for c in cycles if c['ticker']==r['strategy_key'] and c['entry']<=r['timestamp']<=c['exit']]
 assert len(cs)==1,(r,cs)
 c=cs[0];r['cycle_id']=c['cycle_id'];r['cycle_exit_reason']=c['reason'];r['contemporaneous_ticker_if_logged']=alias.get((c['ticker'],c['entry'][:10]),'')
 r['submission_bid']=bid;r['submission_ask']=ask;r['submission_quotes_valid']=good
 r['order_submission_time']=o['time'];r['fill_at_submission_time']=r['timestamp'].replace('+00:00','Z')==o['time']
 r['mid']=((bid+ask)/2 if good else None);r['spread']=(ask-bid if good else None)
 r['relative_spread']=(r['spread']/r['mid'] if good else None)
 r['wide_relative_25pct']=(r['relative_spread']>.25 if good else None)
 # The actual source gate max(2*tick,.25*mid) requires minimum tick not exported.
 # Relative25% alone can flag tiny lowpremium quotes which pass the absolute tick allowance.
 r['midpoint_sensitivity_cost']=(r['quantity']*(r['qc_price']-r['mid'])*r['multiplier'] if good else None)
 r['quoted_halfspread_cost']=(abs(r['quantity'])*r['spread']*.5*r['multiplier'] if good else None)
 r['touch_price']=(ask if r['quantity']>0 else bid) if good else None
 r['fill_minus_touch_signed_cost']=(r['quantity']*(r['qc_price']-r['touch_price'])*r['multiplier'] if good else None)
 r['genuine_cashflow']=-r['quantity']*r['qc_price']*r['multiplier']-r['fee']
 r.pop('tag',None)
for c in cycles:
 rs=[r for r in rows if r['cycle_id']==c['cycle_id']]
 assert abs(sum(r['genuine_cashflow'] for r in rs)-c['pnl'])<1e-7
 c['fill_count']=len(rs);c['contemporaneous_ticker_if_logged']=alias.get((c['ticker'],c['entry'][:10]),'')
 c['midpoint_sensitivity_cost']=sum(r['midpoint_sensitivity_cost'] or 0 for r in rs)
 c['opening_midpoint_sensitivity_cost']=sum(r['midpoint_sensitivity_cost'] or 0 for r in rs if r['reason']=='OPEN')
 c['closing_midpoint_sensitivity_cost']=sum(r['midpoint_sensitivity_cost'] or 0 for r in rs if r['reason'] not in ['OPEN','ROLL'])
 c['rolling_midpoint_sensitivity_cost']=sum(r['midpoint_sensitivity_cost'] or 0 for r in rs if r['reason']=='ROLL')
 c['wide_fill_count']=sum(r['wide_relative_25pct'] is True for r in rs)
 c['max_relative_spread']=max((r['relative_spread'] for r in rs if r['relative_spread'] is not None),default=None)
 c['valid_quote_fill_count']=sum(r['submission_quotes_valid'] for r in rs)
 c['valid_quotes_complete']=c['valid_quote_fill_count']==len(rs)

def aggregate(field):
 out=[]
 for k in sorted({str(r[field]) for r in rows}):
  rs=[r for r in rows if str(r[field])==k]
  out.append({field:k,'fills':len(rs),'midpoint_sensitivity_cost':sum(r['midpoint_sensitivity_cost'] or 0 for r in rs),'fees':sum(r['fee'] for r in rs),'wide_fill_count':sum(r['wide_relative_25pct'] is True for r in rs),'quoted_halfspread_cost':sum(r['quoted_halfspread_cost'] or 0 for r in rs)})
 return out
aggs={'by_order_reason':aggregate('reason'),'by_final_cycle_reason':aggregate('cycle_exit_reason'),'by_security_type':aggregate('security_type')}
summary={'status':'Execution snapshot arithmetic only; not a replacement-fill backtest','baseline':str(BASE),'filled_events':len(rows),'cycles':len(cycles),'valid_submission_quote_fills':sum(r['submission_quotes_valid'] for r in rows),'same_timestamp_submission_fill_count':sum(r['fill_at_submission_time'] for r in rows),'net_pnl':sum(c['pnl'] for c in cycles),'fees':sum(r['fee'] for r in rows),'total_midpoint_sensitivity_cost':sum(r['midpoint_sensitivity_cost'] or 0 for r in rows),'max_absolute_fill_minus_submission_touch_cost':max(abs(r['fill_minus_touch_signed_cost'] or 0) for r in rows),'wide_relative_25pct_fills':sum(r['wide_relative_25pct'] is True for r in rows),**aggs,'largest_midpoint_sensitivities':sorted(cycles,key=lambda c:c['midpoint_sensitivity_cost'],reverse=True)[:15],'limitations':['Submission bid/ask are genuine per-order fields, not raw quote history. They do not establish executable depth, side timestamps, later limit-fill likelihood, or vendor quote correctness.','Positive signed midpoint sensitivity means fill was less favorable than the simultaneous submission midpoint. It is arithmetic, not achievable profit or a slippage-adjusted revised strategy.','25% relative spread flags are descriptive; actual entry gate also permits two minimum ticks and per-contract minimum tick metadata is not present in exported orders.','Forced exits cannot simply reject a wide quote and be assumed to avoid loss. Default broker margin liquidation remains binding.','Original runtime logs truncate; contemporaneous ticker is populated only when entry log exists. Native SID remains authoritative, and display alias is not used for matching.','Many fills share one cycle and market regime; statistics are descriptive, not independent-sample causal estimates.'],'hypotheses_for_future_qc_tests':['Predeclare lower per-underlying margin caps plus portfolio free-margin reserve to reduce forced sales, preserve genuine broker margin checks.','Predeclare liquid broad ETF option universe or historical option volume/OI filters and restrictive opening spread gates, then evaluate all eligible periods without banning historical losers.','Test marketable limit entries with bounded timeout and cancellation/reconciliation; unfilled orders remain unfilled and actual QC fills govern.','Test earlier frequent risk checks and conservative account drawdown/margin triggers while flat-entry rules remain explicit; do not assume stops cap gap losses.','For voluntary exits only, compare bounded limit execution followed by explicit emergency market fallback before mandatory exit deadline. Forced broker exits retain required execution and real bid/ask costs.'],'source_hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [SRC/'orders.json',BASE/'baseline_report/cycles.csv',SRC/'cloud.log']}}
summary['concentration']={
 'largest_cycle_cost_share':max(c['midpoint_sensitivity_cost'] for c in cycles)/summary['total_midpoint_sensitivity_cost'],
 'top5_cycle_cost_share':sum(c['midpoint_sensitivity_cost'] for c in sorted(cycles,key=lambda c:c['midpoint_sensitivity_cost'],reverse=True)[:5])/summary['total_midpoint_sensitivity_cost'],
 'margin_close_cost_share':sum(r['midpoint_sensitivity_cost'] or 0 for r in rows if r['reason']=='MARGIN')/summary['total_midpoint_sensitivity_cost'],
 'ordinary_close_midpoint_sensitivity_cost':sum(r['midpoint_sensitivity_cost'] or 0 for r in rows if r['reason'] not in ['OPEN','ROLL','MARGIN']),
 'relative_spread_over100pct_fills':sum(r['relative_spread'] is not None and r['relative_spread']>1 for r in rows)}
summary['fixed_observed_trade_midpoint_arithmetic']={
 'net_pnl_plus_midpoint_sensitivity':summary['net_pnl']+summary['total_midpoint_sensitivity_cost'],
 'warning':'Still negative for these fixed observed trades even after adding back all touch-to-mid differences. This is NOT a counterfactual account backtest: revised fills would change margin, quantities, later eligibility, and sample endpoint.'}
summary['decision_implication']='Every opening fill was within25% relative spread, so tighter quote checks alone cannot demonstrate that the dominant CBS margin loss was preventable. Entry liquidity and portfolio sizing must be tested prospectively together with default forced-close behavior.'
for name,data in [('fills',rows),('cycles',cycles),*aggs.items()]:
 if not data:continue
 with (OUT/f'{name}.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
con=duckdb.connect(str(OUT/'execution_quality.duckdb'))
for f in OUT.glob('*.csv'):
 name=f.stem;con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM read_csv_auto(?)',[str(f)])
 con.execute(f'COPY "{name}" TO ? (FORMAT PARQUET)',[str(OUT/f'{name}.parquet')])
 assert con.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]==len(list(csv.DictReader(f.open())))
con.close()
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
(OUT/'FINDINGS.txt').write_text('Genuine order submission execution-quality audit\n\n'+json.dumps({k:summary[k] for k in ['filled_events','cycles','valid_submission_quote_fills','same_timestamp_submission_fill_count','net_pnl','fees','total_midpoint_sensitivity_cost','wide_relative_25pct_fills','concentration','fixed_observed_trade_midpoint_arithmetic','decision_implication',*aggs]},indent=2)+'\n\nLimitations:\n'+'\n'.join(summary['limitations'])+'\n\nPredeclared causal hypotheses for future tests:\n'+'\n'.join(summary['hypotheses_for_future_qc_tests'])+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ['largest_midpoint_sensitivities','source_hashes','limitations','hypotheses_for_future_qc_tests']},indent=2))
