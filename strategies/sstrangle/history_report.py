#!/usr/bin/env python3
"""Report a historical SPY baseline with explicit option-data coverage and DTE audits."""
import argparse
import csv
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd

from audit_21dte import audit_dte
from local.prepare import executions, write_csv


NY=ZoneInfo('America/New_York')
DATA_DOC='https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/algoseek/us-equity-options'


def coverage_count(stats, key):
    # QC can omit custom counters from its result payload. Absence is unknown,
    # never evidence of zero available option observations.
    return int(stats[key]) if key in stats else None


def decision_records(log):
    records, seen = [], set()
    for line in log.splitlines():
        if ' ENTRY_DECISIONS ' not in line:
            continue
        row = json.loads(line.split(' ENTRY_DECISIONS ', 1)[1])
        key = (row['ticker'], row['year'])
        if key in seen:
            raise ValueError('Duplicate annual entry decisions')
        seen.add(key)
        records.append(row)
    return records


def effective_start(config, stats):
    start = date(*config['trade_start'])
    if config.get('iv_min', 50) is None:
        return start
    return max(start, date.fromisoformat(stats['first_ivr_ready_SPY']))


def performance_window(daily, initial, begin, end):
    days=sorted(daily)
    before=[daily[day] for day in days if day<begin]
    opening=before[-1] if before else initial
    values=[daily[day] for day in days if begin<=day<=end]
    if not values or end<=begin or opening<=0 or values[-1]<=0:
        raise ValueError('Performance window requires observations, positive equity and a positive duration')
    peak=opening
    drawdown=0
    for value in values:
        peak=max(peak,value)
        drawdown=max(drawdown,1-value/peak)
    years=(end-begin).days/365.25
    return dict(start=str(begin),end=str(end),observations=len(values),opening_equity=opening,
        net_pnl=values[-1]-opening,return_fraction=values[-1]/opening-1,
        cagr=(values[-1]/opening)**(1/years)-1,max_daily_drawdown=drawdown)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign',type=Path)
    args=parser.parse_args()
    campaign=args.campaign.resolve()
    manifest=json.loads((campaign/'manifest.json').read_text())
    outcomes=json.loads((campaign/'outcomes.json').read_text())
    if len(outcomes)!=1 or next(iter(outcomes.values()))['status']!='done':
        raise ValueError('Report requires one completed single-ticker baseline')
    name,record=next(iter(outcomes.items()))
    folder=campaign/name
    full=json.loads((folder/'backtest.json').read_text())['backtest']
    stats=full['runtimeStatistics']
    if int(stats.get('assignments',0)):
        raise ValueError('Assignment occurred; stock/exercise accounting is required before cycle analysis')
    orders=json.loads((folder/'orders.json').read_text())
    rust_orders=json.loads((folder/'orders.rust.json').read_text())
    assert [row['id'] for row in orders]==[row['id'] for row in rust_orders]
    assert len(orders)==int(full['statistics']['Total Orders'])
    cycles=audit_dte(orders)
    fills=executions(orders)
    if fills!=executions(rust_orders):
        raise ValueError('Python and Rust downloads disagree on execution details')
    write_csv(folder/'fills.csv',fills)
    write_csv(folder/'dte_audit.csv',cycles)
    config=manifest['variants']['SPY']
    decisions=decision_records((folder/'cloud.log').read_text())
    decision_rows=[dict(ticker=row['ticker'],year=row['year'],reason=reason,checks=count)
                   for row in decisions for reason,count in row['counts'].items()]
    if decisions:
        if sum(row['checks'] for row in decision_rows)!=int(stats['active_snapshots']):
            raise ValueError('Annual entry-decision coverage does not reconcile')
        if sum(row['checks'] for row in decision_rows if row['reason']=='entry_submitted')!=int(stats['entries']):
            raise ValueError('Entry decisions do not reconcile to filled entries')
        for row in decisions:
            for key,count in row.get('coverage',{}).items():
                stats[f"{key}_{row['ticker']}_{row['year']}"]=str(count)
        write_csv(campaign/'entry_decisions.csv',decision_rows)
    start=date(*config['trade_start'])
    end=date(*config['end'])
    initial=float(config['initial_cash'])
    points=json.loads((folder/'trading_period.json').read_text())['chart']['series']['Equity']['values']
    daily={}
    for point in points:
        stamp,value=(point['x'],point['y']) if isinstance(point,dict) else point[:2]
        day=datetime.fromtimestamp(stamp,NY).date()
        daily[day]=float(value)
    if len(daily)!=int(stats['active_snapshots']):
        raise ValueError('Downloaded daily equity chart is incomplete; do not report drawdowns from a truncated chart')
    days=sorted(daily)
    assert abs(daily[days[-1]]-initial-sum(cycle['pnl'] for cycle in cycles))<.05
    for cycle in cycles:
        if cycle['reason']=='TIME':
            threshold=date.fromisoformat(cycle['calendar_21dte_date'])
            eligible=next(day for day in days if day>=threshold)
            actual=datetime.fromisoformat(cycle['exit'].replace('Z','+00:00')).astimezone(NY).date()
            cycle['time_exit_on_first_eligible_session']=actual==eligible
            if actual!=eligible:
                raise ValueError('TIME exit missed its first eligible trading session')
        else:
            cycle['time_exit_on_first_eligible_session']=None
    write_csv(folder/'dte_audit.csv',cycles)

    coverage=[]
    previous=initial
    for year in range(start.year,end.year+1):
        observations=[daily[day] for day in days if day.year==year]
        ending=observations[-1] if observations else previous
        closed=[cycle for cycle in cycles if int(cycle['exit'][:4])==year]
        coverage.append(dict(year=year,chain_days=coverage_count(stats,f'chain_days_SPY_{year}'),
            fresh_chain_days=coverage_count(stats,f'fresh_chain_days_SPY_{year}'),
            stale_chain_days=coverage_count(stats,f'no_fresh_chain_days_SPY_{year}'),
            valid_iv_days=coverage_count(stats,f'valid_iv_days_SPY_{year}'),
            ivr_ready_days=coverage_count(stats,f'ivr_ready_days_SPY_{year}'),
            entries=sum(int(cycle['entry'][:4])==year for cycle in cycles),closed_cycles=len(closed),
            realized_cycle_pnl=sum(cycle['pnl'] for cycle in closed),
            equity_pnl=ending-previous,year_end_equity=ending))
        previous=ending
    write_csv(campaign/'yearly_coverage.csv',coverage)
    ready=effective_start(config,stats)

    summary=dict(requested_start=str(start),history_start=str(date(*config['start'])),
        first_chain=stats['first_chain_SPY'],first_valid_iv=stats['first_valid_iv_SPY'],
        first_ivr_ready=stats['first_ivr_ready_SPY'],first_entry=stats['first_entry'],
        iv_min=config.get('iv_min',50),entry_decision_checks=sum(row['checks'] for row in decision_rows),
        orders=len(orders),closed_leg_trades=len(full['totalPerformance']['closedTrades']),
        cycles=len(cycles),wins=sum(cycle['pnl']>0 for cycle in cycles),
        fees=sum(cycle['fees'] for cycle in cycles),rolls=sum(cycle['rolls'] for cycle in cycles),
        pending_combo_submitted=int(stats.get('pending_combo_submitted',0)),
        pending_combo_completed=int(stats.get('pending_combo_completed',0)),
        pending_combo_max_delay_seconds=int(stats.get('pending_combo_max_delay_seconds',0)),
        no_fresh_chain_days=int(stats.get('no_fresh_chain',0)),
        ivr_rejections=int(stats.get('ivr_rejected',0)),
        no_delta_contract_rejections=int(stats.get('no_delta_contract',0)),
        stale_management_days=int(stats.get('stale_management',0)),
        mandatory_exit_stale_quotes=int(stats.get('mandatory_exit_stale_quotes',0)),
        annual_coverage_counters_complete=all(row['chain_days'] is not None and
            row['valid_iv_days'] is not None and row['ivr_ready_days'] is not None for row in coverage),
        net_pnl=sum(cycle['pnl'] for cycle in cycles),
        effective_period=performance_window(daily,initial,ready,end),
        post_2012_account_window=performance_window(daily,initial,max(ready,date(2013,1,2)),end),
        time_exits=sum(cycle['reason']=='TIME' for cycle in cycles),
        time_exits_below_21dte=[cycle for cycle in cycles if cycle['reason']=='TIME' and cycle['exit_dte']<21],
        time_exit_first_eligible_session_audit=True,project_id=record['project_id'],backtest_id=record['backtest_id'])
    (campaign/'historical_summary.json').write_text(json.dumps(summary,indent=2))
    frames=dict(cycles=pd.DataFrame(cycles),fills=pd.DataFrame(fills),yearly_coverage=pd.DataFrame(coverage),
                daily_equity=pd.DataFrame([dict(date=str(day),equity=daily[day]) for day in days]))
    if decision_rows:
        frames['entry_decisions']=pd.DataFrame(decision_rows)
    warehouse=campaign/'historical_warehouse'
    warehouse.mkdir(exist_ok=False)
    connection=duckdb.connect(str(warehouse/'history.duckdb'))
    receipts={}
    for table,frame in frames.items():
        connection.register('source_frame',frame)
        connection.execute(f'CREATE TABLE {table} AS SELECT * FROM source_frame')
        path=warehouse/(table+'.parquet')
        connection.execute(f"COPY {table} TO '{path}' (FORMAT PARQUET)")
        receipts[table]=dict(rows=len(frame),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        connection.unregister('source_frame')
    connection.close()
    (warehouse/'manifest.json').write_text(json.dumps(receipts,indent=2))
    effective=summary['effective_period']
    later=summary['post_2012_account_window']
    table='\n'.join(f"| {row['year']} | {row['entries']} | {row['closed_cycles']} | {row['equity_pnl']:,.2f} |" for row in coverage)
    coverage_note=('Annual option availability counters are present in the saved coverage CSV.'
        if summary['annual_coverage_counters_complete'] else
        'QC omitted some annual option availability counters from its response. Blank coverage fields mean unknown, not zero. First-observation dates and trade/account totals are available.')
    gate_note=('no IV-rank entry restriction or IV-history prerequisite' if config.get('iv_min',50) is None
               else f"an IVR >= {config.get('iv_min',50)} entry restriction and 252 prior valid daily IV observations")
    report=f'''# SPY short strangle: extended history

The earlier 2024 start was an experiment configuration choice. This run requests
entries from {start} through {end}, with history loaded from {date(*config['start'])}.
This run has {gate_note}.

[QC run](https://www.quantconnect.com/project/{record['project_id']}/{record['backtest_id']})
executed through the shared Rust server. The exact entry/exit/roll/sizing configuration
is saved in `manifest.json` and `SPY.py`. The algorithm records data coverage,
rejects stale option quotes before IV calculation, entry and rolling, and allows
submitted combo orders to finish on subsequent minute slices. Rejected
orders or combos unresolved after five minutes fail the run; fills are never assumed.

## Data availability

QC documents its main equity-option coverage from January 2012 and notes partial
earlier coverage: [official dataset documentation]({DATA_DOC}).
The first observed SPY option chain was {summary['first_chain']}, the first valid
ATM IV was {summary['first_valid_iv']}, and the first usable 252-observation IV rank
was {summary['first_ivr_ready']}. The first actual entry was {summary['first_entry']}.
Empty option history does not constitute a successful no-trade strategy period.
The run observed {summary['no_fresh_chain_days']} chain days without fresh valid
quotes, including initialization history; these could not seed IV or open trades.

## Results

{summary['cycles']} closed strangles; {summary['orders']} orders;
{summary['closed_leg_trades']} closed leg trades; {summary['wins']} winning cycles.
Net P&L: ${summary['net_pnl']:,.2f}, including ${summary['fees']:,.2f} in fees.
Rolls: {summary['rolls']}.
Delayed combos: {summary['pending_combo_completed']} confirmed out of
{summary['pending_combo_submitted']} submitted; maximum processing delay
{summary['pending_combo_max_delay_seconds']} seconds.

From the policy-eligible start date {ready}, return was {effective['return_fraction']:.2%},
CAGR {effective['cagr']:.2%}, and maximum daily equity drawdown
{effective['max_daily_drawdown']:.2%}. The IV-history prerequisite applies only when
the IV-rank gate is enabled. A separate 2013-onward account-window calculation is saved in
`historical_summary.json` to avoid treating partial pre-2012 coverage as complete.
From {later['start']} through {end}, account-window P&L was
${later['net_pnl']:,.2f} ({later['return_fraction']:.2%}), with
CAGR {later['cagr']:.2%} and daily maximum drawdown {later['max_daily_drawdown']:.2%}.
This is an account-performance window within the continuous backtest; it carries
existing positions and indicator history across the boundary, rather than restarting
the strategy or constituting an independent out-of-sample test.

All {summary['time_exits']} time exits occurred at the first scheduled trading
session with calendar DTE <=21. {len(summary['time_exits_below_21dte'])} had fewer
than 21 calendar DTE because the threshold date was not a trading session.
The complete expiry-based audit is in the per-run `dte_audit.csv`.

| Year | Entries | Closed cycles | Equity P&L ($) |
|---|---:|---:|---:|
{table}

Yearly equity P&L includes marked open positions. It can differ from whole-cycle
P&L booked at exit; both are saved in `yearly_coverage.csv`.
{coverage_note}
This remains a fixed one-contract baseline, with {gate_note}, standard monthly
options, 50% profit target, additional two-credit stop, 21 DTE exit and documented
roll/sizing assumptions. No optimization was applied to this longer history.
The IV-rank gate rejected {summary['ivr_rejections']} entry checks. Another
{summary['no_delta_contract_rejections']} checks found no eligible liquid
16–20 delta contract within the configured universe of 40 listed strikes on each
side. This limited universe can exclude farther-out contracts in high volatility.
Profit/loss management was skipped on {summary['stale_management_days']} days with
stale held-contract quotes; mandatory calendar exits remain separate, with
{summary['mandatory_exit_stale_quotes']} such submissions encountering stale marks.

## Evidence

- Per-run folder `{name}`: raw QC result, orders, Rust-downloaded orders, leg trades,
  fill CSV, cycle CSV, DTE audit, charts and reconciliation audit.
- `historical_summary.json` and `yearly_coverage.csv`: results and coverage.
- `historical_warehouse/`: DuckDB plus checksummed Parquet tables for local research.

## Execution defects found by extending the dates

The first long attempt stopped on October 10, 2018. A focused diagnostic confirmed
both selected contracts still carried data timestamped October 9 at 16:00. The old
entry code accepted these cached quotes and immediately required a filled combo.
The corrected code rejects stale quote bars before building IV history or selecting
entry/roll contracts. It also monitors genuinely pending orders before recording
their cashflows. The earlier execution regression is saved in `strangle_single_20261018_072618`;
failed attempts are not included in these results.

The downloader now requests unfiltered logs and samples equity charts over the
actual backtest dates. The old Unix-epoch chart start could omit daily observations.

Calendar exits are audited from OCC contract expiries, not days held. Actual
execution histories reconcile to final portfolio equity. Maximum drawdown uses
daily snapshots, so it does not measure intraday loss extremes.
'''
    (campaign/'HISTORICAL_RESULTS.md').write_text(report.replace('$-','-$'))
    print(json.dumps(summary,indent=2))
    print('Report:',campaign/'HISTORICAL_RESULTS.md')


if __name__=='__main__':
    main()
