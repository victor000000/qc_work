"""Read-only paired native LVS execution audit; never a strategy performance test.

Ordinary Limit/Market attempts and cancellation/partial-fill events stay distinct.
No synthetic combo groups, assumed fills, price corrections or cloud mutations.
"""
import argparse
import ast
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
import fcntl
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent;STRATEGY=HERE.parent;ROOT=STRATEGY.parents[1]
sys.path[:0]=[str(STRATEGY),str(ROOT/'scripts')]
import qc_storage as storage
from qc_api_check import credentials
from resume_basket import read_existing_backtest,validate_identity,terminal_status,atomic_json
from basket_report import events
spec=importlib.util.spec_from_file_location('_lvs_shared_report',HERE/'report.py')
shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
INITIAL=57718.42
SOURCE_ID='8a6d193829c51b26976d40707c081eb5'
SOURCE=STRATEGY/'results/strangle_basket-calmar_20261019_123602/SSTRANGLE_20261019_123602_cap20_stop1'
PUT='LVS 3033TD1OREOZQ|LVS T4J5S7AT6WRP'
CALL='LVS W3ZT7JJZY6RQ|LVS T4J5S7AT6WRP'
SID_SET={PUT,CALL}
OPEN=datetime(2015,7,28,16,tzinfo=timezone.utc)
TRIGGER=datetime(2015,8,19,13,31,tzinfo=timezone.utc)
MANDATORY_NOON=datetime(2015,8,28,16,tzinfo=timezone.utc)
TERMINAL_STATUSES={3,5,7}


def utc(value):
    if isinstance(value,(int,float)):return datetime.fromtimestamp(value,timezone.utc)
    result=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def tag_fields(order):
    return dict(part.split('=',1) for part in order.get('tag','').split(';')[1:] if '=' in part)


def native_records(orders):
    """Retain every event, including zero-quantity canceled or fee-bearing events."""
    attempts=[];native_events=[];issues=[];seen_orders=set();seen_events=set()
    for order in sorted(orders,key=lambda row:row['id']):
        oid=int(order['id']);sid=order['symbol']['id'];meta=tag_fields(order)
        if oid in seen_orders:issues.append('Duplicate native order ID '+str(oid))
        seen_orders.add(oid)
        multiplier=float(meta.get('multiplier',100))
        if multiplier!=100:issues.append('Unexpected native contract multiplier '+str(oid))
        attempts.append(dict(order_id=oid,native_sid=sid,quantity=float(order['quantity']),
            type=int(order['type']),status=int(order['status']),utc=utc(order['time']).isoformat(),
            tag=order.get('tag',''),attempt=meta.get('attempt','opening' if ':OPEN' in order.get('tag','') else 'unidentified'),
            limit_price=order.get('limitPrice'),submission_data=json.dumps(order.get('orderSubmissionData'),sort_keys=True),
            native_group_id=(order.get('groupOrderManager') or {}).get('id'),multiplier=multiplier))
        for event in order.get('events',[]):
            eid=str(event['id']);key=(oid,eid)
            if key in seen_events:issues.append('Duplicate native order-event identity '+str(key))
            seen_events.add(key)
            quantity=float(event.get('fillQuantity',0))
            raw_price=event.get('fillPrice');price=float(raw_price) if raw_price is not None else None
            # Rust serializes absent optional submission/cancel fee fields as
            # null; Python leaves them absent. Preserve that absence as None,
            # rather than inventing a fee or confusing it with a filled event.
            raw_fee=event.get('orderFeeAmount');fee=float(raw_fee) if raw_fee is not None else None
            if quantity and fee is None:issues.append('Missing actual fee amount on a genuine fill '+eid)
            if quantity and price is None:issues.append('Missing actual price on a genuine fill '+eid)
            finite_fields=tuple(value for value in (quantity,price,fee) if value is not None)
            if any(not math.isfinite(value) for value in finite_fields):issues.append('Nonfinite native event economic field '+eid)
            if quantity and event.get('fillPriceCurrency')!='USD':issues.append('NonUSD fill '+eid)
            if fee and event.get('orderFeeCurrency')!='USD':issues.append('NonUSD fee '+eid)
            if event.get('isAssignment'):issues.append('Assignment requires separate underlying accounting '+eid)
            native_events.append(dict(order_id=oid,event_id=eid,native_sid=sid,
                utc=utc(event['time']).isoformat(),quantity=quantity,price=price,fee=fee,multiplier=multiplier,
                status=str(event.get('status','')).lower().replace('_','').replace(' ','')))
    return attempts,native_events,issues


def gold_orders():
    source=json.loads((SOURCE/'backtest.json').read_text())['backtest']
    if source['backtestId']!=SOURCE_ID or str(source['projectId'])!='31338456':raise ValueError('Wrong original LVS source identity')
    rows=json.loads((SOURCE/'orders.json').read_text())
    rows=[row for row in rows if row['id'] in (257,258,263,264)]
    if [row['id'] for row in rows]!=[257,258,263,264]:raise ValueError('Original genuine LVS orders missing')
    _,records,issues=native_records(rows)
    if issues:raise ValueError('Original LVS evidence invalid: '+str(issues))
    fills=[event for event in records if event['quantity']]
    if [(event['native_sid'],event['quantity'],event['price']) for event in fills]!=[(PUT,-2,.61),(CALL,-2,.62),(PUT,2,62.),(CALL,2,.11)]:
        raise ValueError('Original native LVS economics differ from specified control')
    return rows


def economics(records):
    fields=('native_sid','utc','quantity','price','fee','multiplier')
    return [{field:event[field] for field in fields} for event in records if event['quantity']]


def native_limit_price(bid,tick):
    b=Decimal(str(bid));t=Decimal(str(tick))
    if not b.is_finite() or not t.is_finite() or b<=0 or t<=0:raise ValueError('Invalid actual submission bid/tick')
    return float(((b+2*t)/t).to_integral_value(rounding=ROUND_CEILING)*t)


def instruction_receipts(receipts):
    """Bind surviving fixture instruction receipts by actual native order ID."""
    instructions={};issues=[]
    for receipt in receipts:
        values=receipt.get('limit_order_parameters')
        if not isinstance(values,dict):continue
        for oid,value in values.items():
            key=str(oid)
            if not isinstance(value,dict):issues.append('Malformed native limit instruction receipt');continue
            if key in instructions and instructions[key]!=value:
                issues.append('Repeated native limit instruction receipts disagree for order '+key)
            else:instructions[key]=value
    return instructions,issues


def attempt_role(order,instructions):
    role=tag_fields(order).get('attempt')
    if role:return role,'native_final_order_tag'
    if ':OPEN' in order.get('tag','').split(';')[0]:return 'opening','native_final_order_tag'
    # QC replaces a canceled ticket's final tag with its cancel-request message.
    # Do not rewrite that tag. Require its genuine Limit type/canceled status and
    # exact native-ID-bound instruction receipt to recover only its policy role.
    if order['type']==1 and order['status']==5 and str(order['id']) in instructions:
        return 'limit','native_canceled_limit_type_plus_ID_bound_instruction_receipt'
    return 'unidentified','no_valid_role_receipt'


def audit_policy(orders,records,instructions=None):
    instructions=instructions or {}
    roles={order['id']:attempt_role(order,instructions) for order in orders}
    issues=[];limits=[order for order in orders if roles[order['id']][0]=='limit']
    fallback=[order for order in orders if roles[order['id']][0]=='market_residual']
    if len(limits)!=2 or {order['symbol']['id'] for order in limits}!=SID_SET:
        issues.append('Expected two individual native limits for the two original short legs')
    early_invalid=[utc(event['utc']) for event in records if event['order_id'] in {order['id'] for order in limits}
        and event['status'] in ('invalid','7') and utc(event['utc'])<TRIGGER+timedelta(minutes=2)]
    cancel_start=min(early_invalid) if early_invalid else TRIGGER+timedelta(minutes=2)
    for order in limits:
        oid=order['id'];meta=tag_fields(order)
        terminal=[event for event in records if event['order_id']==oid and event['status'] in ('filled','canceled','cancelled','invalid','3','5','7')]
        if order['status'] not in TERMINAL_STATUSES or not terminal:
            issues.append('Native LIMIT attempt lacks a definitive terminal event, even without fallback')
        elif max(utc(event['utc']) for event in terminal)>cancel_start+timedelta(minutes=2):
            issues.append('Native LIMIT completion/cancel exceeded declared two-minute timeout plus two-minute cancel window')
        if order['type']!=1 or float(order['quantity'])!=2 or order.get('groupOrderManager'):
            issues.append('Limit attempt is not an ordinary two-lot native Limit ticket')
        if utc(order['time'])!=TRIGGER:issues.append('Native limit submission changed original STOP trigger time')
        try:
            receipt=instructions.get(str(oid))
            raw_tick=meta.get('minimum_price_tick')
            if raw_tick is None and receipt is not None:raw_tick=receipt.get('minimum_price_tick')
            if raw_tick is None:raise ValueError('Missing actual tick metadata')
            tick=float(raw_tick);submission=order['orderSubmissionData']
            if receipt is not None and (receipt.get('native_sid')!=order['symbol']['id']
                    or abs(float(receipt['limit_price'])-float(order['limitPrice']))>1e-10
                    or abs(float(receipt['minimum_price_tick'])-tick)>1e-10):
                issues.append('ID-bound limit instruction receipt differs from actual native Limit ticket')
            bid=float(submission['bidPrice']);ask=float(submission['askPrice'])
            if not all(math.isfinite(value) for value in (bid,ask)) or ask<bid:
                raise ValueError('Malformed actual native submission quote receipt')
            expected=native_limit_price(bid,tick)
            if abs(float(order['limitPrice'])-expected)>1e-10:issues.append('Native limit instruction does not equal actual bid+two ticks rounded up')
        except (KeyError,ValueError,TypeError):issues.append('Missing actual native limit price/tick/submission receipt')
        for event in records:
            if event['order_id']==oid and event['quantity'] and event['price'] is not None and event['price']>float(order.get('limitPrice',-1))+1e-10:
                issues.append('Native buy fill exceeded its actual submitted limit')
    ordered_fallback=sorted(fallback,key=lambda order:(utc(order['time']),order['id']))
    for order in ordered_fallback:
        if order['type']!=0 or order.get('groupOrderManager'):issues.append('Residual fallback is not an ordinary native Market ticket')
        submission=utc(order['time'])
        if submission<cancel_start:issues.append('Residual market submitted before timeout or definitive early-invalid trigger')
        if submission>cancel_start+timedelta(minutes=2):issues.append('Residual market submission exceeded declared cancellation window')
        executions=[event for event in records if event['order_id']==order['id'] and event['quantity']]
        if any(utc(event['utc'])>submission+timedelta(minutes=5) for event in executions):
            issues.append('Residual market fill exceeded declared five-minute completion deadline')
        for limit in limits:
            terminal=[event for event in records if event['order_id']==limit['id'] and event['status'] in ('filled','canceled','cancelled','invalid','3','5','7')]
            if limit['status'] not in TERMINAL_STATUSES or not terminal or max(utc(event['utc']) for event in terminal)>submission:
                issues.append('Fallback lacks definitive native limit-terminal/cancel-event barrier')
        sid=order['symbol']['id']
        prior=[event for event in records if event['native_sid']==sid and
            (utc(event['utc'])<submission or (utc(event['utc'])==submission and event['order_id']<order['id']))]
        actual_residual=-sum(event['quantity'] for event in prior)
        if actual_residual<=0 or abs(float(order['quantity'])-actual_residual)>1e-9:
            issues.append('Fallback quantity differs from actual remaining native short quantity')
    return dict(issues=issues,role_receipts=[dict(order_id=order['id'],role=roles[order['id']][0],
            source=roles[order['id']][1],raw_final_tag=order.get('tag','')) for order in limits],
        limit_fill_event_count=sum(bool(event['quantity']) for event in records if event['order_id'] in {order['id'] for order in limits}),
        limit_order_ids=[order['id'] for order in limits],
        fallback_order_ids=[order['id'] for order in fallback],
        zero_fill_canceled_order_ids=[order['id'] for order in limits if order['status']==5 and
            not any(event['order_id']==order['id'] and event['quantity'] for event in records)],
        partial_canceled_order_ids=[order['id'] for order in limits if order['status']==5 and
            0<sum(event['quantity'] for event in records if event['order_id']==order['id'])<float(order['quantity'])],
        observed_early_limit_rejection=bool(early_invalid),
        forced_margin_or_cancel_race_robustness_certified=False)


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
    if set(live)-SID_SET:
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


def audit_attempt(orders,rust_orders,full,limit_exit,gold,receipts):
    attempts,records,issues=native_records(orders)
    rust_attempts,rust_records,rust_issues=native_records(rust_orders)
    if attempts!=rust_attempts or records!=rust_records:issues.append('Python/Rust native order/event receipts differ')
    issues.extend(rust_issues)
    declared=full.get('statistics',{}).get('Total Orders')
    if declared is None or len(orders)!=int(str(declared).replace(',','')):issues.append('Complete declared native order history unavailable')
    fills=[event for event in records if event['quantity']]
    if any(event['quantity']>0 and not TRIGGER<=utc(event['utc'])<MANDATORY_NOON for event in fills):
        issues.append('Actual closing fill occurred outside original STOP/mandatory21DTE window')
    instructions,instruction_issues=instruction_receipts(receipts);issues.extend(instruction_issues)
    roles={order['id']:attempt_role(order,instructions)[0] for order in orders}
    allowed={'limit','market_residual'} if limit_exit else {'market_control'}
    if any(':OPEN' not in order.get('tag','').split(';')[0] and roles[order['id']] not in allowed for order in orders):
        issues.append('Unidentified/default-broker native closing attempt retained; optional policy result unqualified')
    _,gold_events,_=native_records(gold);gold_fills=[event for event in gold_events if event['quantity']]
    original_open=economics(fills[:2])==economics(gold_fills[:2]) and len(fills)>=2
    if not original_open:issues.append('Original two native opening fills differ')
    opening=[order for order in orders if ':OPEN' in order.get('tag','').split(';')[0]]
    if len(opening)!=2 or any(order['type']!=8 or float(order['quantity'])!=-2 or utc(order['time'])!=OPEN for order in opening):
        issues.append('Opening native two-lot ComboMarket identity/time changed')
    if {order['symbol']['id'] for order in orders}-SID_SET:issues.append('Foreign native instruments in isolated LVS execution')
    holdings=Counter();fees=sum(event['fee'] for event in records if event['fee'] is not None)
    cashflow_supported=all(event['native_sid'] in SID_SET and event['multiplier']==100 and event['price'] is not None for event in records if event['quantity'])
    cashflow=sum(-event['quantity']*event['price']*event['multiplier'] for event in records if event['quantity']) if cashflow_supported else None
    for event in sorted(records,key=lambda value:(utc(value['utc']),value['order_id'],value['event_id'])):
        holdings[event['native_sid']]+=event['quantity']
        if holdings[event['native_sid']]>1e-9:issues.append('Native event path overclosed into a long position')
    residual={key:value for key,value in holdings.items() if abs(value)>1e-9}
    for order in orders:
        quantity=sum(event['quantity'] for event in records if event['order_id']==order['id'])
        requested=float(order['quantity'])
        if quantity and (quantity*requested<0 or abs(quantity)>abs(requested)+1e-9):issues.append('Native cumulative fill exceeds/mismatches its requested quantity')
        if order['status']==3 and abs(quantity-requested)>1e-9:issues.append('Filled native status disagrees with actual cumulative quantity')
        if order['status'] not in TERMINAL_STATUSES:issues.append('Native order still live at observed fixture end')
    runtime=full.get('runtimeStatistics',{});ending=None
    for field in ('Equity','Fees','Holdings','Unrealized'):
        if field not in runtime:issues.append('Missing actual terminal account field '+field)
    if 'Equity' in runtime:ending=shared.money(runtime['Equity'])
    if 'Fees' in runtime and abs(abs(shared.money(runtime['Fees']))-fees)>.0051:issues.append('Actual native event fees/account do not reconcile')
    valuation=holding_valuation(residual,runtime.get('Holdings'))
    account_reconciles=False
    if valuation['issue']:
        issues.append(valuation['issue'])
    elif cashflow is not None and ending is not None:
        valuation['derived_equity_from_native_cashflow']=INITIAL+cashflow-fees+valuation['derived_signed_holdings']
        account_reconciles=abs(ending-valuation['derived_equity_from_native_cashflow'])<=.0051
        if not account_reconciles:issues.append('Actual event cashflow/derived signed holdings/account equity do not reconcile')
    for receipt in receipts:
        for key,expected in (('initial_cash',INITIAL),('actual_fees',fees),('actual_cashflow',cashflow)):
            if expected is not None and receipt.get(key) is not None and abs(float(receipt[key])-expected)>.0051:issues.append('Available fixture receipt disagrees with native economics: '+key)
        if 'native_order_ids' in receipt and set(map(int,receipt['native_order_ids']))!={order['id'] for order in orders}:issues.append('Available fixture ticket IDs differ from genuine orders')
        if receipt.get('trigger_at') not in (None,'None','2015-08-19 09:31:00'):issues.append('Available trigger receipt differs from original STOP time')
        if receipt.get('default_margin_overlap'):issues.append('Default forced-margin overlap actually occurred; isolated policy result unqualified')
        if isinstance(receipt.get('residual_native'),dict):
            actual={key:float(value) for key,value in receipt['residual_native'].items() if abs(float(value))>1e-9}
            if actual!=residual:issues.append('Available fixture residual receipt disagrees with native fills')
        if isinstance(receipt.get('actual_fill_events'),list):
            projected=[]
            for event in receipt['actual_fill_events']:
                projected.append(dict(order_id=int(event['order_id']),native_sid=event['native_sid'],utc=utc(event['utc']).isoformat(),
                    quantity=float(event['quantity']),price=float(event['price']),fee=float(event['fee'])))
            expected=[{key:event[key] for key in ('order_id','native_sid','utc','quantity','price','fee')} for event in fills]
            if sorted(projected,key=lambda event:(event['utc'],event['order_id']))!=sorted(expected,key=lambda event:(event['utc'],event['order_id'])):
                issues.append('Available native fill-event diagnostic differs from actual API events')
        if isinstance(receipt.get('native_attempt_status'),dict):
            expected_status={0:'new',1:'submitted',2:'partiallyfilled',3:'filled',5:'canceled',6:'cancelpending',7:'invalid'}
            status_by_id={str(order['id']):expected_status.get(order['status'],str(order['status'])) for order in orders}
            declared={str(oid):str(status).lower().replace('_','').replace(' ','').replace('cancelled','canceled') for oid,status in receipt['native_attempt_status'].items()}
            if declared!=status_by_id:issues.append('Available actual native attempt-status receipt disagrees with API orders')
        if isinstance(receipt.get('cancel_requested_ids'),list):
            declared={int(oid) for oid in receipt['cancel_requested_ids']}
            limit_ids={order['id'] for order in orders if roles[order['id']]=='limit'}
            canceled={order['id'] for order in orders if order['status']==5}
            if not declared<=limit_ids or not canceled<=declared:
                issues.append('Available cancellation-request receipt disagrees with native limit attempts')
        if isinstance(receipt.get('actual_residual_fallback'),dict):
            requested=Counter()
            for order in orders:
                if tag_fields(order).get('attempt')=='market_residual':requested[order['symbol']['id']]+=float(order['quantity'])
            if {key:float(value) for key,value in receipt['actual_residual_fallback'].items()}!=dict(requested):
                issues.append('Available fallback receipt differs from actual residual Market instructions')
        if isinstance(receipt.get('limit_order_parameters'),dict):
            actual_limits={str(order['id']):order for order in orders if roles[order['id']]=='limit'}
            if set(receipt['limit_order_parameters'])!=set(actual_limits):issues.append('Available limit instruction receipt has missing/extra native IDs')
            for oid,instruction in receipt['limit_order_parameters'].items():
                order=actual_limits.get(oid)
                if order is None:continue
                if (instruction.get('native_sid')!=order['symbol']['id'] or abs(float(instruction['limit_price'])-float(order['limitPrice']))>1e-10
                        or (tag_fields(order).get('minimum_price_tick') is not None and abs(float(instruction['minimum_price_tick'])-float(tag_fields(order)['minimum_price_tick']))>1e-10)):
                    issues.append('Available actual limit instruction/tick differs from genuine order')
    policy=audit_policy(orders,records,instructions) if limit_exit else None
    if policy:issues.extend(policy['issues'])
    control_reproduced=(not limit_exit and economics(fills)==economics(gold_fills) and len(orders)==4 and
        abs(fees-4.9)<1e-9 and cashflow is not None and abs(cashflow-fees+12180.9)<1e-8 and not residual)
    if not limit_exit and not control_reproduced:issues.append('Market control did not reproduce original native62/.11 prices and net loss')
    if not limit_exit:
        closes=[order for order in orders if order not in opening]
        if len(closes)!=2 or any(order['type']!=8 or utc(order['time'])!=TRIGGER for order in closes):issues.append('Market control exit is not original native ComboMarket at09:31')
    if residual:issues.append('Actual native residual exposure remains')
    if terminal_status(full)!='done':issues.append('Actual cloud fixture did not complete cleanly')
    if 'Unrealized' in runtime and not residual and shared.money(runtime['Unrealized'])!=0:issues.append('Flat native positions have nonzero account unrealized PnL')
    if 'Holdings' in runtime and not residual and shared.money(runtime['Holdings'])!=0:issues.append('Flat native positions have nonzero account holdings')
    closing_events=fills[2:] if original_open else []
    closing_quantities=Counter()
    for event in closing_events:closing_quantities[event['native_sid']]+=event['quantity']
    fee_total_complete=not any(event['quantity'] and event['fee'] is None for event in records)
    completed_native_cycle=bool(original_open and len(opening)==2 and cashflow_supported and fee_total_complete and not residual
        and closing_events and all(event['quantity']>0 and utc(event['utc'])>OPEN for event in closing_events)
        and dict(closing_quantities)=={PUT:2,CALL:2}
        and all(order['status'] in TERMINAL_STATUSES for order in orders))
    return dict(variant='bounded_limit' if limit_exit else 'market_control',engineering_only=True,
        strategy_performance_claim=False,issues=list(dict.fromkeys(issues)),native_orders=len(orders),actual_fill_events=len(fills),
        all_native_events=len(records),original_opening_economics_identical=original_open,python_rust_equal=attempts==rust_attempts and records==rust_records,
        actual_fees=fees,actual_cashflow=cashflow,cashflow_model_supported=cashflow_supported,
        actual_fee_total_complete=fee_total_complete,
        completed_native_cycle_established=completed_native_cycle,
        native_single_cycle_pnl=cashflow-fees if completed_native_cycle else None,
        cycle_pnl_unavailable_reason=None if completed_native_cycle else 'No verified original opening followed by genuine complete flat native closure; observed cashflow is not a closed-cycle PnL',
        ending_account_equity=ending,residual_native_quantities=residual,market_control_reproduced=control_reproduced,
        aggregate_holding_valuation=valuation,native_cashflow_account_reconciles=account_reconciles,terminal_account_statistics=runtime,
        native_execution_account_audit_passed=not issues,limit_policy=policy,fixture_receipts=len(receipts),
        no_loss_improvement_guaranteed=True,forced_margin_or_cancel_race_robustness_certified=False,
        qc_status=full.get('status'),qc_error=full.get('error'))


def source_receipt(campaign,key,config,row):
    path=campaign/(key+'.py');source=path.read_text()
    if row['code']!=source:raise ValueError('Frozen LVS main differs from actual queued source')
    tree=ast.parse(source)
    configs=[ast.literal_eval(node.value) for node in ast.walk(tree) if isinstance(node,ast.Assign) and
        any(isinstance(target,ast.Name) and target.id=='CONFIG' for target in node.targets)]
    if configs!=[config] or not isinstance(config.get('limit_exit'),bool):raise ValueError('Fixture literal CONFIG differs from manifest')
    helpers=json.loads((campaign/'extra_files.json').read_text()) if (campaign/'extra_files.json').exists() else {}
    actual=json.loads(row['extra_files']) if isinstance(row.get('extra_files'),str) else row.get('extra_files') or {}
    if helpers!=actual:raise ValueError('Actual queued LVS helper source differs')
    if any(needle in source for needle in ('set_fill_model(', 'set_buying_power_model(', 'set_margin_call_model(')):
        raise ValueError('Fixture changed default fill/margin models')
    if 'AccountType.MARGIN' not in source or 'BrokerageName.INTERACTIVE_BROKERS_BROKERAGE' not in source:raise ValueError('Default IBKR margin-account setup missing')
    return dict(main_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),rust_content_hash=row['code_hash'],
        literal_config_verified=True,default_models_preserved_in_frozen_source=True)


def isolated_pair_sources(campaign,keys):
    normalized=[]
    for key in keys:
        tree=ast.parse((campaign/(key+'.py')).read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='CONFIG' for target in node.targets):
                value=ast.literal_eval(node.value);value['limit_exit']=False
                node.value=ast.parse(repr(value),mode='eval').body
        normalized.append(ast.dump(tree,include_attributes=False))
    return len(normalized)==2 and normalized[0]==normalized[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('campaign',type=Path)
    args=parser.parse_args();campaign=args.campaign.resolve();manifest=json.loads((campaign/'manifest.json').read_text())
    if manifest['phase']!='basket-lvs-regression' or len(manifest['jobs'])!=2 or len(manifest['variants'])!=2:raise ValueError('Require one frozen native LVS pair')
    if {config.get('limit_exit') for config in manifest['variants'].values()}!={False,True}:raise ValueError('Require one market control and one bounded-limit variant')
    lock=(campaign/'lvs_report.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:print('Another native LVS collector owns this campaign');return
    user,token=credentials(ROOT/'data/S001.duckdb');gold=gold_orders()
    snapshots=[];audits=[];issues=[];combined_attempts=[];combined_events=[]
    for name in manifest['jobs']:
        key,config=shared.config_for(name,manifest)
        with storage.connect(f'file:{ROOT}/data/SSTRANGLE.duckdb?mode=ro',uri=True) as connection:
            connection.row_factory=storage.Row;saved=connection.execute('SELECT * FROM backtest_queue WHERE name=?',(name,)).fetchone()
        if saved is None:snapshots.append(dict(name=name,status='not_queued_dry_run',completed=False));continue
        row=dict(saved);proof=source_receipt(campaign,key,config,row)
        if not row.get('backtest_id'):snapshots.append(dict(name=name,status=row['status'],completed=False));continue
        try:
            response=shared.read_research_backtest(user,token,campaign,name,row);full=response['backtest'];validate_identity(full,row)
            state=terminal_status(full)
            snapshots.append(dict(name=name,project_id=row['project_id'],backtest_id=row['backtest_id'],
                status=full.get('status'),completed=full.get('completed'),progress=full.get('progress'),error=full.get('error')))
            if state is None:continue
            folder=shared.collect_terminal(user,token,campaign,name,row,response)
            orders=json.loads((folder/'orders.json').read_text());rust=json.loads((folder/'orders.rust.json').read_text());rust=rust['orders'] if isinstance(rust,dict) else rust
            attempts,records,parse_issues=native_records(orders)
            log=(folder/'cloud.log').read_text() if (folder/'cloud.log').exists() else ''
            receipts=events(log,'LVS_EXIT_RECEIPT')
            out=folder/'lvs_engineering_report'
            # Raw native JSON tables persist even for failures/partials and unsupported paths.
            shared.write_tables(out,dict(native_attempts=attempts,native_events=records,
                raw_native_orders=[dict(order_id=order['id'],payload=json.dumps(order)) for order in orders],
                fixture_receipts=[dict(payload=json.dumps(receipt)) for receipt in receipts]))
            audit=audit_attempt(orders,rust,full,config['limit_exit'],gold,receipts)
            audit.update(name=name,project_id=row['project_id'],backtest_id=row['backtest_id'],frozen_source=proof,
                log_collection=json.loads((folder/'log_collection_receipt.json').read_text()))
            atomic_json(out/'summary.json',audit);audits.append(audit)
            combined_attempts.extend(dict(variant=key,**attempt) for attempt in attempts)
            combined_events.extend(dict(variant=key,**event) for event in records)
        except Exception as exc:issues.append(dict(name=name,error=type(exc).__name__+': '+str(exc),retry_read_only=True,cloud_failure_inferred=False))
    snapshot=dict(utc=datetime.now(timezone.utc).isoformat(),jobs=snapshots,collection_issues=issues)
    atomic_json(campaign/'lvs_cloud_progress.json',snapshot)
    with (campaign/'lvs_cloud_progress_history.jsonl').open('a') as history:history.write(json.dumps(snapshot)+'\n')
    print(json.dumps(snapshot,indent=2),flush=True)
    if len(audits)!=2 or issues:return
    control=next(audit for audit in audits if audit['variant']=='market_control');limited=next(audit for audit in audits if audit['variant']=='bounded_limit')
    isolated=isolated_pair_sources(campaign,list(manifest['variants']))
    valid=isolated and control['native_execution_account_audit_passed'] and control['market_control_reproduced'] and limited['native_execution_account_audit_passed']
    limit_key=next(key for key,config in manifest['variants'].items() if config['limit_exit'])
    fallback_ids=set((limited.get('limit_policy') or {}).get('fallback_order_ids',[]))
    comparison=dict(control_closed_cycle_pnl=control['native_single_cycle_pnl'],
        bounded_policy_closed_cycle_pnl=limited['native_single_cycle_pnl'],
        actual_closed_cycle_pnl_difference=(limited['native_single_cycle_pnl']-control['native_single_cycle_pnl'])
            if limited['native_single_cycle_pnl'] is not None and control['native_single_cycle_pnl'] is not None else None,
        control_fees=control['actual_fees'],bounded_policy_fees=limited['actual_fees'],
        control_ending_equity=control['ending_account_equity'],bounded_policy_ending_equity=limited['ending_account_equity'],
        actual_limit_fill_events=(limited.get('limit_policy') or {}).get('limit_fill_event_count'),
        actual_zero_fill_canceled_limit_ids=(limited.get('limit_policy') or {}).get('zero_fill_canceled_order_ids'),
        actual_residual_market_fills=[event for event in combined_events if event['variant']==limit_key
            and event['order_id'] in fallback_ids and event['quantity']],
        scope='One isolated native execution fixture; no portfolio or strategy-performance extrapolation')
    summary=dict(status='native_pair_account_audited' if valid else 'all_native_attempt_evidence_retained_unqualified',
        engineering_pair_verified=valid,pair_source_difference_only_limit_config=isolated,comparison=comparison,engineering_only=True,strategy_performance_claim=False,
        no_loss_improvement_guaranteed=True,forced_margin_or_cancel_race_robustness_certified=False,variants=audits,
        limitations=['Isolated LVS initialcash57718.42 excludes simultaneous ZC; no broad-portfolio equivalence or Calmar claim.',
            'A successful native close does not certify forced-margin/cancel-race safety.',
            'Actual canceled and partial native orders are retained; no synthetic combo groups or assumed limit fills.',
            'A bounded limit can fail and actual residual market buybacks can pay the original uncompetitive offer.'])
    out=campaign/'lvs_engineering_report';shared.write_tables(out,dict(native_attempts=combined_attempts,native_events=combined_events))
    atomic_json(out/'summary.json',summary)
    checksums={str(path.relative_to(campaign)):hashlib.sha256(path.read_bytes()).hexdigest() for path in campaign.rglob('*')
        if path.is_file() and path.name not in ('evidence_checksums.json','lvs_report.lock')}
    atomic_json(out/'evidence_checksums.json',checksums);print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
