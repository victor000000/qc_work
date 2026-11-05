"""Prospective policy for voluntary equity option market buybacks ONLY.

The unqueued guarded_main research integration imports this helper. It does not amend data,
compute P&L, submit orders, or alter mandatory/forced liquidation behavior.
"""
from dataclasses import dataclass
from datetime import datetime,timedelta
import math
from typing import Iterable


@dataclass(frozen=True)
class BuybackQuote:
    """A single current security/cache snapshot, using the security's local clock.

    ask_close must come from the actual QuoteBar ask side, never its aggregate
    close or a TradeBar. A zero security bid is allowed for buy-to-close policy;
    it is not a tradable short-entry bid. No missing ask is invented.
    """
    symbol_id:str
    local_time:datetime
    quote_end_time:datetime|None
    quote_fill_forward:bool
    ask_close:float|None
    security_bid:float
    security_ask:float
    minimum_tick:float


@dataclass(frozen=True)
class GuardDecision:
    applicable:bool
    allowed:bool
    reason:str
    failed_legs:tuple[tuple[str,str],...]=()


def _failure(quote:BuybackQuote)->str|None:
    if not quote.symbol_id:return 'missing_native_symbol'
    if quote.quote_end_time is None:return 'missing_quote_bar'
    if quote.quote_fill_forward:return 'fill_forward_quote'
    try:
        age=quote.local_time-quote.quote_end_time
    except (TypeError,ValueError):return 'incompatible_local_clocks'
    if age<timedelta(0)or age>timedelta(minutes=5):return 'quote_age'
    try:
        ask=float(quote.security_ask);bid=float(quote.security_bid)
        bar_ask=float(quote.ask_close);tick=float(quote.minimum_tick)
    except (TypeError,ValueError,OverflowError):return 'missing_numeric_side'
    if not all(math.isfinite(x)for x in (ask,bid,bar_ask,tick)):return 'nonfinite_quote'
    if ask<=0 or bar_ask<=0:return 'nonpositive_ask'
    # Both values are exposed by the same LEAN side cache. Do not accept a
    # trade-price update, tick rounding, or stale different cached ask instead.
    if ask!=bar_ask:return 'ask_side_cache_mismatch'
    if bid<0 or ask<bid:return 'negative_bid_or_crossed'
    if tick<=0:return 'invalid_native_tick'
    mid=(bid+ask)/2
    if ask-bid>max(2*tick,.25*mid):return 'voluntary_spread'
    return None


def voluntary_market_buyback_guard(reason:str,is_future:bool,
    quotes:Iterable[BuybackQuote])->GuardDecision:
    """Return a decision without mutation; a bypass MUST preserve existing paths.

    Only prospective PROFIT/STOP equity market closes are applicable. In
    particular, TIME/END/MARGIN/SPLIT, all futures-option paths, OPEN and ROLL
    return a bypass without reading quotes. Caller must still apply the
    appropriate existing mandatory/native execution predicates on those paths.
    """
    base_reason=reason.split(';',1)[0]
    if is_future or base_reason not in ('PROFIT','STOP'):
        return GuardDecision(False,True,'bypass_preserve_existing_execution')
    legs=tuple(quotes)
    if len(legs)!=2:return GuardDecision(True,False,'require_two_held_legs')
    if len({q.symbol_id for q in legs})!=2:return GuardDecision(True,False,'require_distinct_native_legs')
    failures=tuple((q.symbol_id,error)for q in legs if(error:=_failure(q))is not None)
    if failures:return GuardDecision(True,False,'voluntary_quote_not_ready',failures)
    return GuardDecision(True,True,'voluntary_equity_pair_ready')
