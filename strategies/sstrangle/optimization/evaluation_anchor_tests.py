"""Missing evaluation capital must never be replaced by original funded cash."""
import importlib.util
from pathlib import Path
from datetime import date
spec=importlib.util.spec_from_file_location('anchor_report',Path(__file__).with_name('report.py'));r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

def run(daily):
    plan=dict(evaluation_start='2020-01-01',end='2026-09-30',initial_cash=60000,minimum_closed_cycles=100,minimum_evaluation_cycles=20)
    summary=dict(account=dict(reported_mdd=.1,window_end_observed=True,positive_equity=True,calmar=3),period_complete=True,cycles=100)
    cycles=[dict(exit='2026-09-29T16:00:00Z') for _ in range(20)]
    return r.evaluation_result('a',summary,daily,cycles,dict(chosen_variant='a'),plan)

def test_absent_opening_equity_cannot_manufacture_evaluation_return():
    result=run({date(2026,1,2):200000,date(2026,9,30):210000})
    assert not result['target_flag']
    assert not result['evaluation']['window_opening_anchor_verified']
    assert result['evaluation']['cagr'] is None and result['evaluation']['calmar'] is None

def test_old_prior_observation_is_not_the_evaluation_opening_balance():
    result=run({date(2019,11,1):60000,date(2020,1,2):200000,date(2026,9,30):210000})
    assert not result['evaluation']['available'] and not result['target_flag']

def test_actual_last_completed_session_equity_is_used():
    result=run({date(2019,12,31):200000,date(2020,1,2):200000,date(2026,9,30):210000})
    assert result['evaluation']['window_opening_anchor_verified']
    assert result['evaluation']['opening_equity']==200000
    assert result['evaluation']['net_pnl']==10000
    assert not result['target_flag']
