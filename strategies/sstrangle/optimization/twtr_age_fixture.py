"""Known TWTR holding: original risk versus an isolated24day noon deadline.

Original risk/quote/execution methods are shared by both branches. Entry and
roll identities replay genuine orders, not a new screen or profitability test.
The original branch is expected to fail at its genuine unexecutable TIME exit.
"""
from AlgorithmImports import *
from collections import Counter
from datetime import date,time
from twtr_original_strategy import ResearchShortStrangle as Control
from holding_age import age_exit_due,validate_max_holding_days
from rules import close_reason


class TWTRHoldingAgeRegression(Control):
    CONFIG = {}

    def initialize(self):
        self.set_start_date(2022,9,20);self.set_end_date(2022,10,31)
        self.set_time_zone('America/New_York');self.initial_cash=47823.595
        self.set_cash(self.initial_cash)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,AccountType.MARGIN)
        self.spy=self.add_equity('SPY',Resolution.MINUTE).symbol
        self.securities[self.spy].set_data_normalization_mode(DataNormalizationMode.RAW)
        self.twtr=Symbol(SecurityIdentifier.Parse('TWTR VLE97YS7S57P'),'TWTR')
        self.key='TWTR VLE97YS7S57P'
        self.states={self.key:dict(ticker='TWTR',future=False,eq=self.twtr)}
        self.positions,self.pending_combos,self.exit_requests={},{},{}
        self.counts,self.annual=Counter(),{}
        self.subscribed_underlyings,self.subscribed_options=set(),set()
        self.active_equity,self.closed_pnl=[],[]
        self.insolvency,self.last_risk_check,self.last_research_exit_day=None,None,None
        self.time_exit_dte=21;self.end=date(2022,10,31)
        self.max_holding_days=validate_max_holding_days(self.CONFIG['max_holding_days'])
        self.opened=False;self.managed_days=set()
        native=[('put31','322PLPRB8BEEE','TWTR  221118P00031000'),
                ('call50','Y3LLKB7QB0W6','TWTR  221118C00050000'),
                ('put43','322PLPRD7REZQ','TWTR  221118P00043000'),
                ('put46','322PLPRDPMF52','TWTR  221118P00046000')]
        self.contracts={k:Symbol(SecurityIdentifier.Parse('TWTR '+sid+'|TWTR VLE97YS7S57P'),alias)
                        for k,sid,alias in native}
        self.rolls={date(2022,10,6):'put43',date(2022,10,21):'put46'}
        self.schedule.on(self.date_rules.every_day(),self.time_rules.at(11,55),self.prepare_fixture)

    def prepare_fixture(self):
        self.cleanup();today=self.time.date();needed=[]
        if today==date(2022,9,21):needed=[self.contracts['put31'],self.contracts['call50']]
        if today in self.rolls and self.positions:needed.append(self.contracts[self.rolls[today]])
        if needed:self.subscribe(self.twtr,[dict(symbol=s) for s in needed],False)

    def on_data(self,data):
        self.process_pending_combos();self.process_exit_requests();self.intraday_risk_exits()
        today=self.time.date()
        if self.time.time()<time(12) or today in self.managed_days:return
        self.managed_days.add(today)
        if today==date(2022,9,21) and not self.opened:
            put,call=self.contracts['put31'],self.contracts['call50']
            if not all(self.good_quote(self.securities[s]) for s in (put,call)):
                raise RuntimeError('Original TWTR opening lacked actual paired quotes')
            self.opened=True
            self.positions[self.key]=dict(put=put,call=call,expiry=date(2022,11,18),quantity=2,
                multiplier=100.,cash=0.,fees=0.,initial=0.,rolls=0,opened=str(today),
                entry_metadata='multiplier=100;quantity=2;engineering_probe=True;entry_replay=True')
            def filled():
                self.positions[self.key]['initial']=self.positions[self.key]['cash']
                self.counts['fixture_open_completed']+=1
            self.execute(self.key,[Leg.create(put,-1),Leg.create(call,-1)],'OPEN',on_filled=filled)
        elif self.key in self.positions and self.key not in self.pending_combos:
            trade=self.positions[self.key];securities=[self.securities[trade[s]] for s in ('put','call')]
            if all(s.exchange.exchange_open for s in securities):
                dte=(trade['expiry']-today).days
                reason=('END' if today>=self.end else 'TIME' if dte<=21 else
                        'AGE' if self.CONFIG['holding_cap'] and age_exit_due(trade['opened'],today,self.max_holding_days) else None)
                if reason is None and self.voluntary_quote_ready(self.key):
                    cost=sum(float(s.ask_price) for s in securities)*200
                    reason=close_reason(trade['cash'],trade['fees']+self.close_fees(trade),cost,
                                        trade['initial'],dte,stop_multiple=self.CONFIG['stop_multiple'])
                if reason:self.exit_requests[self.key]=dict(reason=reason,day=today)
                elif today in self.rolls and all(self.good_quote(s) for s in securities):
                    self.submit_roll(self.key,'put',dict(symbol=self.contracts[self.rolls[today]]))
                self.process_exit_requests()
        self.active_equity.append((str(today),float(self.portfolio.total_portfolio_value)))
        self.plot('Trading period','Equity',self.active_equity[-1][1])

    def on_end_of_algorithm(self):
        if not self.CONFIG['holding_cap']:
            # Never close, erase or value-set the expected failed control exposure.
            self.set_runtime_statistic('fixture_control_residual_retained',str(int(bool(self.positions))))
            return
        self.process_pending_combos()
        if (self.positions or self.pending_combos or self.exit_requests or self.portfolio.invested
                or list(self.transactions.get_open_orders())):
            raise RuntimeError('TWTR age experiment retains actual/logical exposure')
        if self.counts['AGE']!=1 or self.counts['fixture_open_completed']!=1 or len(self.closed_pnl)!=1 or self.counts['MARGIN']:
            raise RuntimeError('TWTR age experiment did not complete its genuine AGE close')
        if abs(float(self.portfolio.total_portfolio_value)-self.initial_cash-sum(self.closed_pnl))>.0051:
            raise RuntimeError('Actual TWTR age cash/fee/account ledger mismatch')
        for k,v in self.counts.items():self.set_runtime_statistic(k,str(v))
        self.set_runtime_statistic('fixture_initial_cash',str(self.initial_cash))
        self.set_runtime_statistic('fixture_cycle_net',str(sum(self.closed_pnl)))
        self.set_runtime_statistic('fixture_age_days',str(self.max_holding_days))
        self.set_runtime_statistic('fixture_synthetic_fills','0')
        self.set_runtime_statistic('fixture_settlement_cash','0')
        self.set_runtime_statistic('fixture_calmar_claim','0')
