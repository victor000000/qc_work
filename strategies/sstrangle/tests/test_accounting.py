"""Exercise the actual algorithm ledger without requiring the LEAN runtime."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
import pytest


@pytest.fixture
def algorithm(monkeypatch):
    imports = ModuleType('AlgorithmImports')
    imports.QCAlgorithm = object
    imports.QuoteBar = object
    imports.OrderStatus = NS(FILLED='filled', INVALID='invalid', CANCELED='canceled')
    monkeypatch.setitem(sys.modules, 'AlgorithmImports', imports)
    path = Path(__file__).parents[1] / 'project'
    for name in ['rules', 'strangle_algo_test']:
        spec = importlib.util.spec_from_file_location(name, path / ('rules.py' if name == 'rules' else 'main.py'))
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
    algo = module.TranscriptShortStrangle()
    algo.positions = {'SPY': {'cash': 0.0, 'fees': 0.0}}
    algo.pending_combos = {}
    algo.active_equity = []
    algo.entry_decisions = {}
    algo.securities = {'p': NS(symbol_properties=NS(contract_multiplier=100)),
                       'c': NS(symbol_properties=NS(contract_multiplier=100))}
    return algo


def test_continuous_entry_is_not_blocked_by_low_or_missing_iv_rank(algorithm):
    from collections import Counter
    from datetime import date, datetime
    a = algorithm
    a.time, a.end = datetime(2017,1,3,15,30), date(2017,12,29)
    a.positions, a.counts = {}, Counter()
    a.states = {'SPY': {}}
    a.iv_min = None
    a.min_iv_rv = a.max_trend_z = None
    submitted = []
    a.try_entry = lambda *args: submitted.append(args) or 'entry_submitted'
    for rank in (None, 0, 49.9):
        assert a.entry_decision('SPY', ['fresh_contract'], rank, set()) == 'entry_submitted'
    assert len(submitted) == 3
    assert a.entry_decision('SPY', [], None, set()) == 'no_fresh_chain'
    a.iv_min = 50
    assert a.entry_decision('SPY', ['fresh_contract'], None, set()) == 'ivr_unavailable'
    assert a.entry_decision('SPY', ['fresh_contract'], 49.9, set()) == 'ivr_below_threshold'
    assert len(submitted) == 3


def test_exit_day_blocks_reentry_but_next_session_can_enter(algorithm):
    from collections import Counter
    from datetime import date, datetime
    a = algorithm
    a.time, a.end = datetime(2017,1,3,15,30), date(2017,12,29)
    a.positions, a.counts, a.states = {}, Counter(), {'SPY': {}}
    a.iv_min = a.min_iv_rv = a.max_trend_z = None
    a.try_entry = lambda *args: 'entry_submitted'
    assert a.entry_decision('SPY', ['contract'], None, {'SPY'}) == 'exit_day'
    a.time = datetime(2017,1,4,15,30)
    assert a.entry_decision('SPY', ['contract'], None, set()) == 'entry_submitted'
    a.positions['SPY'] = {}
    assert a.entry_decision('SPY', ['contract'], None, set()) == 'invested'


def test_no_expiry_in_entry_window_has_an_explicit_skip_reason(algorithm):
    from datetime import datetime
    algorithm.time = datetime(2017,1,3,15,30)
    assert algorithm.try_entry('SPY', [NS(expiry=datetime(2017,1,20))], None) == 'no_entry_expiry'


def test_entry_diagnostics_distinguish_missing_delta_from_illiquidity(algorithm, monkeypatch):
    from collections import Counter
    from datetime import datetime
    a = algorithm
    a.time = datetime(2017,1,3,15,30)
    a.states = {'SPY': {'eq':'stock'}}
    a.securities['stock'] = NS(price=220)
    a.counts = Counter()
    monkeypatch.setitem(a.try_entry.__globals__, 'OptionRight', NS(PUT='put', CALL='call'))
    contract = NS(expiry=datetime(2017,2,17),right='put',strike=210,
                  greeks=NS(delta=-.18),bid_price=1,ask_price=1.02,open_interest=0)
    assert a.try_entry('SPY', [contract], 60) == 'illiquid_put'
    contract.open_interest = 1000
    contract.greeks.delta = -.25
    assert a.try_entry('SPY', [contract], 60) == 'no_delta_put'


def ticket(symbol, quantity, price, status='filled'):
    return NS(symbol=symbol, quantity_filled=quantity, average_fill_price=price,
              status=status, order_events=[NS(order_fee=NS(value=NS(amount=0.65)))])


def test_actual_fill_ledger_includes_rolls_and_closing_fees(algorithm):
    a = algorithm
    a.combo_market_order = lambda *args, **kwargs: [ticket('p', -1, 1), ticket('c', -1, 2)]
    a.execute('SPY', [], 'OPEN')
    assert a.positions['SPY']['cash'] == 300
    a.combo_market_order = lambda *args, **kwargs: [ticket('p', 1, 0.2), ticket('p', -1, 0.8)]
    a.execute('SPY', [], 'ROLL')
    assert a.positions['SPY']['cash'] == 360
    a.combo_market_order = lambda *args, **kwargs: [ticket('p', 1, 0.5), ticket('c', 1, 1)]
    a.execute('SPY', [], 'PROFIT')
    t = a.positions['SPY']
    assert t['cash'] == 210
    assert t['fees'] == pytest.approx(3.90)
    assert t['cash'] - t['fees'] == pytest.approx(206.10)


def test_incomplete_combo_fails_instead_of_recording_a_fictitious_credit(algorithm):
    algorithm.combo_market_order = lambda *args, **kwargs: [ticket('p', 0, 0, 'invalid')]
    with pytest.raises(RuntimeError, match='Incomplete combo execution'):
        algorithm.execute('SPY', [], 'OPEN')
    assert algorithm.positions['SPY']['cash'] == 0


def test_split_warning_preserves_history_until_occurrence_then_resets_returns(algorithm,monkeypatch):
    from collections import Counter
    from datetime import date
    a=algorithm
    monkeypatch.setitem(a.on_splits.__globals__,'SplitType',NS(WARNING='warning'))
    a.time=NS(date=lambda:date(2024,6,7))
    a.counts=Counter()
    state=dict(eq='NVDA',previous=1200,returns={date(2024,6,6):.02})
    a.states={'NVDA':state}
    a.on_splits({'NVDA':NS(type='warning')})
    assert state['split_warning']
    assert state['previous']==1200
    assert state['split_block_day']==date(2024,6,7)
    a.time=NS(date=lambda:date(2024,6,10))
    a.on_splits({'NVDA':NS(type='occurred')})
    assert not state['split_warning']
    assert state['previous'] is None and not state['returns']
    assert state['split_block_day']==date(2024,6,10)
    assert a.counts['split_events']==1


def test_quote_age_uses_security_clock_and_rejects_future_bars(algorithm):
    from datetime import datetime,timedelta
    a=algorithm
    a.time=datetime(2024,4,15,15,30)
    local=datetime(2024,4,15,14,30)
    security=NS(local_time=local,bid_price=38.9,ask_price=39.5,
                cache=NS(get_data={object:lambda:NS(end_time=local-timedelta(minutes=1))}))
    assert a.good_quote(security)
    # Fresh last trade must not rescue a stale quote.
    security.get_last_data=lambda:NS(end_time=local)
    security.cache.get_data[object]=lambda:NS(end_time=local-timedelta(minutes=6))
    assert not a.good_quote(security)
    security.cache.get_data[object]=lambda:NS(end_time=local+timedelta(minutes=1))
    assert not a.good_quote(security)


def test_stale_chain_cannot_seed_iv_rank_or_submit_an_entry(algorithm):
    from collections import Counter, deque
    from datetime import date, datetime
    a = algorithm
    a.time = datetime(2018,10,10,15,30)
    a.trade_start, a.end = date(2018,1,2), date(2018,11,30)
    a.due, a.last_day = True, None
    a.counts = Counter()
    a.positions = {}
    a.iv_min = 0
    a.states = {'SPY':dict(eq='stock',opt='chain',previous=None,returns={},iv=deque([.1]*252))}
    a.securities['stock'] = NS(price=281)
    # It looks liquid but its quote is from the previous session.
    a.securities['p'].cache = NS(get_data={object:lambda:NS(end_time=datetime(2018,10,9,16))})
    a.securities['p'].local_time = a.time
    a.securities['p'].bid_price, a.securities['p'].ask_price = 1.31, 1.33
    a.portfolio = NS(total_portfolio_value=250000)
    a.plot = a.set_runtime_statistic = lambda *args: None
    a.try_entry = lambda *args: pytest.fail('Stale chain must not enter')
    a.on_data(NS(option_chains={'chain':[NS(symbol='p')]}))
    assert a.counts['no_fresh_chain'] == 1
    assert a.counts['iv_observations'] == 0
    assert list(a.states['SPY']['iv']) == [.1]*252
    assert a.counts['decision_ivr_unavailable'] == 1
    assert sum(a.entry_decisions[('SPY',2018)].values()) == 1


@pytest.mark.parametrize('dte,final_day,expected', [(21,False,'TIME'), (20,False,'TIME'),
                                                   (22,False,None), (40,True,'END')])
def test_calendar_exits_are_not_blocked_by_stale_quotes(algorithm, monkeypatch, dte, final_day, expected):
    from collections import Counter, deque
    from datetime import datetime, date, timedelta
    a = algorithm
    today = date(2024,4,26)
    a.time = datetime(2024,4,26,15,30)
    a.trade_start = date(2024,1,2)
    a.end = today if final_day else date(2024,12,31)
    a.due, a.last_day = True, None
    a.counts, a.closed_pnl, a.active_equity = Counter(), [], []
    a.states = {'SPY':dict(eq='stock', opt='chain', previous=None, returns={}, iv=deque())}
    a.securities['stock'] = NS(price=500, invested=False)
    a.positions['SPY'].update(put='p', call='c', expiry=datetime.combine(today+timedelta(days=dte),datetime.min.time()),
                              initial=500, cash=500, rolls=0)
    a.portfolio = NS(total_portfolio_value=250000)
    a.good_quote = lambda security: False
    a.plot = a.log = lambda *args: None
    orders = []
    def execute(ticker, legs, reason, on_filled=None):
        orders.append(reason)
        if on_filled:
            on_filled()
    a.execute = execute
    monkeypatch.setitem(a.on_data.__globals__, 'Leg', NS(create=lambda *args: args))
    a.on_data(NS(option_chains={}))
    assert orders == ([expected] if expected else [])
    assert ('SPY' not in a.positions) == bool(expected)
    if expected:
        assert a.counts['mandatory_exit_stale_quotes'] == 1
    else:
        assert a.counts['stale_management'] == 1


def test_pending_combo_is_booked_once_after_confirmed_fills_before_daily_gate(algorithm):
    from collections import Counter
    from datetime import datetime, timedelta
    a = algorithm
    a.counts = Counter()
    a.time = datetime(2018, 10, 10, 15, 30)
    a.due, a.last_day = False, a.time.date()
    tickets = [ticket('p', 0, 0, 'submitted'), ticket('c', 0, 0, 'submitted')]
    a.combo_market_order = lambda *args, **kwargs: tickets
    callbacks = []
    a.execute('SPY', [], 'OPEN', on_filled=lambda: callbacks.append(a.positions['SPY']['cash']))
    assert a.positions['SPY']['cash'] == 0
    assert not callbacks
    with pytest.raises(RuntimeError, match='Overlapping combo'):
        a.execute('SPY', [], 'OPEN')
    a.time += timedelta(minutes=1)
    # A partially completed combo is not a complete strategy position.
    tickets[0].status, tickets[0].quantity_filled, tickets[0].average_fill_price = 'filled', -1, 1.30
    a.on_data(NS())
    assert not callbacks
    tickets[1].status, tickets[1].quantity_filled, tickets[1].average_fill_price = 'filled', -1, 1.25
    a.on_data(NS())
    a.on_data(NS())
    assert callbacks == [255]
    assert a.positions['SPY']['cash'] == 255
    assert a.positions['SPY']['fees'] == pytest.approx(1.30)
    assert not a.pending_combos
    assert a.counts['pending_combo_completed'] == 1
    assert a.counts['pending_combo_max_delay_seconds'] == 60


def test_pending_time_exit_preserves_cycle_until_filled_on_21_dte(algorithm):
    from collections import Counter
    from datetime import datetime, timedelta
    a = algorithm
    a.counts, a.closed_pnl = Counter(), []
    a.log = lambda *args: None
    a.time = datetime(2024, 4, 26, 15, 30)
    a.positions['SPY'].update(cash=500, initial=500, rolls=0, expiry=datetime(2024, 5, 17))
    tickets = [ticket('p', 0, 0, 'submitted'), ticket('c', 0, 0, 'submitted')]
    a.combo_market_order = lambda *args, **kwargs: tickets
    a.execute('SPY', [], 'TIME', on_filled=lambda: a.finish_close('SPY', 'TIME'))
    assert 'SPY' in a.positions and not a.closed_pnl
    a.time += timedelta(minutes=1)
    a.active_equity = [(str(a.time.date()), 250000)]
    a.portfolio = NS(total_portfolio_value=250298.70)
    plotted = []
    a.plot = lambda *args: plotted.append(args)
    for t in tickets:
        t.status, t.quantity_filled, t.average_fill_price = 'filled', 1, 1
    a.process_pending_combos()
    assert 'SPY' not in a.positions
    assert a.closed_pnl == pytest.approx([298.70])
    assert a.counts['TIME'] == 1
    assert a.counts['time_exit_min_dte'] == 21
    assert a.active_equity == [(str(a.time.date()), 250298.70)]
    assert plotted[-1][-1] == 250298.70


@pytest.mark.parametrize('status,elapsed', [('submitted', 6), ('invalid', 1), ('canceled', 1)])
def test_pending_combo_deadline_or_rejection_fails_without_inventing_fills(algorithm, status, elapsed):
    from collections import Counter
    from datetime import datetime, timedelta
    a = algorithm
    a.counts = Counter()
    a.time = datetime(2018, 10, 10, 15, 30)
    tickets = [ticket('p', 0, 0, 'submitted'), ticket('c', 0, 0, 'submitted')]
    a.combo_market_order = lambda *args, **kwargs: tickets
    a.execute('SPY', [], 'OPEN')
    a.time += timedelta(minutes=elapsed)
    tickets[0].status = status
    for security in a.securities.values():
        security.is_tradable, security.has_data = True, True
        security.local_time = a.time
        security.get_last_data = lambda: None
    with pytest.raises(RuntimeError, match='Unresolved combo execution'):
        a.process_pending_combos()
    assert a.positions['SPY']['cash'] == 0


def test_rejected_roll_keeps_cash_and_does_not_call_fill_callback(algorithm):
    algorithm.combo_market_order=lambda *a,**k:[ticket('p',0,0,'invalid'),ticket('c',0,0,'canceled')]
    rejected=[]
    algorithm.execute('SPY',[],'ROLL',on_filled=lambda:pytest.fail('Unfilled roll committed'),
        on_rejected=lambda:rejected.append(True))
    assert rejected==[True]
    assert algorithm.positions['SPY']=={'cash':0.,'fees':0.}
    assert not algorithm.pending_combos


def test_partial_rejected_roll_remains_a_fatal_accounting_error(algorithm):
    from collections import Counter
    from datetime import datetime
    algorithm.time=datetime(2020,1,2,12)
    algorithm.counts=Counter()
    algorithm.securities['p'].get_last_data=lambda:None
    algorithm.securities['c'].get_last_data=lambda:None
    for s in algorithm.securities.values():
        s.is_tradable=True;s.has_data=True;s.local_time=algorithm.time
    algorithm.combo_market_order=lambda *a,**k:[ticket('p',1,1),ticket('c',0,0,'invalid')]
    algorithm.execute('SPY',[],'ROLL',on_rejected=lambda:pytest.fail('Partial fill ignored'))
    with pytest.raises(RuntimeError,match='Unresolved combo execution'):
        algorithm.process_pending_combos()


def test_pending_roll_rejection_releases_pending_without_changing_cash(algorithm):
    from collections import Counter
    from datetime import datetime
    algorithm.time=datetime(2020,1,2,12)
    algorithm.counts=Counter()
    tickets=[ticket('p',0,0,'submitted'),ticket('c',0,0,'submitted')]
    algorithm.combo_market_order=lambda *a,**k:tickets
    rejected=[]
    algorithm.execute('SPY',[],'ROLL',on_rejected=lambda:rejected.append(True))
    for t in tickets:t.status='invalid'
    algorithm.process_pending_combos()
    assert rejected==[True] and not algorithm.pending_combos
    assert algorithm.positions['SPY']['cash']==0


@pytest.fixture
def closing_algorithm(algorithm):
    from collections import Counter
    from datetime import datetime
    algorithm.time=datetime(2017,8,4,12)
    algorithm.counts=Counter()
    for symbol,price in [('p',.45),('c',.002)]:
        algorithm.securities[symbol].holdings=NS(quantity=-5)
        algorithm.securities[symbol].price=price
        algorithm.securities[symbol].symbol_properties.contract_multiplier=5000
    return algorithm


def test_sequential_close_waits_for_first_fill_and_books_two_real_fills_once(closing_algorithm):
    a=closing_algorithm
    submitted=[];committed=[]
    tickets=[ticket('p',0,0,'submitted'),ticket('c',0,0,'submitted')]
    def market(symbol,quantity,**kwargs):
        assert quantity==5 and kwargs['asynchronous'] is False
        submitted.append((symbol,kwargs['tag']))
        return tickets[len(submitted)-1]
    a.market_order=market
    a.execute_sequential_close('SPY',['c','p'],'TIME;multiplier=5000',5,
        on_filled=lambda:committed.append(True))
    assert [s for s,_ in submitted]==['p']
    assert a.positions['SPY']['cash']==0 and not committed
    tickets[0].status='filled';tickets[0].quantity_filled=5;tickets[0].average_fill_price=.46375
    a.securities['p'].holdings.quantity=0
    a.process_pending_combos()
    assert [s for s,_ in submitted]==['p','c']
    assert submitted[0][1]==submitted[1][1]
    assert a.positions['SPY']['cash']==0 and not committed
    tickets[1].status='filled';tickets[1].quantity_filled=5;tickets[1].average_fill_price=.0025
    a.securities['c'].holdings.quantity=0
    a.process_pending_combos();a.process_pending_combos()
    assert a.positions['SPY']['cash']==pytest.approx(-11656.25)
    assert committed==[True] and not a.pending_combos
    assert a.counts['sequential_closes_completed']==1


def test_sequential_close_rejects_quantity_mismatch_before_any_order(closing_algorithm):
    a=closing_algorithm;a.securities['c'].holdings.quantity=-4
    a.market_order=lambda *args,**kwargs:pytest.fail('Mismatched holdings submitted')
    with pytest.raises(RuntimeError,match='actual short holdings'):
        a.execute_sequential_close('SPY',['p','c'],'TIME',5)
    assert not a.pending_combos


def test_rejected_first_close_does_not_submit_second_or_commit_cycle(closing_algorithm):
    a=closing_algorithm;submitted=[]
    a.market_order=lambda symbol,*args,**kwargs:submitted.append(symbol) or ticket(symbol,0,0,'invalid')
    with pytest.raises(RuntimeError,match='closing order rejected'):
        a.execute_sequential_close('SPY',['p','c'],'TIME',5,
            on_filled=lambda:pytest.fail('Rejected close committed'))
    assert submitted==['p'] and a.positions['SPY']['cash']==0


def test_pending_sequential_close_timeout_never_submits_other_leg(closing_algorithm):
    from datetime import timedelta
    a=closing_algorithm;submitted=[]
    a.market_order=lambda symbol,*args,**kwargs:submitted.append(symbol) or ticket(symbol,0,0,'submitted')
    a.execute_sequential_close('SPY',['p','c'],'TIME',5)
    a.time+=timedelta(minutes=6)
    with pytest.raises(RuntimeError,match='exceeded five minutes'):
        a.process_pending_combos()
    assert submitted==['p'] and a.positions['SPY']['cash']==0


def test_synchronous_sequential_close_records_both_native_fees(closing_algorithm):
    a=closing_algorithm;committed=[]
    def market(symbol,quantity,**kwargs):
        a.securities[symbol].holdings.quantity=0
        return ticket(symbol,quantity,a.securities[symbol].price)
    a.market_order=market
    a.execute_sequential_close('SPY',['p','c'],'TIME',5,on_filled=lambda:committed.append(True))
    assert a.positions['SPY']['cash']==pytest.approx(-11300)
    assert a.positions['SPY']['fees']==pytest.approx(1.30)
    assert committed==[True] and not a.pending_combos
    a.process_pending_combos()
    assert a.positions['SPY']['fees']==pytest.approx(1.30)


def test_second_close_rejection_retains_unfinished_state_and_fails(closing_algorithm):
    a=closing_algorithm;submitted=[]
    def market(symbol,quantity,**kwargs):
        submitted.append(symbol)
        if len(submitted)==1:
            a.securities[symbol].holdings.quantity=0
            return ticket(symbol,quantity,.45)
        return ticket(symbol,0,0,'invalid')
    a.market_order=market
    with pytest.raises(RuntimeError,match='closing order rejected'):
        a.execute_sequential_close('SPY',['p','c'],'TIME',5,
            on_filled=lambda:pytest.fail('Incomplete cycle committed'))
    assert submitted==['p','c'] and 'SPY' in a.pending_combos
    assert a.securities['p'].holdings.quantity==0
    assert a.securities['c'].holdings.quantity==-5
    assert a.counts['sequential_closes_completed']==0
