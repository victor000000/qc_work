#!/usr/bin/env python3
"""Download completed cloud evidence and export account-level comparison metrics."""
import argparse
import csv
from datetime import datetime
import json
import math
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from qc_api_check import credentials, request
from audit import reconstruct


def chart_window(backtest):
    start=datetime.fromisoformat(backtest['backtestStart'])
    end=datetime.fromisoformat(backtest['backtestEnd'])
    if start.tzinfo is None:
        start=start.replace(tzinfo=ZoneInfo('America/New_York'))
    if end.tzinfo is None:
        end=end.replace(tzinfo=ZoneInfo('America/New_York'))
    first,last=int(start.timestamp()),int(end.timestamp())+1
    if last<=first:
        raise ValueError('Invalid backtest chart window')
    # QC resamples over the requested interval. A Unix-epoch start diluted
    # 5000 points across 56 years, losing most actual daily observations.
    return dict(start=first,end=last,count=max(5000,math.ceil((last-first)/43200)))


def read_chart(user,token,parameters):
    for _ in range(15):
        response=request(user,token,'/backtests/chart/read',parameters)
        if isinstance(response.get('chart'),dict):
            return response
        if response.get('status')!='loading':
            raise RuntimeError('Chart response contains no chart')
        time.sleep(2)
    raise TimeoutError('Chart generation did not finish; retry collection')


def read_order_page(user,token,parameters):
    for _ in range(15):
        response=request(user,token,'/backtests/orders/read',parameters)
        if isinstance(response.get('orders'),(list,dict)):
            return response['orders']
        if response.get('status')!='loading':
            raise RuntimeError('Order response contains no orders field')
        time.sleep(2)
    raise TimeoutError('Order generation did not finish; retry collection')


def read_all_orders(user, token, ids, expected):
    """Read every declared order, including campaigns larger than 10,000 orders."""
    orders, seen = [], set()
    if expected is not None and expected < 0:
        raise ValueError('Negative expected order count')
    while expected is None or len(orders) < expected:
        if len(orders) > 100_000:
            raise RuntimeError('Order pagination exceeded algorithm order limit')
        page = read_order_page(user, token, dict(ids, start=len(orders), end=len(orders)+99))
        page = list(page.values()) if isinstance(page, dict) else page
        if not page:
            if expected is None:
                break
            raise RuntimeError(f'Order history ended early: {len(orders)} of {expected}')
        for order in page:
            if order['id'] in seen:
                raise RuntimeError('Duplicate order across downloaded pages')
            seen.add(order['id'])
        orders.extend(page)
        if expected is not None and len(orders) > expected:
            raise RuntimeError('Order response exceeds declared order count')
        if expected is None and len(page) < 99:
            break
    return orders


def validate_cached_backtest(full, ids):
    """Never combine cached evidence with the identity of a retried cloud run."""
    backtest = full.get('backtest', {})
    if str(backtest.get('backtestId')) != str(ids['backtestId']) or str(backtest.get('projectId')) != str(ids['projectId']):
        raise ValueError('Cached backtest identity differs from requested run; preserve the evidence and use a fresh folder')


def entry_features(orders):
    entries, seen_groups = [], set()
    for order in orders:
        parts = order.get('tag', '').split(';')
        head = parts[0]
        if not head.endswith(':OPEN') or len(parts) == 1:
            continue
        group = (order.get('groupOrderManager') or {}).get('id')
        if group is None:
            raise ValueError('Opening order lacks a cycle group identity')
        if group in seen_groups:
            continue
        seen_groups.add(group)
        features = dict(part.split('=', 1) for part in parts[1:] if '=' in part)
        entries.append(dict(ticker=head.split(':')[0], entry=order['time'], **features))
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--reuse-downloads', action='store_true')
    args = parser.parse_args()
    folder = args.folder.resolve()
    outcomes = json.loads((folder / 'outcomes.json').read_text())
    manifest = json.loads((folder/'manifest.json').read_text())
    user, token = credentials(ROOT/'data/S001.duckdb')
    summary = []
    for name, record in outcomes.items():
        if record['status'] not in ('done','failed') or not record.get('backtest_id'):
            continue
        ids = dict(projectId=record['project_id'], backtestId=record['backtest_id'])
        evidence = folder / name
        evidence.mkdir(exist_ok=True)
        cached_backtest = evidence/'backtest.json'
        full = (json.loads(cached_backtest.read_text()) if args.reuse_downloads and cached_backtest.exists()
                else request(user, token, '/backtests/read', ids))
        validate_cached_backtest(full, ids)
        if args.reuse_downloads and not cached_backtest.exists() and any(evidence.iterdir()):
            raise ValueError('Cannot verify cached evidence without its backtest.json; use a fresh folder')
        (evidence/'backtest.json').write_text(json.dumps(full, indent=2))
        window=chart_window(full['backtest'])
        requests_path=evidence/'chart_requests.json'
        chart_requests=json.loads(requests_path.read_text()) if requests_path.exists() else {}
        charts=(sorted(set(['Trading period', 'Strategy Equity', 'Benchmark'])
                       | set(full['backtest'].get('charts',{}))) if record['status']=='done' else [])
        for chart in charts:
            chart_path=evidence/(chart.lower().replace(' ', '_')+'.json')
            if args.reuse_downloads and chart_path.exists():
                continue
            parameters=dict(ids,name=chart,**window)
            response = read_chart(user, token, parameters)
            chart_path.write_text(json.dumps(response, indent=2))
            chart_requests[chart]=parameters
            requests_path.write_text(json.dumps(chart_requests,indent=2))
        orders = []
        cached_orders=evidence/'orders.json'
        if args.reuse_downloads and cached_orders.exists():
            orders=json.loads(cached_orders.read_text())
        if not (args.reuse_downloads and cached_orders.exists()):
            count=full['backtest'].get('statistics',{}).get('Total Orders')
            orders = read_all_orders(user, token, ids, int(str(count).replace(',','')) if count is not None else None)
        (evidence/'orders.json').write_text(json.dumps(orders, indent=2))
        closed_trades=full['backtest'].get('totalPerformance',{}).get('closedTrades',[])
        (evidence/'qc_closed_trades.json').write_text(json.dumps(closed_trades,indent=2))
        entries = entry_features(orders)
        with (evidence/'entry_features.csv').open('w', newline='') as f:
            fields = list(dict.fromkeys(key for entry in entries for key in entry)) if entries else ['ticker','entry','ivr','iv','rv','trend_z','spot','put_delta','call_delta']
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(entries)
        log_path=evidence/'cloud.log'
        logs = log_path.read_text().splitlines() if args.reuse_downloads and log_path.exists() else []
        for start in ([] if args.reuse_downloads and log_path.exists() else range(0, 1_000_000, 200)):
            response = request(user, token, '/backtests/read/log', dict(ids, start=start, end=start+200, query=''))
            page = response.get('log', response.get('logs', []))
            logs.extend(page)
            if len(page) < 200:
                break
        else:
            if not (args.reuse_downloads and log_path.exists()):
                raise RuntimeError('Log pagination exceeded safety limit; preserve partial evidence')
        (evidence/'cloud.log').write_text('\n'.join(logs))
        b = full['backtest']
        if record['status']=='failed':
            failed_audit=dict(cloud_failed=True,error=b.get('error') or record.get('error_message'),
                order_count=len(orders),policy='Failed run evidence retained; not a valid strategy result')
            try:
                recovered=reconstruct(orders)
                failed_audit['reconstructed_closed_cycles']=len(recovered)
                failed_audit['reconstructed_pnl']=sum(c['pnl'] for c in recovered)
            except (ValueError,KeyError) as exc:
                failed_audit['reconstruction_status']=type(exc).__name__
            (evidence/'audit.json').write_text(json.dumps(failed_audit,indent=2))
            print(name+': retained failed-run orders and cloud evidence',flush=True)
            continue
        if b.get('error') or b.get('status', '').rstrip('.') != 'Completed':
            raise RuntimeError(f'{name} is not a clean completed backtest')
        r = b['runtimeStatistics']
        label = next(label for label in manifest['variants'] if name.endswith('_'+label))
        allow_zero = manifest['variants'][label].get('allow_no_trades', False)
        config = manifest['variants'][label]
        basket = manifest['phase'] in ('basket','basket-smoke')
        if entries or allow_zero:
            if len(entries) != int(r.get('entries',0)):
                raise RuntimeError('Missing entry feature annotations')
            for entry in entries:
                minimum = 70 if basket else config.get('iv_min', 50)
                if minimum is not None and ('ivr' not in entry or float(entry['ivr']) < minimum - 0.000001):
                    raise RuntimeError('Entry violates IV rank threshold')
                if basket:
                    if float(entry['ivr']) <= 70 or int(entry['samples']) != config['lookback']:
                        raise RuntimeError('Basket entry violates strict IVR or full-history requirement')
                    rank=100*(float(entry['iv'])-float(entry['iv_low']))/(float(entry['iv_high'])-float(entry['iv_low']))
                    if abs(rank-float(entry['ivr']))>1e-7:
                        raise RuntimeError('Entry IVR is not the recorded min/max range rank')
                if any(not .159999 <= abs(float(entry[k])) <= (.220001 if basket else .200001) for k in ['put_delta','call_delta']):
                    raise RuntimeError('Entry violates delta band')
                if config.get('min_iv_rv') is not None and float(entry['iv'])/float(entry['rv']) < config['min_iv_rv']-0.0001:
                    raise RuntimeError('Entry violates IV/RV threshold')
                if config.get('max_trend_z') is not None and abs(float(entry['trend_z'])) > config['max_trend_z']+0.000001:
                    raise RuntimeError('Entry violates trend threshold')
        required_iv_observations = 100 if manifest['phase'] == 'single' else 300
        if allow_zero and not basket and (int(r.get('active_snapshots', 0)) < 100 or int(r.get('active_iv_observations', 0)) < required_iv_observations):
            raise RuntimeError('Insufficient validation-period quote coverage; zero trades may reflect missing data')
        expected_orders = int(str(b['statistics']['Total Orders']).replace(',',''))
        if len(orders) != expected_orders:
            raise RuntimeError(f'Order coverage mismatch: {len(orders)} versus {expected_orders}')
        audit = dict(complete_order_history=True, order_count=len(orders))
        if int(r.get('assignments', 0)) == 0:
            cycles = reconstruct(orders)
            audit.update(cycles=len(cycles), rolls=sum(c['rolls'] for c in cycles),
                         pnl=sum(c['pnl'] for c in cycles), fees=sum(c['fees'] for c in cycles))
            declared_closed=r.get('closed_cycles')
            if declared_closed is None:
                # QC may omit custom runtime fields. Complete native entry
                # annotations + every closed cycle + zero real holdings provide
                # a separate count check; never invent the missing cloud field.
                if (not basket or len(entries)!=int(r['entries']) or len(cycles)!=len(entries)
                        or float(r['Holdings'].replace('$','').replace(',',''))!=0
                        or float(r['Unrealized'].replace('$','').replace(',',''))!=0):
                    raise RuntimeError('Missing closed-cycle statistic without independent complete evidence')
                audit['closed_count_evidence']='All native annotated entries closed; runtime entries and zero holdings agree; QC closed_cycles field unavailable'
            if ((declared_closed is not None and len(cycles)!=int(declared_closed))
                    or abs(audit['pnl']-float(r['cycle_net_pnl'])) > 0.05):
                raise RuntimeError('Order-event reconstruction does not match runtime cycle accounting')
            if audit['rolls'] != int(r.get('rolls', 0)):
                raise RuntimeError('Roll count differs between fills and runtime statistics')
            if abs(audit['fees'] - abs(float(r['Fees'].replace('$', '').replace(',', '')))) > 0.05:
                raise RuntimeError('Fill fees differ from portfolio fees')
            with (evidence/'cycles.csv').open('w', newline='') as f:
                fields = list(cycles[0]) if cycles else ['ticker','entry','initial_credit','cash','fees','rolls','exit','reason','pnl']
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(cycles)
        else:
            audit['cycle_audit_skipped'] = 'Assignments require stock and exercise accounting'
        (evidence/'audit.json').write_text(json.dumps(audit, indent=2))
        row = dict(name=name, project_id=record['project_id'], backtest_id=record['backtest_id'],
            url=f'https://www.quantconnect.com/project/{record["project_id"]}/{record["backtest_id"]}',
            downloaded_orders=len(orders), cloud_log_lines=len(logs))
        row['ticker'] = 'point-in-time US basket' if basket else ','.join(config.get('tickers', ['SPY','GLD','TLT']))
        row['initial_cash'] = config.get('initial_cash',250000)
        row['entry_feature_rows'] = len(entries)
        for key in ['active_return', 'active_cagr', 'active_daily_mdd', 'active_sharpe_zero_rf',
                    'cycle_net_pnl', 'cycle_win_rate', 'entries', 'closed_cycles', 'open_cycles',
                    'rolls', 'PROFIT', 'TIME', 'STOP', 'END', 'assignments', 'assignment_exits',
                    'entries_SPY', 'entries_GLD', 'entries_TLT', 'first_entry', 'iv_observations',
                    'min_iv_samples', 'ivr_rejected', 'no_delta_contract', 'correlation_rejected',
                    'size_rejected', 'margin_rejected', 'stale_management', 'roll_no_candidate',
                    'roll_missing_contract', 'pnl_reconciliation_difference', 'premium_rejected',
                    'trend_rejected', 'stop_multiple', 'min_iv_rv', 'max_trend_z',
                    'active_snapshots', 'active_iv_observations', 'split_events', 'SPLIT',
                    'mandatory_exit_stale_quotes', 'time_exit_min_dte', 'time_exit_max_dte',
                    'split_entry_rejected', 'Fees']:
            row[key] = r.get(key, None if basket else '0' if key not in ['first_entry', 'Fees'] else '')
        if row['open_cycles'] is None:
            if not basket or len(cycles)!=len(entries) or float(r['Holdings'].replace('$','').replace(',',''))!=0:
                raise RuntimeError('Missing open-cycle statistic without complete flat cycle evidence')
            row['open_cycles_evidence']='Native cycle reconstruction and terminal account holdings; custom cloud open_cycles unavailable'
        if ((row['open_cycles'] is not None and int(row['open_cycles'])!=0)
                or (int(row['entries']) < 1 and not allow_zero)):
            raise RuntimeError('Invalid experiment coverage or residual cycles')
        summary.append(row)
        print(f'{name}: {len(orders)} orders; return={row["active_return"]}; '
              f'cycles={row["closed_cycles"]}; rolls={row["rolls"]}; logs={len(logs)}', flush=True)
    (folder/'summary.json').write_text(json.dumps(summary, indent=2))
    if summary:
        with (folder/'summary.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(summary[0]))
            writer.writeheader()
            writer.writerows(summary)


if __name__ == '__main__':
    main()
