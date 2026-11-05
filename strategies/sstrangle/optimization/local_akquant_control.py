#!/usr/bin/env python3
"""Run a real QC equity cycle through AKQuant as ledger parity only.

Fill-event-only bars cannot establish marked drawdown or optimize exits.
"""
import csv,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'strategies/sstrangle/local'))
from replay import run_engine
folder=ROOT/'strategies/sstrangle/results/strangle_basket_20261018_191012/baseline_report'
rows=list(csv.DictReader((folder/'executions.csv').open()))
key=rows[0]['strategy_key']
selected=[]
for row in rows:
    if row['strategy_key']!=key:continue
    assert float(row['multiplier'])==100
    row=dict(row,timestamp=row['timestamp'],symbol=row['symbol_id'],age_minutes=0)
    selected.append(row)
    if row['reason']=='TIME' and sum(float(r['quantity']) for r in selected)==0:break
assert len(selected)==4 and sum(float(r['quantity']) for r in selected)==0
out=Path(__file__).with_name('local_results_20261019')/'akquant_ledger_control'
_,summary=run_engine(selected,{int(r['order_id']):float(r['qc_price']) for r in selected},out,initial_cash=60000)
summary.update(classification='ledger_control_only_not_strategy_backtest',source_cycle=key,
    valid_calmar=None,expected_cycle_pnl=1753.6,
    warning='Only genuine execution-event prices were supplied. Do not use this equity_curve for drawdown or alternative-exit optimization.')
assert abs(summary['engine_net_pnl']-1753.6)<1e-6
(out/'audit.json').write_text(json.dumps(summary,indent=2))
