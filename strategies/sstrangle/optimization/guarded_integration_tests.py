"""Exercise actual prospective methods with a minimal LEAN object harness."""
import ast
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS
from datetime import date,timedelta
import pytest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('guard_harness',HERE.parent/'tests/test_research_risk.py');harness=importlib.util.module_from_spec(spec);spec.loader.exec_module(harness)

class Quote:pass

def setup(monkeypatch):
    a=harness.load_research(monkeypatch);sys.modules['AlgorithmImports'].QuoteBar=Quote
    spec=importlib.util.spec_from_file_location('guarded_research',HERE/'guarded_main.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    a.__class__=m.ResearchShortStrangle;del a.process_exit_requests
    a.states={'A':dict(future=False)};a.sent=[]
    a.execute=lambda key,legs,reason,on_filled=None:a.sent.append((key,reason))
    m.Leg=NS(create=lambda symbol,quantity:(symbol,quantity))
    for key,sec in a.securities.items():
        sec.symbol=NS(id=key);sec.local_time=a.time;sec.bid_price=1.0
        sec.symbol_properties=NS(minimum_price_variation=.01)
        bar=NS(end_time=a.time,is_fill_forward=False,ask=NS(close=sec.ask_price))
        sec.bar=bar;sec.cache=NS(get_data={Quote:lambda bar=bar:bar})
    return a

def request(a,reason='STOP',day=None):a.exit_requests={'A':dict(reason=reason,day=day or a.time.date())}
def wide(a):a.securities['P'].ask_price=62.;a.securities['P'].bar.ask.close=62.

def test_wide_equity_stop_not_submitted_and_position_retained(monkeypatch):
    a=setup(monkeypatch);wide(a);request(a);a.process_exit_requests()
    assert not a.sent and not a.exit_requests and 'A' in a.positions
    assert a.securities['P'].ask_price==62.

def test_normal_stop_submits_original_native_pair(monkeypatch):
    a=setup(monkeypatch);request(a);a.process_exit_requests()
    assert a.sent==[('A','STOP')] and not a.exit_requests

def test_fresh_tiny_zero_bid_buyback_is_allowed_only_on_voluntary_branch(monkeypatch):
    a=setup(monkeypatch);sec=a.securities['P'];sec.bid_price=0;sec.ask_price=.01;sec.bar.ask.close=.01
    request(a);a.process_exit_requests();assert a.sent==[('A','STOP')]

@pytest.mark.parametrize('reason',['TIME','END','SPLIT','MARGIN'])
def test_nonvoluntary_request_never_uses_spread_guard(monkeypatch,reason):
    a=setup(monkeypatch);wide(a);request(a,reason)
    a.voluntary_quote_ready=lambda key:(_ for _ in ()).throw(AssertionError('Guard reached mandatory path'))
    a.process_exit_requests();assert a.sent==[('A',reason)]

def test_mandatory_stale_quotes_still_wait_instead_of_fabricating_fills(monkeypatch):
    a=setup(monkeypatch);request(a,'TIME');a.good_quote=lambda security:False;a.process_exit_requests()
    assert not a.sent and a.exit_requests['A']['reason']=='TIME'

def test_missed_mandatory_session_still_fails(monkeypatch):
    a=setup(monkeypatch);request(a,'TIME',a.time.date()-timedelta(days=1))
    with pytest.raises(RuntimeError,match='Mandatory exit lacked fresh quotes'):a.process_exit_requests()

def test_futures_stop_preserves_existing_execution_without_guard(monkeypatch):
    a=setup(monkeypatch);a.states['A']['future']=True;request(a);wide(a)
    a.voluntary_quote_ready=lambda key:(_ for _ in ()).throw(AssertionError('Equity guard reached FOP'))
    a.process_exit_requests();assert a.sent==[('A','STOP')]

def test_pending_combo_and_its_request_never_removed(monkeypatch):
    a=setup(monkeypatch);wide(a);request(a);a.pending_combos={'A':object()};a.process_exit_requests()
    assert 'A' in a.pending_combos and 'A' in a.exit_requests and not a.sent

@pytest.mark.parametrize('superseded',['past_day','time_due','end','split'])
def test_unsubmitted_voluntary_request_cannot_override_mandatory_management(monkeypatch,superseded):
    a=setup(monkeypatch);request(a)
    if superseded=='past_day':a.exit_requests['A']['day']-=timedelta(days=1)
    elif superseded=='time_due':a.positions['A']['expiry']=a.time.date()+timedelta(days=a.time_exit_dte)
    elif superseded=='end':a.end=a.time.date()
    else:a.states['A']['split_warning']=True
    a.process_exit_requests();assert not a.sent and not a.exit_requests and 'A' in a.positions

def test_wide_intraday_mark_cannot_itself_generate_a_stop_request(monkeypatch):
    a=setup(monkeypatch);wide(a);a.intraday_risk_exits()
    assert not a.exit_requests and not a.sent

def test_entry_roll_broker_and_accounting_methods_unchanged():
    def methods(path):
        tree=ast.parse(path.read_text());c=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ResearchShortStrangle')
        return {n.name:ast.dump(n,include_attributes=False) for n in c.body if isinstance(n,ast.FunctionDef)}
    original=methods(HERE/'main.py');guarded=methods(HERE/'guarded_main.py')
    changed={name for name in original if original[name]!=guarded[name]}
    assert changed=={'on_data','intraday_risk_exits','process_exit_requests'}
    assert set(guarded)-set(original)=={'voluntary_quote_ready'}
