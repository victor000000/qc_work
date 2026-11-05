from datetime import date
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from history_report import performance_window, coverage_count, effective_start, decision_records


def test_no_iv_gate_performance_includes_early_trades():
    config = dict(trade_start=[2009,1,2], iv_min=None)
    assert effective_start(config, {}) == date(2009,1,2)
    config['iv_min'] = 50
    assert effective_start(config, {'first_ivr_ready_SPY':'2009-01-07'}) == date(2009,1,7)


def test_annual_decision_evidence_cannot_silently_overwrite_duplicates():
    line = '2026-09-30 15:30:00 ENTRY_DECISIONS {"ticker":"SPY","year":2017,"counts":{"invested":200,"entry_submitted":12}}'
    assert decision_records(line)[0]['counts']['entry_submitted'] == 12
    with pytest.raises(ValueError,match='Duplicate'):
        decision_records(line+'\n'+line)


def test_window_uses_preceding_nav_and_excludes_missing_history():
    daily={date(2009,1,2):100,date(2012,12,31):120,date(2013,1,2):108,
           date(2013,12,31):132,date(2014,1,2):1}
    metrics=performance_window(daily,100,date(2013,1,2),date(2013,12,31))
    assert metrics['opening_equity']==120
    assert metrics['observations']==2
    assert metrics['net_pnl']==12
    assert metrics['return_fraction']==pytest.approx(.1)
    assert metrics['max_daily_drawdown']==pytest.approx(.1)
    assert metrics['cagr']>metrics['return_fraction']  # slightly less than one year


def test_missing_history_is_not_reported_as_zero_risk_performance():
    with pytest.raises(ValueError,match='requires observations'):
        performance_window({},250000,date(2009,1,2),date(2012,12,31))


def test_absent_coverage_counter_is_unknown_not_zero():
    assert coverage_count({},'chain_days_SPY_2009') is None
    assert coverage_count({'chain_days_SPY_2009':'0'},'chain_days_SPY_2009') == 0
    assert coverage_count({'chain_days_SPY_2009':'252'},'chain_days_SPY_2009') == 252
