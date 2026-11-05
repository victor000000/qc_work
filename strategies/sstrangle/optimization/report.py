"""Read-only QC research collection, strict execution audit and frozen train/evaluation report.

Never submits, cancels, restarts a server, changes the queue or exports raw quotes.
"""
import argparse
import ast
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
import fcntl
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
STRATEGY = HERE.parent
ROOT = STRATEGY.parents[1]
PROGRESS_FILE = HERE / 'CURRENT_RESEARCH_PROGRESS.json'
sys.path[:0] = [str(HERE), str(STRATEGY), str(ROOT / 'scripts')]
import duckdb
import pandas as pd
from account_drawdown import chart_drawdown, include_chart_drawdown
from equity_rv_annotations import audit_equity_rv_annotation
from holding_age import validate_max_holding_days
from holding_source_chain import verify_chain
import qc_storage as storage
from qc_api_check import credentials, request
from resume_basket import read_existing_backtest, validate_identity, terminal_status, atomic_json
from collect import read_all_orders, chart_window, read_chart, validate_cached_backtest
from qc_contracts import execution_rows, execution_signature, option_identity
from audit import order_group_id, rejected_roll, validate_sequential_close, order_multiplier
from audit_21dte import audit_dte
from basket_report import metadata, ny_time, noon_open, ROOT_MARKETS, audit_available_logs, events
from basket.basket_rules import standard_equity_monthly


def money(value):
    return float(str(value).replace('$', '').replace(',', '').strip())


def record_monitor(campaign, snapshot, identities):
    """Keep continuation state current and retain every read-only observation."""
    atomic_json(campaign/'cloud_progress.json', snapshot)
    with (campaign/'cloud_progress_history.jsonl').open('a') as history:
        history.write(json.dumps(snapshot, allow_nan=False)+'\n')
    if not PROGRESS_FILE.exists():
        return
    state = json.loads(PROGRESS_FILE.read_text())
    if state.get('campaign') != str(campaign):
        return
    state.update(updated_utc=snapshot['utc'], latest_cloud_snapshot=snapshot,
        jobs=identities, goal_achieved=False,
        status='; '.join(row['name']+': '+str(row.get('status'))+
            (' '+format(row['progress'], '.0%') if row.get('progress') is not None else '')
            for row in snapshot['jobs']))
    if snapshot.get('cloud_failures'):
        state['status'] += '; cloud failure confirmed; failed attempts are unqualified'
    if snapshot.get('collection_issues'):
        state['status'] += '; separate read-only evidence collection retry required'
        if not snapshot.get('cloud_failures'):
            state['status'] += '; request error alone is not proof of cloud failure'
    state['target_claim_scope']='Current immutable queued campaign only; qualification requires complete native account, drawdown, execution and evaluation audits'

    atomic_json(PROGRESS_FILE, state)


def config_for(name, manifest):
    matches = [(key, value) for key, value in manifest['variants'].items() if name.endswith('_' + key)]
    if len(matches) != 1:
        raise ValueError('Job does not identify exactly one frozen variant: ' + name)
    return matches[0]


def audit_budget_annotations(orders, config):
    """Audit actual complete fills against capped opening collateral annotations."""
    groups = defaultdict(list)
    for order in sorted(orders, key=lambda row: row['id']):
        groups[order_group_id(order)].append(order)
    active, batches, entries = {}, {}, []
    peak = 0
    last_exit_day = None
    for group in groups.values():
        validate_sequential_close(group)
        if len(group) != 2:
            raise ValueError('Each strategy action requires two native legs')
        head = group[0]['tag'].split(';', 1)[0]
        if any(row['tag'].split(';', 1)[0] != head for row in group):
            raise ValueError('Action identity mismatch')
        key, reason = head.split(':', 1)
        if rejected_roll(group):
            if key not in active:
                raise ValueError('Rejected roll has no position')
            continue
        quantities = [sum(float(e.get('fillQuantity', 0)) for e in row['events']) for row in group]
        quantity = abs(quantities[0])
        if not quantity or quantity != abs(quantities[1]):
            raise ValueError('Missing or unequal actual leg fills')
        if any(row.get('status') != 3 or abs(float(row['quantity'])) != quantity for row in group):
            raise ValueError('Incomplete, partial or rejected strategy action')
        if reason == 'OPEN':
            m = metadata(group[0])
            if any(metadata(row) != m for row in group):
                raise ValueError('Opening legs have inconsistent annotations')
            count = int(m['basket_count']); batch = int(m['batch_id'])
            if not 1 <= count <= 13 or key in active:
                raise ValueError('Invalid basket count or overlapping symbol')
            if any(position['batch_id'] != batch for position in active.values()):
                raise ValueError('New batch before fully flat')
            entered = ny_time(group[0]['time'])
            if entered.time() < time(12) or (last_exit_day is not None and entered.date() <= last_exit_day):
                raise ValueError('Entry before noon or on/before most recent exit date')
            equity = float(m['allocation_equity'])
            total = float(config['total_collateral_fraction'])
            per_symbol = float(config['per_symbol_collateral_fraction'])
            budget = min(equity * total / count, equity * per_symbol)
            if equity <= 0 or abs(float(m['allocation_budget']) - budget) > .001:
                raise ValueError('Research collateral budget does not match min(total/x,per-symbol)')
            if m['allocation_mode'] != 'research_capped_collateral_budget':
                raise ValueError('Unexpected allocation model')
            for field in ('total_collateral_fraction', 'per_symbol_collateral_fraction'):
                if field not in m or abs(float(m[field]) - float(config[field])) > 1e-10:
                    raise ValueError('Missing or inconsistent frozen research annotation: ' + field)
            reserve = float(m['estimated_initial_margin']) + float(m['estimated_entry_fees'])
            if not math.isfinite(reserve) or reserve <= 0 or reserve > budget + .001:
                raise ValueError('Entry margin and fees exceed opening collateral cap')
            if any(q >= 0 for q in quantities) or quantity != int(m['quantity']):
                raise ValueError('Actual short quantities disagree with declared integer lots')
            identities = [option_identity(row['symbol']) for row in group]
            if {identity['call_put'] for identity in identities} != {'P', 'C'} or len({identity['expiry'] for identity in identities}) != 1:
                raise ValueError('Opening legs lack same put/call expiry')
            if any(not .16 <= abs(float(m[field])) <= .22 for field in ('put_delta', 'call_delta')):
                raise ValueError('Opening delta gate violated')
            if m['monthly_only'] != 'True' or int(m['samples']) != int(config['lookback']):
                raise ValueError('Monthly/full IV window gate violated')
            low, high, iv = map(float, (m['iv_low'], m['iv_high'], m['iv']))
            rank = 100 * (iv - low) / (high - low) if high > low else float('nan')
            if not math.isfinite(rank) or rank <= 70 or abs(rank - float(m['ivr'])) > 1e-7:
                raise ValueError('True min/max IV rank gate violated')
            if 'max_holding_days' in config:
                cap=validate_max_holding_days(config['max_holding_days'])
                if str(m.get('max_holding_days')) != str(cap):
                    raise ValueError('Opening lacks exact declared holding-duration annotation')
            elif 'max_holding_days' in m:
                raise ValueError('Undeclared holding-duration annotation')
            if 'min_equity_iv_rv' in config:
                previous = entered.date() - timedelta(days=1)
                if not key.startswith('FUT_'):
                    calendars = json.loads((STRATEGY / 'research/reference/lean_market_hours_20261018.json').read_text())['entries']
                    for _ in range(15):
                        if noon_open(previous, calendars['Equity-usa-[*]']):
                            break
                        previous -= timedelta(days=1)
                    else:
                        raise ValueError('Cannot independently establish previous equity session')
                audit_equity_rv_annotation(key, m, config, previous)
            record = batches.setdefault(batch, dict(batch_id=batch, entry=group[0]['time'],
                count=count, equity=equity, budget=budget, reserve=0., keys=[], volumes=[], sealed=False))
            if (record['sealed'] or record['count'] != count or abs(record['equity'] - equity) > .001
                    or ny_time(record['entry']).date() != entered.date()):
                raise ValueError('Batch membership or frozen opening equity changed')
            record['reserve'] += reserve; record['keys'].append(key); record['volumes'].append(float(m['volume']))
            active[key] = dict(batch_id=batch, quantity=quantity, expiry=identities[0]['expiry'])
            entries.append(dict(key=key, entry=group[0]['time'], expiry=identities[0]['expiry'], **m))
            peak = max(peak, len(active))
            if peak > 13:
                raise ValueError('Basket exceeds 13')
        else:
            if key not in active or active[key]['quantity'] != quantity:
                raise ValueError('Action changed existing contract quantity or lacks position')
            if reason == 'ROLL':
                if sorted(q > 0 for q in quantities) != [False, True]:
                    raise ValueError('Roll does not close one leg and open one leg')
                if any(option_identity(row['symbol'])['expiry'] != active[key]['expiry'] for row in group):
                    raise ValueError('Roll changed expiry')
                credit = sum(-float(event.get('fillQuantity',0))*float(event.get('fillPrice',0))*order_multiplier(row) for row in group for event in row['events'])
                if credit <= 0:
                    raise ValueError('Roll is not a gross credit')
            if reason != 'ROLL':
                if any(q <= 0 for q in quantities):
                    raise ValueError('Exit does not buy back both shorts')
                batches[active[key]['batch_id']]['sealed'] = True
                del active[key]
                last_exit_day = max(ny_time(row['time']).date() for row in group)
    if active:
        raise ValueError('Residual logical strategy positions')
    for record in batches.values():
        if len(record['keys']) != record['count'] or record['volumes'] != sorted(record['volumes'], reverse=True):
            raise ValueError('Batch count/ranking differs from declared sizing denominator')
        if record['reserve'] > record['equity'] * config['total_collateral_fraction'] + .001:
            raise ValueError('Summed opening collateral exceeds account cap')
    return entries, list(batches.values()), peak


def audit_dates(cycles, entries, time_exit_dte=21, max_holding_days=None):
    if max_holding_days is not None:
        validate_max_holding_days(max_holding_days)
    if type(time_exit_dte) is not int or time_exit_dte not in (21, 28):
        raise ValueError("Unsupported research exit DTE")
    calendars = json.loads((STRATEGY / 'research/reference/lean_market_hours_20261018.json').read_text())['entries']
    lookup = {(row['key'], ny_time(row['entry']).date()): row for row in entries}
    for cycle in cycles:
        m = lookup[(cycle['ticker'], ny_time(cycle['entry']).date())]
        cycle.update(batch_id=int(m['batch_id']), quantity=int(m['quantity']), allocation_budget=float(m['allocation_budget']))
        if not 35 <= cycle['entry_dte'] <= 95 or cycle['rolls'] > 3:
            raise ValueError('Entry tenor or maximum roll count violated')
        if cycle['ticker'].startswith('FUT_'):
            root = cycle['ticker'][4:]; market = ROOT_MARKETS[root]
            calendar = calendars.get(f'Future-{market}-{root}', calendars[f'Future-{market}-[*]'])
        else:
            calendar = calendars['Equity-usa-[*]']
            expiry = date.fromisoformat(cycle['expiry']); first = expiry.replace(day=1)
            friday = first + timedelta(days=(4-first.weekday()) % 7 + 14)
            if not standard_equity_monthly(expiry, not noon_open(friday, calendar)):
                raise ValueError('Nonmonthly equity expiry')
        due = date.fromisoformat(cycle['expiry']) - timedelta(days=time_exit_dte)
        cycle['configured_time_exit_dte'] = time_exit_dte
        cycle['calendar_configured_exit_date'] = str(due)
        for _ in range(15):
            if noon_open(due, calendar):
                break
            due += timedelta(days=1)
        else:
            raise ValueError('No eligible mandatory exit session')
        cycle['first_eligible_configured_exit_date'] = str(due)
        exited = ny_time(cycle['exit'])
        if cycle['reason'] == 'TIME':
            if exited.date() != due or not time(12) <= exited.time() <= time(12, 5):
                raise ValueError('TIME exit missed first eligible product noon')
        elif exited > datetime.combine(due, time(12, 5), exited.tzinfo):
            raise ValueError('Position survived mandatory DTE exit')
        if max_holding_days is None:
            if cycle['reason']=='AGE':
                raise ValueError('Undeclared AGE exit')
            continue
        if str(m.get('max_holding_days')) != str(max_holding_days):
            raise ValueError('Missing/mismatched holding cap on audited opening')
        age_due=ny_time(cycle['entry']).date()+timedelta(days=max_holding_days)
        for _ in range(15):
            if noon_open(age_due,calendar):break
            age_due+=timedelta(days=1)
        else:raise ValueError('No eligible holding-duration exit session')
        cycle['max_holding_days']=max_holding_days
        cycle['first_eligible_age_exit_date']=str(age_due)
        if exited > datetime.combine(age_due,time(12,5),exited.tzinfo):
            raise ValueError('Position survived maximum holding-duration exit')
        if cycle['reason']=='AGE':
            if age_due>=due or exited.date()!=age_due or not time(12)<=exited.time()<=time(12,5):
                raise ValueError('AGE exit missed first eligible noon or overrode TIME precedence')


def expected_account_end_session(end):
    """Require the actual requested final US account session, not a four-day guess."""
    calendars=json.loads((STRATEGY/'research/reference/lean_market_hours_20261018.json').read_text())['entries']
    calendar=calendars['Equity-usa-[*]']
    day=end
    for _ in range(15):
        if noon_open(day,calendar):return day
        day-=timedelta(days=1)
    raise ValueError('No eligible final account session in saved exchange calendar')


def account_metrics(daily, initial, begin, end, reported_mdd=None):
    """Actual window evidence; absent endpoints never imply funded-period CAGR."""
    if end <= begin:
        raise ValueError('Invalid account measurement window')
    points=sorted((day,value) for day,value in daily.items() if begin<=day<=end)
    before=[value for day,value in sorted(daily.items()) if day<begin]
    opening=before[-1] if before else initial
    if not math.isfinite(opening) or any(not math.isfinite(value) for _,value in points):
        raise ValueError('Nonfinite account equity')
    expected=expected_account_end_session(end)
    endpoint=bool(points and points[-1][0]>=expected)
    common=dict(start=str(begin),end=str(end),observations=len(points),opening_equity=opening,
        expected_end_session=str(expected),observed_start=str(points[0][0]) if points else None,
        observed_end=str(points[-1][0]) if points else None,window_end_observed=endpoint,
        reported_mdd=reported_mdd)
    if not points:
        return dict(common,available=False,unavailable_reason='No account-equity observations in requested window; no post-terminal observations invented',
            ending_equity=None,net_pnl=None,cagr=None,daily_mdd=None,denominator_mdd=None,
            calmar=None,positive_equity=False)
    ending=points[-1][1]
    if opening<=0:
        return dict(common,available=False,unavailable_reason='Requested window begins with nonpositive account equity; no funded-return metric',
            ending_equity=ending,net_pnl=ending-opening,cagr=None,daily_mdd=None,denominator_mdd=None,
            calmar=None,positive_equity=False)
    peak=opening;daily_mdd=0.
    for _,value in points:
        peak=max(peak,value);daily_mdd=max(daily_mdd,1-value/peak)
    positive=ending>0 and all(value>0 for _,value in points)
    reason=None
    if not positive:
        reason='Nonpositive actual account equity; CAGR and Calmar undefined'
    elif not endpoint:
        reason='Actual equity observations end before the requested final account session; full-window CAGR and Calmar unavailable'
    cagr=(ending/opening)**(365.25/(end-begin).days)-1 if positive and endpoint else None
    denominator=max(daily_mdd,reported_mdd if reported_mdd is not None else 0.)
    return dict(common,available=bool(positive and endpoint),unavailable_reason=reason,ending_equity=ending,
        net_pnl=ending-opening,cagr=cagr,daily_mdd=daily_mdd,denominator_mdd=denominator,
        calmar=cagr/denominator if cagr is not None and denominator>0 else None,
        positive_equity=positive)


def evaluation_result(key,summary,daily,cycles,frozen,plan):
    """Finalization remains possible for genuine terminal debt before evaluation."""
    begin=date.fromisoformat(plan['evaluation_start']);end=date.fromisoformat(plan['end'])
    reported=summary['account']['reported_mdd']
    observed=summary['account'].get('observed_account_chart_mdd_upper_bound',
        summary['account'].get('observed_account_chart_mdd_lower_bound',0.))
    evaluation=account_metrics(daily,plan['initial_cash'],begin,end,
        max(reported,observed) if reported is not None else observed or None)
    anchor_day=expected_account_end_session(begin-timedelta(days=1))
    anchor_present=anchor_day in daily
    evaluation.update(expected_opening_anchor_session=str(anchor_day),window_opening_anchor_verified=anchor_present)
    if not anchor_present and evaluation['available']:
        evaluation.update(available=False,cagr=None,calmar=None,unavailable_reason='Missing actual account equity at the evaluation opening boundary; initial cash cannot substitute for accumulated account equity')
    count=sum(begin<=ny_time(cycle['exit']).date()<=end for cycle in cycles)
    account=summary['account']
    qualifies=(key==frozen['chosen_variant'] and summary['period_complete']
        and account.get('window_end_observed',False) and account['positive_equity']
        and summary['cycles']>=plan['minimum_closed_cycles'] and count>=plan['minimum_evaluation_cycles']
        and account['reported_mdd'] is not None and account['calmar'] is not None and account['calmar']>2
        and evaluation['available'] and evaluation['window_end_observed'] and evaluation['positive_equity']
        and evaluation['calmar'] is not None and evaluation['calmar']>2)
    return dict(variant=key,summary=summary,evaluation=evaluation,evaluation_cycles=count,target_flag=bool(qualifies))


def daily_marks(response):
    series = response['chart']['series']
    candidate = series.get('Equity') or series.get('Equity Sum')
    if candidate is None:
        raise ValueError('Account equity chart has no Equity series')
    daily = {}
    for point in candidate['values']:
        if isinstance(point, dict):
            stamp = point['x']; value = point.get('close', point.get('y'))
        else:
            stamp = point[0]
            value = point[4] if len(point) == 5 else point[1]
        if isinstance(value, dict):
            value = value['close']
        day = datetime.fromtimestamp(stamp, timezone.utc).astimezone(ny_time('2020-01-01T00:00:00Z').tzinfo).date()
        daily[day] = float(value)
    return daily


def write_tables(folder, frames):
    folder.mkdir(exist_ok=True)
    receipts = {}
    with duckdb.connect(str(folder / 'research.duckdb')) as connection:
        for table, rows in frames.items():
            frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
            if not len(frame.columns):
                frame = pd.DataFrame(columns=['no_records'])
            connection.register('frame', frame)
            connection.execute('CREATE OR REPLACE TABLE ' + table + ' AS SELECT * FROM frame')
            connection.unregister('frame')
            frame.to_csv(folder / (table + '.csv'), index=False)
            path = folder / (table + '.parquet')
            connection.execute('COPY ' + table + ' TO ? (FORMAT PARQUET, COMPRESSION ZSTD)', [str(path)])
            count = connection.execute('SELECT COUNT(*) FROM read_parquet(?)', [str(path)]).fetchone()[0]
            if count != len(frame):
                raise ValueError('Parquet row count differs from DuckDB')
            receipts[table] = dict(rows=count, parquet_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), readback_verified=True)
    atomic_json(folder / 'tables.json', receipts)


def verify_frozen_source(campaign, key, config, row):
    source_path = campaign / (key + '.py')
    source = source_path.read_text()
    if row['code'] != source:
        raise ValueError('Frozen variant source differs from actual Rust queued code')
    extras = json.loads((campaign/'extra_files.json').read_text())
    actual_extras = json.loads(row['extra_files']) if isinstance(row['extra_files'], str) else row['extra_files']
    if actual_extras != extras:
        raise ValueError('Frozen helpers differ from actual Rust queued helpers')
    tree = ast.parse(source)
    configs = [ast.literal_eval(node.value) for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'CONFIG' for target in node.targets)]
    if configs != [config]:
        raise ValueError('Rendered source CONFIG differs from campaign manifest')
    for needle in ("self.CONFIG['risk_interval_minutes']", "self.CONFIG['stop_multiple']"):
        if needle not in source:
            raise ValueError('Research risk rule is not referenced by frozen implementation')
    if 'max_holding_days' in config:
        validate_max_holding_days(config['max_holding_days'])
        if not (config.get('cross_asset_voluntary_guard') is True and config.get('fresh_risk_retry') is True
                and config.get('voluntary_spread_guard') is True and 'min_equity_iv_rv' in config
                and config.get('future_rv_policy')=='original_rules'):
            raise ValueError('Holding-cap source chain configuration mismatch')
        verify_chain(campaign,source.replace('CONFIG = '+repr(config),'CONFIG = {}',1),extras)
    elif 'min_equity_iv_rv' in config:
        receipt = json.loads((campaign/'equity_rv_source_receipt_20261019.json').read_text())
        unrendered = source.replace('CONFIG = '+repr(config), 'CONFIG = {}', 1)
        if hashlib.sha256(unrendered.encode()).hexdigest() != receipt['generated_sha256']:
            raise ValueError('Equity RV source differs from frozen narrow-transformation proof')
        parent = Path(receipt['parent'])
        if hashlib.sha256(parent.read_bytes()).hexdigest() != receipt['parent_sha256']:
            raise ValueError('Preserved guarded parent source changed')
        if not {'completed_volatility.py','equity_rv_features.py'}.issubset(extras):
            raise ValueError('Missing frozen equity RV dependencies')
    return dict(main_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
        helpers_sha256=hashlib.sha256((campaign/'extra_files.json').read_bytes()).hexdigest(),
        rust_content_hash=row['code_hash'], queued_code_and_helpers_identical=True)


def collect_logs(user, token, folder, ids, api=request, page_size=200, max_pages=5000):
    """Persist identity-bound API pages; API exhaustion never proves full cloud coverage.

    Each failed attempt has its own receipt. Valid cached pages are reused; a
    malformed/repeated page remains raw evidence but is not silently accepted.
    """
    if page_size != 200 or max_pages < 1:
        raise ValueError('Require200-line log pages and a positive pagination bound')
    pages = folder/'log_pages'; pages.mkdir(exist_ok=True)
    identity = {key:str(value) for key,value in ids.items()}
    lines, hashes, receipts = [], set(), []
    receipt = dict(identity=identity, started_utc=datetime.now(timezone.utc).isoformat(),
        page_size=page_size, api_pagination_exhausted=False, full_cloud_log_coverage='unknown',
        coverage_note='QC may truncate stored logs before this endpoint; complete native orders remain execution authority.', pages=receipts)
    try:
        for page_index in range(max_pages):
            start = page_index*page_size
            parameters = dict(ids,start=start,end=start+page_size,query='')
            path = pages/('page_'+str(start).zfill(7)+'.json')
            if path.exists():
                envelope=json.loads(path.read_text())
                if envelope.get('identity') != identity or envelope.get('parameters') != parameters:
                    raise ValueError('Cached log page identity or requested offset differs')
                response=envelope['response']
            else:
                response=api(user,token,'/backtests/read/log',parameters)
                atomic_json(path,dict(identity=identity,parameters=parameters,response=response))
            if not isinstance(response,dict):
                raise ValueError('Log response is not an object')
            if response.get('success') is False or response.get('errors'):
                raise RuntimeError('Log endpoint rejected page: '+str(response.get('errors')))
            for key in ('projectId','backtestId'):
                if key in response and str(response[key]) != identity[key]:
                    raise ValueError('Returned log page identity differs')
            if 'logs' not in response and 'log' not in response:
                raise ValueError('Log response omitted log/logs; cannot infer empty page')
            page=response.get('logs',response.get('log'))
            if not isinstance(page,list) or any(not isinstance(line,str) for line in page) or len(page)>page_size:
                raise ValueError('Malformed or oversized log page')
            digest=hashlib.sha256(json.dumps(page,ensure_ascii=False).encode()).hexdigest()
            if page and digest in hashes:
                raise ValueError('Repeated log page at a different offset')
            if page and lines and lines[-1] == page[0]:
                raise ValueError('Log pages overlap at the requested offset boundary')
            if page:hashes.add(digest)
            lines.extend(page)
            receipts.append(dict(start=start,end=start+page_size,lines=len(page),
                response_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            if len(page)<page_size:
                receipt['api_pagination_exhausted']=True
                break
        else:
            raise RuntimeError('Log pagination safety bound reached; partial evidence retained')
        warnings=[line for line in lines if ('maximum' in line.lower() and 'log data' in line.lower())
            or 'logs have been truncated' in line.lower() or 'log limit exceeded' in line.lower()]
        receipt['source_log_limit_warning']=bool(warnings)
        if warnings:
            receipt['full_cloud_log_coverage']='limited_by_qc_log_cap_warning'
            receipt['source_log_limit_messages']=warnings
        content='\n'.join(lines)
        path=folder/'cloud.log'
        if path.exists() and path.read_text()!=content:
            previous_hash=hashlib.sha256(path.read_bytes()).hexdigest()
            preserved=folder/('cloud.previous_'+previous_hash[:16]+'.log')
            if not preserved.exists():preserved.write_bytes(path.read_bytes())
        path.write_text(content)
        receipt.update(status='collected_available_api_logs',lines=len(lines),
            cloud_log_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    except Exception as exc:
        receipt.update(status='collection_error',error=type(exc).__name__+': '+str(exc),
            retry_read_only=True,lines=len(lines),cloud_failure_inferred=False)
        if lines:
            partial='\n'.join(lines)
            digest=hashlib.sha256(partial.encode()).hexdigest()
            path=folder/('cloud.partial_'+digest[:16]+'.log')
            if not path.exists():path.write_text(partial)
        raise
    finally:
        receipt['finished_utc']=datetime.now(timezone.utc).isoformat()
        atomic_json(folder/'log_collection_receipt.json',receipt)
        with (folder/'log_collection_attempts.jsonl').open('a') as history:
            history.write(json.dumps(receipt)+'\n')
    return receipt


def verified_terminal_cache(folder,row):
    """Reuse only a full terminal response pinned by an exact identity/hash receipt.

    Legacy/missing/nonterminal evidence is not cache proof. Integrity conflicts
    fail before any API request or overwrite, preserving the original evidence.
    """
    path=folder/'backtest.json';receipt_path=folder/'collection_receipt.json'
    ids=dict(projectId=row['project_id'],backtestId=row['backtest_id'])
    receipt=json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    if receipt is not None and 'identity' in receipt:
        identity=receipt['identity']
        if not isinstance(identity,dict) or any(str(identity.get(key))!=str(value) for key,value in ids.items()):
            raise ValueError('Terminal cache collection receipt identity differs from frozen execution')
    if not path.exists():return None
    payload=json.loads(path.read_text())
    validate_cached_backtest(payload,ids)
    backtest=payload['backtest'];status=terminal_status(backtest)
    if payload.get('success') is False or payload.get('errors'):
        raise ValueError('Cached full response contains an API error; evidence must be investigated')
    if receipt is None:return None
    if 'cloud_status' in receipt and receipt['cloud_status']!=status:
        raise ValueError('Terminal cache collection receipt status differs from cached response')
    digest=receipt.get('backtest_sha256')
    if digest is not None and digest!=hashlib.sha256(path.read_bytes()).hexdigest():
        raise ValueError('Terminal cache backtest SHA256 differs from collection receipt; original evidence preserved')
    if (digest is None or 'identity' not in receipt or 'cloud_status' not in receipt
            or backtest.get('completed') is not True or status not in ('done','failed')):
        return None
    return payload


def read_research_backtest(user,token,campaign,name,row):
    """Known terminal evidence avoids API polling; every live execution is read anew."""
    cached=verified_terminal_cache(campaign/name,row)
    if cached is not None:return cached
    response=read_existing_backtest(user,token,row)
    validate_identity(response['backtest'],row)
    return response


def collect_terminal(user, token, campaign, name, row, response):
    folder = campaign / name; folder.mkdir(exist_ok=True)
    full = response['backtest']; ids = dict(projectId=row['project_id'], backtestId=row['backtest_id'])
    validate_identity(full,row)
    if response.get('success') is False or response.get('errors'):
        raise ValueError('Cannot pin a full response containing an API error')
    if terminal_status(full) is None:
        raise ValueError('Cannot collect/pin a nonterminal cloud response')
    cached = folder / 'backtest.json'
    trusted=verified_terminal_cache(folder,row)
    if trusted is not None and trusted!=response:
        conflict=hashlib.sha256(json.dumps(response,sort_keys=True).encode()).hexdigest()
        atomic_json(folder/('backtest.conflicting_response_'+conflict[:16]+'.json'),response)
        raise ValueError('Pinned full terminal response changed; conflicting evidence retained without overwrite')
    if trusted is None:
        if cached.exists() and json.loads(cached.read_text())!=response:
            old_hash=hashlib.sha256(cached.read_bytes()).hexdigest()
            preserved=folder/('backtest.previous_'+old_hash[:16]+'.json')
            if not preserved.exists():preserved.write_bytes(cached.read_bytes())
        atomic_json(cached, response)
    prior_path=folder/'collection_receipt.json'
    prior=json.loads(prior_path.read_text()) if prior_path.exists() else {}
    # Pin the actual full response immediately, even if a later order/log/chart
    # request fails. That failure needs an artifact retry, not another full read.
    pin=dict(prior,identity=ids,utc=datetime.now(timezone.utc).isoformat(),cloud_status=terminal_status(full),
        backtest_sha256=hashlib.sha256(cached.read_bytes()).hexdigest(),
        collection_stage='full_terminal_response_preserved; remaining_artifacts_pending')
    atomic_json(prior_path,pin)
    with (folder/'collection_attempts.jsonl').open('a') as history:history.write(json.dumps(pin)+'\n')
    orders_path = folder / 'orders.json'
    if not orders_path.exists():
        count = full.get('statistics', {}).get('Total Orders')
        orders = read_all_orders(user, token, ids, int(str(count).replace(',', '')) if count is not None else None)
        atomic_json(orders_path, orders)
    rust_path = folder / 'orders.rust.json'
    if not rust_path.exists():
        subprocess.run([str(ROOT/'target/release/qc-backtest-server'), '--data-dir', str(ROOT/'data'),
            'backtest-orders', '--strategy', 'sstrangle', '--name', name, '--out', str(rust_path)], check=True)
    collection_issues=[]
    try:
        collect_logs(user,token,folder,ids,api=request)
    except Exception as exc:
        # Logs are optional diagnostics. Continue preserving account evidence on
        # an actual cloud failure even if this independent request times out.
        collection_issues.append(dict(artifact='cloud.log',error=type(exc).__name__+': '+str(exc),
            retry_read_only=True,cloud_failure_inferred=False))
    # Charts are account results, never option quote history. Retain failed evidence too.
    for chart in ('Trading period', 'Strategy Equity'):
        path = folder / (chart.lower().replace(' ', '_') + '.json')
        if not path.exists():
            try:
                atomic_json(path, read_chart(user, token, dict(ids, name=chart, **chart_window(full))))
            except Exception as exc:
                issue=dict(artifact=chart,error=type(exc).__name__+': '+str(exc),retry_read_only=True,
                    cloud_failure_inferred=False,identity=ids,utc=datetime.now(timezone.utc).isoformat())
                atomic_json(folder/(chart.lower().replace(' ', '_')+'_unavailable.json'),issue)
                with (folder/'chart_collection_attempts.jsonl').open('a') as history:
                    history.write(json.dumps(issue)+'\n')
                collection_issues.append(issue)
    receipt=dict(identity=ids,utc=datetime.now(timezone.utc).isoformat(),cloud_status=terminal_status(full),
        backtest_sha256=hashlib.sha256(cached.read_bytes()).hexdigest(),collection_stage='available_artifact_collection_finished',
        issues=collection_issues,collection_errors_are_not_cloud_failures=True)
    atomic_json(folder/'collection_receipt.json',receipt)
    with (folder/'collection_attempts.jsonl').open('a') as history:history.write(json.dumps(receipt)+'\n')
    return folder


def audit_variant(folder, config, row):
    full = json.loads((folder/'backtest.json').read_text())['backtest']
    orders = json.loads((folder/'orders.json').read_text())
    rust = json.loads((folder/'orders.rust.json').read_text()); rust = rust['orders'] if isinstance(rust, dict) else rust
    fills = execution_rows(orders)
    if execution_signature(fills) != execution_signature(execution_rows(rust)):
        raise ValueError('Rust/Python native execution mismatch')
    declared = full.get('statistics', {}).get('Total Orders')
    if declared is None or len(orders) != int(str(declared).replace(',', '')):
        raise ValueError('Order count missing/incomplete')
    entries, batches, peak = audit_budget_annotations(orders, config)
    cycles = audit_dte(orders); audit_dates(cycles, entries, config.get('time_exit_dte',21),config.get('max_holding_days'))
    residual = Counter()
    for fill in fills:
        residual[fill['symbol_id']] += fill['quantity']
    if any(abs(value) > 1e-7 for value in residual.values()):
        raise ValueError('Nonzero actual residual position')
    runtime = full.get('runtimeStatistics', {}); initial = float(config['initial_cash'])
    net = sum(cycle['pnl'] for cycle in cycles); fees = sum(fill['fee'] for fill in fills)
    if (abs(money(runtime['Equity']) - initial - net) > .005
            or abs(abs(money(runtime['Fees']))-fees) > .005
            or money(runtime['Holdings']) != 0 or money(runtime['Unrealized']) != 0):
        raise ValueError('Native cash/fees/holdings differ from terminal account')
    optional = {'entries': len(entries), 'closed_cycles': len(cycles), 'cycle_net_pnl': net}
    for key, expected in optional.items():
        if key in runtime and abs(float(runtime[key])-expected) > .05:
            raise ValueError('Runtime accounting disagrees with native orders: ' + key)
    log = (folder/'cloud.log').read_text()
    logs = audit_available_logs(events(log, 'ENTRY'), events(log, 'CYCLE'), entries, cycles)
    log_receipt=folder/'log_collection_receipt.json'
    logs['collection_receipt']=json.loads(log_receipt.read_text()) if log_receipt.exists() else dict(status='legacy_unverified_log_collection',full_cloud_log_coverage='unknown')
    chart = folder/'trading_period.json'
    if not chart.exists():
        chart = folder/'strategy_equity.json'
    daily = daily_marks(json.loads(chart.read_text()))
    if abs(daily[max(daily)]-initial-net) > .05:
        raise ValueError('Last equity chart mark differs from actual terminal cash')
    if 'active_snapshots' in runtime and chart.name == 'trading_period.json' and len(daily) != int(runtime['active_snapshots']):
        raise ValueError('Daily equity chart incomplete versus declared snapshots')
    begin = date(*config['start']); end = date(*config['end'])
    # Reject truncated chart sampling, even when optional runtime fields disappear.
    observations = sorted(daily)
    if any((right-left).days > 7 for left, right in zip(observations, observations[1:])):
        raise ValueError('Account chart has missing/resampled intervals longer than seven days')
    reported = full.get('statistics', {}).get('Drawdown')
    reported = float(str(reported).rstrip('%')) / 100 if reported is not None else None
    terminal = full.get('backtestEnd', '')[:10]
    outcome = runtime.get('baseline_outcome', 'insolvent' if initial+net <= 0 else 'period_complete')
    period_complete = terminal_status(full) == 'done' and outcome == 'period_complete' and max(daily) >= expected_account_end_session(end)
    metrics = account_metrics(daily, initial, begin, end, reported)
    chart_audits=[]
    for filename in ('trading_period.json','strategy_equity.json'):
        path=folder/filename
        if path.exists():
            observed=chart_drawdown(json.loads(path.read_text()),initial,begin,end)
            chart_audits.append(dict(source=filename,**observed))
    include_chart_drawdown(metrics,chart_audits)
    period_complete=period_complete and metrics['window_end_observed']
    notes = [key for key in ('entries', 'closed_cycles', 'cycle_net_pnl', 'active_snapshots', 'baseline_outcome') if key not in runtime]
    summary = dict(name=row['name'], project_id=row['project_id'], backtest_id=row['backtest_id'],
        orders=len(orders), fills=len(fills), cycles=len(cycles), fees=fees, net_pnl=net, peak_basket=peak,
        period_complete=period_complete, outcome=outcome, account=metrics, missing_custom_runtime_fields=notes,
        diagnostic_log_coverage=logs, risk_rule_verification='Stop multiple and15minute interval verified against immutable queued source and manifest; not inferred from omitted runtime fields. Triggers can execute later on stale/missing quotes or sequential fills.', monthly_futures_validation='Frozen cloud product expiry functions; actual exported monthly annotations checked',
        audits=dict(native_downloads_equal=True, zero_residuals=True, account_reconciles=True,
            capped_collateral=True, full504_true_ivr=True, first_21dte_exit=(config.get('time_exit_dte',21)==21), first_configured_dte_exit=True, configured_exit_dte=config.get('time_exit_dte',21), maximum_holding_days=config.get('max_holding_days'), holding_duration_exit_audited=('max_holding_days' in config), no_replacement_or_same_day_entries=True))
    write_tables(folder/'research_report', dict(executions=fills, cycles=cycles, entries=entries,
        batches=[dict(record, keys=json.dumps(record['keys']), volumes=json.dumps(record['volumes'])) for record in batches],
        daily_equity=[dict(date=str(day),equity=value) for day,value in sorted(daily.items())]))
    evidence = {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in folder.iterdir() if path.is_file()}
    atomic_json(folder/'research_report/evidence_checksums.json',evidence)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    marks=sorted(daily.items());peak=initial;drawdowns=[]
    for _,value in marks:
        peak=max(peak,value);drawdowns.append(100*(value/peak-1))
    figure,axes=plt.subplots(2,1,figsize=(11,6),sharex=True)
    axes[0].plot([d for d,_ in marks],[v for _,v in marks]);axes[0].set_ylabel('Account equity USD')
    axes[0].set_title(row['name'])
    axes[1].fill_between([d for d,_ in marks],drawdowns,0,alpha=.5);axes[1].set_ylabel('Daily drawdown %')
    figure.tight_layout();figure.savefig(folder/'research_report/equity_drawdown.png',dpi=150);plt.close(figure)
    atomic_json(folder/'research_report/summary.json', summary)
    return summary, daily, cycles


def freeze_training(campaign, records, plan, excluded=None):
    path = campaign/'training_selection.json'
    training = []
    for key, summary, daily, cycles in records:
        end = date.fromisoformat(plan['training_end']); begin = date.fromisoformat(plan['history_start'])
        metrics = account_metrics(daily, plan['initial_cash'], begin, end)
        count = sum(ny_time(cycle['exit']).date() <= end for cycle in cycles)
        # QC whole-period drawdown must not leak evaluation outcomes into train selection.
        training.append(dict(variant=key, metrics=metrics, cycles=count,
            eligible=count >= 40 and metrics['positive_equity'] and metrics['window_end_observed'] and metrics['calmar'] is not None and summary.get('period_complete',True),
            exclusion_reason=('Incomplete funded period' if not summary.get('period_complete',True) else
                metrics['unavailable_reason'] if not metrics['window_end_observed'] or not metrics['available'] else None)))
    eligible = [row for row in training if row['eligible']]
    winner = max(eligible, key=lambda row:(row['metrics']['calmar'], row['variant']))['variant'] if eligible else None
    frozen = dict(selection_rule='Highest2012-2019 daily-equity training Calmar, minimum40closedcycles; tie lexicographic variant',
        chosen_variant=winner, training=training, excluded_attempts=excluded or [], prior_inspection=plan['prior_inspection'])
    if path.exists():
        existing = json.loads(path.read_text())
        if {k:v for k,v in existing.items() if k != 'frozen_utc'} != frozen:
            raise ValueError('Previously frozen training selection differs; preserve evidence')
        return existing
    frozen['frozen_utc'] = datetime.now(timezone.utc).isoformat()
    atomic_json(path, frozen)
    return frozen


def failed_attempt_evidence(folder, row, full, source_receipt):
    """Summarize genuine failed evidence without forcing an open portfolio flat."""
    orders=json.loads((folder/'orders.json').read_text())
    rust=json.loads((folder/'orders.rust.json').read_text())
    rust=rust['orders'] if isinstance(rust,dict) else rust
    fills=execution_rows(orders)
    native_equal=execution_signature(fills)==execution_signature(execution_rows(rust))
    if not native_equal:raise ValueError('Failed-run Rust/Python native executions differ')
    residual=Counter()
    for fill in fills:residual[fill['symbol_id']]+=fill['quantity']
    declared=full.get('statistics',{}).get('Total Orders')
    complete=declared is not None and len(orders)==int(str(declared).replace(',',''))
    if declared is not None and not complete:raise ValueError('Failed-run order export is incomplete')
    receipt=json.loads((folder/'collection_receipt.json').read_text())
    summary=dict(name=row['name'],backtest_id=row['backtest_id'],project_id=row['project_id'],
        cloud_status='failed',cloud_failure_confirmed=True,error=full.get('error'),qualified_for_selection=False,
        requested_period_complete=False,target_flag=False,orders=len(orders),actual_fills=len(fills),
        complete_declared_orders=complete,rust_python_executions_equal=native_equal,
        actual_execution_fees=sum(fill['fee'] for fill in fills),
        executed_cashflow_less_fees=sum(-fill['quantity']*fill['qc_price']*fill['multiplier']-fill['fee'] for fill in fills),
        cashflow_is_not_realized_profit_when_positions_remain=True,
        residual_native_quantities={key:value for key,value in residual.items() if abs(value)>1e-7},
        terminal_account_statistics=full.get('runtimeStatistics',{}),collection_receipt=receipt,
        frozen_source=source_receipt,evidence=str(folder),full_period_performance_published=False)
    atomic_json(folder/'failed_attempt_evidence.json',summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('campaign', type=Path)
    args = parser.parse_args(); campaign = args.campaign.resolve()
    manifest = json.loads((campaign/'manifest.json').read_text())
    if manifest['phase'] != 'basket-calmar':
        raise ValueError('Require a frozen basket-calmar campaign')
    lock = (campaign/'research_report.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('Another research collector owns this campaign'); return
    plan_path = campaign/'research_plan.json'
    plan = json.loads(plan_path.read_text())
    user, token = credentials(ROOT/'data/S001.duckdb')
    progress, records, collection_issues, cloud_failures, identities, attempts = [], [], [], [], [], []
    for name in manifest['jobs']:
        key, config = config_for(name, manifest)
        with storage.connect(f'file:{ROOT}/data/SSTRANGLE.duckdb?mode=ro', uri=True) as connection:
            connection.row_factory = storage.Row
            saved = connection.execute('SELECT * FROM backtest_queue WHERE name=?', (name,)).fetchone()
        if saved is None:
            raise ValueError('Frozen queue job missing: ' + name)
        row = dict(saved)
        identities.append({field: row.get(field) for field in
            ('name', 'status', 'project_id', 'backtest_id', 'error_message')})
        source_receipt = verify_frozen_source(campaign,key,config,row)
        if not row.get('backtest_id'):
            progress.append(dict(name=name,status=row['status'],completed=False)); continue
        try:
            response = read_research_backtest(user,token,campaign,name,row); full=response['backtest']; validate_identity(full,row)
            status = terminal_status(full)
            progress.append(dict(name=name,backtest_id=row['backtest_id'],status=full.get('status'),
                completed=full.get('completed'),progress=full.get('progress'),error=full.get('error')))
            if status is None:
                continue
            folder = collect_terminal(user,token,campaign,name,row,response)
            collection_receipt=json.loads((folder/'collection_receipt.json').read_text())
            collection_issues.extend(dict(name=name,**issue) for issue in collection_receipt['issues'])
            if status != 'done':
                failed=failed_attempt_evidence(folder,row,full,source_receipt)
                cloud_failures.append(dict(name=name,variant=key,error=full.get('error'),evidence=str(folder),qualified=False))
                attempts.append(dict(variant=key,**failed))
                continue
            summary,daily,cycles = audit_variant(folder,config,row)
            summary['frozen_source'] = source_receipt
            atomic_json(folder/'research_report/summary.json',summary)
            records.append((key,summary,daily,cycles))
            attempts.append(dict(variant=key,cloud_status='done',qualified_for_selection=summary['period_complete'],summary=summary))
        except Exception as exc:
            collection_issues.append(dict(name=name,error=type(exc).__name__+': '+str(exc),retry_read_only=True))
            # A failed evidence request cannot erase a separately observed cloud error.
            observed=next((item for item in progress if item['name']==name),{})
            if observed.get('error') and not any(item['name']==name for item in cloud_failures):
                cloud_failures.append(dict(name=name,variant=key,error=observed['error'],qualified=False,evidence_collection_incomplete=True))
    snapshot=dict(utc=datetime.now(timezone.utc).isoformat(),jobs=progress,collection_issues=collection_issues,cloud_failures=cloud_failures)
    record_monitor(campaign,snapshot,identities)
    out=campaign/'research_report';out.mkdir(exist_ok=True)
    atomic_json(out/'attempts.json',dict(utc=snapshot['utc'],attempts=attempts,
        cloud_failures=cloud_failures,collection_issues=collection_issues,observations=progress,
        target_reached=False,full_campaign_audited=False))
    print(json.dumps(dict(progress=progress,cloud_failures=cloud_failures,collection_issues=collection_issues),indent=2),flush=True)
    all_terminal=len(progress)==len(manifest['jobs']) and all(item.get('completed') for item in progress)
    if collection_issues or not all_terminal:
        return
    frozen = freeze_training(campaign,records,plan,excluded=cloud_failures)
    results=[]
    # Evaluation metrics are computed only after the training decision is persisted.
    for key,summary,daily,cycles in records:
        results.append(evaluation_result(key,summary,daily,cycles,frozen,plan))
    out=campaign/'research_report';out.mkdir(exist_ok=True)
    report=dict(status='completed_attempts_reported' if results else 'attempts_collected_no_qualified_result',target_reached=any(row['target_flag'] for row in results),
        training_selection=frozen,variants=results,attempts=attempts,failed_attempts=cloud_failures,robustness_certified=False,
        target_claim_scope='This frozen campaign only; later feasibility-v2 code is not thereby verified',
        limitations=plan['limitations']+['Temporal split is not a pristine out-of-sample claim; baseline and other intervals were previously inspected.',
            'Denominator includes daily marks, the upper drawdown bound from available account OHLC when intrabar ordering is unknown, and QC-reported drawdown; unobserved intraday peaks remain a sampling limit. Frozen training selection continues to use its predeclared daily-account metric.',
            'No strategy is certified robust merely by crossing Calmar2 in this fixed two-variant experiment.'])
    atomic_json(out/'summary.json',report)
    text=['US short-strangle fixed-variant research',
        'Training choice frozen before evaluation calculation: '+str(frozen['chosen_variant']),
        'Target flag: '+str(report['target_reached'])+'; robustness certification: false',
        plan['prior_inspection'],'']
    for row in results:
        summary=row['summary'];account=summary['account'];evaluation=row['evaluation']
        text.extend([row['variant'],
            'QC backtest '+summary['backtest_id'],
            'Full funded-window CAGR '+str(account['cagr'])+'; conservative MDD '+str(account['denominator_mdd'])+'; Calmar '+str(account['calmar']),
            'Evaluation CAGR '+str(evaluation['cagr'])+'; conservative MDD '+str(evaluation['denominator_mdd'])+'; Calmar '+str(evaluation['calmar']),
            'Evaluation availability: '+str(evaluation['available'])+'; reason: '+str(evaluation['unavailable_reason']),
            'Cycles '+str(summary['cycles'])+'; evaluation cycles '+str(row['evaluation_cycles'])+'; fees USD '+str(summary['fees']),
            'Requested period complete '+str(summary['period_complete'])+'; target flag '+str(row['target_flag']),''])
    for failure in cloud_failures:
        text.extend(['FAILED / UNQUALIFIED: '+failure['variant'],failure['error'],'Evidence: '+failure.get('evidence','pending')])
    text.extend(report['limitations'])
    (out/'REPORT.txt').write_text('\n'.join(text)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
