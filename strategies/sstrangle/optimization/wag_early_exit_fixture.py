"""Isolated 28DTE research change: original opening, early actual close, no roll. Not equivalent to21DTE baseline."""
"""Future-use exact-position engineering fixture. NOT queued/deployed by this file.
Render with the unchanged frozen basket_strategy/execution_base dependencies.
Only CONFIG.buyback permits a zero bid for fresh positive-ask closing buybacks.
No raw market quote history is logged. Native executed fills remain real orders.
"""
from AlgorithmImports import *
from basket_strategy import BasketShortStrangle
from collections import Counter
from datetime import date,datetime,time,timedelta
import json


class WAGEarlyExitRegression(BasketShortStrangle):
    CONFIG = {}
    def initialize(self):
        self.set_start_date(2019,11,13);self.set_end_date(2019,12,3)
        self.set_time_zone(TimeZones.NEW_YORK)
        self.initial_cash=41194.185;self.set_cash(self.initial_cash)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,AccountType.MARGIN)
        self.underlying=Symbol(SecurityIdentifier.Parse('WAG R735QTJ8XC9X'),'WBA')
        self.add_equity(self.underlying,Resolution.MINUTE).set_data_normalization_mode(DataNormalizationMode.RAW)
        if str(self.underlying.id)!='WAG R735QTJ8XC9X':raise RuntimeError('Wrong permanent WBA SID')
        self.contracts={}
        for put,strike,encoded in [(True,57.5,'319LY2CLLOLC6'),(False,70,'XAHXWU0GSY86'),(False,65,'XAHXWUA227XI')]:
            sid='WAG '+encoded+'|WAG R735QTJ8XC9X'
            alias='WBA   191220'+('P' if put else 'C')+str(int(strike*1000)).zfill(8)
            symbol=Symbol(SecurityIdentifier.Parse(sid),alias)
            if (str(symbol.id)!=sid or str(symbol.underlying.id)!=str(self.underlying.id)
                    or symbol.id.date.date()!=date(2019,12,20)
                    or float(symbol.id.strike_price)!=strike):raise RuntimeError('Native fixture contract mismatch')
            self.contracts[(put,strike)]=symbol
        self.key=str(self.underlying.id)
        self.states={self.key:dict(ticker='WBA',eq=self.underlying,future=False)}
        self.positions={};self.pending_combos={};self.exit_requests={};self.counts=Counter()
        self.active_equity=[];self.closed_pnl=[];self.insolvency=None
        self.opened=False;self.rolled=False;self.closed_at=None;self.failed=False
        self.subscribed_options=set();self.subscribed_underlyings={self.underlying}
        self.native_first_four=[];self.all_tickets=[];self.predicates=Counter()
        self.close_submission_utc=None;self.close_submission_predicates={}
        self.schedule.on(self.date_rules.every_day(),self.time_rules.at(11,55),self.prepare_fixture)
        self.set_runtime_statistic('scope','Exact WBA native exit fixture; engineering only')

    def prepare_fixture(self):
        needed=[]
        if self.time.date()==date(2019,11,14):needed=[(True,57.5),(False,70)]
        if self.time.date()==date(2019,11,27):needed=[(False,65)]
        for k in needed:
            symbol=self.contracts[k]
            if symbol not in self.subscribed_options:
                self.add_option_contract(symbol,Resolution.MINUTE)
                self.subscribed_options.add(symbol)

    def buyback_quote(self,security):
        if not self.CONFIG.get('buyback',False):return self.good_quote(security)
        bar=security.cache.get_data[QuoteBar]()
        return (bar is not None and not bar.is_fill_forward
            and security.local_time-timedelta(minutes=5)<=bar.end_time<=security.local_time
            and bar.ask is not None and float(bar.ask.close)>0
            and abs(float(bar.ask.close)-float(security.ask_price))<1e-10
            and float(security.bid_price)>=0 and float(security.ask_price)>0
            and float(security.ask_price)>=float(security.bid_price))

    def diagnose(self,side,symbol):
        security=self.securities[symbol];bar=security.cache.get_data[QuoteBar]()
        k=side+'_';self.predicates[k+'observations']+=1
        self.predicates[k+'subscribed']+=int(symbol in self.subscribed_options)
        self.predicates[k+'held_short_one']+=int(float(security.holdings.quantity)==-1)
        if bar is None:self.predicates[k+'bar_absent']+=1;return
        self.predicates[k+'fill_forward']+=int(bar.is_fill_forward)
        fresh=security.local_time-timedelta(minutes=5)<=bar.end_time<=security.local_time
        self.predicates[k+'stale_or_future']+=int(not fresh)
        bid,ask=float(security.bid_price),float(security.ask_price)
        self.predicates[k+'zero_bid']+=int(bid==0)
        self.predicates[k+'negative_bid']+=int(bid<0)
        self.predicates[k+'nonpositive_ask']+=int(ask<=0)
        self.predicates[k+'crossed']+=int(ask<bid)
        self.predicates[k+'current_bar_ask_present']+=int(bar.ask is not None and float(bar.ask.close)>0
            and abs(float(bar.ask.close)-ask)<1e-10)
        self.predicates[k+'fresh_nonff_zero_bid_positive_ask']+=int(fresh and not bar.is_fill_forward and bid==0 and ask>0)
        self.predicates[k+'strict_pass']+=int(self.good_quote(security))
        self.predicates[k+'buyback_pass']+=int(self.buyback_quote(security))

    def record_combo_fills(self,key,tickets):
        # Parent uses real ticket averages, signed quantities, native multipliers and actual event fees.
        super().record_combo_fills(key,tickets)
        expected=[(self.contracts[(True,57.5)],-1,.92),(self.contracts[(False,70)],-1,.44),
                  (self.contracts[(False,70)],1,.22),(self.contracts[(False,65)],-1,.34)]
        for ticket in tickets:
            self.all_tickets.append(ticket)
            if len(self.native_first_four)<2:
                symbol,qty,price=expected[len(self.native_first_four)]
                if (ticket.symbol!=symbol or float(ticket.quantity_filled)!=qty
                        or abs(float(ticket.average_fill_price)-price)>1e-8):
                    raise RuntimeError('Exact-position first four native economic fills differ from original')
                self.native_first_four.append(ticket.order_id)

    def on_data(self,data):
        self.process_pending_combos()
        today=self.time.date()
        # Preserve the frozen request's original day; never reset it to evade deadline.
        if self.exit_requests and today>date(2019,11,22):
            self.failed=True;self.publish('outstanding TIME request crossed original eligible session')
            raise RuntimeError('Mandatory exit lacked fresh quotes on its eligible session: '+self.key)
        if today==date(2019,11,14) and self.time.time()>=time(12) and not self.opened:
            p,c=self.contracts[(True,57.5)],self.contracts[(False,70)]
            if not all(self.liquid_security(self.securities[s]) for s in (p,c)):return
            if self.time.time()!=time(12):raise RuntimeError('Exact fixture OPEN missed original noon')
            self.opened=True
            self.positions[self.key]=dict(put=p,call=c,expiry=date(2019,12,20),quantity=1,multiplier=100.,
                cash=0.,fees=0.,initial=0.,rolls=0,opened=str(today),entry_metadata='multiplier=100;quantity=1;engineering_probe=True')
            def opened():self.positions[self.key]['initial']=self.positions[self.key]['cash']
            self.execute(self.key,[Leg.create(p,-1),Leg.create(c,-1)],'OPEN',on_filled=opened)
        if today==date(2019,11,27) and self.time.time()>=time(12) and not self.rolled and self.positions:
            trade=self.positions[self.key];new=self.contracts[(False,65)]
            old=self.securities[trade['call']];replacement=self.securities[new]
            if (not self.good_quote(old) or not self.good_quote(self.securities[trade['put']])
                    or not self.liquid_security(replacement)):return
            if float(replacement.bid_price)-float(old.ask_price)<float(replacement.symbol_properties.minimum_price_variation):return
            if self.time.time()!=time(12):raise RuntimeError('Exact fixture ROLL missed original noon')
            self.rolled=True
            def rolled():trade['call']=new;trade['rolls']+=1;self.counts['rolls']+=1
            self.execute(self.key,[Leg.create(trade['call'],1),Leg.create(new,-1)],'ROLL',on_filled=rolled)
        if today==date(2019,11,22) and self.time.time()>=time(12) and self.positions:
            trade=self.positions[self.key]
            for side in ('put','call'):self.diagnose(side,trade[side])
            if self.key in self.pending_combos:return
            if not all(self.securities[trade[s]].exchange.exchange_open for s in ('put','call')):return
            self.exit_requests.setdefault(self.key,dict(reason='TIME',day=today))
            if all(self.buyback_quote(self.securities[trade[s]]) for s in ('put','call')):
                # Bind predicate evidence to this actual submission, rather than
                # earlier observations somewhere in the session. No raw quote
                # series or hypothetical fill is exported.
                self.close_submission_utc=str(self.utc_time)
                for side in ('put','call'):
                    security=self.securities[trade[side]]
                    bar=security.cache.get_data[QuoteBar]()
                    fresh=(bar is not None and not bar.is_fill_forward
                        and security.local_time-timedelta(minutes=5)<=bar.end_time<=security.local_time)
                    self.close_submission_predicates[side]=dict(
                        fresh_nonff=bool(fresh),
                        current_bar_ask=bool(bar is not None and bar.ask is not None and float(bar.ask.close)>0
                            and abs(float(bar.ask.close)-float(security.ask_price))<1e-10),
                        zero_bid_positive_ask=bool(float(security.bid_price)==0 and float(security.ask_price)>0),
                        strict_pass=bool(self.good_quote(security)),
                        buyback_pass=bool(self.buyback_quote(security)))
                def closed():
                    self.closed_at=self.time
                    self.finish_close(self.key,'TIME')
                # Actual order annotations retain only quote-validity flags and
                # this order's decision timestamp, so a log cap cannot erase
                # the gate-to-ticket binding. They contain no quote history.
                reason='TIME;quote_gate_utc='+self.close_submission_utc.replace(' ','T')
                for side in ('put','call'):
                    receipt=self.close_submission_predicates[side]
                    reason+=';'+side+'_quote_fresh='+str(receipt['fresh_nonff'])
                    reason+=';'+side+'_current_bar_ask='+str(receipt['current_bar_ask'])
                    reason+=';'+side+'_zero_bid='+str(receipt['zero_bid_positive_ask'])
                self.execute(self.key,[Leg.create(trade['put'],1),Leg.create(trade['call'],1)],reason,on_filled=closed)
                del self.exit_requests[self.key]

    def publish(self,note):
        residual={str(s.id):float(self.portfolio[s].quantity) for s in self.contracts.values() if float(self.portfolio[s].quantity)}
        fees=sum(float(e.order_fee.value.amount) for t in self.all_tickets for e in t.order_events)
        cashflow=sum(-float(t.quantity_filled)*float(t.average_fill_price)*float(self.securities[t.symbol].symbol_properties.contract_multiplier) for t in self.all_tickets)
        result=dict(variant='buyback' if self.CONFIG.get('buyback',False) else 'strict_control',note=note,
            initial_cash=self.initial_cash,equity=float(self.portfolio.total_portfolio_value),fees=fees,
            actual_ticket_cashflow=cashflow,native_order_ids=[t.order_id for t in self.all_tickets],
            first_two_native_fills_matched=len(self.native_first_four),residual_native=residual,
            close_submission_utc=self.close_submission_utc,
            close_submission_predicates=self.close_submission_predicates,
            closed_at=str(self.closed_at),counts=dict(self.counts),predicate_counts=dict(self.predicates))
        self.log('WAG_EXIT_FIXTURE '+json.dumps(result))
        for k,v in self.predicates.items():self.set_runtime_statistic(k,str(v))
        return result

    def on_end_of_algorithm(self):
        self.process_pending_combos();r=self.publish('end-of-fixture; no synthetic liquidation')
        if self.failed:return # Preserve the prior explicit runtime error and actual residual evidence.
        if self.positions or self.pending_combos or self.exit_requests or self.portfolio.invested:
            raise RuntimeError('WBA fixture left actual residual positions')
        if len(self.all_tickets)!=4 or len(self.native_first_four)!=2 or self.counts['rolls']!=0 or self.counts['TIME']!=1:
            raise RuntimeError('Exact original opening/roll/closing ticket path not complete')
        if self.closed_at!=datetime(2019,11,22,12):raise RuntimeError('Native fixture did not close at first eligible noon28DTE')
        if abs(float(self.portfolio.total_portfolio_value)-(self.initial_cash+r['actual_ticket_cashflow']-r['fees']))>.005:
            raise RuntimeError('WBA actual fees/cash/account mismatch')
        if abs(sum(self.closed_pnl)-(r['actual_ticket_cashflow']-r['fees']))>.005:
            raise RuntimeError('WBA cycle actual-fill/account mismatch')
