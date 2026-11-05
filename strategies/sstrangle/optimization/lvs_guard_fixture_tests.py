import importlib.util
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace as NS
from datetime import datetime,date,timedelta
from collections import Counter
import pytest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('guard_setup',HERE/'guarded_integration_tests.py');support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)

def setup(monkeypatch):
    actual=support.setup(monkeypatch).__class__
    guard=ModuleType('guarded_strategy');guard.ResearchShortStrangle=actual;monkeypatch.setitem(sys.modules,'guarded_strategy',guard)
    class Parent:
        def on_data(self,data):self.parent_calls+=1
        def receipt(self,note):return {'note':note}
    parent=ModuleType('lvs_original_fixture');parent.LVSExitRegression=Parent;monkeypatch.setitem(sys.modules,'lvs_original_fixture',parent)
    spec=importlib.util.spec_from_file_location('lvs_guard_tested',HERE/'lvs_guard_fixture.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.OrderStatus=NS(INVALID='invalid',CANCELED='canceled')
    a=m.LVSGuardRegression();a.CONFIG=dict(voluntary_guard=True);a.parent_calls=0
    a.pending_bind=False;a.failure_note=None;a.done=False;a.state='HELD';a.reconcile=lambda:None
    a.time=datetime(2015,8,19,9,31);a.guard_key='LVS_FIXTURE';a.positions={};a.pending_combos={};a.exit_requests={};a.counts=Counter()
    a.contracts={'put':'P','call':'C'};a.portfolio={k:NS(quantity=-2) for k in ('P','C')};a.guard_context_ready=False
    a.check_open_fills=lambda:None;a.time_exit_dte=28
    return a,m,actual

def test_control_delegates_immediately_to_original_fixture(monkeypatch):
    a,_,_=setup(monkeypatch);a.CONFIG['voluntary_guard']=False;a.on_data(None);assert a.parent_calls==1

def test_context_requires_actual_equal_held_quantity(monkeypatch):
    a,_,_=setup(monkeypatch);a.portfolio['C'].quantity=-1
    with pytest.raises(RuntimeError,match='two actual held'):a.ensure_guard_context()
    assert not a.positions and not a.guard_context_ready

def test_context_records_original_opening_economics_after_checks(monkeypatch):
    a,_,_=setup(monkeypatch);a.ensure_guard_context();t=a.positions[a.guard_key]
    assert t['quantity']==2 and t['cash']==246 and t['fees']==2.6
    assert t['expiry']==date(2015,9,18) and a.guard_context_ready

def test_before_training_observation_no_alternative_risk_path_is_implied(monkeypatch):
    a,_,_=setup(monkeypatch);a.time=datetime(2015,8,18,12)
    a.ensure_guard_context=lambda:(_ for _ in ()).throw(AssertionError('Unexpected risk start'))
    a.on_data(None);assert not a.positions and not a.parent_calls

def test_uses_actual_guarded_risk_methods_without_reimplementation(monkeypatch):
    a,_,actual=setup(monkeypatch)
    for name in ('voluntary_quote_ready','process_exit_requests','intraday_risk_exits','order_fees','close_fees'):
        assert getattr(type(a),name) is getattr(actual,name)

def test_pending_close_cannot_finalize_without_actual_phase_completion(monkeypatch):
    a,_,_=setup(monkeypatch);a.state='GUARD_MARKET';a.phase_tickets=[NS(status='submitted')];a.phase_complete=lambda:False
    a.market_deadline=a.time+timedelta(minutes=5);actions=[];a.close_filled_callback=lambda:actions.append('callback');a.finish_actual=lambda:actions.append('finish')
    a.settle_guard_orders();assert not actions

def test_pending_close_timeout_keeps_real_exposure(monkeypatch):
    a,_,_=setup(monkeypatch);a.state='GUARD_MARKET';a.phase_tickets=[NS(status='submitted')];a.phase_complete=lambda:False;a.market_deadline=a.time
    with pytest.raises(RuntimeError,match='not complete'):a.settle_guard_orders()
    assert all(s.quantity==-2 for s in a.portfolio.values())

def test_only_confirmed_fill_phase_runs_logical_callback(monkeypatch):
    a,_,_=setup(monkeypatch);a.state='GUARD_MARKET';a.phase_tickets=[NS(status='filled')];a.phase_complete=lambda:True
    actions=[];a.reconcile=lambda:actions.append('reconcile');a.close_filled_callback=lambda:actions.append('callback');a.finish_actual=lambda:actions.append('finish')
    a.settle_guard_orders();assert actions==['reconcile','callback','finish']

def test_exit_submission_checks_real_holdings_before_order(monkeypatch):
    a,_,_=setup(monkeypatch);a.portfolio['P'].quantity=-1
    with pytest.raises(RuntimeError,match='quantities changed'):a.execute(a.guard_key,[],'STOP')

def test_native_market_instruction_has_no_fabricated_price_or_limit(monkeypatch):
    a,_,_=setup(monkeypatch);seen=[];legs=[object(),object()]
    a.combo_market_order=lambda *args,**kwargs:(seen.append((args,kwargs)) or ['real-ticket-placeholder'])
    a.bind=lambda ts,phase:seen.append((ts,phase));a.execute(a.guard_key,legs,'STOP')
    assert seen[0][0]==(legs,2) and seen[0][1]['asynchronous'] is False
    assert set(seen[0][1])=={'asynchronous','tag'}
    assert a.state=='GUARD_MARKET' and a.pending_combos[a.guard_key]

def test_noon28dte_mandatory_request_reaches_same_request_processor(monkeypatch):
    a,_,_=setup(monkeypatch);a.time=datetime(2015,8,21,12);a.triggered_at=datetime(2015,8,19,9,31)
    a.ensure_guard_context=lambda:None;a.intraday_risk_exits=lambda:None;a.settle_guard_orders=lambda:None
    a.securities={k:NS(exchange=NS(exchange_open=True)) for k in ('P','C')};observed=[]
    a.process_exit_requests=lambda:observed.append(dict(a.exit_requests))
    a.on_data(None)
    assert not observed[0] and observed[-1][a.guard_key]==dict(reason='TIME',day=date(2015,8,21))
