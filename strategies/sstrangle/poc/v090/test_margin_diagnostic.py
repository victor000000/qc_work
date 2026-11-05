from types import SimpleNamespace as N
import json
import sys
import pytest

@pytest.fixture(autouse=True)
def native_parameters(monkeypatch):
    monkeypatch.setitem(sys.modules, "QuantConnect.Securities.Positions", N(ReservedBuyingPowerForPositionGroupParameters=lambda p,g:N(portfolio=p,group=g)))

from .margin_diagnostic import observe_margin_call


def test_snapshot_preserves_requests_and_reports_native_group_reserve():
    requests=[N(symbol='short',quantity=1)]
    model=N(GetType=lambda:N(Name='NativeSpread'),get_reserved_buying_power_for_position_group=lambda parameters:N(absolute_used_buying_power=7000 if parameters.group.buying_power_model is model else 0))
    logs=[]
    a=N(time='2022-11-15 13:41',portfolio=N(total_portfolio_value=6000,cash=9000,total_margin_used=7000,margin_remaining=-1000,positions=N(groups=[N(buying_power_model=model)])),securities={'s':N(invested=True,symbol='short',holdings=N(quantity=-1,holdings_value=-3000))},debug=logs.append)
    assert observe_margin_call(a,requests) is requests
    data=json.loads(logs[0].split(' ',1)[1])
    assert data['groups']==[{'model':'NativeSpread','reserved':7000}]
    assert data['holdings'][0]['quantity']==-1
    assert data['used']>data['equity'] and data['remaining']==-1000
    assert requests[0].quantity==1


def test_failed_diagnostic_does_not_suppress_liquidation():
    logs=[];requests=[object()]
    assert observe_margin_call(N(debug=logs.append),requests) is requests
    assert json.loads(logs[0].split(' ',1)[1])['error']=='AttributeError'


def test_runtime_receipt_survives_missing_metadata_and_is_bounded():
    from .margin_diagnostic import record_margin_state
    stats={}
    record_margin_state(N(set_runtime_statistic=stats.__setitem__), 'MD')
    assert len(stats)==17 and max(map(len,stats.values()))<=180
    raw=''.join(stats['MD'+str(i).zfill(2)] for i in range(16))[:int(stats['MDlen'])]
    assert json.loads(raw)['error']=='AttributeError'
