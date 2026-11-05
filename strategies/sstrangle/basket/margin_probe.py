"""Reproduce a genuine failed-run position; engineering only, not an entry screen."""
from AlgorithmImports import *
from collections import Counter
from datetime import date,datetime,time
import json
from basket_strategy import BasketShortStrangle


class MarginExecutionProbe(BasketShortStrangle):
    CONFIG = {}

    def initialize(self):
        self.set_start_date(2014,6,12)
        self.set_end_date(2014,6,30)
        self.initial_cash=60000
        self.set_cash(self.initial_cash)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,AccountType.MARGIN)
        underlying=Symbol(SecurityIdentifier.Parse('VIAB R735QTJ8XC9X'),'VIAB')
        self.add_equity(underlying,Resolution.MINUTE).set_data_normalization_mode(DataNormalizationMode.RAW)
        expiry=datetime(2014,7,19)
        put=Symbol.create_option(underlying,Market.USA,OptionStyle.AMERICAN,OptionRight.PUT,55,expiry)
        call=Symbol.create_option(underlying,Market.USA,OptionStyle.AMERICAN,OptionRight.CALL,67.5,expiry)
        for symbol in (put,call):self.add_option_contract(symbol,Resolution.MINUTE)
        self.key=str(underlying.id)
        self.states={self.key:dict(ticker='VIAB',future=False)}
        self.positions={};self.pending_combos={};self.exit_requests={}
        self.counts=Counter();self.active_equity=[];self.closed_pnl=[]
        self.legs=(put,call);self.opened=False
        self.set_runtime_statistic('scope','Fixed genuine-position margin API regression; not screened baseline')

    def on_data(self,data):
        self.process_pending_combos()
        if self.time.date()==date(2014,6,13) and self.time.time()>=time(12) and not self.opened:
            if not all(self.good_quote(self.securities[s]) for s in self.legs):return
            self.opened=True
            self.positions[self.key]=dict(put=self.legs[0],call=self.legs[1],expiry=date(2014,7,19),
                quantity=47,multiplier=100,cash=0.,fees=0.,initial=0.,rolls=0,opened=str(self.time.date()),
                entry_metadata='multiplier=100;quantity=47;engineering_probe=True')
            self.execute(self.key,[Leg.create(s,-1) for s in self.legs],'OPEN',
                on_filled=self.confirm_entry)
        if self.time.date()==date(2014,6,30) and self.time.time()>=time(12) and self.positions:
            self.exit_requests[self.key]=dict(reason='END',day=self.time.date())
            self.process_exit_requests()

    def confirm_entry(self):
        trade=self.positions[self.key];trade['initial']=trade['cash']
        self.counts['entries']+=1

    def on_end_of_algorithm(self):
        self.process_pending_combos()
        if self.positions or self.pending_combos or self.portfolio.invested:
            raise RuntimeError('Margin probe left residual positions')
        if not self.counts['MARGIN']:
            raise RuntimeError('Probe did not exercise actual margin liquidation')
        net=float(self.portfolio.total_portfolio_value)-self.initial_cash
        if abs(net-sum(self.closed_pnl))>.05:
            raise RuntimeError('Margin probe account/ledger mismatch')
        for key,value in self.counts.items():self.set_runtime_statistic(key,str(value))
        self.set_runtime_statistic('cycle_net_pnl',str(sum(self.closed_pnl)))
        self.set_runtime_statistic('closed_cycles',str(len(self.closed_pnl)))
        self.set_runtime_statistic('residual_holdings','0')
        self.log('MARGIN_PROBE '+json.dumps(dict(net_pnl=net,cycles=len(self.closed_pnl),
            counts=dict(self.counts),scope='Engineering API reproduction; no baseline performance claim')))
