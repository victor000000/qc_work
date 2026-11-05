"""Replay the actual final BAC cycle, including its native margin liquidation."""
from AlgorithmImports import *
from collections import Counter
from datetime import date,datetime,time
from basket_strategy import BasketShortStrangle


class InsolvencyRegression(BasketShortStrangle):
    CONFIG = {}

    def initialize(self):
        self.set_start_date(2020,3,6);self.set_end_date(2020,3,16)
        self.initial_cash=872.71;self.set_cash(self.initial_cash)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,AccountType.MARGIN)
        underlying=Symbol(SecurityIdentifier.Parse('NB R735QTJ8XC9X'),'BAC')
        self.add_equity(underlying,Resolution.MINUTE).set_data_normalization_mode(DataNormalizationMode.RAW)
        self.contracts={}
        for put,strike,sid in [(True,21,'31CV49EL2H38M'),(False,30,'XDR43YIW3E4M'),
                               (False,27,'XDR43YMUXA5I')]:
            symbol=Symbol(SecurityIdentifier.Parse('NB '+sid+'|NB R735QTJ8XC9X'),
                'BAC   200417'+('P' if put else 'C')+str(int(strike*1000)).zfill(8))
            self.contracts[(put,strike)]=symbol
        self.key=str(underlying.id);self.states={self.key:dict(ticker='BAC',future=False)}
        self.positions={};self.pending_combos={};self.exit_requests={};self.counts=Counter()
        self.active_equity=[];self.closed_pnl=[];self.insolvency=None
        self.opened=False;self.rolled=False
        self.schedule.on(self.date_rules.every_day(),self.time_rules.at(11,55),self.prepare_fixture)
        self.set_runtime_statistic('scope','Exact BAC insolvency regression; not screened baseline performance')

    def prepare_fixture(self):
        needed=([(True,21),(False,30)] if self.time.date()==date(2020,3,9) else
                [(False,27)] if self.time.date()==date(2020,3,10) else [])
        for key in needed:self.add_option_contract(self.contracts[key],Resolution.MINUTE)

    def on_data(self,data):
        if self.insolvency:return
        self.process_pending_combos()
        if self.time.time()<time(12):return
        if self.time.date()==date(2020,3,9) and not self.opened:
            put,call=self.contracts[(True,21)],self.contracts[(False,30)]
            if not all(self.good_quote(self.securities[s]) for s in (put,call)):return
            self.opened=True
            self.positions[self.key]=dict(put=put,call=call,expiry=date(2020,4,17),quantity=1,
                multiplier=100.,cash=0.,fees=0.,initial=0.,rolls=0,opened=str(self.time.date()),
                entry_metadata='multiplier=100;quantity=1;engineering_probe=True')
            def opened():self.positions[self.key]['initial']=self.positions[self.key]['cash']
            self.execute(self.key,[Leg.create(put,-1),Leg.create(call,-1)],'OPEN',on_filled=opened)
        if self.time.date()==date(2020,3,10) and self.positions and not self.rolled:
            trade=self.positions[self.key];new=self.contracts[(False,27)]
            if not all(self.good_quote(self.securities[s]) for s in (trade['call'],new)):return
            self.rolled=True
            def rolled():trade['call']=new;trade['rolls']+=1;self.counts['rolls']+=1
            self.execute(self.key,[Leg.create(trade['call'],1),Leg.create(new,-1)],'ROLL',on_filled=rolled)

    def on_end_of_algorithm(self):
        self.process_pending_combos()
        if (not self.insolvency or self.positions or self.pending_combos or self.exit_requests
                or self.portfolio.invested or self.transactions.get_open_orders()):
            raise RuntimeError('BAC regression did not finish as a fully flat bankrupt account')
        final=float(self.portfolio.total_portfolio_value)
        if abs(final+42.29)>.005 or abs(final-self.initial_cash-sum(self.closed_pnl))>.005:
            raise RuntimeError('BAC native insolvency cash/fees differ from original evidence')
        if self.time.date()!=date(2020,3,12) or self.counts['MARGIN']!=1:
            raise RuntimeError('BAC insolvency timing or native liquidation changed')
        if self.counts['terminal_margin_batches_skipped']!=1:
            raise RuntimeError('BAC regression did not exercise stale-request prevention exactly once')
        for k,v in self.counts.items():self.set_runtime_statistic(k,str(v))
        for k,v in dict(baseline_outcome='insolvent',insolvency_utc=self.insolvency['utc'],
                insolvency_equity=final,cycle_net_pnl=sum(self.closed_pnl),residual_holdings=0).items():
            self.set_runtime_statistic(k,str(v))
