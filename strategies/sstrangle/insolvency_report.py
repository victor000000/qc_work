"""Audit the exact native BAC insolvency fixture against preserved baseline fills."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import duckdb
import pandas as pd
from collect import read_all_orders
from qc_contracts import execution_rows,execution_signature

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from qc_api_check import credentials,request


def economic_signature(rows):
    fields=('timestamp','strategy_key','reason','symbol_id','underlying_id','expiry','call_put',
            'strike','security_type','quantity','qc_price','multiplier','fee')
    return [{k:row[k] for k in fields} for row in rows]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('campaign',type=Path)
    campaign=parser.parse_args().campaign.resolve()
    manifest=json.loads((campaign/'manifest.json').read_text())
    if manifest['phase']!='basket-insolvency-regression':raise ValueError('Wrong fixture')
    outcomes=json.loads((campaign/'outcomes.json').read_text());name,row=next(iter(outcomes.items()))
    user,token=credentials(ROOT/'data/S001.duckdb')
    ids=dict(projectId=row['project_id'],backtestId=row['backtest_id'])
    folder=campaign/name;folder.mkdir(exist_ok=True)
    full=request(user,token,'/backtests/read',ids)
    (folder/'backtest.json').write_text(json.dumps(full,indent=2))
    b=full['backtest']
    if row['status']!='done' or b.get('error') or not b['completed']:raise ValueError('Fixture failed')
    orders=read_all_orders(user,token,ids,int(b['statistics']['Total Orders']))
    (folder/'orders.json').write_text(json.dumps(orders,indent=2))
    subprocess.run([str(ROOT/'target/release/qc-backtest-server'),'--data-dir',str(ROOT/'data'),
        'backtest-orders','--strategy','sstrangle','--name',name,'--out',str(folder/'orders.rust.json')],check=True)
    rust=json.loads((folder/'orders.rust.json').read_text());rust=rust['orders'] if isinstance(rust,dict) else rust
    fills=execution_rows(orders)
    if execution_signature(fills)!=execution_signature(execution_rows(rust)):raise ValueError('Rust/Python mismatch')
    gold_path=HERE/'results/strangle_basket_20261018_173739/failure_diagnostics/summary.json'
    gold=json.loads(gold_path.read_text())['last_cycle_fills']
    if economic_signature(fills)!=economic_signature(gold):raise ValueError('BAC actual fills changed from original native cycle')
    holdings={}
    for f in fills:holdings[f['symbol_id']]=holdings.get(f['symbol_id'],0)+f['quantity']
    fees=sum(f['fee'] for f in fills)
    net=sum(-f['quantity']*f['qc_price']*f['multiplier']-f['fee'] for f in fills)
    r=b['runtimeStatistics'];money=lambda v:float(v.replace('$','').replace(',',''))
    if (len(fills)!=6 or any(holdings.values()) or abs(fees-6)>.005 or abs(net+915)>.005
            or abs(money(r['Equity'])-872.71-net)>.005 or money(r['Holdings'])!=0
            or abs(abs(money(r['Fees']))-fees)>.005 or r['baseline_outcome']!='insolvent'
            or int(r['terminal_margin_batches_skipped'])!=1):
        raise ValueError('Insolvency account/fees/terminal protection failed')
    summary=dict(utc=datetime.now(timezone.utc).isoformat(),status='passed',engineering_only=True,
        project_id=ids['projectId'],backtest_id=ids['backtestId'],campaign=str(campaign),
        actual_fills=len(fills),initial_cash=872.71,net_pnl=net,ending_equity=money(r['Equity']),fees=fees,
        insolvency_utc=r['insolvency_utc'],audits=dict(original_economic_fills_identical=True,
        rust_python_fills_equal=True,no_duplicate_liquidation=True,zero_residual_holdings=True,
        actual_fees_and_account_reconcile=True,explicit_insolvency_outcome=True))
    out=HERE/'results/insolvency_fix_20261018';out.mkdir(exist_ok=True)
    frame=pd.DataFrame(fills);frame.to_parquet(out/'executions.parquet',index=False)
    frame.to_csv(out/'executions.csv',index=False)
    with duckdb.connect(str(out/'evidence.duckdb')) as db:
        db.register('frame',frame);db.execute('CREATE OR REPLACE TABLE executions AS SELECT * FROM frame')
        if db.execute('SELECT COUNT(*) FROM read_parquet(?)',[str(out/'executions.parquet')]).fetchone()[0]!=len(fills):
            raise ValueError('Parquet readback mismatch')
    summary['executions_parquet_sha256']=hashlib.sha256((out/'executions.parquet').read_bytes()).hexdigest()
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
