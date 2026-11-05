"""Collect actual isolated28DTE executions; no submission or performance claim."""
import argparse
from collections import Counter
from datetime import datetime
import importlib.util
import json
from pathlib import Path

def load(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
wag=load('_early_wag','wag_exit_report.py')
shared=load('_early_shared','report.py')

def audit(orders,rust,full):
    fills=wag.execution_rows(orders);other=wag.execution_rows(rust);issues=[]
    if wag.economic_signature(fills)!=wag.economic_signature(other):issues.append('Rust/Python mismatch')
    if len(orders)!=4 or len(fills)!=4:issues.append('Expected four actual orders/fills')
    if wag.economic_signature(fills[:2])!=wag.economic_signature(wag.original_first_four()[:2]):issues.append('Original opening differs')
    residual=Counter();cash=fees=0.
    for f in fills:
        residual[f['symbol_id']]+=f['quantity'];cash-=f['quantity']*f['qc_price']*f['multiplier'];fees+=f['fee']
    if any(abs(q)>1e-8 for q in residual.values()):issues.append('Actual residual holdings')
    closing=fills[2:]
    if len(closing)!=2 or any(f['quantity']!=1 or f['reason']!='TIME' or shared.ny_time(f['timestamp']).replace(tzinfo=None)!=datetime(2019,11,22,12) for f in closing):issues.append('Missing exact28DTE noon buybacks')
    runtime=full.get('runtimeStatistics',{})
    try:
        equity=shared.money(runtime['Equity'])
        if abs(equity-(41194.185+cash-fees))>.0051:issues.append('Account cashflow mismatch')
        if abs(abs(shared.money(runtime['Fees']))-fees)>.005:issues.append('Fee mismatch')
        if shared.money(runtime['Holdings'])!=0:issues.append('Runtime holdings nonzero')
    except (KeyError,ValueError):equity=None;issues.append('Missing terminal account evidence')
    if wag.terminal_status(full)!='done':issues.append('Cloud not cleanly completed')
    return dict(engineering_only=True,calmar_claim=False,verified=not issues,issues=issues,orders=len(orders),fills=len(fills),cashflow=cash,fees=fees,net_pnl=cash-fees,ending_equity=equity,residuals=dict(residual),exit_dte=28),fills

def main():
    parser=argparse.ArgumentParser();parser.add_argument('campaign',type=Path);a=parser.parse_args();c=a.campaign.resolve();manifest=json.loads((c/'manifest.json').read_text());name=manifest['jobs'][0]
    if manifest['phase']!='basket-wag-early' or len(manifest['jobs'])!=1:raise ValueError('Wrong campaign')
    with wag.storage.connect(f'file:{wag.ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as db:
        db.row_factory=wag.storage.Row;row=dict(db.execute('SELECT * FROM backtest_queue WHERE name=?',(name,)).fetchone())
    source=wag.frozen_source(c,'wag_early28',manifest['variants']['wag_early28'],row)
    if not row.get('backtest_id'):print(json.dumps(dict(status=row['status'],name=name)));return
    user,token=wag.credentials(wag.ROOT/'data/S001.duckdb');response=shared.read_research_backtest(user,token,c,name,row);full=response['backtest'];wag.validate_identity(full,row)
    if wag.terminal_status(full) is None:print(json.dumps(dict(status=full.get('status'),backtest_id=row['backtest_id'])));return
    folder=shared.collect_terminal(user,token,c,name,row,response)
    orders=json.loads((folder/'orders.json').read_text());rust=json.loads((folder/'orders.rust.json').read_text());rust=rust['orders'] if isinstance(rust,dict) else rust
    result,fills=audit(orders,rust,full);result.update(project_id=row['project_id'],backtest_id=row['backtest_id'],frozen_source=source)
    out=c/'early_exit_report';shared.write_tables(out,dict(executions=fills));wag.atomic_json(out/'summary.json',result);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
