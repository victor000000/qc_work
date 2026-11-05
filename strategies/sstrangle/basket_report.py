"""Audit a completed monthly-only basket and publish its execution research files."""
import argparse
from collections import Counter,defaultdict
from datetime import date,datetime,time,timedelta
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb
import pandas as pd
from audit_21dte import audit_dte
from audit import rejected_roll,order_group_id,validate_sequential_close
from qc_contracts import execution_rows,execution_signature,option_identity
from history_report import performance_window
from basket.basket_rules import standard_equity_monthly

NY=ZoneInfo('America/New_York')
ROOT_MARKETS={**dict.fromkeys(['CL','NG','RB','HO'],'nymex'),
              **dict.fromkeys(['ZN','ZT','ZB','ZC','ZS','ZW'],'cbot'),
              **dict.fromkeys(['ES','NQ'],'cme'),**dict.fromkeys(['GC','SI','HG'],'comex')}


def ny_time(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(NY)


def events(log,marker):
    rows=[]
    for line in log.splitlines():
        if ' '+marker+' ' in line:
            rows.append(dict(json.loads(line.split(' '+marker+' ',1)[1]),log_time=line[:19]))
    return rows


def metadata(order):
    return dict(p.split('=',1) for p in order['tag'].split(';')[1:] if '=' in p)


def audit_batches(orders,lookback):
    groups=defaultdict(list)
    for order in sorted(orders,key=lambda o:o['id']):
        groups[order_group_id(order)].append(order)
    active,batches,entries={}, {}, []
    peak=0
    for group in groups.values():
        validate_sequential_close(group)
        if len(group)!=2:
            raise ValueError('Combo must contain exactly two legs')
        key,reason=group[0]['tag'].split(';',1)[0].split(':',1)
        if any(o['tag'].split(';',1)[0]!=key+':'+reason for o in group):
            raise ValueError('Mismatched combo tags')
        if rejected_roll(group):
            if key not in active:
                raise ValueError('Rejected roll has no active holding')
            continue
        quantities=[sum(float(e.get('fillQuantity',0)) for e in o['events']) for o in group]
        if not quantities[0] or abs(quantities[0])!=abs(quantities[1]):
            raise ValueError('Unequal leg quantities')
        quantity=abs(quantities[0])
        if reason=='OPEN':
            m=metadata(group[0]);batch=int(m['batch_id'])
            if key in active or any(t['batch_id']!=batch for t in active.values()):
                raise ValueError('New batch entered before every previous holding closed')
            if ny_time(group[0]['time']).time()<time(12):
                raise ValueError('Entry occurred before noon')
            if any(q>=0 for q in quantities) or quantity!=int(m['quantity']):
                raise ValueError('Opening fills do not match declared short lots')
            identities=[option_identity(o['symbol']) for o in group]
            if {r['call_put'] for r in identities}!={'P','C'} or len({r['expiry'] for r in identities})!=1:
                raise ValueError('Opening legs do not share a put/call expiry')
            if m['monthly_only']!='True' or float(m['ivr'])<=70 or int(m['samples'])!=lookback:
                raise ValueError('Monthly/IVR/full-window gate violated')
            rank=100*(float(m['iv'])-float(m['iv_low']))/(float(m['iv_high'])-float(m['iv_low']))
            if abs(rank-float(m['ivr']))>1e-7:
                raise ValueError('IVR is not min/max range rank')
            budget=float(m['allocation_equity'])/int(m['basket_count'])
            if abs(budget-float(m['allocation_budget']))>.001:
                raise ValueError('Opening budget is not equity/x')
            if float(m['estimated_initial_margin'])+float(m['estimated_entry_fees'])>budget+.001:
                raise ValueError('Opening lots exceed equity/x collateral budget')
            record=batches.setdefault(batch,dict(batch_id=batch,entry=group[0]['time'],
                planned_count=int(m['basket_count']),equity=float(m['allocation_equity']),
                budget=budget,keys=[],volumes=[],sealed=False))
            if record['sealed'] or ny_time(record['entry']).date()!=ny_time(group[0]['time']).date():
                raise ValueError('Replacement entry added to an existing batch')
            if record['planned_count']!=int(m['basket_count']) or abs(record['budget']-budget)>.001:
                raise ValueError('Batch opening budgets differ')
            record['keys'].append(key);record['volumes'].append(float(m['volume']))
            active[key]=dict(batch_id=batch,quantity=quantity)
            entries.append(dict(key=key,entry=group[0]['time'],expiry=identities[0]['expiry'],**m))
            peak=max(peak,len(active))
            if peak>13:
                raise ValueError('Basket exceeds thirteen holdings')
        else:
            if key not in active or quantity!=active[key]['quantity']:
                raise ValueError('Existing position quantity changed or cycle is missing')
            if reason!='ROLL':
                if any(q<=0 for q in quantities):
                    raise ValueError('Closing combo must buy back both short legs')
                batches[active[key]['batch_id']]['sealed']=True
                del active[key]
    if active:
        raise ValueError('Unclosed holdings in downloaded order history')
    for record in batches.values():
        if len(record['keys'])!=record['planned_count']:
            raise ValueError('Actual batch membership differs from sizing denominator')
        if record['volumes']!=sorted(record['volumes'],reverse=True):
            raise ValueError('Batch entries are not in descending underlying volume')
    return entries,list(batches.values()),peak


def parsed_day(value):
    return datetime.strptime(value,'%m/%d/%Y').date()


def basket_performance_window(daily,initial,begin,end):
    """A bankrupt account has a measurable loss, but no real-valued CAGR."""
    if daily[max(daily)]>0:
        return performance_window(daily,initial,begin,end)
    values=[v for d,v in sorted(daily.items()) if begin<=d<=end]
    before=[v for d,v in sorted(daily.items()) if d<begin]
    opening=before[-1] if before else initial
    if not values or opening<=0 or end<=begin:
        raise ValueError('Invalid insolvent performance window')
    peak=opening;drawdown=0
    for value in values:
        peak=max(peak,value);drawdown=max(drawdown,1-value/peak)
    return dict(start=str(begin),end=str(end),observations=len(values),opening_equity=opening,
        net_pnl=values[-1]-opening,return_fraction=values[-1]/opening-1,cagr=None,
        cagr_reason='Undefined for nonpositive terminal equity',max_daily_drawdown=drawdown)


def audit_available_logs(entry_logs,close_logs,entries,cycles):
    """API log truncation cannot replace native fills or complete order metadata."""
    if len(entries)!=len(cycles):
        raise ValueError('Entry/cycle counts differ')
    expected={(e['key'],str(ny_time(e['entry']).date())):e for e in entries}
    actual={(c['ticker'],str(ny_time(c['entry']).date())):c for c in cycles}
    seen=set()
    for row in entry_logs:
        key=(row['key'],row['date'])
        if key in seen or key not in expected:
            raise ValueError('Unexpected or repeated entry diagnostic')
        seen.add(key)
        for field in ('ivr','samples','quantity','batch_id','allocation_budget'):
            if field in row and abs(float(row[field])-float(expected[key][field]))>1e-6:
                raise ValueError('Entry diagnostic disagrees with real order metadata')
    seen=set()
    for row in close_logs:
        key=(row['key'],row['entry'])
        if key in seen or key not in actual:
            raise ValueError('Unexpected or repeated close diagnostic')
        seen.add(key);cycle=actual[key]
        if (row['reason']!=cycle['reason'] or row['date']!=str(ny_time(cycle['exit']).date())
                or abs(float(row['pnl'])-cycle['pnl'])>.005
                or abs(float(row['fees'])-cycle['fees'])>.005):
            raise ValueError('Close diagnostic disagrees with actual fills')
    return dict(entry_logs=len(entry_logs),cycle_logs=len(close_logs),
        complete=len(entry_logs)==len(entries) and len(close_logs)==len(cycles),
        authority='Complete native order metadata, actual fills and runtime counts; available logs cross-checked')


def seconds(value):
    days,clock=(value.split('.',1) if '.' in value else ('0',value))
    h,m,s=map(int,clock.split(':'))
    return int(days)*86400+h*3600+m*60+s


def noon_open(day,entry):
    local=datetime.combine(day,time(12),NY).astimezone(ZoneInfo(entry['exchangeTimeZone']))
    local_day=local.date()
    if local_day in {parsed_day(d) for d in entry.get('holidays',[])}:
        return False
    at=local.hour*3600+local.minute*60
    for field,comparison in [('earlyCloses',lambda a,b:a>=b),('lateOpens',lambda a,b:a<b)]:
        special={parsed_day(d):seconds(v) for d,v in entry.get(field,{}).items()}
        if local_day in special and comparison(at,special[local_day]):
            return False
    return any(s['state']=='market' and seconds(s['start'])<=at<seconds(s['end'])
               for s in entry[local.strftime('%A').lower()])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign',type=Path)
    args=parser.parse_args();campaign=args.campaign.resolve()
    manifest=json.loads((campaign/'manifest.json').read_text())
    outcomes=json.loads((campaign/'outcomes.json').read_text())
    if len(outcomes)!=1:
        raise ValueError('Expected a single basket baseline run')
    name,record=next(iter(outcomes.items()))
    if record['status']!='done':
        raise ValueError('Cloud run failed; cannot publish a baseline')
    folder=campaign/name;config=manifest['variants']['basket']
    full=json.loads((folder/'backtest.json').read_text())['backtest'];stats=full['runtimeStatistics']
    orders=json.loads((folder/'orders.json').read_text())
    if len(orders)!=int(str(full['statistics']['Total Orders']).replace(',','')):
        raise ValueError('Incomplete order history')
    fills=execution_rows(orders)
    rust=execution_rows(json.loads((folder/'orders.rust.json').read_text()))
    if execution_signature(fills)!=execution_signature(rust):
        raise ValueError('Rust and Python execution downloads disagree')
    entries,batches,peak=audit_batches(orders,config['lookback'])
    cycles=audit_dte(orders)
    log=(folder/'cloud.log').read_text()
    entry_logs=events(log,'ENTRY');close_logs=events(log,'CYCLE')
    log_coverage=audit_available_logs(entry_logs,close_logs,entries,cycles)
    entry_map={(r['key'],ny_time(r['entry']).date()):r for r in entries}
    residual=Counter()
    for fill in fills:
        residual[fill['symbol_id']]+=fill['quantity']
    if any(abs(q)>1e-7 for q in residual.values()):
        raise ValueError('Residual option holdings in exported fills')
    calendar_path=Path(__file__).parent/'research/reference/lean_market_hours_20261018.json'
    calendars=json.loads(calendar_path.read_text())['entries']
    for cycle in cycles:
        entry=entry_map[(cycle['ticker'],ny_time(cycle['entry']).date())]
        cycle.update(batch_id=int(entry['batch_id']),quantity=int(entry['quantity']),
            allocation_budget=float(entry['allocation_budget']),
            estimated_initial_margin=float(entry['estimated_initial_margin']))
        if not 35<=cycle['entry_dte']<=95:
            raise ValueError('Entry DTE outside monthly entry window')
        if cycle['ticker'].startswith('FUT_'):
            root=cycle['ticker'][4:];market=ROOT_MARKETS[root]
            cal=calendars.get(f'Future-{market}-{root}',calendars[f'Future-{market}-[*]'])
        else:
            cal=calendars['Equity-usa-[*]']
            expiry=date.fromisoformat(cycle['expiry'])
            first=expiry.replace(day=1);friday=first+timedelta(days=(4-first.weekday())%7+14)
            if not standard_equity_monthly(expiry,not noon_open(friday,cal)):
                raise ValueError('Non-monthly equity expiry')
        if cycle['reason']=='TIME' or (cycle['reason']=='MARGIN' and cycle['exit_dte']<=21):
            eligible=date.fromisoformat(cycle['calendar_21dte_date'])
            for _ in range(15):
                if noon_open(eligible,cal):break
                eligible+=timedelta(days=1)
            else:raise ValueError('No eligible product session in calendar')
            if cycle['reason']=='TIME':
                cycle['expected_time_exit']=str(eligible)
                cycle['time_exit_on_first_eligible_session']=ny_time(cycle['exit']).date()==eligible
                if not cycle['time_exit_on_first_eligible_session']:
                    raise ValueError('21-DTE exit missed first eligible product session: '+str(cycle))
            elif ny_time(cycle['exit'])>datetime.combine(eligible,time(12),NY):
                raise ValueError('Margin liquidation occurred after mandatory DTE exit was due')
        elif cycle['reason'] not in ('END','MARGIN') and cycle['exit_dte']<=21:
            raise ValueError('Mandatory DTE exit was not given priority')
    for b in batches:
        batch_cycles=[c for c in cycles if c['batch_id']==b['batch_id']]
        b['exit']=max(c['exit'] for c in batch_cycles)
        b['pnl']=sum(c['pnl'] for c in batch_cycles)
        b['fees']=sum(c['fees'] for c in batch_cycles)
        b['keys']=json.dumps(b['keys']);b['volumes']=json.dumps(b['volumes'])
    initial=float(config['initial_cash']);net=sum(c['pnl'] for c in cycles)
    money=lambda value:float(str(value).replace('$','').replace(',',''))
    if (abs(money(stats['Equity'])-initial-net)>.005
            or abs(abs(money(stats['Fees']))-sum(f['fee'] for f in fills))>.005
            or money(stats['Holdings'])!=0 or money(stats['Unrealized'])!=0):
        raise ValueError('Actual fills/fees disagree with terminal account and holdings')
    if (abs(net-float(stats['cycle_net_pnl']))>.05
            or ('closed_cycles' in stats and len(cycles)!=int(stats['closed_cycles']))
            or len(entries)!=int(stats['entries'])):
        raise ValueError('Cycle/fill accounting differs from cloud result')
    values=json.loads((folder/'trading_period.json').read_text())['chart']['series']['Equity']['values']
    daily={}
    for point in values:
        stamp,value=(point['x'],point['y']) if isinstance(point,dict) else point[:2]
        daily[datetime.fromtimestamp(stamp,NY).date()]=float(value)
    if len(daily)!=int(stats['active_snapshots']):
        raise ValueError('Incomplete daily equity chart')
    if abs(daily[max(daily)]-initial-net)>.05:
        raise ValueError('Final daily equity does not reconcile with execution ledger')
    start=date(*config['trade_start']);requested_end=date(*config['end'])
    terminal_utc=stats.get('insolvency_utc','none')
    inferred_outcome='insolvent' if terminal_utc!='none' else 'period_complete'
    outcome=stats.get('baseline_outcome',inferred_outcome)
    end=(date.fromisoformat(stats['observed_end']) if 'observed_end' in stats else
         ny_time(terminal_utc).date()) if outcome=='insolvent' else requested_end
    if outcome=='insolvent':
        terminal=ny_time(stats['insolvency_utc'])
        if (initial+net>0 or terminal.date()!=end or max(ny_time(f['timestamp']) for f in fills)>terminal
                or abs(float(stats['insolvency_equity'])-initial-net)>.005
                or int(stats.get('terminal_margin_batches_skipped',0))!=1):
            raise ValueError('Insolvency outcome disagrees with actual terminal fills/account')
    annual=[];previous=initial
    for year in range(start.year,end.year+1):
        marks=[v for d,v in sorted(daily.items()) if d.year==year]
        ending=marks[-1] if marks else previous
        closed=[c for c in cycles if ny_time(c['exit']).year==year]
        annual.append(dict(year=year,entries=sum(ny_time(c['entry']).year==year for c in cycles),
            closed_cycles=len(closed),realized_cycle_pnl=sum(c['pnl'] for c in closed),
            equity_pnl=ending-previous,ending_equity=ending));previous=ending
    attempts=defaultdict(list)
    for order in orders:
        attempts[order_group_id(order)].append(order)
    sequential_pairs={order_group_id(o) for o in orders if order_group_id(o)<0}
    if (int(stats.get('sequential_closes_completed',0))!=len(sequential_pairs)
            or ('sequential_closes_submitted' in stats
                and int(stats['sequential_closes_submitted'])!=len(sequential_pairs))):
        raise ValueError('Native sequential closing pairs differ from runtime completion counts')
    summary=dict(project_id=record['project_id'],backtest_id=record['backtest_id'],
        url=f'https://www.quantconnect.com/project/{record["project_id"]}/{record["backtest_id"]}',
        engineering_smoke=bool(config.get('engineering_smoke')),initial_cash=initial,
        orders=len(orders),executions=len(fills),cycles=len(cycles),batches=len(batches),peak_basket=peak,
        equity_cycles=sum(not c['ticker'].startswith('FUT_') for c in cycles),
        future_cycles=sum(c['ticker'].startswith('FUT_') for c in cycles),
        first_entry=stats['first_entry'],ivr_observations=config['lookback'],net_pnl=net,
        fees=sum(c['fees'] for c in cycles),wins=sum(c['pnl']>0 for c in cycles),
        rolls=sum(c['rolls'] for c in cycles),exit_reasons=dict(Counter(c['reason'] for c in cycles)),
        rejected_rolls=sum(rejected_roll(g) for g in attempts.values()),
        sequential_future_closes=len(sequential_pairs),
        margin_call_events=int(stats.get('margin_call_events',0)),
        baseline_outcome=outcome,requested_end=str(requested_end),observed_end=str(end),
        unavailable_custom_runtime_fields=[k for k in ('closed_cycles','baseline_outcome','observed_end',
            'sequential_closes_submitted') if k not in stats],
        terminal_evidence='Complete native fills, runtime entries, cycle P&L, explicit insolvency timestamp/equity and terminal margin guard; optional missing fields are not fabricated',
        requested_period_complete=outcome=='period_complete',diagnostic_log_coverage=log_coverage,
        account_period=basket_performance_window(daily,initial,start,end),
        trading_period=basket_performance_window(daily,initial,date.fromisoformat(stats['first_entry']),end),
        audits=dict(rust_execution_match=True,full_history_ivr=True,equal_opening_budgets=True,
            no_replacement_entries=True,unchanged_contract_counts=True,monthly_only=True,
            first_eligible_21dte_exits=True,zero_residual_holdings=True,pnl_reconciles=True),
        calendar_metadata_sha256=hashlib.sha256(calendar_path.read_bytes()).hexdigest(),
        data_unit_repair=json.loads((campaign/'baseline_plan.json').read_text()).get('data_unit_repair'),
        limitations=json.loads((campaign/'baseline_plan.json').read_text())['limitations_to_report'])
    frames=dict(cycles=pd.DataFrame(cycles),executions=pd.DataFrame(fills),entries=pd.DataFrame(entries),
        batches=pd.DataFrame(batches),annual=pd.DataFrame(annual),
        daily_equity=pd.DataFrame([dict(date=str(d),equity=v) for d,v in sorted(daily.items())]))
    out=campaign/'baseline_report';out.mkdir(exist_ok=False)
    receipts={}
    with duckdb.connect(str(out/'baseline.duckdb')) as connection:
        for table,frame in frames.items():
            connection.register('frame',frame)
            connection.execute(f'CREATE TABLE {table} AS SELECT * FROM frame')
            connection.unregister('frame')
            path=out/(table+'.parquet')
            connection.execute(f'COPY {table} TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(path)])
            frame.to_csv(out/(table+'.csv'),index=False)
            receipts[table]=dict(rows=len(frame),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    with duckdb.connect(str(out/'baseline.duckdb'),read_only=True) as connection:
        for table,receipt in receipts.items():
            db_rows=connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            parquet_rows=connection.execute('SELECT COUNT(*) FROM read_parquet(?)',
                [str(out/(table+'.parquet'))]).fetchone()[0]
            if db_rows!=receipt['rows'] or parquet_rows!=receipt['rows']:
                raise ValueError('DuckDB and Parquet row counts differ: '+table)
            receipt['readback_verified']=True
    (out/'manifest.json').write_text(json.dumps(dict(summary=summary,tables=receipts),indent=2))
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    marks=frames['daily_equity'].copy()
    marks['date']=pd.to_datetime(marks['date'])
    marks['drawdown_pct']=100*(marks['equity']/marks['equity'].cummax().clip(lower=initial)-1)
    figure,axes=plt.subplots(2,1,figsize=(11,6),sharex=True,gridspec_kw={'height_ratios':[2,1]})
    axes[0].plot(marks['date'],marks['equity'],color='#245c94',linewidth=1.2)
    axes[0].axhline(initial,color='gray',linewidth=.6,linestyle='--')
    axes[0].set_ylabel('Account equity (USD)')
    axes[0].set_title('Engineering verification' if summary['engineering_smoke']
                      else 'Monthly short-strangle baseline — $60,000 starting equity')
    axes[1].fill_between(marks['date'],marks['drawdown_pct'],0,color='#b45f5f',alpha=.7)
    axes[1].set_ylabel('Drawdown (%)')
    for axis in axes:
        axis.grid(alpha=.2)
    figure.tight_layout()
    figure.savefig(out/'equity_drawdown.png',dpi=160)
    plt.close(figure)
    title='Engineering verification; not full baseline performance' if summary['engineering_smoke'] else 'Short-strangle baseline'
    p=summary['trading_period']
    cagr_text=f"{p['cagr']:.2%}" if p['cagr'] is not None else 'undefined (nonpositive terminal equity)'
    table='\n'.join(f"| {r['year']} | {r['entries']} | {r['closed_cycles']} | ${r['equity_pnl']:,.2f} |" for r in annual)
    report=f'''# {title}

![Account equity and daily drawdown](equity_drawdown.png)

QC backtest [{summary['backtest_id']}]({summary['url']}), run through the shared Rust server.
Requested account history {start} to {requested_end}; observed through {end}; first entry {summary['first_entry']}.
Outcome: {outcome}. No observations or performance are fabricated after insolvency.
Initial equity ${initial:,.2f}; final equity ${initial+net:,.2f}; net P&L ${net:,.2f}.
Trading-window return {p['return_fraction']:.2%}, CAGR {cagr_text}, maximum daily
equity drawdown {p['max_daily_drawdown']:.2%}, including the terminal liquidation mark. These differ from full-period
statistics that include the IV-history warmup. Intraday drawdown can be larger.

{len(cycles)} closed strangles in {len(batches)} non-overlapping batches;
{summary['equity_cycles']} equity/ETF cycles, {summary['future_cycles']} futures-option cycles.
{len(orders)} orders, {len(fills)} fills, {summary['rolls']} rolls; fees ${summary['fees']:,.2f}.
Peak holdings {peak}/13. Exit reasons: {json.dumps(summary['exit_reasons'])}.

True min/max range IVR >70 with {config['lookback']} completed observations.
Only standard monthly expiries; entry first monthly >=35 DTE, targeting around45;
mandatory exit on the first product-open noon at <=21 calendar DTE.
No new batch until all prior positions and pending orders close. Each batch uses
equal account-equity/x collateral budgets at opening, sized using conservative
LEAN initial leg margins plus fees. Whole-contract rounding leaves cash unused.
Existing lots are unchanged. Contract multipliers and actual fills/fees drive P&L.
The frozen plan records the bounded QC LO/CL premium-unit repair for December21–24,2015;
minute data is normalized before fills/margin and daily chain premiums before IV modeling.
QC margin calls close the full affected strangle and appear as MARGIN exits.
Wholly rejected rolls ({summary['rejected_rolls']}) leave the original holding
and roll count unchanged; raw rejected orders remain in the downloaded evidence.

Rust and Python downloads match. The audit verifies batch separation, equal entry
budgets, fixed quantities, IVR history/rank, expiry metadata, first eligible DTE
exits, account reconciliation and no residual holdings. Exchange-calendar
metadata is saved with its source and hash; futures monthly dates are enforced
in QC with product expiry functions, rather than its always-true standard flag.

| Year | Entries | Closed cycles | Account equity P&L |
|---|---:|---:|---:|
{table}

These findings apply to this frozen configuration. Source coverage is QC's
historical equity universe plus its fifteen supported futures-option roots,
not every US futures market. Earnings vetoes use only events known through the
limited feed horizon. Futures IV/delta uses a Black76 approximation. Ranking raw
shares against futures contracts follows the requested rule but compares units.
Invalid prices, unavailable history, spread/quote, margin and monthly-expiry
failures remain exclusions. Independent local quote data remains a separate need.

The CSV, DuckDB and checksum-verified Parquet files contain strategy results and
genuine execution records; raw licensed market-history exports are not included.
'''
    (out/'REPORT.md').write_text(report)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
