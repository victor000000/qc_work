"""Regression guards against counting legs and accepting corrupt native evidence."""
import copy
import json
from pathlib import Path
import pytest
from collect_demo import audit_orders

FIXTURE = Path(__file__).resolve().parents[1]/'results/qc_baseline_poc_20261023/smoke_v3_evidence'

@pytest.fixture
def native():
    orders=json.loads((FIXTURE/'orders.json').read_text())
    rt=json.loads((FIXTURE/'backtest.json').read_text())['backtest']['runtimeStatistics']
    return orders,rt


def test_native_smoke_counts_whole_episodes_and_settles(native):
    orders,rt=native
    episodes,legs,events,annual,audit=audit_orders(orders,'',rt,False)
    assert len(episodes)==74 and len(legs)==296 and len(events)==447
    assert abs(audit['attribution_error'])<1e-7
    assert audit['residual_positions']==0
    assert annual.trades.tolist()==[74]


def test_annual_gate_does_not_annualize_or_ignore_absent_year(native):
    orders,rt=native
    *_,annual,audit=audit_orders(orders,'',rt,True,[2024,2025])
    assert annual.trades.tolist()==[74,0]
    assert not audit['annual_pass']


@pytest.mark.parametrize('corruption',['duplicate_order','missing_leg','partial_fill','wrong_wing','wrong_cash','wrong_ticker','missing_combo_identity'])
def test_reject_corrupted_native_evidence(native,corruption):
    original,rt=native
    orders=copy.deepcopy(original);rt=dict(rt)
    if corruption=='duplicate_order':orders.append(copy.deepcopy(orders[0]))
    elif corruption=='missing_leg':orders.pop(0)
    elif corruption=='partial_fill':
        event=next(e for e in orders[0]['events'] if e['fillQuantity'])
        event['fillQuantity']/=2
    elif corruption=='wrong_wing':
        orders[0]['symbol']['value']=orders[0]['symbol']['value'][:-8]+'04000000'
    elif corruption=='wrong_cash':rt['native_net_pnl']=str(float(rt['native_net_pnl'])+100)
    elif corruption=='wrong_ticker':orders[0]['symbol']['value']=orders[0]['symbol']['value'].replace('SPXW','QQQ')
    elif corruption=='missing_combo_identity':orders[0]['groupOrderManager']=None
    with pytest.raises(ValueError):audit_orders(orders,'',rt,False)


def test_documented_midpoint_and_package_slippage_roundtrip():
    folder=FIXTURE.parent/'smoke_v5_evidence'
    orders=json.loads((folder/'orders.json').read_text())
    rt=json.loads((folder/'backtest.json').read_text())['backtest']['runtimeStatistics']
    episodes,legs,events,annual,audit=audit_orders(orders,(folder/'cloud.log').read_text(),rt,False)
    assert len(episodes)==75 and len(legs)==300
    assert audit['midpoint_package_fill_audit'] and audit['residual_positions']==0
    assert abs(audit['attribution_error'])<1e-7


@pytest.mark.parametrize('corruption',['missing_model_tag','wrong_package_slip'])
def test_reject_wrong_midpoint_source_convention(corruption):
    folder=FIXTURE.parent/'smoke_v5_evidence'
    orders=json.loads((folder/'orders.json').read_text())
    rt=json.loads((folder/'backtest.json').read_text())['backtest']['runtimeStatistics']
    event=next(e for e in orders[0]['events'] if e['fillQuantity'])
    if corruption=='missing_model_tag':event['message']=''
    else:event['message']=event['message'].replace('oo_slip=0.01250000','oo_slip=0.05000000')
    with pytest.raises(ValueError):audit_orders(orders,'',rt,False)


def test_reject_fill_before_recorded_decision(native):
    original,rt=native
    orders=copy.deepcopy(original)
    event=next(e for e in orders[0]['events'] if e['fillQuantity'])
    event['time']-=3600
    with pytest.raises(ValueError,match='predates decision'):
        audit_orders(orders,'',rt,False)
