"""Replay the actual five-lot ZW cycle and its rejected 21-DTE close."""
from AlgorithmImports import *
from collections import Counter
from datetime import date,datetime,time,timedelta
from basket_strategy import BasketShortStrangle
import execution_base
import json
import hashlib
from time import perf_counter
from types import SimpleNamespace


class ZWExecutionRegression(BasketShortStrangle):
    CONFIG = {}
    def initialize(self):
        self.set_start_date(2017,7,5);self.set_end_date(2017,8,7)
        self.initial_cash=15703.82;self.set_cash(self.initial_cash)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,AccountType.MARGIN)
        self.future=Symbol(SecurityIdentifier.Parse('ZW WNVN7IGPFOKL'),'ZW14U17')
        self.add_future_contract(self.future,Resolution.MINUTE)
        self.counts=Counter();self.positions={};self.pending_combos={};self.exit_requests={}
        self.active_equity=[];self.closed_pnl=[];self.opened=False;self.done_rolls=set();self.monthly_cache={}
        self.key='FUT_ZW';self.states={self.key:dict(ticker='ZW',future=True)}
        self.contracts={}
        native=[(True,5,'30MFYF35DAXYG','OZW   170825P00005000'),
            (False,6.5,'WNBY9NG372DK','OZW   170825C00006500'),
            (False,5.75,'WNBY9PSFJMEG','OZW   170825C00005750'),
            (False,5.7,'WNBY9NERKDZC','OZW   170825C00005700'),
            (False,5.6,'WNBY9NELM1XK','OZW   170825C00005600')]
        for put,strike,encoded,alias in native:
            self.contracts[(put,strike)]=Symbol(SecurityIdentifier.Parse(
                'OZW '+encoded+'|ZW WNVN7IGPFOKL'),alias)
        self.subscribed=set()
        self.performance_digest=hashlib.sha256()
        self.equity_probe_done=False
        if self.CONFIG.get('performance_probe'):
            self.spy=self.add_equity('SPY',Resolution.DAILY).symbol
            self.securities[self.spy].set_data_normalization_mode(DataNormalizationMode.RAW)
            self.lookback=504
            self.price_volume={}
            self.equity_candidates={}
        self.schedule.on(self.date_rules.every_day(),self.time_rules.at(11,55),self.prepare_fixture)
        self.set_runtime_statistic('scope','Exact failed-cycle fixture; not screened baseline performance')

    def prepare_fixture(self):
        today=self.time.date()
        if self.CONFIG.get('performance_probe'):
            if not self.equity_probe_done:self.probe_equity()
            started=perf_counter()
            records=self.records_for(self.future,True)
            point=self.atm_iv(records)
            # The holding path reads the same completed daily universe again.
            self.records_for(self.future,True)
            from basket_rules import monthly_expiry
            expiry=monthly_expiry([r['expiry'] for r in records],today,True)
            legs=self.selected_legs(records,expiry) if expiry else None
            selected={side:dict(id=str(r['symbol'].id),iv=r['iv'],delta=r['delta'])
                for side,r in (legs or {}).items()}
            self.performance_digest.update(json.dumps(dict(day=str(today),point=str(point),
                selected=selected),sort_keys=True).encode())
            self.counts['perf_fixture_us']+=round((perf_counter()-started)*1_000_000)
            self.counts['perf_fixture_days']+=1
        needed=[]
        if today==date(2017,7,6):needed=[(True,5),(False,6.5)]
        rolls={date(2017,7,14):5.75,date(2017,7,17):5.7,date(2017,7,18):5.6}
        if today in rolls:needed.append((False,rolls[today]))
        for key in needed:
            symbol=self.contracts[key]
            if symbol not in self.subscribed:
                self.add_future_option_contract(symbol,Resolution.MINUTE)
                self.subscribed.add(symbol)
        if needed:self.log('FIXTURE_SUBSCRIPTIONS '+str(today)+' count='+str(len(needed)))

    def probe_equity(self):
        self.equity_probe_done=True
        # A short native history window verifies Python/.NET seeding behavior;
        # all504 observations are independently compared in the local benchmark.
        state=dict(eq=self.spy,iv={},last_checked=self.time.date()-timedelta(days=10))
        started=perf_counter();self.seed_equity_iv(state)
        self.counts['perf_equity_history_us']=round((perf_counter()-started)*1_000_000)
        self.counts['perf_equity_history_samples']=len(state['iv'])
        self.performance_digest.update(repr(sorted(state['iv'].items())).encode())
        probe_symbols=[self.spy,Symbol.create('QQQ',SecurityType.EQUITY,Market.USA),
            Symbol.create('AAPL',SecurityType.EQUITY,Market.USA)]
        started=perf_counter()
        for i in range(25):
            rows=[SimpleNamespace(symbol=symbol,end_time=self.time-timedelta(days=25-i),
                price=(30.+i/100 if j==0 else 100. if j==1 else 10.),
                volume=(5_000_001.+i if j==0 else 1e6 if j==1 else 7e6),market_cap=1e12)
                for j,symbol in enumerate(probe_symbols)]
            self.screen_equities(rows)
            selected={k:{name:value for name,value in record.items() if name!='eq'}
                for k,record in self.equity_candidates.items()}
            self.performance_digest.update(json.dumps(selected,sort_keys=True).encode())
        self.counts['perf_equity_screen_us']=round((perf_counter()-started)*1_000_000)

    def execute(self,key,legs,reason,on_filled=None):
        if self.CONFIG.get('combo_control') and reason=='TIME':
            return execution_base.TranscriptShortStrangle.execute(self,key,legs,
                reason+';multiplier=5000',on_filled,quantity=5)
        return super().execute(key,legs,reason,on_filled)

    def on_data(self,data):
        self.process_pending_combos()
        today=self.time.date()
        if self.time.time()<time(12):return
        if today==date(2017,7,6) and not self.opened:
            put,call=self.contracts[(True,5)],self.contracts[(False,6.5)]
            if not all(self.good_quote(self.securities[s]) for s in (put,call)):return
            self.opened=True
            self.positions[self.key]=dict(put=put,call=call,expiry=date(2017,8,25),quantity=5,
                multiplier=5000.,cash=0.,fees=0.,initial=0.,rolls=0,opened=str(today),
                entry_metadata='multiplier=5000;quantity=5;engineering_probe=True')
            def opened():self.positions[self.key]['initial']=self.positions[self.key]['cash']
            self.execute(self.key,[Leg.create(put,-1),Leg.create(call,-1)],'OPEN',on_filled=opened)
        rolls={date(2017,7,14):5.75,date(2017,7,17):5.7,date(2017,7,18):5.6}
        if today in rolls and today not in self.done_rolls and self.positions:
            trade=self.positions[self.key];new=self.contracts[(False,rolls[today])]
            if not all(self.good_quote(self.securities[s]) for s in (trade['call'],new)):return
            self.done_rolls.add(today)
            def rolled():
                trade['call']=new;trade['rolls']+=1;self.counts['rolls']+=1
            self.execute(self.key,[Leg.create(trade['call'],1),Leg.create(new,-1)],'ROLL',on_filled=rolled)
        if today>=date(2017,8,4) and self.positions:
            self.exit_requests[self.key]=dict(reason='TIME',day=today)
            self.process_exit_requests()

    def on_end_of_algorithm(self):
        self.process_pending_combos()
        if self.positions or self.pending_combos or self.portfolio.invested:
            raise RuntimeError('ZW regression left residual holdings')
        if self.counts['TIME']!=1 or self.counts['MARGIN'] or len(self.done_rolls)!=3:
            raise RuntimeError('ZW regression did not complete original lots/rolls and 21-DTE exit')
        net=float(self.portfolio.total_portfolio_value)-self.initial_cash
        if abs(net-sum(self.closed_pnl))>.05:raise RuntimeError('ZW regression ledger/account mismatch')
        for k,v in self.counts.items():self.set_runtime_statistic(k,str(v))
        if self.CONFIG.get('performance_probe'):
            # Runtime statistics reject hash strings. This is a test checksum
            # of aggregate decisions, never an encoding of exported price rows.
            self.log('PERFORMANCE_CHECKSUM '+self.performance_digest.hexdigest())
        self.set_runtime_statistic('cycle_net_pnl',str(sum(self.closed_pnl)))
        self.set_runtime_statistic('residual_holdings','0')
        self.log('ZW_REGRESSION '+json.dumps(dict(net_pnl=net,counts=dict(self.counts),residual=0)))
