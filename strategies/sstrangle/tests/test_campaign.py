import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('strangle_campaign', Path(__file__).parents[1] / 'campaign.py')
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


def row(label, cycles, pnl, dd=.02, rolls=10):
    return dict(name='SSTRANGLE_example_'+label, closed_cycles=str(cycles),
                cycle_net_pnl=str(pnl), active_daily_mdd=str(dd), rolls=str(rolls))


def test_selection_rejects_high_profit_with_insufficient_trades():
    result = campaign.choose([row('edge', 9, 10000), row('trend', 10, -100)],
                             {'edge': {'min_iv_rv': 1.2}, 'trend': {'max_trend_z': 1}})
    assert result['candidate_label'] == 'trend'
    assert result['candidate_config'] == {'max_trend_z': 1}


def test_selection_uses_predeclared_tiebreakers():
    result = campaign.choose([row('stop1', 12, 100, .02), row('edge', 12, 100, .01)],
                             {'stop1': {'stop_multiple': 1}, 'edge': {'min_iv_rv': 1.2}})
    assert result['candidate_label'] == 'edge'
    with pytest.raises(ValueError, match='No candidate'):
        campaign.choose([row('edge', 9, 10000)], {'edge': {}})
