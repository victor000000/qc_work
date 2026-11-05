"""Guard the local optimization boundary and SPX-sized engine accounting."""
import importlib.util
from pathlib import Path
import sys

import pytest

LOCAL = Path(__file__).parents[1]/'local'


@pytest.fixture
def research(monkeypatch):
    monkeypatch.syspath_prepend(str(LOCAL))
    spec=importlib.util.spec_from_file_location('single_research_test',LOCAL/'optimize_single.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_discovery_purges_cycles_with_future_outcomes(research):
    cycles=[dict(entry='2025-12-01',exit='2025-12-20'),
            dict(entry='2025-12-20',exit='2026-01-05'),
            dict(entry='2026-01-02',exit='2026-02-01')]
    train,valid=research.partition(cycles,'2025-12-31')
    assert train==cycles[:1]
    assert valid==cycles[2:]


def test_missing_feature_cannot_pass_requested_gate(research):
    f=dict(ivr=60,iv=.3,rv=None,trend_z=None)
    assert research.allowed(f,dict(ivr=50,iv_rv=None,trend=None))
    assert not research.allowed(f,dict(ivr=50,iv_rv=1.2,trend=None))
    assert not research.allowed(f,dict(ivr=50,iv_rv=None,trend=1))


def test_spx_capital_is_preserved_in_actual_engine(research,tmp_path):
    rows=[dict(order_id=1,symbol='SPX240216P04500000',timestamp='2024-01-02T20:30:00+00:00',
               quantity=-1,fee=1,expiry='2024-02-16',call_put='P',strike=4500,
               underlying='SPX',age_minutes=None),
          dict(order_id=2,symbol='SPX240216P04500000',timestamp='2024-01-03T20:30:00+00:00',
               quantity=1,fee=1,expiry='2024-02-16',call_put='P',strike=4500,
               underlying='SPX',age_minutes=None)]
    _,audit=research.run_engine(rows,{1:10,2:8},tmp_path/'engine',initial_cash=2500000)
    assert audit['engine_executions']==2
    assert audit['engine_net_pnl']==198
    assert audit['final_equity']==2500198
