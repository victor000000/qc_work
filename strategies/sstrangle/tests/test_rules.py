import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('strangle_rules', Path(__file__).parents[1] / 'project/rules.py')
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)


def test_disabled_iv_gate_differs_from_zero_threshold():
    assert rules.iv_entry_rejection(None, None) is None
    assert rules.iv_entry_rejection(0, None) is None
    assert rules.iv_entry_rejection(None, 0) == 'ivr_unavailable'
    assert rules.iv_entry_rejection(float('nan'), 50) == 'ivr_unavailable'
    assert rules.iv_entry_rejection(49.99, 50) == 'ivr_below_threshold'
    assert rules.iv_entry_rejection(50, 50) is None


def test_rank_requires_history_and_uses_only_supplied_past():
    assert rules.iv_rank(0.3, [0.1, 0.2], 3) is None
    assert rules.iv_rank(0.3, [0.1, 0.2, 0.5], 3) == 50
    assert rules.iv_rank(0.8, [0.1, 0.2, 0.5], 3) == 100
    assert rules.iv_rank(0.3, [0.2]*3, 3) is None


def test_targets_include_roll_cash_and_fees_not_each_leg_profit():
    assert rules.close_reason(300, 4, 145, 300, 30) == 'PROFIT'
    assert rules.close_reason(300, 6, 145, 300, 30) is None
    assert rules.close_reason(350, 6, 190, 300, 30) == 'PROFIT'
    assert rules.close_reason(300, 4, 900, 300, 30) == 'STOP'
    assert rules.close_reason(300, 4, 150, 300, 21) == 'TIME'
    assert rules.close_reason(300, 4, 150, 300, 30, True) == 'END'


def test_roll_untested_side_from_short_position_delta():
    assert rules.roll_side(-0.05, 0.40) == 'put'
    assert rules.roll_side(-0.40, 0.05) == 'call'
    assert rules.roll_side(-0.18, 0.18) is None


def test_correlation_aligns_dates_and_rejects_inadequate_history():
    a = {i: i/100 for i in range(65)}
    b = {i: -i/100 for i in range(5, 70)}
    assert abs(rules.correlation(a, b) + 1) < 1e-10
    assert rules.correlation(a, {i: i for i in range(20)}) is None


def test_tighter_stop_is_a_loss_multiple_not_a_buyback_multiple():
    assert rules.close_reason(300, 4, 600, 300, 30, stop_multiple=1) == 'STOP'
    assert rules.close_reason(300, 4, 600, 300, 30) is None


def test_features_use_only_trailing_twenty_observations():
    past = [0.01, -0.01] * 10
    rv, trend = rules.return_features(past)
    assert rv > 0 and abs(trend) < 0.1
    assert rules.return_features([0.9]*10 + past) == (rv, trend)
    assert rules.return_features(past[:19]) == (None, None)
    assert rules.return_features([0.0]*20) == (None, None)


def test_symmetric_trend_filter_and_relative_volatility_filter():
    assert rules.entry_filter_reason(.24, .2, .5, min_iv_rv=1.2) is None
    assert rules.entry_filter_reason(.23, .2, .5, min_iv_rv=1.2) == 'premium_rejected'
    assert rules.entry_filter_reason(.24, .2, 1.01, max_trend_z=1) == 'trend_rejected'
    assert rules.entry_filter_reason(.24, .2, -1.01, max_trend_z=1) == 'trend_rejected'
    assert rules.entry_filter_reason(None, None, None) is None
    assert rules.entry_filter_reason(.24, None, None, min_iv_rv=1.2) == 'premium_rejected'
