"""Regressions for calendar scheduling and real basket execution paths."""
from collections import Counter
from datetime import date, datetime
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
import pytest


@pytest.fixture
def basket(monkeypatch):
    imports=ModuleType('AlgorithmImports')
    imports.QCAlgorithm=object
    monkeypatch.setitem(sys.modules,'AlgorithmImports',imports)
    root=Path(__file__).parents[1]
    for name,path in [('rules',root/'project/rules.py'),('execution_base',root/'project/main.py'),
                      ('basket_rules',root/'basket/basket_rules.py'),('basket_test',root/'basket/main.py')]:
        spec=importlib.util.spec_from_file_location(name,path)
        module=importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules,name,module)
        spec.loader.exec_module(module)
    a=module.BasketShortStrangle()
    a.process_pending_combos=lambda:None
    a.process_exit_requests=lambda:None
    a.time=datetime(2012,2,6,9,31)
    a.due=True
    a.last_day=None
    a.positions={}
    a.pending_combos={}
    a.exit_requests={}
    a.batch_id=0
    a.monthly_cache={}
    a.trade_start=date(2012,1,3)
    a.spy='SPY'
    a.securities={'SPY':NS(exchange=NS(exchange_open=True))}
    a.prepared_day=date(2012,2,3)
    a.prepared=[{'key':'OLD_FRIDAY_CANDIDATE'}]
    a.active_equity=[]
    a.portfolio=NS(total_portfolio_value=250000)
    a.counts=Counter()
    a.plot=lambda *args:None
    return a


def test_weekend_trigger_cannot_shift_daily_execution_to_next_open(basket):
    basket.on_data(None)
    assert basket.last_day is None
    assert not basket.active_equity
    basket.time=datetime(2012,2,6,12,0)
    basket.on_data(None)
    assert basket.last_day==date(2012,2,6)
    assert len(basket.active_equity)==1
    assert not basket.due


def test_repeated_trigger_does_not_duplicate_daily_snapshot(basket):
    basket.time=datetime(2012,2,6,12,0)
    basket.on_data(None)
    basket.due=True
    basket.time=datetime(2012,2,6,12,1)
    basket.on_data(None)
    assert len(basket.active_equity)==1


def test_equal_budget_entry_sizes_both_legs_without_resizing_existing_position(basket,monkeypatch):
    monkeypatch.setattr(sys.modules['basket_test'],'Leg',NS(create=lambda symbol,quantity:(symbol,quantity)),raising=False)
    basket.positions={'HELD':{'quantity':7}}
    basket.states={'NEW':{'future':False}}
    basket.portfolio.margin_remaining=60000
    for symbol in ('P','C'):
        basket.securities[symbol]=NS(symbol=symbol,symbol_properties=NS(contract_multiplier=100))
    basket.securities['U']=NS(price=100)
    basket.liquid_security=lambda security:True
    basket.initial_margin=lambda securities,quantity:1000*quantity
    basket.order_fees=lambda securities,quantity:2*abs(quantity)
    basket.decision=lambda *args:None
    submitted=[]
    def capture(self,key,legs,reason,on_filled=None,quantity=1):
        submitted.append((key,legs,reason,quantity))
    monkeypatch.setattr(sys.modules['execution_base'].TranscriptShortStrangle,'execute',capture)
    candidate=dict(key='NEW',eq='U',legs={'put':dict(symbol='P',delta=-.19),
        'call':dict(symbol='C',delta=.19)},unit_cost=1002,statistics={'ivr':80},
        volume=100000,expiry=date(2012,3,17))
    basket.open_candidate(candidate,2,60000)
    assert basket.positions['HELD']['quantity']==7
    assert basket.positions['NEW']['quantity']==29
    assert submitted==[('NEW',[('P',-1),('C',-1)],'OPEN',29)]
    assert 'allocation_budget=30000.0' in basket.positions['NEW']['entry_metadata']
    basket.time=datetime(2012,2,25,12,0)
    basket.good_quote=lambda security:True
    basket.exit_requests={'NEW':dict(reason='TIME',day=basket.time.date())}
    type(basket).process_exit_requests(basket)
    assert submitted[-1]==('NEW',[('P',1),('C',1)],'TIME;multiplier=100.0',29)


def test_no_replacement_entry_while_previous_batch_has_a_position(basket):
    basket.time=datetime(2012,2,6,12,0)
    basket.prepared_day=basket.time.date()
    basket.positions={'HELD':dict(put='P',call='C')}
    basket.securities.update({s:NS(exchange=NS(exchange_open=False)) for s in ('P','C')})
    basket.prepared=[{'key':'NEW'}]  # Intentionally incomplete: must never reach sizing.
    basket.on_data(None)
    assert set(basket.positions)=={'HELD'}
    assert basket.batch_id==0


def test_credit_roll_is_skipped_if_margin_increase_cannot_be_funded(basket):
    old=NS(symbol='OLD',ask_price=1)
    new=NS(symbol='NEW',bid_price=1.1,symbol_properties=NS(minimum_price_variation=.01))
    basket.securities.update(OLD=old,NEW=new)
    basket.positions={'A':dict(put='OLD',quantity=10,cash=100)}
    basket.portfolio.margin_remaining=50
    basket.liquid_security=lambda security:True
    basket.initial_margin=lambda securities,quantity:1000 if securities[0] is old else 1100
    basket.order_fees=lambda *args:1
    decisions=[]
    basket.decision=lambda *args:decisions.append(args)
    basket.execute=lambda *args,**kwargs:pytest.fail('Unaffordable roll submitted')
    basket.submit_roll('A','put',dict(symbol='NEW'))
    assert decisions==[('A','roll_margin')]


def test_margin_call_closes_whole_pair_once_and_keeps_other_positions(basket,monkeypatch):
    monkeypatch.setattr(sys.modules['basket_test'],'Leg',NS(create=lambda s,q:(s,q)),raising=False)
    basket.positions={'A':dict(put='P',call='C',quantity=7,multiplier=100),
                      'B':dict(put='BP',call='BC',quantity=2,multiplier=100)}
    basket.states={'A':{'future':False},'B':{'future':False}}
    basket.securities.update(P=NS(),C=NS())
    basket.good_quote=lambda s:True
    basket.portfolio.margin_remaining=100
    basket.log=lambda msg:None
    submitted=[]
    def capture(self,key,legs,reason,on_filled=None,quantity=1):
        submitted.append((key,legs,reason,quantity))
        del self.positions[key]
    monkeypatch.setattr(sys.modules['execution_base'].TranscriptShortStrangle,'execute',capture)
    basket.process_exit_requests=lambda:type(basket).process_exit_requests(basket)
    requests=[NS(symbol='P'),NS(symbol='C')]
    assert basket.on_margin_call(requests) is requests
    assert submitted==[('A',[('P',1),('C',1)],'MARGIN;multiplier=100',7)]
    assert set(basket.positions)=={'B'}
    assert basket.counts['margin_call_events']==1


def test_margin_call_cannot_silently_suppress_unknown_or_stale_liquidation(basket):
    basket.positions={'A':dict(put='P',call='C')}
    with pytest.raises(RuntimeError,match='Untracked'):
        basket.on_margin_call([NS(symbol='OTHER')])
    basket.states={'A':{'future':False},'B':{'future':False}}
    basket.securities.update(P=NS(),C=NS())
    basket.good_quote=lambda s:False
    with pytest.raises(RuntimeError,match='fresh paired quotes'):
        basket.on_margin_call([NS(symbol='P')])
    basket.pending_combos={'A':{}}
    with pytest.raises(RuntimeError,match='overlaps'):
        basket.on_margin_call([NS(symbol='P')])


def test_margin_hook_cannot_return_obsolete_requests_without_restoring_buying_power(basket):
    basket.positions={'A':dict(put='P',call='C')}
    basket.states={'A':{'future':False},'B':{'future':False}}
    basket.securities.update(P=NS(),C=NS())
    basket.good_quote=lambda s:True
    basket.portfolio.margin_remaining=-100
    basket.log=lambda msg:None
    basket.process_exit_requests=lambda:basket.exit_requests.clear()
    with pytest.raises(RuntimeError,match='restore buying power'):
        basket.on_margin_call([NS(symbol='P')])


def test_daily_chain_repair_uses_source_session_not_next_day_label(basket,monkeypatch):
    root=Path(__file__).parents[1]
    spec=importlib.util.spec_from_file_location('premium_units',root/'basket/premium_units.py')
    units=importlib.util.module_from_spec(spec);spec.loader.exec_module(units)
    monkeypatch.setitem(sys.modules,'premium_units',units)
    monkeypatch.setattr(sys.modules['basket_test'],'OptionRight',NS(PUT='P'),raising=False)
    symbol=NS(id=NS(symbol='LO'),underlying=NS(id=NS(symbol='CL')))
    record=NS(symbol=symbol,expiry=datetime(2016,1,14),strike=38,right='P',last_price=319,
        underlying_last_price=35,implied_volatility=0,greeks=NS(delta=0),open_interest=1000,
        time=datetime(2015,12,22))
    assert basket.contract_record(record,True)['price']==pytest.approx(3.19)
    # December24 is still affected when its completed daily record is labelled25.
    record.time=datetime(2015,12,25)
    assert basket.contract_record(record,True)['price']==pytest.approx(3.19)
    # Normal prices on December28 must not be divided on their December29 label.
    record.time=datetime(2015,12,29);record.last_price=2.8
    assert basket.contract_record(record,True)['price']==pytest.approx(2.8)


def test_daily_chain_cache_is_date_and_delivery_specific_and_drops_unused_long_tenor(basket):
    from datetime import timedelta
    today=basket.time.date();reads=[]
    contracts=[NS(symbol='MONTHLY',expiry=datetime.combine(today+timedelta(days=45),datetime.min.time())),
        NS(symbol='LONG',expiry=datetime.combine(today+timedelta(days=120),datetime.min.time())),
        NS(symbol='WEEKLY',expiry=datetime.combine(today+timedelta(days=40),datetime.min.time()))]
    basket.option_chain=lambda delivery:reads.append(delivery) or contracts
    basket.is_monthly=lambda symbol,future:symbol!='WEEKLY'
    basket.contract_record=lambda c,future:dict(symbol=c.symbol)
    assert basket.records_for('ZW_U17',True)==[dict(symbol='MONTHLY')]
    assert basket.records_for('ZW_U17',True)==[dict(symbol='MONTHLY')]
    basket.records_for('ZW_Z17',True)
    assert reads==['ZW_U17','ZW_Z17']
    basket.time+=timedelta(days=1)
    basket.records_for('ZW_U17',True)
    assert reads==['ZW_U17','ZW_Z17','ZW_U17']


def test_future_model_cache_recomputes_changed_price_and_observed_date(basket,monkeypatch):
    from datetime import timedelta
    calls=[];rates=[]
    monkeypatch.setattr(sys.modules['basket_test'],'black76_iv_delta',
        lambda *args:calls.append(args) or ((None,None) if args[0]==0 else (.3,.19)))
    basket.risk_free_interest_rate_model=NS(get_interest_rate=lambda observed:rates.append(observed) or .03)
    record=dict(future=True,price=1,spot=100,strike=110,observed=basket.time.date(),
        expiry=basket.time.date()+timedelta(days=45),put=False)
    basket.model_record(record);basket.model_record(record)
    assert len(calls)==len(rates)==1
    record['price']=0;basket.model_record(record);basket.model_record(record)
    assert len(calls)==2 and (record['iv'],record['delta'])==(None,None)
    record['price']=1;basket.model_record(record)
    assert len(calls)==3 and record['iv']==.3
    record['observed']+=timedelta(days=1);basket.model_record(record)
    assert len(calls)==4 and len(rates)==2
    basket.time+=timedelta(days=1);basket.model_record(record)
    assert len(calls)==5 and len(rates)==3


def test_future_records_do_not_request_native_greeks_that_black76_replaces(basket,monkeypatch):
    monkeypatch.setattr(sys.modules['basket_test'],'OptionRight',NS(PUT='P'),raising=False)
    # Load the real bounded premium rule without importing the LEAN runtime.
    path=Path(__file__).parents[1]/'basket/premium_units.py'
    spec=importlib.util.spec_from_file_location('premium_units',path);units=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(units);monkeypatch.setitem(sys.modules,'premium_units',units)
    class Contract:
        symbol=NS(id=NS(symbol='OZW'),underlying=NS(id=NS(symbol='ZW')))
        expiry=datetime(2017,8,25);strike=5;right='P';last_price=.1
        underlying_last_price=5.4;open_interest=1000;time=datetime(2017,7,7)
        @property
        def implied_volatility(self):raise AssertionError('Unused native IV requested')
        @property
        def greeks(self):raise AssertionError('Unused native Greeks requested')
    record=basket.contract_record(Contract(),True)
    assert record['iv'] is None and record['delta'] is None
    assert record['price']==.1 and record['strike']==5


def test_history_atm_one_pass_preserves_tenor_strike_and_first_equal_ties(basket,monkeypatch):
    from datetime import timedelta
    monkeypatch.setattr(sys.modules['basket_test'],'OptionRight',NS(PUT='P',CALL='C'),raising=False)
    basket.is_monthly=lambda symbol:True
    observed=date(2020,1,2)
    def contract(dte,strike,right,iv):
        return NS(symbol=NS(id=NS(date=datetime.combine(observed+timedelta(days=dte),datetime.min.time()),
            strike_price=strike,option_right=right)),implied_volatility=iv)
    chain=NS(underlying=NS(price=100),data=[contract(50,100,'P',.8),contract(50,100,'C',.8),
        contract(40,102,'P',.6),contract(40,98,'P',.2),contract(40,98,'P',.9),
        contract(40,102,'C',.7),contract(40,98,'C',.4)])
    assert basket.history_atm_iv(chain,observed)==pytest.approx(.3)
    # An invalid chosen ATM leg cannot be replaced by another strike or tenor.
    chain.data[3].implied_volatility=0
    assert basket.history_atm_iv(chain,observed) is None
    chain.data[3].implied_volatility=.2
    chain.data=[c for c in chain.data if not(c.symbol.id.option_right=='C' and
        c.symbol.id.date.date()==observed+timedelta(days=40))]
    assert basket.history_atm_iv(chain,observed) is None
    chain.underlying.price=float('nan')
    assert basket.history_atm_iv(chain,observed) is None


def test_flat_insolvency_preserves_debt_and_blocks_new_entries(basket,monkeypatch):
    basket.portfolio=NS(total_portfolio_value=-42.29,total_margin_used=0,invested=False)
    basket.transactions=NS(get_open_orders=lambda:[])
    installed=[]
    basket.portfolio.set_margin_call_model=installed.append
    basket.utc_time=datetime(2020,3,12,13,36)
    basket.time=datetime(2020,3,12,9,36)
    basket.active_equity=[('2020-03-11',100.0)]
    basket.log=lambda text:None
    stopped=[];basket.quit=stopped.append
    fake=ModuleType('terminal_margin');fake.FlatInsolvencyMarginModel=lambda a:('terminal',a)
    monkeypatch.setitem(sys.modules,'terminal_margin',fake)
    assert basket.record_insolvency()
    assert basket.insolvency['equity']==-42.29
    assert basket.active_equity[-1]==('2020-03-12',-42.29)
    assert len(stopped)==len(installed)==1
    assert basket.record_insolvency()
    assert len(stopped)==1
    basket.on_data(None)
    basket.prepare_day()
    with pytest.raises(RuntimeError,match='after account insolvency'):
        basket.open_candidate({},1,0)


@pytest.mark.parametrize('leftover', ['positions','pending_combos','exit_requests','invested'])
def test_insolvency_never_hides_unresolved_holdings_or_orders(basket,leftover):
    basket.portfolio=NS(total_portfolio_value=-42.29,invested=False)
    if leftover=='invested':basket.portfolio.invested=True
    else:setattr(basket,leftover,{'A':{}})
    assert not basket.record_insolvency()


def test_insolvency_rejects_unbooked_open_orders(basket):
    basket.portfolio=NS(total_portfolio_value=-42.29,total_margin_used=0,invested=False)
    basket.transactions=NS(get_open_orders=lambda:[object()])
    with pytest.raises(RuntimeError,match='unresolved margin or orders'):
        basket.record_insolvency()


def test_terminal_model_skips_only_already_closed_bankrupt_requests(basket,monkeypatch):
    imports=sys.modules['AlgorithmImports']
    class Default:
        def __init__(self,*args):pass
    monkeypatch.setattr(imports,'DefaultMarginCallModel',Default,raising=False)
    monkeypatch.setattr(imports,'OrderTicket',object,raising=False)
    generic=ModuleType('System.Collections.Generic');generic.List=list
    monkeypatch.setitem(sys.modules,'System.Collections.Generic',generic)
    path=Path(__file__).parents[1]/'basket/terminal_margin.py'
    spec=importlib.util.spec_from_file_location('terminal_model_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    class Portfolio:
        total_portfolio_value=-42.29
        total_margin_used=0
        invested=False
        quantity=0
        def __getitem__(self,key):return self
    basket.portfolio=Portfolio();basket.default_order_properties=None
    basket.insolvency={'equity':-42.29}
    basket.transactions=NS(get_open_orders=lambda:[])
    model=module.FlatInsolvencyMarginModel(basket)
    assert model.execute_margin_call([NS(symbol='P')])==[]
    assert basket.counts['terminal_margin_batches_skipped']==1
    basket.portfolio.quantity=1
    with pytest.raises(RuntimeError,match='still has a holding'):
        model.execute_margin_call([NS(symbol='P')])
    basket.portfolio.quantity=0;basket.portfolio.total_portfolio_value=100
    with pytest.raises(RuntimeError,match='verified flat bankrupt'):
        model.execute_margin_call([NS(symbol='P')])
