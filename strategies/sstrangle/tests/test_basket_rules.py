import importlib.util
from datetime import date, timedelta
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('basket_rules', Path(__file__).parents[1] / 'basket/basket_rules.py')
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)


def observations(values):
    return [(date(2012, 1, 1) + timedelta(days=i), v) for i, v in enumerate(values)]


def test_batch_entry_waits_for_positions_pending_orders_and_exits():
    assert rules.can_start_batch({}, {}, {})
    assert not rules.can_start_batch({'A':{}},{},{})
    assert not rules.can_start_batch({}, {'A':{}},{})
    assert not rules.can_start_batch({}, {},{'A':{}})


def test_monthlies_exclude_thursday_weeklies_when_friday_is_open():
    assert rules.standard_equity_monthly(date(2026,3,20))
    assert not rules.standard_equity_monthly(date(2026,3,19))
    assert rules.standard_equity_monthly(date(2014,4,17),third_friday_closed=True)
    assert not rules.standard_equity_monthly(date(2026,3,13))
    assert rules.standard_equity_monthly(date(2012,3,17))
    assert not rules.standard_equity_monthly(date(2026,3,21))


def test_equal_cash_allocations_use_actual_basket_count_and_whole_lots():
    assert rules.equal_budget_quantity(60000,13,1000,60000)==4
    assert rules.equal_budget_quantity(60000,6,1000,60000)==10
    assert rules.equal_budget_quantity(60000,1,1000,60000)==60
    assert rules.equal_budget_quantity(60000,6,1000,3500)==3
    assert rules.equal_budget_quantity(60000,6,1000,-1)==0


def test_equal_budget_selection_retains_volume_priority_and_excludes_unaffordable_contracts():
    candidates=[dict(key=str(i),volume=100-i,unit_cost=1000) for i in range(15)]
    selected,count=rules.equal_budget_candidates(candidates,0,60000)
    assert count==13 and [r['key'] for r in selected]==[str(i) for i in range(13)]
    selected,count=rules.equal_budget_candidates([dict(key='EXPENSIVE',volume=500,unit_cost=70000),
                                                 dict(key='TRADEABLE',volume=100,unit_cost=30000)],0,60000)
    assert count==1 and selected[0]['key']=='TRADEABLE'
    selected,count=rules.equal_budget_candidates(candidates,11,60000)
    assert count==13 and len(selected)==2
    assert rules.equal_budget_candidates(candidates,13,60000)==([],13)


def test_rank_cannot_be_replaced_by_percentile_for_entry():
    rows = observations([.1] * 58 + [1.1, .2])
    result = rules.iv_statistics(rows, rows[-1][0], min_points=60)
    assert result['ivr'] == pytest.approx(10)
    assert result['ivp'] == pytest.approx(100 * 59 / 60)
    assert not rules.high_iv_rank(result['ivr'])
    assert rules.high_iv_rank(result['ivp'])  # This substitution would enter incorrectly.


def test_rank_gate_is_strict_and_undefined_range_cannot_enter():
    for rank in (None, float('nan'), 0, 70):
        assert not rules.high_iv_rank(rank)
    assert rules.high_iv_rank(70.001)
    rows = observations([.2] * 60)
    result = rules.iv_statistics(rows, rows[-1][0], min_points=60)
    assert result['ivr'] is None and result['ivp'] == 100


def test_latest_observation_is_included_and_old_extreme_expires():
    rows = observations([10] + [.1] * 250 + [.5, .3])
    result = rules.iv_statistics(rows, rows[-1][0], lookback=252, min_points=252)
    assert result['samples'] == 252
    assert result['ivr'] == pytest.approx(50)
    assert result['iv_high'] == .5
    assert rules.iv_statistics(rows[:59], rows[58][0])['ivr'] is None


def test_user_two_year_window_requires_504_observations():
    rows = observations([.1] * 502 + [.5, .3])
    assert rules.iv_statistics(rows[:-1], rows[-1][0])['ivr'] is None
    result = rules.iv_statistics(rows, rows[-1][0])
    assert result['samples'] == 504
    assert result['ivr'] == pytest.approx(50)


def test_no_duplicate_future_or_invalid_iv_observations():
    rows = observations([.1] * 58 + [.5, .3])
    with pytest.raises(ValueError, match='Future'):
        rules.iv_statistics(rows, rows[-2][0])
    with pytest.raises(ValueError, match='Duplicate'):
        rules.iv_statistics(rows + rows[-1:], rows[-1][0])
    for bad in (None, float('nan'), float('inf'), -1):
        assert rules.iv_statistics(rows[:-1] + [(rows[-1][0], bad)], rows[-1][0])['ivr'] is None


def test_screen_unknown_etf_cap_retained_and_thresholds_strict():
    rows = [(date(2012, 1, 1) + timedelta(days=i), 31, 5_000_001) for i in range(20)]
    assert rules.equity_screen(rows, None)[0] is None
    assert not rules.equity_screen(rows, 0)[1]['cap_known']
    assert rules.equity_screen(rows, 1_000_000_000)[0] == 'market_cap'
    assert rules.equity_screen(rows[:19], None)[0] == 'price_volume_history'
    assert rules.equity_screen([(d, 30, v) for d, p, v in rows], None)[0] == 'price'
    assert rules.equity_screen([(d, p, 5_000_000) for d, p, v in rows], None)[0] == 'volume'


def test_volume_priority_and_pending_orders_reserve_basket_capacity():
    values = [dict(key='ES', volume=10), dict(key='SPY', volume=100), dict(key='QQQ', volume=100)]
    assert [c['key'] for c in rules.ordered_candidates(values)] == ['QQQ', 'SPY', 'ES']
    assert rules.available_slots(range(12), [11, 12]) == 0
    assert rules.available_slots(range(12), [11]) == 1


def test_standard_monthly_expiries_and_futures_calendar():
    # 2012 equity options used Saturday expiration; future monthlies differ.
    today = date(2012, 1, 3)
    dates = [date(2012, 1, 21), date(2012, 2, 10), date(2012, 2, 18), date(2012, 3, 17)]
    assert rules.monthly_expiry(dates, today) == date(2012, 2, 18)
    assert rules.monthly_expiry(dates, today, future=True) == date(2012, 2, 10)


def test_earnings_veto_uses_only_events_known_at_entry():
    today, expiry = date(2012, 1, 3), date(2012, 2, 18)
    assert not rules.earnings_veto([(date(2012, 1, 4), date(2012, 1, 9))], today, expiry)
    assert rules.earnings_veto([(today, date(2012, 1, 9))], today, expiry)
    assert not rules.earnings_veto([(today, date(2012, 2, 20))], today, expiry)


def test_reserve_uses_product_multiplier():
    assert rules.strangle_reserve(100, 90, 110, 2, 100) == 1200
    assert rules.strangle_reserve(100, 90, 110, 2, 1000) == 12000


def test_future_iv_matches_known_atm_value_and_put_call_parity():
    price, delta = rules.black76_price_delta(100, 100, 1, .2, 0)
    assert price == pytest.approx(7.9655674554)
    assert delta == pytest.approx(.5398278373)
    assert rules.black76_iv_delta(price, 100, 100, 1, 0) == pytest.approx((.2, delta))
    import math
    call, _ = rules.black76_price_delta(101, 95, .2, .3, .04)
    put, _ = rules.black76_price_delta(101, 95, .2, .3, .04, True)
    assert call-put == pytest.approx(6*math.exp(-.04*.2))
    assert rules.black76_iv_delta(put, 101, 95, .2, .04, True)[0] == pytest.approx(.3)


def test_future_iv_rejects_bad_units_negative_prices_and_no_time_value():
    assert rules.black76_iv_delta(5, 3.52, 3.5, .1, .01) == (None, None)
    assert rules.black76_iv_delta(1, -1, 100, .1, .01) == (None, None)
    assert rules.black76_iv_delta(0, 100, 105, .1, .01) == (None, None)


def test_cached_equity_screen_matches_full_validation_with_replacements_and_expiry():
    import random
    from collections import deque
    rng=random.Random(619);rows=deque(maxlen=20);fast=rules.EquityScreenWindow()
    for i in range(1000):
        day=date(2020,1,1)+timedelta(days=i//2 if i%7==0 else i)
        if i%5==0 and rows:day=rows[-1][0]  # Correct same-session replacement.
        price=rng.choice([30.,30.00000000000001,100.,0.,float('nan')])
        volume=rng.choice([5e6,5000000.000000001,7e6,-1.,float('inf')])
        point=(day,price,volume)
        if rows and rows[-1][0]==day:rows[-1]=point
        else:rows.append(point)
        fast.append(point)
        cap=rng.choice([None,0,1e9,1e9+1,1e12])
        original=rules.equity_screen(list(rows),cap)
        assert fast.screen(cap)==original
        assert fast.candidate_info(cap)==(original[1] if original[0] is None else None)
    # Evict all earlier invalid samples and check exact arithmetic at boundaries.
    for i in range(20):
        point=(date(2030,1,1)+timedelta(days=i),30.00000000000001,5000000.000000001)
        rows.append(point);fast.append(point)
    assert fast.screen(None)==rules.equity_screen(list(rows),None)
    assert fast.invalid_count==0
    assert fast.candidate_info(None)==rules.equity_screen(list(rows),None)[1]
