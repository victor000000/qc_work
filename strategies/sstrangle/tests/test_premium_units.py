"""Regression of the exact failed CL submission units and repair boundaries."""
from collections import Counter
from datetime import datetime,date
import importlib.util
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace as NS
import pytest


@pytest.fixture
def units(monkeypatch):
    root=Path(__file__).parents[1]/'basket'
    imports=ModuleType('AlgorithmImports')
    class Quote:
        def GetHashCode(self):return id(self)
    class Trade:
        def GetHashCode(self):return id(self)
    imports.SecurityDataFilter=object;imports.QuoteBar=Quote;imports.TradeBar=Trade
    monkeypatch.setitem(sys.modules,'AlgorithmImports',imports)
    loaded=[]
    for name in ('premium_units','premium_filter'):
        spec=importlib.util.spec_from_file_location(name,root/(name+'.py'));m=importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules,name,m);spec.loader.exec_module(m);loaded.append(m)
    return loaded,imports


def test_unit_fix_is_bounded_to_confirmed_root_and_sessions(units):
    (u,_),_=units
    assert u.premium_factor('LO','CL',date(2015,12,18))==1
    assert u.premium_factor('LO','CL',date(2015,12,21))==.01
    assert u.premium_factor('LO','CL',date(2015,12,24))==.01
    assert u.premium_factor('LO','CL',date(2015,12,28))==1
    for root,underlying in [('LO','OTHER'),('OZN','ZN'),('CL','CL')]:
        assert u.premium_factor(root,underlying,date(2015,12,21))==1


def test_original_failed_quote_is_normalized_once_before_margin(units):
    (_,f),imports=units;counts=Counter();model=f.PremiumUnitFilter(counts)
    q=imports.QuoteBar();q.time=datetime(2015,12,21,8,30);q.end_time=datetime(2015,12,21,8,31)
    q.is_fill_forward=False
    q.bid=NS(open=317.,high=317.,low=317.,close=317.)
    q.ask=NS(open=321.,high=321.,low=321.,close=321.);q.value=319.
    security=NS(symbol=NS(id=NS(symbol='LO'),underlying=NS(id=NS(symbol='CL'))),
                symbol_properties=NS(contract_multiplier=1000))
    assert model.filter(security,q)
    assert q.bid.close==pytest.approx(3.17) and q.ask.close==pytest.approx(3.21)
    assert q.value==pytest.approx(3.19)
    assert q.ask.close*security.symbol_properties.contract_multiplier==pytest.approx(3210)
    assert model.filter(security,q) and q.value==pytest.approx(3.19)
    q.is_fill_forward=True
    assert model.filter(security,q) and q.value==pytest.approx(3.19)
    assert counts['unit_repaired_quote_bars']==1


def test_trade_bar_and_open_interest_semantics(units):
    (_,f),imports=units;counts=Counter();model=f.PremiumUnitFilter(counts)
    security=NS(symbol=NS(id=NS(symbol='LO'),underlying=NS(id=NS(symbol='CL'))))
    t=imports.TradeBar();t.time=datetime(2015,12,23,12);t.end_time=t.time;t.is_fill_forward=False
    t.open=310.;t.high=320.;t.low=300.;t.close=315.;t.volume=25
    assert model.filter(security,t) and t.close==pytest.approx(3.15) and t.volume==25
    oi=NS(is_fill_forward=False,value=10000)
    assert model.filter(security,oi) and oi.value==10000
    assert counts['unit_repaired_trade_bars']==1
