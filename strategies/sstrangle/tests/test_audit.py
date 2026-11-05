import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('strangle_audit', Path(__file__).parents[1] / 'audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def order(identifier, group, reason, quantity, price):
    return dict(id=identifier, time=str(group), tag='SPY:' + reason,
        groupOrderManager={'id': group}, events=[dict(fillQuantity=quantity,
        fillPrice=price, orderFeeAmount=1)])


def test_reconstruct_whole_cycle_with_roll_and_actual_fees():
    orders = [order(1, 1, 'OPEN', -1, 1), order(2, 1, 'OPEN', -1, 2),
              order(3, 2, 'ROLL', 1, 0.1), order(4, 2, 'ROLL', -1, 0.4),
              order(5, 3, 'PROFIT', 1, 0.5), order(6, 3, 'PROFIT', 1, 0.6)]
    cycles = audit.reconstruct(orders)
    assert len(cycles) == 1
    assert cycles[0]['pnl'] == pytest.approx(214)
    assert cycles[0]['rolls'] == 1
    assert cycles[0]['fees'] == 6


def test_reject_duplicate_pages_and_unclosed_positions():
    opening = [order(1, 1, 'OPEN', -1, 1), order(2, 1, 'OPEN', -1, 2)]
    with pytest.raises(ValueError, match='Duplicate'):
        audit.reconstruct(opening + opening)
    with pytest.raises(ValueError, match='Unclosed'):
        audit.reconstruct(opening)


def test_diagnostic_order_annotations_preserve_cycle_reconstruction():
    orders = [order(1, 1, 'OPEN;ivr=55;iv=0.25', -1, 1),
              order(2, 1, 'OPEN;ivr=55;iv=0.25', -1, 2),
              order(3, 2, 'TIME', 1, .4), order(4, 2, 'TIME', 1, .5)]
    assert audit.reconstruct(orders)[0]['pnl'] == pytest.approx(206)


def test_future_multiplier_is_applied_to_every_fill_and_required():
    orders = [order(1,1,'OPEN;multiplier=1000',-1,1),order(2,1,'OPEN;multiplier=1000',-1,2),
              order(3,2,'TIME;multiplier=1000',1,.4),order(4,2,'TIME;multiplier=1000',1,.5)]
    for row in orders:
        row['securityType']=8
    assert audit.reconstruct(orders)[0]['pnl'] == pytest.approx(2096)
    orders[-1]['tag']='CL:TIME'
    with pytest.raises(ValueError,match='explicit contract multiplier'):
        audit.reconstruct(orders)


def test_wholly_rejected_roll_does_not_change_cash_fees_or_roll_count():
    rows=[order(1,1,'OPEN',-1,1),order(2,1,'OPEN',-1,2)]
    rejected=[order(3,2,'ROLL',0,0),order(4,2,'ROLL',0,0)]
    for r in rejected:r.update(status=7,events=[])
    closing=[order(5,3,'MARGIN',1,.5),order(6,3,'MARGIN',1,.6)]
    cycle=audit.reconstruct(rows+rejected+closing)[0]
    assert cycle['rolls']==0 and cycle['pnl']==pytest.approx(186)
    rejected[0]['events']=[dict(fillQuantity=1,fillPrice=.1)]
    with pytest.raises(ValueError,match='two filled legs'):
        audit.reconstruct(rows+rejected+closing)


def sequential_order(identifier, symbol, reason='TIME', pair=1):
    return dict(id=identifier,time='2017-08-04T16:00:00Z',
        tag=f'FUT_ZW:{reason};multiplier=5000;execution=sequential_close;close_pair={pair}',
        securityType=8,quantity=5,status=3,type=0,symbol={'id':symbol},groupOrderManager=None,
        events=[dict(fillQuantity=5,fillPrice=.1,orderFeeAmount=12.35)])


def test_identified_native_market_closes_are_paired_without_fabricating_a_combo():
    rows=[sequential_order(9,'put'),sequential_order(10,'call')]
    assert [audit.order_group_id(o) for o in rows]==[-1,-1]
    audit.validate_sequential_close(rows)
    rows[1]['status']=7
    with pytest.raises(ValueError,match='complete native market fill'):
        audit.validate_sequential_close(rows)


def test_ungrouped_open_or_unmarked_order_is_never_accepted():
    with pytest.raises(ValueError,match='identified futures-option close'):
        audit.order_group_id(sequential_order(1,'put',reason='OPEN'))
    row=sequential_order(1,'put');row['tag']='FUT_ZW:TIME;multiplier=5000'
    with pytest.raises(ValueError,match='identified futures-option close'):
        audit.order_group_id(row)


def test_sequential_close_rejects_missing_leg_reused_symbol_or_delayed_order():
    first,second=sequential_order(9,'put'),sequential_order(10,'call')
    with pytest.raises(ValueError,match='two identically tagged'):
        audit.validate_sequential_close([first])
    second['symbol']['id']='put'
    with pytest.raises(ValueError,match='distinct contracts'):
        audit.validate_sequential_close([first,second])
    second['symbol']['id']='call';second['time']='2017-08-04T16:06:00Z'
    with pytest.raises(ValueError,match='five minutes'):
        audit.validate_sequential_close([first,second])
