"""Monitor/collect the existing paired QC speed regression; never submit or cancel."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys
import duckdb
import pandas as pd
import qc_storage as storage
from resume_basket import read_existing_backtest,validate_identity,terminal_status,atomic_json
from collect import read_all_orders
from qc_contracts import execution_rows,execution_signature
from audit_21dte import audit_dte

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from qc_api_check import credentials,request


def cross_run_signature(fills):
    # QC prefixes every event ID with its run ID. Preserve its order/event
    # suffix and all remaining fields, including price, timestamp, fee and lots.
    rows=execution_signature(fills)
    return [dict(row,event_id=row['event_id'].split('-',1)[1]) for row in rows]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('campaign',type=Path)
    args=parser.parse_args();campaign=args.campaign.resolve()
    manifest=json.loads((campaign/'manifest.json').read_text())
    if manifest['phase']!='basket-performance-regression' or len(manifest['jobs'])!=2:
        raise ValueError('Require the frozen reference/optimized pair')
    user,token=credentials(ROOT/'data/S001.duckdb');records=[];snapshots=[]
    for name in manifest['jobs']:
        with storage.connect(f'file:{ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as c:
            c.row_factory=storage.Row;row=dict(c.execute('SELECT * FROM backtest_queue WHERE name=?',(name,)).fetchone())
        if not row.get('backtest_id'):
            snapshots.append(dict(name=name,status=row['status'],completed=False));continue
        response=read_existing_backtest(user,token,row);b=response['backtest'];validate_identity(b,row)
        snapshots.append(dict(name=name,backtest_id=row['backtest_id'],status=b.get('status'),
            completed=b.get('completed'),error=b.get('error')))
        if terminal_status(b) is not None:records.append((name,row,response))
    atomic_json(campaign/'cloud_progress.json',dict(utc=datetime.now(timezone.utc).isoformat(),jobs=snapshots))
    print(json.dumps(snapshots),flush=True)
    if len(records)!=2:return
    if any(terminal_status(b['backtest'])!='done' for _,_,b in records):
        for name,row,response in records:
            atomic_json(campaign/(name+'.terminal.json'),response)
        raise RuntimeError('Performance regression cloud failure; terminal evidence preserved')
    gold_folder=HERE/'results/strangle_basket-zw-regression_20261018_173542/SSTRANGLE_20261018_173542_zw_regression'
    gold=cross_run_signature(execution_rows(json.loads((gold_folder/'orders.json').read_text())))
    fills_all=[];timings=[];digests=[]
    for name,row,response in records:
        folder=campaign/name;folder.mkdir(exist_ok=True);b=response['backtest']
        atomic_json(folder/'backtest.json',response)
        ids=dict(projectId=row['project_id'],backtestId=row['backtest_id'])
        count=b.get('statistics',{}).get('Total Orders')
        orders=read_all_orders(user,token,ids,int(str(count).replace(',','')) if count is not None else None)
        atomic_json(folder/'orders.json',orders)
        subprocess.run([str(ROOT/'target/release/qc-backtest-server'),'--data-dir',str(ROOT/'data'),
            'backtest-orders','--strategy','sstrangle','--name',name,'--out',str(folder/'orders.rust.json')],check=True)
        rust=json.loads((folder/'orders.rust.json').read_text());rust=rust['orders'] if isinstance(rust,dict) else rust
        fills=execution_rows(orders)
        if execution_signature(fills)!=execution_signature(execution_rows(rust)):
            raise ValueError('Rust/Python fill mismatch')
        if cross_run_signature(fills)!=gold:
            raise ValueError('Optimized/reference trades differ from original validated native fills')
        cycles=audit_dte(orders);r=b['runtimeStatistics']
        if len(fills)!=10 or len(cycles)!=1 or cycles[0]['exit_dte']!=21 or cycles[0]['rolls']!=3:
            raise ValueError('Paired performance regression changed real execution or21DTE exit')
        equity=float(r['Equity'].replace('$','').replace(',',''))
        if abs(equity-15703.82-cycles[0]['pnl'])>.005:
            raise ValueError('Performance fixture account does not reconcile')
        log=request(user,token,'/backtests/read/log',dict(**ids,start=0,end=200,query=''))
        atomic_json(folder/'engineering_log.json',log)
        lines=log.get('logs',log.get('log',[]))
        hashes=[line.split('PERFORMANCE_CHECKSUM ',1)[1].strip()
            for line in lines if ' PERFORMANCE_CHECKSUM ' in line]
        if len(hashes)!=1:
            raise ValueError('Missing or repeated aggregate engineering checksum; preserve this attempt')
        digest=hashes[0]
        if len(digest)!=64:raise ValueError('Missing aggregate selection fingerprint')
        version='reference' if name.endswith('_perf_reference') else 'optimized'
        digests.append(digest)
        timings.append(dict(version=version,name=name,backtest_id=row['backtest_id'],
            fixture_days=int(r['perf_fixture_days']),phase_seconds=int(r['perf_fixture_us'])/1e6,
            equity_history_samples=int(r['perf_equity_history_samples']),
            equity_history_seconds=int(r['perf_equity_history_us'])/1e6,
            equity_screen_seconds=int(r['perf_equity_screen_us'])/1e6,
            actual_fills=len(fills),cycle_pnl=cycles[0]['pnl'],fees=sum(f['fee'] for f in fills),
            ending_equity=equity,selection_sha256=digest))
        fills_all.extend(dict(version=version,**f) for f in fills)
    if len(set(digests))!=1 or len({r['fixture_days'] for r in timings})!=1:
        raise ValueError('Daily ATM IV/delta or selected contracts changed')
    if len({r['equity_history_samples'] for r in timings})!=1 or timings[0]['equity_history_samples']<=0:
        raise ValueError('Native equity history probe is missing or changed')
    t={r['version']:r['phase_seconds'] for r in timings}
    by_version={r['version']:r for r in timings}
    summary=dict(status='passed',engineering_only=True,full_cloud_speedup_validated=False,
        measured_futures_preparation_speedup=t['reference']/t['optimized'],timings=timings,
        measured_short_equity_history_speedup=by_version['reference']['equity_history_seconds']/by_version['optimized']['equity_history_seconds'],
        measured_synthetic_equity_screen_speedup=by_version['reference']['equity_screen_seconds']/by_version['optimized']['equity_screen_seconds'],
        audits=dict(selection_fingerprint_equal=True,original_fills_identical=True,
            rust_python_fills_equal=True,first21dte_exit=True,account_reconciles=True),
        limitations='One paired native futures fixture plus short SPY history/synthetic screening probes; does not measure full-universe seeding or total full-baseline speedup')
    out=HERE/'results/performance_fix_20261018';out.mkdir(exist_ok=True)
    with duckdb.connect(str(out/'cloud_regression.duckdb')) as c:
        for table,frame in [('executions',pd.DataFrame(fills_all)),('timings',pd.DataFrame(timings))]:
            frame.to_csv(out/('cloud_'+table+'.csv'),index=False);frame.to_parquet(out/('cloud_'+table+'.parquet'),index=False)
            c.register('frame',frame);c.execute('CREATE OR REPLACE TABLE '+table+' AS SELECT * FROM frame')
    atomic_json(out/'cloud_summary.json',summary);print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
