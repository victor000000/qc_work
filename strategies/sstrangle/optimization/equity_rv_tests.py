from datetime import datetime,timedelta,date
from types import SimpleNamespace as NS
from collections import Counter
from pathlib import Path
import ast,math
import pytest
from equity_rv_features import equity_features,equity_rv_admitted
from completed_volatility import VolatilityFeatures
from build_equity_rv_source import render,PARENT
LOCAL=datetime(2020,9,2,12)
def bars():
 ds=[date(2020,6,1)+timedelta(days=i) for i in range(61)]
 bs=[NS(symbol=NS(id='native'),end_time=datetime.combine(d,datetime.min.time())+timedelta(hours=16),close=100+(-1)**i+i,is_fill_forward=False) for i,d in enumerate(ds)];return ds,bs

def test_source_requires_every_expected_prior_session():
 ds,bs=bars();f=equity_features(bs,'native',LOCAL,ds,.4);assert f.ready and f.closes==61
 assert not equity_features(bs[:-1],'native',LOCAL,ds,.4).ready
@pytest.mark.parametrize('kind',['identity','forward','current'])
def test_source_safety_checks_remain_fatal(kind):
 ds,bs=bars()
 if kind=='identity':bs[-1].symbol=NS(id='other')
 if kind=='forward':bs[-1].is_fill_forward=True
 if kind=='current':bs[-1].end_time=LOCAL
 with pytest.raises(ValueError):equity_features(bs,'native',LOCAL,ds,.4)
def test_ratio_boundary_and_invalid_gate_never_auto_admit():
 f=VolatilityFeatures(61,60,.2,.25,1.2,True,'ready')
 assert equity_rv_admitted(f,1.2) and not equity_rv_admitted(f,1.20000001)
 for t in [True,0,float('nan'),float('inf')]:
  with pytest.raises(ValueError):equity_rv_admitted(f,t)
def test_generated_source_changes_only_declared_methods_and_uses_gate():
 p=ast.parse(PARENT.read_text());s=render();r=ast.parse(s)
 def methods(t):return {n.name:ast.dump(n,include_attributes=False) for c in t.body if isinstance(c,ast.ClassDef) for n in c.body if isinstance(n,ast.FunctionDef)}
 a,b=methods(p),methods(r)
 assert {k for k in a if a[k]!=b[k]}=={'initialize','prepare_day'}
 assert set(b)-set(a)=={'equity_rv_for','admit_equity_rv'}
 assert "if not self.admit_equity_rv(candidate,statistics):\n                continue\n            legs = self.selected_legs" in s
 assert "self.settings.daily_precise_end_time=True" in s
 assert "from equity_rv_features import" in s

def gate_method():
 tree=ast.parse(render());f=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='admit_equity_rv');namespace={'equity_rv_admitted':equity_rv_admitted};exec(compile(ast.Module(body=[f],type_ignores=[]),'<actual_admission_method>','exec'),namespace);return namespace['admit_equity_rv']
def test_actual_strategy_method_blocks_bad_equity_and_annotates_allowed():
 f=VolatilityFeatures(61,60,.2,.25,1.2,True,'ready');self=NS(CONFIG={'min_equity_iv_rv':1.2},time=LOCAL,counts=Counter(),decision=lambda *a:None,equity_rv_for=lambda *a:(f,date(2020,9,1)))
 candidate={'future':False,'eq':'native','key':'native'};stats={'last_day':str(LOCAL.date()),'iv':.3}
 assert gate_method()(self,candidate,stats) and stats['rv_samples']==61 and stats['rv_threshold']==1.2
 self.CONFIG['min_equity_iv_rv']=1.3;assert not gate_method()(self,candidate,dict(last_day=str(LOCAL.date()),iv=.3))
def test_all_futures_bypass_new_filter_explicitly_without_reading_price_features():
 def fail(*a):raise AssertionError('Futures must not use unvalidated RV')
 self=NS(counts=Counter(),equity_rv_for=fail);stats={}
 assert gate_method()(self,{'future':True},stats) and stats=={'rv_policy':'future_original_rules'}
