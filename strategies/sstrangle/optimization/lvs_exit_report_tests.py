from copy import deepcopy
from datetime import timedelta
import importlib.util
from pathlib import Path
import pytest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('lvs_exit_report',HERE/'lvs_exit_report.py')
report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)


def base_orders():
    rows=deepcopy(report.gold_orders())
    for index,row in enumerate(rows,1):
        row['id']=index;row['tag']='LVS_FIXTURE:'+('OPEN' if index<=2 else 'STOP')+';multiplier=100'
        if index>2:row['tag']+=';attempt=market_control'
        row['groupOrderManager']['id']=1 if index<=2 else 2
        row['groupOrderManager']['orderIds']=[1,2] if index<=2 else [3,4]
        for j,event in enumerate(row['events'],1):event.update(id=f'fixture-{index}-{j}',orderId=index)
    return rows


def native_event(oid,index,time,quantity=0,price=0,fee=0,status='submitted'):
    return dict(id=f'fixture-{oid}-{index}',orderId=oid,time=time.timestamp(),fillQuantity=quantity,
        fillPrice=price,orderFeeAmount=fee,fillPriceCurrency='USD',orderFeeCurrency='USD',status=status,isAssignment=False)


def limit_orders(mode='filled'):
    rows=base_orders()[:2];templates=base_orders()[2:]
    for index,source,price,bid in [(3,templates[0],.63,.61),(4,templates[1],.08,.06)]:
        row=deepcopy(source);row.update(id=index,type=1,status=3,limitPrice=price,groupOrderManager=None)
        row['tag']='LVS_FIXTURE:STOP;attempt=limit;exit_intent=1;multiplier=100;minimum_price_tick=.01'
        row['orderSubmissionData']['bidPrice']=bid
        row['events']=[native_event(index,1,report.TRIGGER)]
        if mode=='canceled':
            row['status']=5;row['events'].append(native_event(index,2,report.TRIGGER+timedelta(minutes=2),status='canceled'))
        elif mode=='partial' and index==3:
            row['status']=5
            row['events'] += [native_event(index,2,report.TRIGGER+timedelta(minutes=1),1,price,1,'partiallyFilled'),
                native_event(index,3,report.TRIGGER+timedelta(minutes=2),status='canceled')]
        else:row['events'].append(native_event(index,2,report.TRIGGER+timedelta(minutes=1),2,price,1.3 if index==3 else 1,'filled'))
        rows.append(row)
    if mode in ('canceled','partial'):
        for index,template,quantity,price in ([(5,templates[0],1,62.)] if mode=='partial' else [(5,templates[0],2,62.),(6,templates[1],2,.11)]):
            row=deepcopy(template);time=report.TRIGGER+timedelta(minutes=2)
            row.update(id=index,type=0,status=3,quantity=quantity,groupOrderManager=None,time=time.isoformat())
            row['tag']='LVS_FIXTURE:STOP;attempt=market_residual;exit_intent=1;multiplier=100'
            row['events']=[native_event(index,1,time),native_event(index,2,time,quantity,price,1,'filled')]
            rows.append(row)
    return rows


def account(rows,failed=False):
    _,events,_=report.native_records(rows)
    fees=sum(event['fee'] for event in events if event['fee'] is not None);cash=sum(-event['quantity']*event['price']*event['multiplier'] for event in events if event['quantity'])
    return dict(completed=True,status='Runtime Error' if failed else 'Completed',error='execution failed' if failed else None,
        statistics={'Total Orders':str(len(rows))},runtimeStatistics={
            'Equity':f'${report.INITIAL+cash-fees:.2f}','Fees':f'${fees:.2f}','Holdings':'$0.00','Unrealized':'$0.00'})


def test_original_control_exact_native_economics_fees_and_isolated_cash():
    rows=base_orders();actual=report.audit_attempt(rows,deepcopy(rows),account(rows),False,report.gold_orders(),[])
    assert actual['issues']==[] and actual['market_control_reproduced']
    assert actual['actual_fees']==pytest.approx(4.9)
    assert actual['native_single_cycle_pnl']==pytest.approx(-12180.9)
    assert actual['ending_account_equity']==pytest.approx(45537.52)
    assert not actual['strategy_performance_claim']


def test_real_native_limits_are_accounted_without_fake_combo_groups():
    rows=limit_orders();actual=report.audit_attempt(rows,deepcopy(rows),account(rows),True,report.gold_orders(),[])
    assert actual['issues']==[] and actual['native_execution_account_audit_passed']
    attempts,events,_=report.native_records(rows)
    assert [attempt['native_group_id'] for attempt in attempts[2:]]==[None,None]
    assert len(events)>actual['actual_fill_events']
    assert not actual['forced_margin_or_cancel_race_robustness_certified']


def test_zero_fill_canceled_limits_retained_and_fallback_may_pay_bad_original_ask():
    rows=limit_orders('canceled');actual=report.audit_attempt(rows,deepcopy(rows),account(rows),True,report.gold_orders(),[])
    assert actual['issues']==[]
    assert actual['native_orders']==6 and actual['actual_fill_events']==4
    assert actual['limit_policy']['zero_fill_canceled_order_ids']==[3,4]
    assert actual['limit_policy']['fallback_order_ids']==[5,6]
    assert actual['native_single_cycle_pnl'] < -12000


def test_partial_cancel_falls_back_only_actual_one_lot_residual():
    rows=limit_orders('partial');actual=report.audit_attempt(rows,deepcopy(rows),account(rows),True,report.gold_orders(),[])
    assert actual['issues']==[]
    assert actual['limit_policy']['partial_canceled_order_ids']==[3]
    assert rows[-1]['quantity']==1 and actual['residual_native_quantities']=={}
    rows[-1]['quantity']=2
    wrong=report.audit_attempt(rows,deepcopy(rows),account(rows),True,report.gold_orders(),[])
    assert not wrong['native_execution_account_audit_passed']
    assert any('Fallback quantity' in issue for issue in wrong['issues'])


def test_fallback_requires_native_cancel_barrier_and_submitted_limit_bounds():
    rows=limit_orders('partial');rows[2]['events'][-1]['time']+=60
    actual=report.audit_attempt(rows,deepcopy(rows),account(rows),True,report.gold_orders(),[])
    assert any('cancel-event barrier' in issue for issue in actual['issues'])
    rows=limit_orders();rows[2]['events'][-1]['fillPrice']=1
    actual=report.audit_attempt(rows,deepcopy(rows),account(rows),True,report.gold_orders(),[])
    assert any('exceeded' in issue for issue in actual['issues'])


def test_failed_or_nonreproduced_control_is_preserved_unqualified():
    rows=base_orders();rows[-2]['events'][-1]['fillPrice']=.62
    actual=report.audit_attempt(rows,deepcopy(rows),account(rows),False,report.gold_orders(),[])
    assert not actual['market_control_reproduced']
    assert not actual['native_execution_account_audit_passed']
    rows=limit_orders('partial');actual=report.audit_attempt(rows,rows,account(rows,True),True,report.gold_orders(),[])
    assert actual['qc_error']=='execution failed' and not actual['native_execution_account_audit_passed']


def test_zero_quantity_fee_events_are_in_account_reconciliation():
    rows=limit_orders('canceled')
    rows[2]['events'][-1]['orderFeeAmount']=.25
    actual=report.audit_attempt(rows,deepcopy(rows),account(rows),True,report.gold_orders(),[])
    assert actual['issues']==[] and actual['actual_fees']==pytest.approx(4.85)
    attempts,events,_=report.native_records(rows)
    assert any(event['quantity']==0 and event['fee']==.25 for event in events)


def test_missing_unused_last_price_does_not_invalidate_bid_plus_tick_instruction():
    rows=limit_orders()
    for row in rows[2:]:row['orderSubmissionData'].pop('lastPrice',None)
    result=report.audit_attempt(rows,deepcopy(rows),account(rows),True,report.gold_orders(),[])
    assert result['issues']==[]
    rows[2]['orderSubmissionData'].pop('askPrice')
    result=report.audit_attempt(rows,deepcopy(rows),account(rows),True,report.gold_orders(),[])
    assert any('submission receipt' in issue for issue in result['issues'])


def test_limit_terminal_and_mandatory_deadlines_apply_even_without_fallback():
    rows=limit_orders();rows[2]['events'][-1]['time']=(report.TRIGGER+timedelta(minutes=5)).timestamp()
    result=report.audit_attempt(rows,deepcopy(rows),account(rows),True,report.gold_orders(),[])
    assert any('cancel window' in issue for issue in result['issues'])
    rows=limit_orders();rows[2]['events'][-1]['time']=report.MANDATORY_NOON.timestamp()
    result=report.audit_attempt(rows,deepcopy(rows),account(rows),True,report.gold_orders(),[])
    assert any('mandatory21DTE window' in issue for issue in result['issues'])


def test_definitive_early_invalid_limit_allows_immediate_cancellation_then_residual_fallback():
    rows=limit_orders('canceled')
    rows[2]['status']=7;rows[2]['events'][-1].update(time=report.TRIGGER.timestamp(),status='invalid')
    rows[3]['events'][-1]['time']=report.TRIGGER.timestamp()
    for row in rows[4:]:
        row['time']=report.TRIGGER.isoformat()
        for event in row['events']:event['time']=report.TRIGGER.timestamp()
    result=report.audit_attempt(rows,deepcopy(rows),account(rows),True,report.gold_orders(),[])
    assert result['issues']==[] and result['limit_policy']['observed_early_limit_rejection']


def test_available_native_receipt_disagreement_and_default_margin_overlap_are_unqualified():
    rows=limit_orders('partial')
    receipt=dict(initial_cash=report.INITIAL,default_margin_overlap=True,
        native_order_ids=[1,2,3,4,5],cancel_requested_ids=[],
        actual_residual_fallback={report.PUT:2},residual_native={report.PUT:0,report.CALL:0})
    result=report.audit_attempt(rows,deepcopy(rows),account(rows),True,report.gold_orders(),[receipt])
    assert not result['native_execution_account_audit_passed']
    assert any('forced-margin overlap' in issue for issue in result['issues'])
    assert any('cancellation-request receipt' in issue for issue in result['issues'])
    assert any('fallback receipt' in issue for issue in result['issues'])


def test_lvs_short_gross_holdings_sign_and_mixed_positions_are_not_net_marks():
    short=report.holding_valuation({report.PUT:-2,report.CALL:-2},'$1,234.50')
    assert short['derived_signed_holdings']==-1234.5 and short['gross_holdings_abs']==1234.5
    assert not short['per_leg_marks_derived']
    mixed=report.holding_valuation({report.PUT:-2,report.CALL:2},'$1,234.50')
    assert mixed['derived_signed_holdings'] is None and 'Mixed' in mixed['issue']
    unknown=report.holding_valuation({'unknown native instrument':-1},'$10')
    assert unknown['derived_signed_holdings'] is None


def test_actual_143108_pre_subscription_failures_have_no_invented_zero_pnl_cycle():
    import json
    campaign=report.STRATEGY/'results/strangle_basket-lvs-regression_20261019_143108'
    for variant,limit_exit in [('lvs_market_control',False),('lvs_limit_exit',True)]:
        folder=campaign/('SSTRANGLE_20261019_143108_'+variant)
        rows=json.loads((folder/'orders.json').read_text());rust=json.loads((folder/'orders.rust.json').read_text())
        rust=rust['orders'] if isinstance(rust,dict) else rust
        full=json.loads((folder/'backtest.json').read_text())['backtest']
        result=report.audit_attempt(rows,rust,full,limit_exit,report.gold_orders(),[])
        assert result['native_orders']==0 and result['actual_fill_events']==0
        assert result['actual_cashflow']==0 and result['actual_fees']==0
        assert result['ending_account_equity']==pytest.approx(57718.42)
        assert result['native_single_cycle_pnl'] is None and not result['completed_native_cycle_established']
        assert 'No verified original opening' in result['cycle_pnl_unavailable_reason']
        assert not result['native_execution_account_audit_passed'] and result['qc_error']


def test_actual_completed_native_cycle_still_reports_pnl_independently_of_later_cloud_error():
    rows=base_orders();full=account(rows,failed=True)
    result=report.audit_attempt(rows,deepcopy(rows),full,False,report.gold_orders(),[])
    assert result['completed_native_cycle_established'] and result['native_single_cycle_pnl']==pytest.approx(-12180.9)
    assert not result['native_execution_account_audit_passed']


def test_actual_143611_pair_handles_optional_rust_nulls_and_id_bound_canceled_limits():
    import json
    campaign=report.STRATEGY/'results/strangle_basket-lvs-regression_20261019_143611'
    expected=[('lvs_market_control',False,-12180.9,45537.52,4),('lvs_limit_exit',True,75.1,57793.52,6)]
    for variant,limit_exit,pnl,ending,count in expected:
        folder=campaign/('SSTRANGLE_20261019_143611_'+variant)
        rows=json.loads((folder/'orders.json').read_text());rust=json.loads((folder/'orders.rust.json').read_text())
        rust=rust['orders'] if isinstance(rust,dict) else rust
        full=json.loads((folder/'backtest.json').read_text())['backtest']
        receipts=report.events((folder/'cloud.log').read_text(),'LVS_EXIT_RECEIPT')
        result=report.audit_attempt(rows,rust,full,limit_exit,report.gold_orders(),receipts)
        assert result['issues']==[] and result['native_execution_account_audit_passed']
        assert result['native_orders']==count and result['actual_fill_events']==4
        assert result['native_single_cycle_pnl']==pytest.approx(pnl)
        assert result['actual_fees']==pytest.approx(4.9) and result['actual_fee_total_complete']
        assert result['ending_account_equity']==pytest.approx(ending) and result['residual_native_quantities']=={}
        _,python_events,_=report.native_records(rows);_,rust_events,_=report.native_records(rust)
        assert python_events==rust_events
        assert any(event['quantity']==0 and event['fee'] is None for event in rust_events)
        assert all(event['fee'] is not None for event in rust_events if event['quantity'])
        if limit_exit:
            policy=result['limit_policy']
            assert policy['zero_fill_canceled_order_ids']==[3,4] and policy['limit_fill_event_count']==0
            assert policy['fallback_order_ids']==[5,6]
            assert all(row['raw_final_tag']=='Fixture two-minute limit timeout; no assumed cancellation' for row in policy['role_receipts'])
        assert not result['forced_margin_or_cancel_race_robustness_certified']


def test_absent_none_nonfill_economics_remain_missing_but_real_fill_fees_are_required():
    rows=limit_orders('canceled')
    for row in rows:
        for event in row['events']:
            if not event['fillQuantity']:
                event['orderFeeAmount']=None;event['fillPrice']=None
    _,events,issues=report.native_records(rows)
    assert not issues and any(event['quantity']==0 and event['price'] is None and event['fee'] is None for event in events)
    result=report.audit_attempt(rows,deepcopy(rows),account(rows),True,report.gold_orders(),[])
    assert result['issues']==[]
    rows[0]['events'][-1]['orderFeeAmount']=None
    result=report.audit_attempt(rows,deepcopy(rows),account(rows),True,report.gold_orders(),[])
    assert not result['actual_fee_total_complete'] and not result['native_execution_account_audit_passed']
    assert result['native_single_cycle_pnl'] is None
    assert any('Missing actual fee amount on a genuine fill' in issue for issue in result['issues'])
