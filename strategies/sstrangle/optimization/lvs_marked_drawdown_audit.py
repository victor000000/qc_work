"""Audit native ACCOUNT OHLC, preserving uncertain within-bar ordering."""
import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[3]
CAMPAIGN=ROOT/'strategies/sstrangle/results/strangle_basket-lvs-guard_20261019_160702'
def stamp(t):return datetime.fromtimestamp(t,timezone.utc).isoformat()
def analyze(values):
 if not values:raise ValueError('No account observations')
 close_peak=values[0][1];prior_high=close_peak;lo_bound=hi_bound=close_dd=0.;worst=None
 for t,o,h,l,c in values:
  if not (0<l<=min(o,c)<=max(o,c)<=h):raise ValueError('Invalid positive OHLC')
  # First/open and previous completed highs precede this low; current high precedes close.
  known_peak=max(prior_high,o)
  proven=max(0.,1-l/known_peak,1-c/max(known_peak,h))
  possible=max(0.,1-l/max(known_peak,h))
  if proven>lo_bound:lo_bound=proven;worst={'time':stamp(t),'known_prior_peak':known_peak,'account_low':l,'account_high':h,'account_close':c}
  hi_bound=max(hi_bound,possible);prior_high=max(prior_high,h)
  close_peak=max(close_peak,c);close_dd=max(close_dd,1-c/close_peak)
 return {'sampled_close_mdd':close_dd,'sampled_account_ohlc_mdd_lower_bound':lo_bound,'sampled_account_ohlc_mdd_upper_bound':hi_bound,'worst_guaranteed_bar':worst,'bars':len(values)}
def main():
 rows=[]
 for suffix in ['lvs_guard_control','lvs_guarded']:
  p=CAMPAIGN/f'SSTRANGLE_20261019_160702_{suffix}'
  chart=p/'strategy_equity.json';data=json.loads(chart.read_text())['chart']['series']['Equity']['values']
  b=json.loads((p/'backtest.json').read_text())['backtest'];stats=b['statistics']
  row=analyze(data);row.update({'variant':suffix,'backtest_id':b['backtestId'],'qc_reported_mdd':float(stats['Drawdown'].strip('%'))/100,'start_equity':float(stats['Start Equity']),'end_equity':float(stats['End Equity']),'account_chart_sha256':hashlib.sha256(chart.read_bytes()).hexdigest()})
  row['net_account_change']=row['end_equity']-row['start_equity'];rows.append(row)
 out={'engineering_only':True,'full_strategy_calmar_proven':False,'input':'Genuine native account equity OHLC, no market quote export','intrabar_order_known':False,'bounds_scope':'Only available chart observations. The sampled upper bound is NOT an upper bound on unobserved full-resolution account drawdown.','variants':rows,'decision':'Retain QC reported drawdown and independent account lower bound; smaller final realized loss does not justify replacing marked drawdown with trade PnL drawdown. Pending full-universe run remains unchanged.'}
 target=Path(__file__).with_name('lvs_marked_drawdown_findings_20261019.json');target.write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if __name__=='__main__':main()
