from pathlib import Path
import sys
from datetime import datetime,date
from types import ModuleType,SimpleNamespace as NS
from collections import Counter
import importlib.util
import pytest

ROOT=Path(__file__).parents[1]
sys.path.insert(0,str(ROOT/'optimization'))
from risk_rules import collateral_budget,capped_candidates,capped_quantity,validate_risk


def test_single_symbol_does_not_consume_full_equity():
    assert collateral_budget(60000,1,.2,.05)==3000
    assert capped_quantity(60000,1,1002,60000,.2,.05)==2
    assert collateral_budget(60000,13,.2,.05)==pytest.approx(12000/13)


def test_membership_reaches_fixed_point_before_freezing_budget():
    rows=[dict(key='A',volume=3,unit_cost=1200),dict(key='B',volume=2,unit_cost=4000),dict(key='C',volume=1,unit_cost=1600)]
    selected,n=capped_candidates(rows,0,60000,13,.2,.05)
    assert n==2 and [r['key'] for r in selected]==['A','C']
    with pytest.raises(ValueError):capped_candidates(rows,1,60000,13,.2,.05)


def test_smaller_affordable_basket_is_not_discarded_after_rejecting_thirteen():
    rows=[dict(key=str(i),volume=100-i,unit_cost=1000) for i in range(13)]
    selected,count=capped_candidates(rows,0,60000,13,.2,.05)
    assert count==12 and [r['key'] for r in selected]==[str(i) for i in range(12)]
    assert sum(r['unit_cost'] for r in selected)==12000


def test_unaffordable_high_volume_name_does_not_hide_other_eligible_names():
    rows=[dict(key='expensive',volume=1000,unit_cost=4000)]+[
        dict(key=str(i),volume=100-i,unit_cost=900) for i in range(13)]
    selected,count=capped_candidates(list(reversed(rows)),0,60000,13,.2,.05)
    assert count==13 and [r['key'] for r in selected]==[str(i) for i in range(13)]


def test_capped_selection_matches_exhaustive_feasible_portfolios():
    from itertools import combinations
    import random
    rng=random.Random(21)
    for _ in range(30):
        rows=[dict(key=str(i),volume=100-i,unit_cost=rng.choice([500,1000,2000,4000])) for i in range(6)]
        feasible=[subset for count in range(1,7) for subset in combinations(rows,count)
            if all(r['unit_cost']<=min(60000*.2/count,60000*.05) for r in subset)]
        chosen,count=capped_candidates(list(reversed(rows)),0,60000,13,.2,.05)
        expected=min(feasible,key=lambda subset:(-len(subset),tuple(-r['volume'] for r in subset))) if feasible else ()
        assert count==len(expected) and [r['key'] for r in chosen]==[r['key'] for r in expected]


@pytest.mark.parametrize('value',[0,-1,float('nan'),float('inf')])
def test_invalid_cost_cannot_create_a_position(value):
    assert capped_quantity(60000,1,value,60000,.2,.05)==0


def test_bad_risk_config_is_rejected():
    with pytest.raises(ValueError):validate_risk(.2,1,1,15)
    with pytest.raises(ValueError):validate_risk(.2,.05,0,15)


def load_research(monkeypatch):
    imports=ModuleType('AlgorithmImports');imports.QCAlgorithm=object
    monkeypatch.setitem(sys.modules,'AlgorithmImports',imports)
    for name,path in [('rules',ROOT/'project/rules.py'),('execution_base',ROOT/'project/main.py'),
       ('basket_rules',ROOT/'basket/basket_rules.py'),('research_risk_rules',ROOT/'optimization/risk_rules.py'),
       ('research_module',ROOT/'optimization/main.py')]:
        spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules,name,m);spec.loader.exec_module(m)
    a=m.ResearchShortStrangle();a.CONFIG=dict(total_collateral_fraction=.2,per_symbol_collateral_fraction=.05,stop_multiple=1.,risk_interval_minutes=15)
    a.time_exit_dte=21 # initialize() sets this in LEAN; this harness constructs without initialization.
    a.time=datetime(2014,6,20,10,1);a.end=date(2026,9,30);a.insolvency=None
    a.positions={'A':dict(put='P',call='C',expiry=date(2014,7,31),quantity=2,multiplier=100,cash=200,fees=4,initial=200)}
    a.securities={k:NS(ask_price=1.1,exchange=NS(exchange_open=True)) for k in ('P','C')}
    a.counts=Counter();a.pending_combos={};a.exit_requests={};a.last_risk_check=None
    a.good_quote=lambda x:True;a.close_fees=lambda t:4;a.process_exit_requests=lambda:None
    return a


def test_stop_is_evaluated_before_noon_and_does_not_reset_credit(monkeypatch):
    a=load_research(monkeypatch);a.intraday_risk_exits()
    assert a.exit_requests=={'A':dict(reason='STOP',day=a.time.date())}
    assert a.positions['A']['initial']==200


def test_intraday_check_preserves_noon_21dte_exit_priority(monkeypatch):
    a=load_research(monkeypatch);a.positions['A']['expiry']=date(2014,7,11)
    a.intraday_risk_exits();assert not a.exit_requests
    a.positions['A']['expiry']=date(2014,7,31);a.time=datetime(2014,6,20,10,2)
    a.intraday_risk_exits();assert not a.exit_requests
    a.time=datetime(2014,6,20,10,16);a.intraday_risk_exits();assert a.exit_requests['A']['reason']=='STOP'


@pytest.mark.parametrize('threshold,expiry,should_stop',[(28,date(2014,7,18),False),(28,date(2014,7,19),True),(21,date(2014,7,18),True)])
def test_configured_time_exit_retains_priority_over_intraday_stop(monkeypatch,threshold,expiry,should_stop):
    a=load_research(monkeypatch);a.time_exit_dte=threshold;a.positions['A']['expiry']=expiry
    a.intraday_risk_exits()
    assert bool(a.exit_requests)==should_stop
    if should_stop:assert a.exit_requests['A']['reason']=='STOP'
