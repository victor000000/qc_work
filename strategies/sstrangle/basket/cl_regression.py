"""Replay the real failed CL cycle with corrected data; engineering only."""
from AlgorithmImports import *
from collections import Counter
from datetime import date,datetime,time
from basket_strategy import BasketShortStrangle
from premium_filter import PremiumUnitFilter
import json


class CLExecutionRegression(BasketShortStrangle):
    CONFIG = {}
    def initialize(self):
        self.set_start_date(2015,11,27);self.set_end_date(2015,12,30)
        self.initial_cash=14460.57;self.set_cash(self.initial_cash)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,AccountType.MARGIN)
        self.future=Symbol(SecurityIdentifier.Parse('CL W7DWN4VXAQPT'),'CL20G16')
        self.add_future_contract(self.future,Resolution.MINUTE)
        self.counts=Counter();self.positions={};self.pending_combos={};self.exit_requests={}
        self.active_equity=[];self.closed_pnl=[];self.opened=False;self.done_rolls=set()
        self.key='FUT_CL';self.states={self.key:dict(ticker='CL',future=True)}
        self.contracts={}
        for put,strike in [(True,38),(False,50),(False,45),(False,44.5),(False,44)]:
            symbol=Symbol.create_option(self.future,'LO',Market.NYMEX,OptionStyle.AMERICAN,
                OptionRight.PUT if put else OptionRight.CALL,strike,datetime(2016,1,14))
            security=self.add_future_option_contract(symbol,Resolution.MINUTE)
            security.set_data_filter(PremiumUnitFilter(self.counts));self.contracts[(put,strike)]=symbol
        self.schedule.on(self.date_rules.every_day(),self.time_rules.at(11,55),self.check_daily_chain)
        self.set_runtime_statistic('scope','Exact failed-cycle fixture; not screened baseline performance')

    def check_daily_chain(self):
        for c in self.option_chain(self.future):
            if c.symbol in self.contracts.values():
                record=self.contract_record(c,True)
                # Aggregate-only data consistency assertion, not a price export.
                if record['put'] and record['price']>record['strike']:
                    raise RuntimeError('Daily-chain CL premium still in incorrect units')

    def on_data(self,data):
        self.process_pending_combos()
        today=self.time.date()
        if self.time.time()<time(12):return
        if today==date(2015,11,30) and not self.opened:
            put,call=self.contracts[(True,38)],self.contracts[(False,50)]
            if not all(self.good_quote(self.securities[s]) for s in (put,call)):return
            self.opened=True
            self.positions[self.key]=dict(put=put,call=call,expiry=date(2016,1,14),quantity=1,
                multiplier=1000.,cash=0.,fees=0.,initial=0.,rolls=0,opened=str(today),
                entry_metadata='multiplier=1000;quantity=1;engineering_probe=True')
            def opened():self.positions[self.key]['initial']=self.positions[self.key]['cash']
            self.execute(self.key,[Leg.create(put,-1),Leg.create(call,-1)],'OPEN',on_filled=opened)
        rolls={date(2015,12,8):45,date(2015,12,10):44.5,date(2015,12,11):44}
        if today in rolls and today not in self.done_rolls and self.positions:
            trade=self.positions[self.key];new=self.contracts[(False,rolls[today])]
            if not all(self.good_quote(self.securities[s]) for s in (trade['call'],new)):return
            self.done_rolls.add(today)
            def rolled():
                trade['call']=new;trade['rolls']+=1;self.counts['rolls']+=1
            self.execute(self.key,[Leg.create(trade['call'],1),Leg.create(new,-1)],'ROLL',on_filled=rolled)
        if today>=date(2015,12,24) and self.positions:
            self.exit_requests[self.key]=dict(reason='TIME',day=today)
            self.process_exit_requests()

    def on_end_of_algorithm(self):
        self.process_pending_combos()
        if self.positions or self.pending_combos or self.portfolio.invested:
            raise RuntimeError('CL regression left residual holdings')
        if self.counts['TIME']!=1 or self.counts['MARGIN'] or len(self.done_rolls)!=3:
            raise RuntimeError('CL regression did not complete original lots/rolls and 21-DTE exit')
        if not self.counts['unit_repaired_quote_bars'] or not self.counts['unit_repaired_daily_records']:
            raise RuntimeError('CL repair did not exercise minute and daily paths')
        net=float(self.portfolio.total_portfolio_value)-self.initial_cash
        if abs(net-sum(self.closed_pnl))>.05:raise RuntimeError('CL regression ledger/account mismatch')
        for k,v in self.counts.items():self.set_runtime_statistic(k,str(v))
        self.set_runtime_statistic('cycle_net_pnl',str(sum(self.closed_pnl)))
        self.set_runtime_statistic('residual_holdings','0')
        self.log('CL_REGRESSION '+json.dumps(dict(net_pnl=net,counts=dict(self.counts),residual=0)))
