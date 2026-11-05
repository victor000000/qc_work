import ast
from datetime import datetime, timedelta, timezone
from types import MethodType
import pytest
from fresh_risk_slots import FreshRiskSlots
from build_risk_retry_source import render, PARENT
from guarded_integration_tests import setup


def actual_method():
    tree = ast.parse(render())
    f = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'intraday_risk_exits')
    from rules import close_reason
    namespace = dict(FreshRiskSlots=FreshRiskSlots, close_reason=close_reason)
    exec(compile(ast.Module(body=[f], type_ignores=[]), '<actual_retry_method>', 'exec'), namespace)
    return namespace['intraday_risk_exits']


def attach_retry(a):
    a.utc_time = a.time + timedelta(hours=4)
    a.intraday_risk_exits = MethodType(actual_method(), a)
    return a


def test_stale_boundary_then_fresh_next_minute_exposes_parent_delay(monkeypatch):
    old = setup(monkeypatch)
    old.voluntary_quote_ready = lambda key: False
    old.intraday_risk_exits()
    old.time += timedelta(minutes=1)
    old.voluntary_quote_ready = lambda key: True
    old.intraday_risk_exits()
    assert not old.sent
    new = attach_retry(setup(monkeypatch))
    new.voluntary_quote_ready = lambda key: False
    new.intraday_risk_exits()
    new.time += timedelta(minutes=1); new.utc_time += timedelta(minutes=1)
    new.voluntary_quote_ready = lambda key: True
    new.intraday_risk_exits()
    assert new.sent == [('A', 'STOP')]


def test_genuine_no_trigger_evaluation_consumes_interval(monkeypatch):
    a = attach_retry(setup(monkeypatch))
    a.voluntary_quote_ready = lambda key: True
    for s in a.securities.values(): s.ask_price = .4
    a.intraday_risk_exits()
    assert not a.sent and a.counts['research_fresh_risk_evaluations'] == 1
    for s in a.securities.values(): s.ask_price = 2
    a.time += timedelta(minutes=1); a.utc_time += timedelta(minutes=1)
    a.intraday_risk_exits()
    assert not a.sent and a.counts['research_fresh_risk_evaluations'] == 1
    a.time += timedelta(minutes=15); a.utc_time += timedelta(minutes=15)
    a.intraday_risk_exits()
    assert a.sent == [('A', 'STOP')]


def test_positions_do_not_consume_each_others_quote_opportunity():
    s = FreshRiskSlots(15); now = datetime(2020, 1, 2, 17)
    s.complete('liquid', now)
    assert not s.due('liquid', now + timedelta(minutes=1))
    assert s.due('delayed', now + timedelta(minutes=1))
    s.complete('delayed', now + timedelta(minutes=1))
    s.retain({'delayed'})
    assert set(s.consumed) == {'delayed'}


@pytest.mark.parametrize('blocked', ['pending', 'closed', 'time_due', 'insolvent'])
def test_original_management_gates_are_not_bypassed(monkeypatch, blocked):
    a = attach_retry(setup(monkeypatch)); a.voluntary_quote_ready = lambda key: True
    if blocked == 'pending': a.pending_combos['A'] = object()
    elif blocked == 'closed': a.securities['P'].exchange.exchange_open = False
    elif blocked == 'time_due': a.positions['A']['expiry'] = a.time.date() + timedelta(days=21)
    else: a.insolvency = {'equity': -1}
    a.intraday_risk_exits()
    assert not a.sent and not a.counts['research_fresh_risk_evaluations']


def test_clock_and_consumption_fail_closed():
    s = FreshRiskSlots(15); now = datetime(2020, 1, 2, 17, tzinfo=timezone.utc)
    s.complete('a', now)
    with pytest.raises(ValueError): s.complete('a', now)
    with pytest.raises(ValueError): s.due('a', now - timedelta(minutes=16))
    with pytest.raises(ValueError): s.due('a', now.astimezone(timezone(timedelta(hours=8))))


def test_generation_changes_only_the_risk_scheduler_method():
    def methods(source):
        return {n.name: ast.dump(n, include_attributes=False) for n in ast.walk(ast.parse(source))
                if isinstance(n, ast.FunctionDef)}
    a, b = methods(PARENT.read_text()), methods(render())
    assert set(a) == set(b)
    assert {name for name in a if a[name] != b[name]} == {'intraday_risk_exits'}
