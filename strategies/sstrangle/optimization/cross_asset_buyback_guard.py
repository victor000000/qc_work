"""Prospective voluntary buyback guard for equity AND futures options.

Uses the existing native-side validation and native tick units. It never alters
a quote or applies its spread rule to mandatory or broker-forced liquidations.
"""
from voluntary_quote_guard import GuardDecision, _failure


def cross_asset_market_buyback_guard(reason, is_future, quotes):
    if type(is_future) is not bool:
        raise ValueError('Explicit option asset class required')
    if reason.split(';', 1)[0] not in ('PROFIT', 'STOP'):
        return GuardDecision(False, True, 'bypass_preserve_existing_execution')
    legs = tuple(quotes)
    if len(legs) != 2:
        return GuardDecision(True, False, 'require_two_held_legs')
    if len({q.symbol_id for q in legs}) != 2:
        return GuardDecision(True, False, 'require_distinct_native_legs')
    failures = tuple((q.symbol_id, error) for q in legs if (error := _failure(q)) is not None)
    if failures:
        return GuardDecision(True, False, 'voluntary_quote_not_ready', failures)
    return GuardDecision(True, True, 'voluntary_future_pair_ready' if is_future else 'voluntary_equity_pair_ready')
