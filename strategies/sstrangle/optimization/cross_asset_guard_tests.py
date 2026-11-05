import ast
from dataclasses import replace
from datetime import datetime, timedelta
from types import MethodType, SimpleNamespace as NS
import pytest
from build_cross_asset_guard_source import render, PARENT
from cross_asset_buyback_guard import cross_asset_market_buyback_guard
from voluntary_quote_guard import BuybackQuote
from guarded_integration_tests import setup, request, wide, Quote

NOW = datetime(2016, 6, 30, 11)


def q(native='put', **changes):
    quote = BuybackQuote(native, NOW, NOW, False, .05, .04875, .05, .00125)
    return replace(quote, **changes)


def actual_methods(a):
    methods = [n for n in ast.walk(ast.parse(render())) if isinstance(n, ast.FunctionDef)
               and n.name in ('voluntary_quote_ready', 'process_exit_requests')]
    namespace = dict(BuybackQuote=BuybackQuote, cross_asset_market_buyback_guard=cross_asset_market_buyback_guard,
                     QuoteBar=Quote, Leg=NS(create=lambda symbol, quantity: (symbol, quantity)))
    exec(compile(ast.Module(body=methods, type_ignores=[]), '<actual_cross_asset_guard>', 'exec'), namespace)
    for f in methods:
        setattr(a, f.name, MethodType(namespace[f.name], a))
    return a


def test_realistic_commodity_units_and_wide_exit_side():
    normal = [q(), q('call')]
    assert cross_asset_market_buyback_guard('STOP', True, normal).allowed
    wide_pair = [q(ask_close=.4, security_bid=.0225, security_ask=.4), q('call')]
    result = cross_asset_market_buyback_guard('STOP', True, wide_pair)
    assert not result.allowed and result.failed_legs == (('put', 'voluntary_spread'),)
    assert wide_pair[0].security_ask == .4


@pytest.mark.parametrize('reason', ['TIME', 'END', 'SPLIT', 'MARGIN', 'OPEN', 'ROLL'])
def test_all_nonvoluntary_paths_bypass_without_reading_quotes(reason):
    def forbidden():
        raise AssertionError('Nonvoluntary guard read quotes')
        yield
    assert not cross_asset_market_buyback_guard(reason, True, forbidden()).applicable


def test_futures_stale_or_forwarded_quotes_never_become_ready():
    for bad in [q(quote_end_time=NOW-timedelta(minutes=6)), q(quote_fill_forward=True),
                q(ask_close=.06), q(security_bid=-.01)]:
        assert not cross_asset_market_buyback_guard('STOP', True, [bad, q('call')]).allowed


def test_actual_future_wide_stop_is_deferred_with_real_holdings_retained(monkeypatch):
    old = setup(monkeypatch); old.states['A']['future'] = True; wide(old); request(old)
    old.process_exit_requests(); assert old.sent == [('A', 'STOP')]
    new = actual_methods(setup(monkeypatch)); new.states['A']['future'] = True; wide(new); request(new)
    new.process_exit_requests()
    assert not new.sent and not new.exit_requests and 'A' in new.positions
    assert new.securities['P'].ask_price == 62.


def test_actual_ready_future_stop_uses_original_execution_entrypoint(monkeypatch):
    a = actual_methods(setup(monkeypatch)); a.states['A']['future'] = True; request(a)
    a.process_exit_requests(); assert a.sent == [('A', 'STOP')]


@pytest.mark.parametrize('reason', ['TIME', 'END', 'SPLIT', 'MARGIN'])
def test_actual_forced_future_exits_ignore_voluntary_spread_rule(monkeypatch, reason):
    a = actual_methods(setup(monkeypatch)); a.states['A']['future'] = True; wide(a); request(a, reason)
    a.voluntary_quote_ready = lambda key: (_ for _ in ()).throw(AssertionError('Forced exit entered guard'))
    a.process_exit_requests(); assert a.sent == [('A', reason)]


def test_transform_retains_entries_rolls_fills_fees_and_all_other_methods():
    def methods(source):
        return {n.name: ast.dump(n, include_attributes=False) for n in ast.walk(ast.parse(source))
                if isinstance(n, ast.FunctionDef)}
    old, new = methods(PARENT.read_text()), methods(render())
    assert set(old) == set(new)
    assert {k for k in old if old[k] != new[k]} == {'voluntary_quote_ready', 'process_exit_requests'}
