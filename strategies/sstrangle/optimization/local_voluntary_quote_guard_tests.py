import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from voluntary_quote_guard import BuybackQuote,voluntary_market_buyback_guard

NOW=datetime(2026,10,19,9,31)
def leg(symbol='PUT',bid=.61,ask=.65,tick=.01):
    return BuybackQuote(symbol,NOW,NOW,False,ask,bid,ask,tick)
def evaluate(a,b=None,reason='STOP',future=False):
    return voluntary_market_buyback_guard(reason,future,[a,b or leg('CALL')])

class GuardTests(unittest.TestCase):
    def test_real_lvs_extreme_quote_is_deferred_without_repair(self):
        quote=leg('LVS put nativeSID',bid=.61,ask=62)
        decision=evaluate(quote,leg('LVS call nativeSID',bid=.06,ask=.11))
        self.assertFalse(decision.allowed)
        self.assertIn(('LVS put nativeSID','voluntary_spread'),decision.failed_legs)
        self.assertEqual(quote.security_ask,62)
    def test_ordinary_pair_allowed(self):self.assertTrue(evaluate(leg()).allowed)
    def test_one_illiquid_held_leg_blocks_pair(self):
        self.assertFalse(evaluate(leg(),leg('CALL',bid=.01,ask=.5)).allowed)
    def test_tiny_zero_bid_buyback_can_pass_without_entry_permission(self):
        self.assertTrue(evaluate(leg(bid=0,ask=.01)).allowed)
    def test_five_minutes_inclusive_then_stale(self):
        self.assertTrue(evaluate(replace(leg(),quote_end_time=NOW-timedelta(minutes=5))).allowed)
        self.assertFalse(evaluate(replace(leg(),quote_end_time=NOW-timedelta(minutes=5,microseconds=1))).allowed)
    def test_future_quote_or_clock_mismatch_rejected(self):
        self.assertFalse(evaluate(replace(leg(),quote_end_time=NOW+timedelta(microseconds=1))).allowed)
        self.assertFalse(evaluate(replace(leg(),quote_end_time=NOW.replace(tzinfo=timezone.utc))).allowed)
    def test_tradebar_or_missing_ask_cannot_replace_quote_side(self):
        self.assertFalse(evaluate(replace(leg(),quote_end_time=None)).allowed)
        self.assertFalse(evaluate(replace(leg(),ask_close=None)).allowed)
        self.assertFalse(evaluate(replace(leg(),ask_close=.66)).allowed)
    def test_fill_forward_rejected(self):self.assertFalse(evaluate(replace(leg(),quote_fill_forward=True)).allowed)
    def test_negative_crossed_nonfinite_sides_and_bad_tick_rejected(self):
        for q in [leg(bid=-.01),leg(bid=.7,ask=.6),leg(ask=float('nan')),
            leg(ask=float('inf')),leg(ask=0),leg(tick=0),leg(tick=float('nan'))]:
            with self.subTest(q=q):self.assertFalse(evaluate(q).allowed)
    def test_native_tick_floor_and_mid_threshold_boundaries(self):
        self.assertTrue(evaluate(leg(bid=.01,ask=.03,tick=.01)).allowed)
        self.assertFalse(evaluate(leg(bid=.01,ask=.0300001,tick=.01)).allowed)
        self.assertTrue(evaluate(leg(bid=.875,ask=1.125,tick=.01)).allowed)
        self.assertFalse(evaluate(leg(bid=.8749,ask=1.1251,tick=.01)).allowed)
    def test_all_nonvoluntary_and_futures_bypass_without_reading_quotes(self):
        class NoRead:
            def __iter__(self):raise AssertionError('Nonvoluntary quotes must not be gated')
        for reason,future in [('TIME',False),('END',False),('MARGIN',False),('SPLIT',False),
            ('OPEN',False),('ROLL',False),('STOP',True),('PROFIT',True),('MARGIN;multiplier=100',False)]:
            d=voluntary_market_buyback_guard(reason,future,NoRead())
            self.assertFalse(d.applicable);self.assertTrue(d.allowed)
    def test_require_two_distinct_native_held_legs(self):
        self.assertFalse(voluntary_market_buyback_guard('STOP',False,[leg()]).allowed)
        self.assertFalse(evaluate(leg(),leg()).allowed)
    def test_profit_and_tagged_stop_share_policy(self):
        self.assertFalse(evaluate(leg(ask=62),reason='PROFIT').allowed)
        self.assertFalse(evaluate(leg(ask=62),reason='STOP;multiplier=100').allowed)

if __name__=='__main__':unittest.main()
