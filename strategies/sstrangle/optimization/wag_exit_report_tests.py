from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from datetime import datetime,timezone
import pytest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('wag_exit_report',HERE/'wag_exit_report.py')
report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)


def fixture_orders(buyback=True):
    # Genuine preserved native QC orders, not OCC aliases or invented combo fills.
    original=json.loads((report.SOURCE_FOLDER/'orders.json').read_text())
    rows=deepcopy([row for row in original if row['id'] in (759,760,761,762)])
    for index,row in enumerate(rows,1):
        row['id']=index;row['groupOrderManager']['id']=1 if index<=2 else 2
        row['groupOrderManager']['orderIds']=[1,2] if index<=2 else [3,4]
        for event in row['events']:
            event['orderId']=index;event['id']='fixture-'+str(index)+'-'+str(event['orderEventId'])
    if buyback:
        stamp=int(report.CLOSE_UTC.timestamp())
        for index,source,price in [(5,rows[0],.16),(6,rows[3],.10)]:
            row=deepcopy(source);row.update(id=index,time='2019-11-29T17:00:00Z',quantity=1.,direction=0)
            row['tag']='WAG R735QTJ8XC9X:TIME;multiplier=100;quote_gate_utc=2019-11-29T17:00:00;put_quote_fresh=True;put_current_bar_ask=True;put_zero_bid=True;call_quote_fresh=True;call_current_bar_ask=True;call_zero_bid=False'
            row['groupOrderManager']['id']=3;row['groupOrderManager']['orderIds']=[5,6]
            row['orderSubmissionData']=dict(bidPrice=0 if index==5 else .08,askPrice=.16 if index==5 else .10,lastPrice=price)
            row['events']=[dict(id='fixture-'+str(index)+'-2',orderId=index,time=stamp,fillQuantity=1.,fillPrice=price,
                fillPriceCurrency='USD',orderFeeCurrency='USD',orderFeeAmount=1.,isAssignment=False)]
            rows.append(row)
    return rows


def account(orders,buyback=True):
    return dict(completed=True,status='Completed' if buyback else 'Runtime Error',
        error=None if buyback else 'Mandatory exit lacked fresh quotes on its eligible session: WAG R735QTJ8XC9X',
        statistics={'Total Orders':str(len(orders))},runtimeStatistics={
            'Equity':'$41,310.19' if buyback else '$41,274.01','Fees':'$6.00' if buyback else '$4.00',
            'Holdings':'$0.00' if buyback else '-$64.18','Unrealized':'$0.00' if buyback else '$79.82'})


def test_original_native_economic_prefix_and_buyback_cash_account_reconcile():
    rows=fixture_orders();full=account(rows)
    result=report.audit_fixture(rows,deepcopy(rows),full,'wag_buyback',report.original_first_four(),[])
    assert result['first_four_economic_fills_identical'] and result['buyback_execution_account_audit_passed']
    assert result['issues']==[] and result['net_closed_cycle_pnl']==pytest.approx(116)
    assert result['fees']==6 and result['residual_native_quantities']=={}
    assert result['submission_zero_bid_cause_proof']['proven']
    assert not result['strategy_performance_claim']


def test_control_preserves_expected_real_short_57point5put_65call():
    rows=fixture_orders(False)
    result=report.audit_fixture(rows,deepcopy(rows),account(rows,False),'wag_control',report.original_first_four(),[])
    assert result['actual_control_failure_reproduced'] and result['issues']==[]
    assert result['residual_native_quantities']=={report.PUT:-1,report.CALL65:-1}
    assert result['net_closed_cycle_pnl'] is None


def test_clean_close_without_bound_quote_receipt_leaves_cause_unproven():
    rows=fixture_orders()
    for row in rows[4:]:row['tag']='WAG R735QTJ8XC9X:TIME;multiplier=100'
    result=report.audit_fixture(rows,deepcopy(rows),account(rows),'wag_buyback',report.original_first_four(),[])
    assert result['buyback_execution_account_audit_passed']
    assert not result['submission_zero_bid_cause_proof']['proven']


def test_earlier_aggregate_zero_bid_or_wrong_log_ids_cannot_prove_submission_cause():
    rows=fixture_orders()
    diagnostic=dict(close_submission_utc='2019-11-29 17:00:00',native_order_ids=[1,2,3,4,100,101],
        close_submission_predicates=dict(put=dict(fresh_nonff=True,zero_bid_positive_ask=True),call=dict(fresh_nonff=True,zero_bid_positive_ask=False)))
    assert not report.bound_zero_bid_proof(rows,[diagnostic])['proven']
    for row in rows[4:]:row['orderSubmissionData']['bidPrice']=.01
    assert not report.bound_zero_bid_proof(rows,[])['proven']


def test_native_prefix_quantity_price_or_time_change_rejected():
    rows=fixture_orders();rows[0]['events'][-1]['fillPrice']=.91
    result=report.audit_fixture(rows,deepcopy(rows),account(rows),'wag_buyback',report.original_first_four(),[])
    assert not result['buyback_execution_account_audit_passed']
    assert not result['first_four_economic_fills_identical']
    rows=fixture_orders();rows[-1]['events'][0]['time']+=60
    result=report.audit_fixture(rows,deepcopy(rows),account(rows),'wag_buyback',report.original_first_four(),[])
    assert any('Nov29noon21DTE' in value for value in result['issues'])


def test_rust_python_difference_and_incomplete_order_download_fail():
    rows=fixture_orders();rust=deepcopy(rows);rust[-1]['events'][0]['fillPrice']=.12
    with pytest.raises(ValueError,match='Rust/Python'):report.audit_fixture(rows,rust,account(rows),'wag_buyback',report.original_first_four(),[])
    full=account(rows);full['statistics']['Total Orders']='7'
    with pytest.raises(ValueError,match='Incomplete'):report.audit_fixture(rows,rows,full,'wag_buyback',report.original_first_four(),[])


def test_unexpected_control_outcome_cannot_reproduce_original_failure():
    rows=fixture_orders(False);full=account(rows,False);full['error']='Unrelated worker timeout'
    result=report.audit_fixture(rows,rows,full,'wag_control',report.original_first_four(),[])
    assert not result['actual_control_failure_reproduced']
    assert any('did not reproduce' in issue for issue in result['issues'])


def test_native_zero_bid_on_wrong_leg_or_missing_fresh_predicate_is_not_proof():
    rows=fixture_orders()
    for row in rows[4:]:row['tag']=row['tag'].replace('put_zero_bid=True','put_zero_bid=False').replace('call_zero_bid=False','call_zero_bid=True')
    assert not report.bound_zero_bid_proof(rows,[])['proven']
    rows=fixture_orders()
    for row in rows[4:]:row['tag']=row['tag'].replace('put_quote_fresh=True','put_quote_fresh=False')
    assert not report.bound_zero_bid_proof(rows,[])['proven']


def test_submission_receipts_must_match_rust_export_and_native_combos_are_not_fabricated():
    rows=fixture_orders();rust=deepcopy(rows);rust[-2]['orderSubmissionData']['bidPrice']=.01
    with pytest.raises(ValueError,match='submission receipts differ'):
        report.audit_fixture(rows,rust,account(rows),'wag_buyback',report.original_first_four(),[])
    rows=fixture_orders();rows[-1]['groupOrderManager']['orderIds']=[5,100]
    result=report.audit_fixture(rows,rows,account(rows),'wag_buyback',report.original_first_four(),[])
    assert not result['buyback_execution_account_audit_passed']
    assert any('members differ' in issue for issue in result['issues'])


def test_missing_or_false_current_bar_ask_cannot_prove_zero_bid_repair():
    for replacement in ('put_current_bar_ask=False','removed_field=True'):
        rows=fixture_orders()
        for row in rows[4:]:row['tag']=row['tag'].replace('put_current_bar_ask=True',replacement)
        assert not report.bound_zero_bid_proof(rows,[])['proven']


def test_actual_142652_native_control_gross_short_holdings_reconcile_without_invented_marks():
    campaign=report.STRATEGY/'results/strangle_basket-wag-regression_20261019_142652'
    for variant in ('wag_control','wag_buyback'):
        folder=campaign/('SSTRANGLE_20261019_142652_'+variant)
        orders=json.loads((folder/'orders.json').read_text());rust=json.loads((folder/'orders.rust.json').read_text())
        rust=rust['orders'] if isinstance(rust,dict) else rust
        full=json.loads((folder/'backtest.json').read_text())['backtest']
        log=(folder/'cloud.log').read_text() if (folder/'cloud.log').exists() else ''
        diagnostics=report.events(log,'WAG_EXIT_FIXTURE')
        result=report.audit_fixture(orders,rust,full,variant,report.original_first_four(),diagnostics)
        valuation=result['aggregate_holding_valuation']
        assert result['native_cashflow_account_reconciles']
        assert valuation['runtime_holdings_raw']=='$139.00' and valuation['gross_holdings_abs']==139
        assert valuation['derived_signed_holdings']==-139 and not valuation['per_leg_marks_derived']
        assert valuation['derived_equity_from_native_cashflow']==pytest.approx(41199.185)
        assert result['terminal_account_statistics']==full['runtimeStatistics']
        if variant=='wag_control':assert result['actual_control_failure_reproduced'] and result['issues']==[]
        else:
            assert not result['buyback_execution_account_audit_passed']
            assert result['residual_native_quantities']=={report.PUT:-1,report.CALL65:-1}
            assert not result['submission_zero_bid_cause_proof']['proven']


def test_mixed_or_unknown_residuals_cannot_derive_signed_gross_holding_value():
    mixed=report.holding_valuation({report.PUT:-1,report.CALL65:1},'$139.00')
    unknown=report.holding_valuation({'UNKNOWN native SID':-1},'$139.00')
    assert mixed['derived_signed_holdings'] is None and 'Mixed' in mixed['issue']
    assert unknown['derived_signed_holdings'] is None and 'Unknown' in unknown['issue']
    assert report.holding_valuation({report.PUT:-1},'unavailable')['derived_signed_holdings'] is None
    assert report.holding_valuation({report.PUT:-1},'nan')['derived_signed_holdings'] is None
    assert report.holding_valuation({report.PUT:1,report.CALL65:2},'$139.00')['derived_signed_holdings']==139
    rows=fixture_orders(False)
    rows[-1]['quantity']=1;rows[-1]['events'][-1]['fillQuantity']=1
    result=report.audit_fixture(rows,deepcopy(rows),account(rows,False),'wag_control',report.original_first_four(),[])
    assert not result['native_cashflow_account_reconciles']
    assert any('Mixed long/short' in issue for issue in result['issues'])
