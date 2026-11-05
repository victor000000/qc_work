"""Audit actual failed-baseline fills through insolvency; never publish a full-period return."""
from collections import Counter
from datetime import date,datetime,time,timedelta,timezone
import hashlib
import json
from pathlib import Path
import sys
import duckdb
import pandas as pd
from audit import reconstruct
from audit_21dte import audit_dte
from basket_report import audit_batches,ny_time,noon_open,ROOT_MARKETS
from basket.basket_rules import standard_equity_monthly
from qc_contracts import execution_rows,execution_signature,option_identity

HERE=Path(__file__).resolve().parent
campaign=HERE/'results/strangle_basket_20261018_173739'
folder=campaign/'SSTRANGLE_20261018_173739_basket'
orders=json.loads((folder/'orders.json').read_text());rust=json.loads((folder/'orders.rust.json').read_text())
full=json.loads((folder/'backtest.json').read_text())['backtest'];fills=execution_rows(orders)
assert execution_signature(fills)==execution_signature(execution_rows(rust))
assert len(orders)==int(full['statistics']['Total Orders'])==1010
cycles=audit_dte(orders);entries,batches,peak=audit_batches(orders,504)
entry_map={(r['key'],r['entry']):r for r in entries}
alias={(f['strategy_key'],ny_time(f['timestamp']).date()):(f['strategy_key'][4:] if f['strategy_key'].startswith('FUT_') else (f['underlying_alias'] or f['underlying']).split()[0]) for f in fills if f['reason']=='OPEN'}
calendars=json.loads((HERE/'research/reference/lean_market_hours_20261018.json').read_text())['entries']
residual=Counter()
for f in fills:residual[f['symbol_id']]+=f['quantity']
assert not any(residual.values())
for c in cycles:
    e=entry_map[(c['ticker'],c['entry'])]
    c.update(mapped_ticker=alias[(c['ticker'],ny_time(c['entry']).date())],quantity=int(e['quantity']),batch_id=int(e['batch_id']),
        allocation_equity=float(e['allocation_equity']),allocation_budget=float(e['allocation_budget']))
    assert 35<=c['entry_dte']<=95
    if c['ticker'].startswith('FUT_'):
        root=c['ticker'][4:];market=ROOT_MARKETS[root]
        cal=calendars.get(f'Future-{market}-{root}',calendars[f'Future-{market}-[*]'])
    else:
        cal=calendars['Equity-usa-[*]'];expiry=date.fromisoformat(c['expiry'])
        friday=expiry.replace(day=1)+timedelta(days=(4-expiry.replace(day=1).weekday())%7+14)
        assert standard_equity_monthly(expiry,not noon_open(friday,cal))
    if c['reason']=='TIME' or(c['reason']=='MARGIN' and c['exit_dte']<=21):
        expected=date.fromisoformat(c['calendar_21dte_date'])
        for _ in range(15):
            if noon_open(expected,cal):break
            expected+=timedelta(days=1)
        else:raise ValueError('No eligible product session')
        if c['reason']=='TIME':assert ny_time(c['exit']).date()==expected
        else:assert ny_time(c['exit'])<=datetime.combine(expected,time(12),ny_time(c['exit']).tzinfo)
    elif c['reason'] not in ('END','MARGIN'):assert c['exit_dte']>21
net=sum(c['pnl'] for c in cycles);fees=sum(f['fee'] for f in fills)
equity=float(full['runtimeStatistics']['Equity'].replace('$','').replace(',',''))
assert abs(60000+net-equity)<.005
assert abs(fees-float(full['statistics']['Total Fees'].replace('$','').replace(',','')))<.005
last=cycles[-1];assert last['mapped_ticker']=='BAC' and last['reason']=='MARGIN'
assert abs(last['allocation_equity']-872.71)<.005 and abs(last['pnl']+915)<.005
assert abs(equity+42.29)<.005
cycle_df=pd.DataFrame(cycles)
by_ticker=cycle_df.groupby('ticker',as_index=False).agg(mapped_ticker=('mapped_ticker','last'),cycles=('pnl','size'),pnl=('pnl','sum'),fees=('fees','sum')).sort_values('pnl')
last_orders=[o for o in orders if o['tag'].startswith(last['ticker']+':') and o['time']>=last['entry']]
last_fills=[f for f in fills if f['order_id']>=min(o['id'] for o in last_orders)]
proof=[]
for bid,backtest in [('CL','2015-11-30'),('ZW','2017-07-06')]:
    rows=[c for c in cycles if c['ticker']=='FUT_'+bid and ny_time(c['entry']).date().isoformat()==backtest]
    assert len(rows)==1 and rows[0]['exit_dte']==21;proof+=rows
summary=dict(utc=datetime.now(timezone.utc).isoformat(),status='confirmed account insolvency after fully filled BAC liquidation',
    full_requested_baseline_valid=False,performance_period='Observed execution only:2012-01-03 through2020-03-12; requested2026 end not reached',
    project_id=31338456,backtest_id=full['backtestId'],cloud_error=full['error'],
    orders=len(orders),actual_fills=len(fills),closed_cycles=len(cycles),batches=len(batches),peak_basket=peak,
    initial_cash=60000.,fill_ledger_net_pnl=net,fees=fees,ending_equity=equity,residual_holdings=0,
    exit_reasons=dict(Counter(c['reason'] for c in cycles)),
    audits=dict(complete_declared_orders=True,rust_python_actual_fills_match=True,
        entire_observed_fill_ledger_reconciles=True,actual_fees_reconcile=True,no_residual_holdings=True,
        full504_range_ivr_above70=True,opening_equity_divided_by_batch_count=True,
        no_rebalancing_or_replacement_entries=True,first_eligible21dte_exits=True,
        monthly_metadata_and_standard_equity_expiries=True),
    last_cycle=last,last_cycle_fills=last_fills,largest_losses=by_ticker.head(8).to_dict('records'),
    previous_CL_ZW_repairs_survived=proof,
    diagnosis='BAC started with872.71 account equity, one put and one call. The final MARGIN close realized a915.00 cycle loss including fees. All positions closed, leaving-42.29. With negative cash and zero holdings, remaining buying power cannot become nonnegative. The guard misclassifies this economic terminal state as an execution runtime error; there is no missing-fill or residual-position discrepancy in QC exports. This does not independently validate vendor quote accuracy.',
    necessary_engineering_fix='Represent fully flat nonpositive-equity insolvency as an explicit terminal outcome without new entries, added funds, disabled margin checks or fabricated fills. Preserve the debt and bankruptcy date. Validate separately before any rerun.',
    risk_issue='Full available equity/x can concentrate nearly all collateral in one naked strangle when only one candidate is affordable. Exposure/risk-rule changes are strategy changes and are not applied before baseline review.',
    display_identity='Loss grouping uses native strategy SIDs. Human ticker aliases are exported display labels and can change or be malformed; they are never used to match actual holdings or fills.',
    log_limit='Downloaded QC console logs stop in2016 despite complete1010order history; order annotations and fill events are authoritative for later cycles. Full log-based confirmation is unavailable.',
    monitoring='Paused on actual cloud failure; staged speed-validation pair was not launched')
out=campaign/'failure_diagnostics';out.mkdir(exist_ok=True)
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
frames=dict(executions=pd.DataFrame(fills),cycles=cycle_df,pnl_by_ticker=by_ticker,
    terminal_cycle_executions=pd.DataFrame(last_fills),residual_holdings=pd.DataFrame([dict(symbol_id=s,quantity=q) for s,q in residual.items() if q],columns=['symbol_id','quantity']))
receipts={}
with duckdb.connect(str(out/'failure_evidence.duckdb')) as c:
    for table,frame in frames.items():
        c.register('frame',frame);c.execute('CREATE OR REPLACE TABLE '+table+' AS SELECT * FROM frame')
        path=out/(table+'.parquet');c.execute('COPY '+table+' TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(path)])
        frame.to_csv(out/(table+'.csv'),index=False)
        assert c.execute('SELECT count(*) FROM '+table).fetchone()[0]==len(frame)
        assert c.execute('SELECT count(*) FROM read_parquet(?)',[str(path)]).fetchone()[0]==len(frame)
        receipts[table]=dict(rows=len(frame),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
(out/'manifest.json').write_text(json.dumps(dict(scope='Failed requested-period run; audited observed fills through insolvency',
    tables=receipts,source_sha256={n:hashlib.sha256((folder/n).read_bytes()).hexdigest()
        for n in ['orders.json','orders.rust.json','backtest.json','cloud.log']}),indent=2)+'\n')
p=HERE/'research/CURRENT_BASELINE_PROGRESS.json';d=json.loads(p.read_text());d.update(updated_at=summary['utc'],
    status='failed: account insolvent2020-03-12 after complete BAC margin close; exported fills reconcile',
    performance_valid=False,automatic_monitor_status='PAUSED',failure_summary=str(out/'summary.json'),
    required_next_steps=[summary['necessary_engineering_fix'],'Review exposure/risk only after distinguishing observed bankruptcy from a complete requested-period baseline.'])
d['performance_optimization']['status']='local speedups validated; paired QC stage not launched because full baseline failed; monitor paused'
p.write_text(json.dumps(d,indent=2)+'\n')
print(json.dumps({k:summary[k] for k in ['orders','actual_fills','closed_cycles','batches','peak_basket','fill_ledger_net_pnl','fees','ending_equity','largest_losses']},indent=2))
