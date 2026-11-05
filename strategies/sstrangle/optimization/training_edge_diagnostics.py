"""Descriptive genuine closed training trades, never a counterfactual backtest."""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone
import duckdb
import pandas as pd
ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/'strategies/sstrangle/optimization/first_trial_failure_results_20261019'
ORDERS=ROOT/'strategies/sstrangle/results/strangle_basket-calmar_20261019_123602/SSTRANGLE_20261019_123602_cap20_stop1/orders.json'
OUT=Path(__file__).with_name('training_edge_diagnostics_20261019')
def stamp(s):return datetime.fromisoformat(s.replace('Z','+00:00'))
def main():
 OUT.mkdir(exist_ok=True);f=pd.read_csv(SOURCE/'closed_cycles.csv')
 if any(stamp(x).date().isoformat()>'2019-12-31' for x in f['exit']):raise ValueError('Evaluation outcome leakage')
 orders=json.loads(ORDERS.read_text());openings={};opening_orders={}
 for o in orders:
  head,*fields=o['tag'].split(';');key,reason=head.rsplit(':',1)
  if reason!='OPEN':continue
  m=dict(v.split('=',1) for v in fields if '=' in v);k=(key,stamp(o['time']))
  if k in openings and openings[k]!=m:raise ValueError('Inconsistent native opening metadata')
  openings[k]=m;opening_orders.setdefault(k,[]).append(o)
 rows=[]
 for r in f.to_dict('records'):
  m=openings[(r['key'],stamp(r['entry']))];iv=float(m['iv']);rank=float(m['ivr']);low=float(m['iv_low']);high=float(m['iv_high'])
  if not rank>70 or abs(rank-100*(iv-low)/(high-low))>1e-7:raise ValueError('Incorrect true IV rank')
  opened=opening_orders[(r['key'],stamp(r['entry']))]
  if len(opened)!=2:raise ValueError('Two genuine opening orders required')
  widths=[];width_cash=0.;native_credit=0.
  for o in opened:
   q=o['orderSubmissionData'];bid=float(q['bidPrice']);ask=float(q['askPrice']);qty=abs(float(o['quantity']));mult=float(m['multiplier'])
   if not 0<bid<=ask:raise ValueError('Invalid original opening snapshot')
   if float(o['price'])!=bid:raise ValueError('Native opening not at attached submission bid')
   widths.append((ask-bid)/((ask+bid)/2));width_cash+=(ask-bid)*qty*mult
   native_credit+=float(o['price'])*qty*mult
  credit=float(r['opening_credit'])
  if abs(native_credit-credit)>1e-7:raise ValueError('Opening credit differs from actual native orders')
  r.update(max_entry_relative_spread=max(widths),entry_halfspread_cash=width_cash/2,
   entry_halfspread_to_initial_credit=width_cash/2/credit,
   entry_spread_bucket='<=10%' if max(widths)<=.10 else '>10%')
  if credit<=0:raise ValueError('Nonpositive actual initial credit')
  r.update(ivr=rank,entry_iv=iv,ivr_bin='70-80' if rank<80 else '80-90' if rank<90 else '90-100',
   normalized_net_pnl=float(r['net_realized_pnl'])/credit,fees_per_opening_credit=float(r['fees'])/credit)
  rows.append(r)
 con=duckdb.connect(str(OUT/'diagnostics.duckdb'));con.register('input_frame',pd.DataFrame(rows));con.execute('create or replace table closed_training_cycles as select * from input_frame')
 queries={
 'overall':"select 'all genuine closed training trades' bucket,* from (select count(*) cycles,sum(net_realized_pnl) actual_net_pnl,sum(fees) actual_fees,sum(opening_credit) initial_credit,sum(net_realized_pnl)/sum(opening_credit) aggregate_net_to_credit,avg(normalized_net_pnl) mean_normalized_net,avg((net_realized_pnl>0)::int) win_rate,min(normalized_net_pnl) worst_net_to_credit from closed_training_cycles)",
 'ivr_buckets':"select ivr_bin bucket,count(*) cycles,sum(net_realized_pnl) actual_net_pnl,sum(fees) actual_fees,avg(normalized_net_pnl) mean_normalized_net,avg((net_realized_pnl>0)::int) win_rate,min(normalized_net_pnl) worst_net_to_credit from closed_training_cycles group by 1 order by 1",
 'entry_width_buckets':"select entry_spread_bucket bucket,count(*) cycles,sum(net_realized_pnl) actual_net_pnl,sum(entry_halfspread_cash) actual_opening_snapshot_halfspread_cash,avg(entry_halfspread_to_initial_credit) mean_opening_halfspread_to_credit,sum((wide_closing_orders>0)::int) cycles_with_wide_close,avg(normalized_net_pnl) mean_normalized_net from closed_training_cycles group by 1 order by 1",
 'exit_buckets':"select exit_reason bucket,count(*) cycles,sum(net_realized_pnl) actual_net_pnl,sum(fees) actual_fees,avg(normalized_net_pnl) mean_normalized_net,avg((net_realized_pnl>0)::int) win_rate,min(normalized_net_pnl) worst_net_to_credit from closed_training_cycles group by 1 order by 1"}
 tables=['closed_training_cycles'];summary={}
 for name,q in queries.items():
  con.execute('create or replace table '+name+' as '+q);tables.append(name);summary[name]=con.execute('select * from '+name).fetchdf().to_dict('records')
 receipts={}
 for name in tables:
  path=OUT/(name+'.parquet');con.execute('copy '+name+' to ? (format parquet,compression zstd)',[str(path)])
  n=con.execute('select count(*) from '+name).fetchone()[0];assert n==con.execute('select count(*) from read_parquet(?)',[str(path)]).fetchone()[0]
  receipts[name]={'rows':n,'parquet_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'readback_verified':True}
 audit=json.loads((SOURCE/'summary.json').read_text());assert len(rows)==audit['closed_cycles'];assert abs(summary['overall'][0]['actual_net_pnl']-audit['closed_cycle_net_realized_pnl'])<1e-7
 result={'created_utc':datetime.now(timezone.utc).isoformat(),'scope':'All121 genuine closed2014-2019 trades from failed cap20_stop1 candidate; one unresolved trade is NOT liquidated or treated as zero','not_a_new_strategy_backtest':True,'new_gate_selected':False,'full_period_calmar':None,'entry_snapshot_halfspread_arithmetic_is_not_alternative_fills':True,'normalized_values_are_not_portfolio_returns':True,'source_orders_sha256':hashlib.sha256(ORDERS.read_bytes()).hexdigest(),'source_cycles_sha256':hashlib.sha256((SOURCE/'closed_cycles.csv').read_bytes()).hexdigest(),'tables':receipts,**summary,'limitations':['Post-inspected descriptive bins, not causal effects or a promoted IVR cutoff.','Failed run and unresolved short inventory prohibit full-period return claims.','New entry filters would change baskets, later opportunities and account paths.','Current guarded full run retains its frozen parameters.','Source run had its preserved prefix-feasibility restriction; these descriptive trades do not validate the later feasible-v2 opportunity path.']}
 (OUT/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False));print(json.dumps(result,indent=2,allow_nan=False))
if __name__=='__main__':main()
