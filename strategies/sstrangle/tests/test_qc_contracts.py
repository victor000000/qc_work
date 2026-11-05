from datetime import date
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).parents[1]))
from qc_contracts import option_identity,execution_signature


def test_option_sid_survives_duplicate_historical_alias_and_handles_futures():
    put=option_identity(dict(id='LO 2Z41I94YJ8FT0|CL V52FC5EG3QV5',value='unusable display alias'))
    assert put==dict(option_root='LO',expiry='2012-03-15',call_put='P',strike=89.,security_type=8)
    equity=option_identity(dict(id='HD 2Z43H5BGXLVAE|HD R735QTJ8XC9X'))
    assert equity['expiry']=='2012-03-17' and equity['strike']==41 and equity['call_put']=='P'
    with pytest.raises(ValueError,match='not an option'):
        option_identity(dict(id='HD R735QTJ8XC9X'))


def test_rust_comparison_ignores_only_optional_alias_not_actual_delivery_or_fill():
    row=dict(underlying_id='CL V52FC5EG3QV5',underlying_alias='CL20J12',qc_price=1,quantity=-5)
    assert execution_signature([row])==execution_signature([dict(row,underlying_alias='')])
    assert execution_signature([row])!=execution_signature([dict(row,underlying_id='CL DIFFERENT')])
    assert execution_signature([row])!=execution_signature([dict(row,qc_price=1.01)])



def actual_example():
    # Synthetic native-order shape; no private account tape is required.
    return dict(id=1, quantity=-2, status=3, securityType=2, tag='fixture:OPEN',
        symbol=dict(id='HD 2Z43H5BGXLVAE|HD R735QTJ8XC9X', value='synthetic-put'),
        groupOrderManager=dict(id=1), events=[dict(id='fixture-event', time=1577970000,
        fillQuantity=-2, fillPrice=1.5, fillPriceCurrency='USD', orderFeeAmount=2)])


@pytest.mark.parametrize('status',[3,'3','Filled',2,'PartiallyFilled'])
def test_filled_record_without_events_is_not_zero_actual_trades(status):
    from qc_contracts import execution_rows
    order=actual_example();order['status']=status;order['events']=[]
    with pytest.raises(ValueError,match='lacks genuine fill events'):execution_rows([order])


def test_genuine_filled_quantity_cannot_be_partially_omitted():
    from qc_contracts import execution_rows
    order=actual_example()
    actual=execution_rows([order]);assert sum(r['quantity'] for r in actual)==order['quantity']
    for event in order['events']:
        if event.get('fillQuantity'):event['fillQuantity']/=2
    with pytest.raises(ValueError,match='incomplete genuine fill events'):execution_rows([order])


def test_unfilled_rejected_order_can_have_no_execution_events():
    from qc_contracts import execution_rows
    order=actual_example();order['status']=6;order['events']=[]
    assert execution_rows([order])==[]


def test_partial_native_fill_is_preserved_as_partial_not_manufactured_complete():
    from qc_contracts import execution_rows
    order=actual_example();order['status']=2
    for event in order['events']:
        if event.get('fillQuantity'):event['fillQuantity']/=2
    actual=execution_rows([order])
    assert sum(r['quantity'] for r in actual)==order['quantity']/2


def test_live_tail_shape_cannot_certify_zero_fills():
    from qc_contracts import execution_rows
    order=actual_example(); order['events']=[]
    with pytest.raises(ValueError,match='lacks genuine fill events'):
        execution_rows([order])


def test_missing_fill_fee_is_not_assumed_zero():
    from qc_contracts import execution_rows
    order=actual_example()
    for event in order['events']:
        if event.get('fillQuantity'):event.pop('orderFeeAmount',None)
    with pytest.raises(ValueError,match='explicit fee evidence'):execution_rows([order])


def test_explicit_zero_fee_remains_a_real_zero():
    from qc_contracts import execution_rows
    order=actual_example()
    for event in order['events']:
        if event.get('fillQuantity'):event['orderFeeAmount']=0
    assert sum(r['fee'] for r in execution_rows([order]))==0



@pytest.mark.parametrize('price',[float('nan'),float('inf'),-1])
def test_nonfinite_or_negative_option_fill_price_cannot_enter_account_arithmetic(price):
    from qc_contracts import execution_rows
    order=actual_example()
    for event in order['events']:
        if event.get('fillQuantity'):event['fillPrice']=price
    with pytest.raises(ValueError,match='Invalid actual option fill price'):execution_rows([order])
