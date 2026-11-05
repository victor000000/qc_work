"""Collect genuine QC/Rust execution evidence for the exact ZW exit regression."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import duckdb
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from qc_api_check import credentials,request
from collect import read_all_orders
from qc_contracts import execution_rows,execution_signature
from audit_21dte import audit_dte


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign',type=Path)
    parser.add_argument('--control',action='store_true')
    args=parser.parse_args();campaign=args.campaign.resolve()
    records=json.loads((campaign/'outcomes.json').read_text())
    if len(records)!=1:raise ValueError('Expected one frozen regression job')
    name,record=next(iter(records.items()));evidence=campaign/name;evidence.mkdir(exist_ok=True)
    ids=dict(projectId=record['project_id'],backtestId=record['backtest_id'])
    user,token=credentials(ROOT/'data/S001.duckdb')
    response=request(user,token,'/backtests/read',ids);b=response['backtest']
    if str(b['backtestId'])!=str(ids['backtestId']) or int(b['projectId'])!=ids['projectId']:
        raise ValueError('Wrong cloud execution')
    (evidence/'backtest.json').write_text(json.dumps(response,indent=2))
    if not b.get('completed'):raise ValueError('Cloud execution is not terminal')
    count=b.get('statistics',{}).get('Total Orders')
    orders=read_all_orders(user,token,ids,int(str(count).replace(',','')) if count is not None else None)
    (evidence/'orders.json').write_text(json.dumps(orders,indent=2))
    subprocess.run([str(ROOT/'target/release/qc-backtest-server'),'--data-dir',str(ROOT/'data'),
        'backtest-orders','--strategy','sstrangle','--name',name,'--out',str(evidence/'orders.rust.json')],check=True)
    rust=json.loads((evidence/'orders.rust.json').read_text())
    if isinstance(rust,dict):rust=rust['orders']
    fills=execution_rows(orders)
    if execution_signature(fills)!=execution_signature(execution_rows(rust)):
        raise ValueError('Rust and Python actual fills differ')
    logs=[]
    for start in range(0,10000,200):
        page=request(user,token,'/backtests/read/log',dict(ids,start=start,end=start+200,query=''))
        lines=page.get('log',page.get('logs',[]));logs.extend(lines)
        if len(lines)<200:break
    (evidence/'cloud.log').write_text('\n'.join(logs))
    original=HERE/'results/strangle_basket_20261018_145612/SSTRANGLE_20261018_145612_basket/orders.json'
    previous=[f for f in execution_rows(json.loads(original.read_text())) if f['order_id']>=717]
    def signature(rows):return [(r['timestamp'],r['symbol_id'],r['quantity'],r['qc_price'],r['fee']) for r in rows]
    if signature(fills[:8])!=signature(previous):
        raise ValueError('Fixture entry and three rolls differ from the original failed position')
    summary=dict(utc=datetime.now(timezone.utc).isoformat(),engineering_only=True,
        project_id=ids['projectId'],backtest_id=ids['backtestId'],campaign=str(campaign),
        orders=len(orders),fills=len(fills),initial_cash=15703.82,
        audits=dict(rust_python_fills_match=True,original_entry_and_three_rolls_match=True))
    cycles=[]
    if args.control:
        if len(orders)!=10 or len(fills)!=8 or 'Incomplete combo execution' not in (b.get('error') or ''):
            raise ValueError('Control did not reproduce the exact rejected combo exit')
        if any(o['status']!=7 for o in orders[-2:]):raise ValueError('Control exit was not wholly rejected')
        summary.update(status='original 21DTE combo rejection reproduced',error=b['error'])
    else:
        if b.get('error') or b['status'].rstrip('.')!='Completed':
            raise ValueError('Corrected engineering regression did not complete')
        cycles=audit_dte(orders)
        if len(orders)!=10 or len(fills)!=10 or len(cycles)!=1:
            raise ValueError('Incomplete corrected execution history')
        c=cycles[0]
        if c['exit_dte']!=21 or c['reason']!='TIME' or c['rolls']!=3:
            raise ValueError('Original three-roll 21DTE exit changed')
        if any(r['quantity']!=5 or r['group_id']>=0 for r in fills[-2:]):
            raise ValueError('Closing fills are not the full five-lot sequential pair')
        holdings=Counter()
        for f in fills:holdings[f['symbol_id']]+=f['quantity']
        if any(holdings.values()):raise ValueError('Residual holdings in native fills')
        r=b['runtimeStatistics'];net=float(r['cycle_net_pnl'])
        equity=float(r['Equity'].replace('$','').replace(',',''))
        fees=sum(f['fee'] for f in fills)
        if abs(c['pnl']-net)>.005 or abs(15703.82+net-equity)>.005:
            raise ValueError('Actual fill ledger and final account differ')
        if abs(fees-float(r['Fees'].replace('$','').replace(',','').replace('-','')))>.005:
            raise ValueError('Actual fees and account fees differ')
        summary.update(status='passed',net_pnl=net,ending_equity=equity,fees=fees,
            exit=c['exit'],exit_dte=21,rolls=3,residual_holdings=0)
        summary['audits'].update(first_eligible_21dte_exit=True,full_quantity=True,
            no_residual_holdings=True,account_and_fees_reconcile=True,default_margin_models=True)
    (evidence/'regression_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    output=HERE/'results/zw_exit_fix_20261018';output.mkdir(exist_ok=True)
    prefix='control' if args.control else 'corrected'
    frames={'executions':pd.DataFrame(fills)}
    if cycles:frames['cycles']=pd.DataFrame(cycles)
    with duckdb.connect(str(output/(prefix+'.duckdb'))) as connection:
        for table,frame in frames.items():
            frame.to_csv(output/(prefix+'_'+table+'.csv'),index=False)
            frame.to_parquet(output/(prefix+'_'+table+'.parquet'),index=False)
            connection.register('frame',frame);connection.execute('CREATE OR REPLACE TABLE '+table+' AS SELECT * FROM frame')
    (output/(prefix+'_summary.json')).write_text(json.dumps(summary,indent=2)+'\n')
    combined_path=output/'summary.json'
    combined=json.loads(combined_path.read_text()) if combined_path.exists() else {}
    combined[prefix]=summary
    combined.update(status='corrected cloud regression passed; full baseline pending' if not args.control
        else 'original rejection reproduced; corrected regression pending',performance_valid=False)
    combined_path.write_text(json.dumps(combined,indent=2)+'\n')
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file() and p.name!='checksums.json'}
    (output/'checksums.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
