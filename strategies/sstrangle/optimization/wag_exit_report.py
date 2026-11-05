"""Read-only native WBA exit regression collector; no strategy-performance claim."""
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
STRATEGY=HERE.parent
ROOT=STRATEGY.parents[1]
sys.path[:0]=[str(STRATEGY),str(ROOT/'scripts')]
import qc_storage as storage
from qc_api_check import credentials
from resume_basket import read_existing_backtest, validate_identity, terminal_status, atomic_json
from qc_contracts import execution_rows, execution_signature
from audit_21dte import audit_dte
from basket_report import ny_time, events

spec=importlib.util.spec_from_file_location('_wag_research_report',HERE/'report.py')
shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
INITIAL=41194.185
SOURCE_BACKTEST='8a6d193829c51b26976d40707c081eb5'
SOURCE_FOLDER=STRATEGY/'results/strangle_basket-calmar_20261019_123602/SSTRANGLE_20261019_123602_cap20_stop1'
PUT='WAG 319LY2CLLOLC6|WAG R735QTJ8XC9X'
CALL70='WAG XAHXWU0GSY86|WAG R735QTJ8XC9X'
CALL65='WAG XAHXWUA227XI|WAG R735QTJ8XC9X'
CLOSE_UTC=datetime(2019,11,29,17,tzinfo=timezone.utc)


def economic_signature(fills):
    """Aliases, campaign event prefixes and order IDs differ; economics must not."""
    fields=('timestamp','symbol_id','underlying_id','quantity','qc_price','multiplier','fee','reason','expiry','strike','call_put')
    return [{field:fill[field] for field in fields} for fill in fills]


def original_first_four():
    full=json.loads((SOURCE_FOLDER/'backtest.json').read_text())['backtest']
    if full['backtestId']!=SOURCE_BACKTEST or str(full['projectId'])!='31338456':
        raise ValueError('Original failed economic evidence identity differs')
    orders=json.loads((SOURCE_FOLDER/'orders.json').read_text())
    rows=[order for order in orders if order['id'] in (759,760,761,762)]
    if [order['id'] for order in rows]!=[759,760,761,762]:raise ValueError('Missing original native fixture orders')
    fills=execution_rows(rows)
    if [(fill['symbol_id'],fill['quantity'],fill['qc_price']) for fill in fills]!=[(PUT,-1,.92),(CALL70,-1,.44),(CALL70,1,.22),(CALL65,-1,.34)]:
        raise ValueError('Original economic fixture is not the specified WBA cycle')
    return fills


def frozen_source(campaign,key,config,row):
    path=campaign/(key+'.py');source=path.read_text()
    if source!=row['code']:raise ValueError('Actual queued fixture differs from frozen main source')
    extra=json.loads((campaign/'extra_files.json').read_text())
    queued=json.loads(row['extra_files']) if isinstance(row['extra_files'],str) else row['extra_files']
    if extra!=queued:raise ValueError('Actual queued fixture helpers differ')
    original_helpers=json.loads((SOURCE_FOLDER.parent/'extra_files.json').read_text())
    shared_helpers=('rules.py','execution_base.py','basket_rules.py','terminal_margin.py','premium_units.py','premium_filter.py')
    if any(extra.get(key)!=original_helpers.get(key) or key not in extra for key in shared_helpers):
        raise ValueError('Fixture changed original native execution/margin helper source')
    configs=[ast.literal_eval(node.value) for node in ast.walk(ast.parse(source)) if isinstance(node,ast.Assign)
        and any(isinstance(target,ast.Name) and target.id=='CONFIG' for target in node.targets)]
    if configs!=[config]:raise ValueError('Fixture source CONFIG differs from manifest')
    if 'AccountType.MARGIN' not in source or 'set_brokerage_model' not in source:
        raise ValueError('Fixture source lacks the default brokerage margin-account setup')
    prohibited=('set_fill_model(', 'set_buying_power_model(', 'set_security_initializer(')
    if any(needle in source for needle in prohibited):raise ValueError('Fixture altered default execution/margin models')
    return dict(main_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        helpers_sha256=hashlib.sha256((campaign/'extra_files.json').read_bytes()).hexdigest(),
        rust_content_hash=row['code_hash'],queued_source_identical=True,original_execution_margin_helpers_unchanged=True)


def isolated_pair_sources(campaign):
    trees=[]
    for key in ('wag_control','wag_buyback'):
        tree=ast.parse((campaign/(key+'.py')).read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='CONFIG' for target in node.targets):
                config=ast.literal_eval(node.value);config['buyback']=False
                node.value=ast.parse(repr(config),mode='eval').body
        trees.append(ast.dump(tree,include_attributes=False))
    return trees[0]==trees[1]


def utc_stamp(value):
    stamp=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    # The frozen fixture explicitly emits self.utc_time, whose str is UTC-naive.
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)


def bound_zero_bid_proof(orders, fixture_logs):
    """Bind genuine native submission data to frozen gate tags, cross-check logs."""
    closes=[order for order in orders if order.get('tag','').split(';',1)[0].endswith(':TIME')]
    if len(closes)!=2:return dict(proven=False,reason='Missing two genuine closing orders')
    ids={int(order['id']) for order in closes}
    metadata=[dict(part.split('=',1) for part in order['tag'].split(';')[1:] if '=' in part) for order in closes]
    fields=('quote_gate_utc','put_quote_fresh','put_current_bar_ask','put_zero_bid',
            'call_quote_fresh','call_current_bar_ask','call_zero_bid')
    if any(any(field not in row for field in fields) for row in metadata):
        return dict(proven=False,reason='Missing actual closing-order decision predicate tags')
    gate={field:metadata[0][field] for field in fields}
    if any(any(row[field]!=gate[field] for field in fields) for row in metadata):
        return dict(proven=False,reason='Two closing orders carry inconsistent gate receipts')
    try:
        if utc_stamp(gate['quote_gate_utc'])!=CLOSE_UTC:return dict(proven=False,reason='Gate receipt is not first eligible Nov29noon')
    except ValueError:return dict(proven=False,reason='Invalid gate timestamp')
    if gate['put_quote_fresh']!='True' or gate['call_quote_fresh']!='True':
        return dict(proven=False,reason='Both closing legs do not have fresh nonFF decision predicates')
    if gate['put_current_bar_ask']!='True' or gate['call_current_bar_ask']!='True':
        return dict(proven=False,reason='Both closing legs lack positive matching ask sides in their current quote bars')
    for diagnostic in fixture_logs:
        value=diagnostic.get('close_submission_utc')
        if not value or value=='None':continue
        try:
            if utc_stamp(value)!=CLOSE_UTC:return dict(proven=False,reason='Available log UTC disagrees with actual gate tags')
            native_ids=diagnostic['native_order_ids']
            if {int(value) for value in native_ids[-2:]}!=ids:return dict(proven=False,reason='Available log closing IDs disagree with actual tickets')
            predicates=diagnostic['close_submission_predicates']
            for side in ('put','call'):
                expected_zero=gate[side+'_zero_bid']=='True'
                if (predicates[side]['fresh_nonff'] is not True or predicates[side]['current_bar_ask'] is not True
                        or predicates[side]['zero_bid_positive_ask']!=expected_zero):
                    return dict(proven=False,reason='Available log predicates disagree with actual gate tags')
        except (KeyError,ValueError,TypeError):return dict(proven=False,reason='Malformed available submission diagnostic')
    proof=[]
    for order in closes:
        data=order.get('orderSubmissionData')
        if not isinstance(data,dict):continue
        try:
            bid=float(data['bidPrice']);ask=float(data['askPrice']);stamp=utc_stamp(order['time'])
        except (KeyError,ValueError,TypeError):continue
        side='put' if order['symbol']['id']==PUT else 'call' if order['symbol']['id']==CALL65 else None
        if side is None or bid!=0 or ask<=0 or stamp!=CLOSE_UTC or gate[side+'_zero_bid']!='True':continue
        proof.append(dict(order_id=order['id'],symbol_id=order['symbol']['id'],submission_utc=order['time'],
            actual_order_zero_bid_positive_ask=True,bound_fresh_nonff_predicate=True,current_bar_ask_present=True,
            proof_source='Actual closing order tags and native orderSubmissionData; available logs cross-checked; quote bar ask-side presence is not an independent exchange-side timestamp'))
    return dict(proven=bool(proof),legs=proof,reason=None if proof else 'Native zero-bid positive-ask submission and bound fresh/nonFF decision do not coincide')


def holding_valuation(residual,raw_holdings):
    """QC's aggregate Holdings is gross; only homogeneous known native signs suffice.

    No per-leg market marks or mixed-position net value can be inferred here.
    """
    result=dict(runtime_holdings_raw=raw_holdings,gross_holdings_abs=None,
        derived_signed_holdings=None,per_leg_marks_derived=False,issue=None,basis=None)
    if raw_holdings is None:
        result['issue']='Missing aggregate account Holdings field';return result
    try:gross=abs(shared.money(raw_holdings))
    except (ValueError,TypeError):
        result['issue']='Unknown/unparseable aggregate Holdings; signed value cannot be derived';return result
    if not math.isfinite(gross) or any(not math.isfinite(float(quantity)) for quantity in residual.values()):
        result['issue']='Nonfinite aggregate Holdings or native residual quantity; signed value cannot be derived';return result
    result['gross_holdings_abs']=gross
    live={key:quantity for key,quantity in residual.items() if abs(quantity)>1e-9}
    if set(live)-{PUT,CALL70,CALL65}:
        result['issue']='Unknown native residual instruments; aggregate signed value cannot be derived';return result
    if not live:
        if gross!=0:
            result['issue']='No actual residual positions but account reports nonzero gross Holdings';return result
        result.update(derived_signed_holdings=0.,basis='Actual native residuals are flat and aggregate Holdings zero');return result
    if all(quantity<0 for quantity in live.values()):
        result.update(derived_signed_holdings=-gross,basis='All actual known option residuals short; aggregate gross value is a liability')
    elif all(quantity>0 for quantity in live.values()):
        result.update(derived_signed_holdings=gross,basis='All actual known option residuals long; aggregate gross value is an asset')
    else:
        result['issue']='Mixed long/short actual residuals; gross aggregate cannot reveal signed net value'
    return result


def audit_fixture(orders,rust_orders,full,variant,gold,fixture_logs):
    fills=execution_rows(orders);rust=execution_rows(rust_orders)
    if execution_signature(fills)!=execution_signature(rust):raise ValueError('Rust/Python genuine fill mismatch')
    rust_by_id={order['id']:order for order in rust_orders}
    for order in orders:
        if order.get('orderSubmissionData')!=rust_by_id[order['id']].get('orderSubmissionData'):
            raise ValueError('Rust/Python genuine order-submission receipts differ')
    count=full.get('statistics',{}).get('Total Orders')
    if count is None or len(orders)!=int(str(count).replace(',','')):raise ValueError('Incomplete native order history')
    issues=[]
    prefix_ok=len(fills)>=4 and economic_signature(fills[:4])==economic_signature(gold)
    if not prefix_ok:issues.append('First four native economic fills differ from original orders759–762')
    if any(order.get('status')!=3 or abs(float(order.get('quantity',0)))!=1 for order in orders):issues.append('Not all native orders completely filled one contract')
    if len(orders)!=len(fills):issues.append('Additional rejected/partial/unfilled native orders exist')
    native_groups={}
    for order in orders:
        manager=order.get('groupOrderManager') or {}
        if order.get('type')!=8 or int(manager.get('id',0))<=0 or manager.get('count')!=2:
            issues.append('Fixture action lacks its genuine two-leg native ComboMarket identity')
        native_groups.setdefault(manager.get('id'),[]).append(order['id'])
    for manager_id,order_ids in native_groups.items():
        if len(order_ids)!=2:issues.append('Incomplete native two-leg action group')
        for order in orders:
            manager=order.get('groupOrderManager') or {}
            if manager.get('id')==manager_id and set(manager.get('orderIds',[]))!=set(order_ids):
                issues.append('Native combo manager members differ from genuine order IDs')
    residual=Counter()
    for fill in fills:residual[fill['symbol_id']]+=fill['quantity']
    residual={key:value for key,value in residual.items() if abs(value)>1e-9}
    fees=sum(fill['fee'] for fill in fills)
    cashflow=sum(-fill['quantity']*fill['qc_price']*fill['multiplier'] for fill in fills)
    runtime=full.get('runtimeStatistics',{})
    for field in ('Fees','Equity','Holdings','Unrealized'):
        if field not in runtime:issues.append('Missing terminal account field '+field)
    if 'Fees' in runtime and abs(abs(shared.money(runtime['Fees']))-fees)>.0051:issues.append('Actual fees disagree with account')
    for diagnostic in fixture_logs:
        if 'initial_cash' in diagnostic and abs(float(diagnostic['initial_cash'])-INITIAL)>1e-8:issues.append('Fixture initial cash differs')
        if 'fees' in diagnostic and abs(float(diagnostic['fees'])-fees)>.0051:issues.append('Fixture diagnostic fees disagree')
        if 'actual_ticket_cashflow' in diagnostic and abs(float(diagnostic['actual_ticket_cashflow'])-cashflow)>.0051:issues.append('Fixture diagnostic cashflow disagrees')
    control_expected=(terminal_status(full)=='failed' and 'Mandatory exit lacked fresh quotes' in str(full.get('error'))
        and len(fills)==4 and residual=={PUT:-1,CALL65:-1} and prefix_ok)
    for diagnostic in fixture_logs:
        counts=diagnostic.get('counts',{})
        expected_time=1 if variant=='wag_buyback' and len(fills)==6 else 0
        for field,expected in (('rolls',1),('TIME',expected_time)):
            if field in counts and int(counts[field])!=expected:issues.append('Available fixture counter differs from genuine fills: '+field)
        if variant=='wag_buyback' and diagnostic.get('closed_at') not in (None,'None','2019-11-29 12:00:00'):
            issues.append('Available fixture closing timestamp differs from first eligible noon')
    valuation=holding_valuation(residual,runtime.get('Holdings'))
    account_reconciles=False
    if valuation['issue']:
        issues.append(valuation['issue'])
    elif 'Equity' in runtime:
        marked_equity=INITIAL+cashflow-fees+valuation['derived_signed_holdings']
        valuation['derived_equity_from_native_cashflow']=marked_equity
        account_reconciles=abs(shared.money(runtime['Equity'])-marked_equity)<=.0051
        if not account_reconciles:issues.append('Native cashflow/derived signed holdings/account mark do not reconcile')
    cycle=None
    proof=dict(proven=False,reason='Control is not a repaired buyback')
    clean=False
    if variant=='wag_buyback':
        if terminal_status(full)!='done':issues.append('Buyback variant did not complete cleanly')
        if len(fills)!=6 or len(orders)!=6:issues.append('Buyback requires exactly six genuine filled orders')
        if residual:issues.append('Buyback left actual residual holdings')
        closes=fills[4:]
        if (len(closes)!=2 or {fill['symbol_id'] for fill in closes}!={PUT,CALL65}
                or any(fill['quantity']!=1 or fill['reason']!='TIME' or datetime.fromisoformat(fill['timestamp'])!=CLOSE_UTC for fill in closes)):
            issues.append('Two actual TIME buybacks did not occur at Nov29noon21DTE')
        if not residual and len(fills)==6:
            cycles=audit_dte(orders)
            if len(cycles)!=1 or cycles[0]['exit_dte']!=21 or cycles[0]['rolls']!=1:issues.append('Native cycle tenor/rolls mismatch')
            else:cycle=cycles[0]
        if 'Holdings' in runtime and shared.money(runtime['Holdings'])!=0:issues.append('Terminal account holdings not zero')
        if 'Unrealized' in runtime and shared.money(runtime['Unrealized'])!=0:issues.append('Terminal unrealized PnL not zero')
        if cycle is not None and abs(cycle['pnl']-(cashflow-fees))>.0051:issues.append('Cycle PnL does not reconcile')
        proof=bound_zero_bid_proof(orders,fixture_logs)
        clean=not issues
    elif variant=='wag_control':
        if not control_expected:issues.append('Strict control did not reproduce expected original failure and residuals')
    else:raise ValueError('Unknown native fixture variant')
    return dict(variant=variant,engineering_only=True,strategy_performance_claim=False,issues=issues,
        orders=len(orders),actual_fills=len(fills),first_four_economic_fills_identical=prefix_ok,
        rust_python_equal=True,residual_native_quantities=residual,fees=fees,
        native_cashflow=cashflow,net_closed_cycle_pnl=cycle['pnl'] if cycle else None,
        ending_account_equity=shared.money(runtime['Equity']) if 'Equity' in runtime else None,
        aggregate_holding_valuation=valuation,native_cashflow_account_reconciles=account_reconciles,
        terminal_account_statistics=runtime,
        actual_control_failure_reproduced=control_expected if variant=='wag_control' else None,
        buyback_execution_account_audit_passed=clean,submission_zero_bid_cause_proof=proof,
        unavailable_optional_runtime_counters=[key for key in ('rolls','TIME','closed_cycles') if key not in runtime],
        fixture_log_receipts=len(fixture_logs),qc_status=full.get('status'),qc_error=full.get('error'))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('campaign',type=Path)
    args=parser.parse_args();campaign=args.campaign.resolve()
    manifest=json.loads((campaign/'manifest.json').read_text())
    if manifest.get('phase')!='basket-wag-regression' or set(manifest['variants'])!={'wag_control','wag_buyback'} or len(manifest['jobs'])!=2:
        raise ValueError('Require exactly one frozen native control/buyback pair')
    if manifest.get('source_failure')!={'project_id':31338456,'backtest_id':SOURCE_BACKTEST}:raise ValueError('Wrong original source failure identity')
    lock=(campaign/'wag_report.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:print('Another native WAG collector owns this campaign');return
    user,token=credentials(ROOT/'data/S001.duckdb')
    snapshots=[];audits=[];issues=[];all_fills=[];gold=original_first_four()
    for name in manifest['jobs']:
        key,config=shared.config_for(name,manifest)
        with storage.connect(f'file:{ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as connection:
            connection.row_factory=storage.Row;saved=connection.execute('SELECT * FROM backtest_queue WHERE name=?',(name,)).fetchone()
        if saved is None:snapshots.append(dict(name=name,status='not_queued_dry_run',completed=False));continue
        row=dict(saved);source=frozen_source(campaign,key,config,row)
        if not row.get('backtest_id'):snapshots.append(dict(name=name,status=row['status'],completed=False));continue
        try:
            response=shared.read_research_backtest(user,token,campaign,name,row);full=response['backtest'];validate_identity(full,row)
            state=terminal_status(full)
            snapshots.append(dict(name=name,project_id=row['project_id'],backtest_id=row['backtest_id'],
                status=full.get('status'),completed=full.get('completed'),progress=full.get('progress'),error=full.get('error')))
            if state is None:continue
            folder=shared.collect_terminal(user,token,campaign,name,row,response)
            orders=json.loads((folder/'orders.json').read_text());rust=json.loads((folder/'orders.rust.json').read_text())
            rust=rust['orders'] if isinstance(rust,dict) else rust
            log=(folder/'cloud.log').read_text() if (folder/'cloud.log').exists() else ''
            fixture_logs=events(log,'WAG_EXIT_FIXTURE')
            audit=audit_fixture(orders,rust,full,key,gold,fixture_logs)
            audit.update(project_id=row['project_id'],backtest_id=row['backtest_id'],frozen_source=source,
                log_collection=json.loads((folder/'log_collection_receipt.json').read_text()))
            frames=dict(executions=execution_rows(orders),fixture_diagnostics=[dict(payload=json.dumps(value)) for value in fixture_logs])
            shared.write_tables(folder/'wag_engineering_report',frames)
            atomic_json(folder/'wag_engineering_report/summary.json',audit)
            all_fills.extend(dict(variant=key,**fill) for fill in execution_rows(orders));audits.append(audit)
        except Exception as exc:issues.append(dict(name=name,error=type(exc).__name__+': '+str(exc),retry_read_only=True,cloud_failure_inferred=False))
    snapshot=dict(utc=datetime.now(timezone.utc).isoformat(),jobs=snapshots,collection_issues=issues)
    atomic_json(campaign/'wag_cloud_progress.json',snapshot)
    print(json.dumps(snapshot,indent=2),flush=True)
    if len(audits)!=2 or issues:return
    by={audit['variant']:audit for audit in audits};control=by['wag_control'];buyback=by['wag_buyback']
    isolated=isolated_pair_sources(campaign)
    proved=(isolated and control['actual_control_failure_reproduced'] and not control['issues']
        and buyback['buyback_execution_account_audit_passed'] and buyback['submission_zero_bid_cause_proof']['proven'])
    summary=dict(status='cause_reproduced_and_native_buyback_verified' if proved else 'evidence_collected_cause_unproven',
        cause_proven=bool(proved),engineering_only=True,strategy_performance_claim=False,
        pair_source_difference_only_buyback_config=isolated,variants=audits,
        limitations=['Native short exact-position fixture only; no Calmar or broad strategy performance inference.',
            'Actual closing submission data and bound fresh/nonFF gate tags are required; available log predicates are cross-checked, and missing logs are never fabricated.',
            'A clean repaired close alone does not prove the control failure cause.'])
    out=campaign/'wag_engineering_report';shared.write_tables(out,dict(executions=all_fills))
    atomic_json(out/'summary.json',summary)
    receipts={str(path.relative_to(campaign)):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in campaign.rglob('*') if path.is_file() and path.name not in ('evidence_checksums.json','wag_report.lock')}
    atomic_json(out/'evidence_checksums.json',receipts)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
