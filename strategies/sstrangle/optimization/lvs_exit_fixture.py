"""Future-use native LVS execution fixture; NOT integrated, queued or cloud-proved.
Only genuine default-model tickets/events create cashflow, quantities and fees.
"""
from AlgorithmImports import *
from datetime import date,datetime,time,timedelta
from decimal import Decimal,ROUND_CEILING
import json


def declared_buy_limit(bid,tick):
    """ONE predeclared policy: bid+two minimum ticks, rounded up to tick.
    This is a native limit instruction, never an assumed executed price.
    """
    b,t=Decimal(str(bid)),Decimal(str(tick))
    if not b.is_finite() or not t.is_finite() or b<=0 or t<=0:raise ValueError('Invalid bid/tick')
    return float(((b+2*t)/t).to_integral_value(rounding=ROUND_CEILING)*t)


class LVSExitRegression(QCAlgorithm):
    CONFIG = {}

    def initialize(self):
        self.set_start_date(2015,7,27);self.set_end_date(2015,9,1)
        self.set_time_zone(TimeZones.NEW_YORK)
        self.initial_cash=57718.42;self.set_cash(self.initial_cash)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,AccountType.MARGIN)
        self.underlying=Symbol(SecurityIdentifier.Parse('LVS T4J5S7AT6WRP'),'LVS')
        self.add_equity(self.underlying,Resolution.MINUTE).set_data_normalization_mode(DataNormalizationMode.RAW)
        self.contracts={}
        for put,strike,encoded in [(True,47.5,'3033TD1OREOZQ'),(False,60.,'W3ZT7JJZY6RQ')]:
            sid='LVS '+encoded+'|LVS T4J5S7AT6WRP'
            symbol=Symbol(SecurityIdentifier.Parse(sid),'LVS   150918'+('P' if put else 'C')+str(int(strike*1000)).zfill(8))
            if (str(symbol.id)!=sid or str(symbol.underlying.id)!=str(self.underlying.id)
                or symbol.id.date.date()!=date(2015,9,18) or float(symbol.id.strike_price)!=strike):
                raise RuntimeError('Wrong native LVS fixture contract')
            self.contracts['put' if put else 'call']=symbol
        self.state='WAIT_OPEN';self.subscribed=False;self.phase_tickets=[];self.tickets={}
        self.events={};self.open_ids=[];self.close_ids=[];self.triggered_at=None
        self.cancel_requested=set();self.cancel_started=None;self.forced=False;self.done=False
        self.limit_instructions={}
        self.failure_note=None;self.limit_deadline=None;self.market_deadline=None
        self.intended_fallback={};self.pending_bind=False
        self.schedule.on(self.date_rules.every_day(),self.time_rules.at(11,55),self.prepare_fixture)
        self.set_runtime_statistic('scope','Isolated LVS native execution only; ZC batch path excluded')

    def prepare_fixture(self):
        if self.time.date()==date(2015,7,28) and not self.subscribed:
            for symbol in self.contracts.values():self.add_option_contract(symbol,Resolution.MINUTE)
            self.subscribed=True

    def good_quote(self,symbol):
        s=self.securities[symbol];bar=s.cache.get_data[QuoteBar]()
        return (bar is not None and not bar.is_fill_forward
            and s.local_time-timedelta(minutes=5)<=bar.end_time<=s.local_time
            and float(s.bid_price)>0 and float(s.ask_price)>=float(s.bid_price))

    def liquid_entry(self,symbol):
        if not self.good_quote(symbol):return False
        s=self.securities[symbol];b,a=float(s.bid_price),float(s.ask_price)
        tick=float(s.symbol_properties.minimum_price_variation)
        return b>=tick and a-b<=max(2*tick,.25*(b+a)/2)

    def on_order_event(self,event):
        key=(int(event.order_id),int(event.id))
        rec=dict(order_id=int(event.order_id),event_id=int(event.id),native_sid=str(event.symbol.id),
            quantity=float(event.fill_quantity),price=float(event.fill_price),
            fee=float(event.order_fee.value.amount),status=str(event.status),utc=str(event.utc_time))
        if key in self.events and self.events[key]!=rec:
            self.failure_note='Native event identity changed';return
        self.events[key]=rec

    def bind(self,tickets,phase):
        ts=list(tickets)
        if len({int(t.order_id) for t in ts})!=len(ts):raise RuntimeError('Duplicate native ticket')
        for t in ts:
            if int(t.order_id) in self.tickets:raise RuntimeError('Reused native order')
            self.tickets[int(t.order_id)]=t
            (self.open_ids if phase=='OPEN' else self.close_ids).append(int(t.order_id))
        self.phase_tickets=ts

    def reconcile(self):
        if self.pending_bind:return
        # Contract subscriptions intentionally start shortly before the real
        # entry. A SID constructed in initialize is not yet a portfolio key.
        if not self.subscribed:
            if self.tickets or any(e['quantity'] for e in self.events.values()) or self.portfolio.invested:
                raise RuntimeError('Unexpected actual exposure before native contract subscriptions')
            return
        unknown={e['order_id'] for e in self.events.values() if e['quantity']} - set(self.tickets)
        if unknown:raise RuntimeError('Unexpected broker native execution retained: '+str(sorted(unknown)))
        expected={str(s.id):0. for s in self.contracts.values()}
        for order_id,t in self.tickets.items():
            fills=[e for e in self.events.values() if e['order_id']==order_id and e['quantity']]
            qty=sum(e['quantity'] for e in fills)
            if abs(qty-float(t.quantity_filled))>1e-8:raise RuntimeError('Native event/ticket quantity mismatch')
            expected[str(t.symbol.id)]+=qty
            if float(self.securities[t.symbol].symbol_properties.contract_multiplier)!=100:
                raise RuntimeError('Fixture requires original model multiplier100')
        if any(abs(float(self.portfolio[s].quantity)-expected[str(s.id)])>1e-8 for s in self.contracts.values()):
            raise RuntimeError('Native holdings/event ledger mismatch; no synthetic reconciliation')

    def phase_complete(self):
        return all(t.status==OrderStatus.FILLED and float(t.quantity_filled)==float(t.quantity) for t in self.phase_tickets)

    def all_terminal(self,tickets):
        return all(t.status in (OrderStatus.FILLED,OrderStatus.CANCELED,OrderStatus.INVALID) for t in tickets)

    def check_open_fills(self):
        if len(self.open_ids)!=2:raise RuntimeError('Original OPEN native pair missing')
        expected={self.contracts['put']:(-2.,.61),self.contracts['call']:(-2.,.62)}
        for i in self.open_ids:
            t=self.tickets[i];qty,price=expected[t.symbol]
            if float(t.quantity_filled)!=qty or abs(float(t.average_fill_price)-price)>1e-8:
                raise RuntimeError('Original LVS native opening fills do not match')
        fees=sum(e['fee'] for e in self.events.values() if e['order_id'] in self.open_ids)
        if abs(fees-2.6)>1e-8:raise RuntimeError('Original opening fees differ')

    def on_margin_call(self,requests):
        # Preserve default broker liquidation; do not suppress, replace or return an empty request list.
        self.forced=True;self.failure_note='Unexpected default-margin overlap in isolated execution fixture'
        return requests

    def on_data(self,data):
        if self.pending_bind:return
        if self.failure_note:raise RuntimeError(self.failure_note)
        self.reconcile()
        if self.done:return
        today=self.time.date()
        if self.state=='WAIT_OPEN':
            if today==date(2015,7,28) and self.time.time()>=time(12):
                if self.time.time()!=time(12) or not all(self.liquid_entry(s) for s in self.contracts.values()):
                    raise RuntimeError('Original noon OPEN eligibility not reproduced')
                self.pending_bind=True
                try:self.bind(self.combo_market_order([Leg.create(s,-1) for s in self.contracts.values()],2,
                    asynchronous=False,tag='LVS_FIXTURE:OPEN;multiplier=100;engineering_probe=True'),'OPEN')
                finally:self.pending_bind=False
                self.state='OPEN_PENDING';self.market_deadline=self.time+timedelta(minutes=5)
        if self.state=='OPEN_PENDING':
            if any(t.status in (OrderStatus.INVALID,OrderStatus.CANCELED) for t in self.phase_tickets):raise RuntimeError('Original OPEN rejected')
            if not self.phase_complete():
                if self.time>=self.market_deadline:raise RuntimeError('Original OPEN remained pending')
                return
            self.reconcile();self.check_open_fills();self.state='HELD'
        if self.state=='HELD' and today==date(2015,8,19) and self.time.time()>=time(9,31):
            if self.time.time()!=time(9,31) or not all(self.good_quote(s) for s in self.contracts.values()):
                raise RuntimeError('Original voluntary STOP trigger quote/time not reproduced')
            if any(float(self.portfolio[s].quantity)!=-2 for s in self.contracts.values()):raise RuntimeError('Original two-lot shorts missing')
            # Genuine ask-based trigger, not a forced price. Original stop_multiple1 and close fee estimate2.60.
            close_cost=sum(float(self.securities[s].ask_price) for s in self.contracts.values())*200
            if 246-2.6-2.6-close_cost > -246:raise RuntimeError('Original risk STOP not triggered on actual quotes')
            self.triggered_at=self.time
            self.pending_bind=True
            try:
                if not self.CONFIG.get('limit_exit',False):
                    ts=self.combo_market_order([Leg.create(s,1) for s in self.contracts.values()],2,
                        asynchronous=False,tag='LVS_FIXTURE:STOP;attempt=market_control;multiplier=100')
                    self.bind(ts,'CLOSE');self.state='CONTROL_MARKET'
                else:
                    ts=[]
                    for s in self.contracts.values():
                        if self.forced or float(self.portfolio[s].quantity)!=-2:
                            raise RuntimeError('Unexpected default broker overlap before native limit submission')
                        security=self.securities[s]
                        price=declared_buy_limit(security.bid_price,security.symbol_properties.minimum_price_variation)
                        tick=float(security.symbol_properties.minimum_price_variation)
                        ticket=self.limit_order(s,2,price,tag='LVS_FIXTURE:STOP;attempt=limit;exit_intent=1;multiplier=100;minimum_price_tick='+str(tick))
                        ts.append(ticket)
                        self.limit_instructions[str(ticket.order_id)]=dict(native_sid=str(s.id),minimum_price_tick=tick,limit_price=price)
                    self.bind(ts,'CLOSE');self.limit_tickets=list(ts)
                    self.state='LIMIT';self.limit_deadline=self.time+timedelta(minutes=2)
            finally:self.pending_bind=False
            self.market_deadline=self.time+timedelta(minutes=5)
        if self.state=='LIMIT':
            if self.phase_complete():self.finish_actual();return
            if self.time>=self.limit_deadline or any(t.status==OrderStatus.INVALID for t in self.limit_tickets):
                self.state='CANCELING';self.cancel_started=self.time
                for t in self.limit_tickets:
                    if t.status not in (OrderStatus.FILLED,OrderStatus.CANCELED,OrderStatus.INVALID):
                        if int(t.order_id) not in self.cancel_requested:
                            self.cancel_requested.add(int(t.order_id));t.cancel('Fixture two-minute limit timeout; no assumed cancellation')
        if self.state=='CANCELING':
            if not self.all_terminal(self.limit_tickets):
                if self.time-self.cancel_started>=timedelta(minutes=2):raise RuntimeError('Cancellation not definitive; market fallback prohibited')
                return
            self.reconcile()
            if any(int(t.order_id) in {int(o.id) for o in self.transactions.get_open_orders()} for t in self.limit_tickets):
                raise RuntimeError('Terminal cancel still has an open native order')
            residual={s:-float(self.portfolio[s].quantity) for s in self.contracts.values()}
            if any(q<0 or q!=int(q) for q in residual.values()):raise RuntimeError('Residual native quantity would overclose')
            if not any(residual.values()):self.finish_actual();return
            self.intended_fallback={str(s.id):q for s,q in residual.items() if q}
            self.pending_bind=True
            try:
                ts=[]
                for s,q in residual.items():
                    if not q:continue
                    if self.forced or float(self.portfolio[s].quantity)!=-q:
                        raise RuntimeError('Unexpected default broker overlap before native residual market')
                    ts.append(self.market_order(s,int(q),asynchronous=False,
                        tag='LVS_FIXTURE:STOP;attempt=market_residual;exit_intent=1;multiplier=100'))
                self.bind(ts,'CLOSE');self.state='RESIDUAL_MARKET';self.market_deadline=self.time+timedelta(minutes=5)
            finally:self.pending_bind=False
        if self.state in ('CONTROL_MARKET','RESIDUAL_MARKET'):
            if any(t.status in (OrderStatus.INVALID,OrderStatus.CANCELED) for t in self.phase_tickets):raise RuntimeError('Market close rejected/partial canceled; real exposure remains')
            if self.phase_complete():self.finish_actual();return
            if self.time>=self.market_deadline:raise RuntimeError('Native market close not completed within five minutes')
        # Forced/mandatory exits are not replaced by this optional policy. This fixture must close before21DTE.
        if (date(2015,9,18)-today).days<=21 and self.portfolio.invested:
            raise RuntimeError('Fixture voluntary execution unresolved before mandatory21DTE; no suppressed mandatory loss')

    def receipt(self,note):
        fills=[e for e in self.events.values() if e['quantity']]
        fees=sum(e['fee'] for e in self.events.values())
        known={str(s.id) for s in self.contracts.values()}
        cashflow=(sum(-e['quantity']*e['price']*100 for e in fills)
            if all(e['native_sid'] in known for e in fills) else None)
        return dict(note=note,variant='bid_plus_two_ticks_limit_2min' if self.CONFIG.get('limit_exit',False) else 'market_control',
            scope='Isolated LVS only; no simultaneous ZC replay',initial_cash=self.initial_cash,
            equity=float(self.portfolio.total_portfolio_value),actual_cashflow=cashflow,actual_fees=fees,
            actual_fill_events=fills,native_order_ids=sorted(self.tickets),limit_order_parameters=getattr(self,'limit_instructions',{}),
            native_attempt_status={str(i):str(t.status) for i,t in self.tickets.items()},
            cancel_requested_ids=sorted(self.cancel_requested),actual_residual_fallback=self.intended_fallback,
            residual_native={str(s.id):float(self.portfolio[s].quantity) for s in self.contracts.values() if s in self.securities},
            unsubscribed_native=[str(s.id) for s in self.contracts.values() if s not in self.securities],
            trigger_at=str(self.triggered_at),default_margin_overlap=self.forced,completed=self.done)

    def finish_actual(self):
        self.reconcile()
        if not self.all_terminal(self.tickets.values()) or self.transactions.get_open_orders():raise RuntimeError('Unresolved native orders at completion')
        if self.portfolio.invested or any(float(self.portfolio[s].quantity) for s in self.contracts.values()):raise RuntimeError('Actual native residual holdings remain')
        r=self.receipt('Actual flat completion; no invented fills')
        if not self.CONFIG.get('limit_exit',False):
            expected={self.contracts['put']:62.,self.contracts['call']:.11}
            if len(self.close_ids)!=2:raise RuntimeError('Native market-control pair count mismatch')
            for i in self.close_ids:
                t=self.tickets[i]
                if float(t.quantity_filled)!=2 or abs(float(t.average_fill_price)-expected[t.symbol])>1e-8:
                    raise RuntimeError('Native original62/.11 control not reproduced')
            if abs(r['actual_fees']-4.9)>1e-8 or abs(r['actual_cashflow']-r['actual_fees']+12180.9)>1e-8:
                raise RuntimeError('Original native control economic path not reproduced')
        if self.triggered_at!=datetime(2015,8,19,9,31):raise RuntimeError('Original STOP trigger time changed')
        if abs(r['equity']-(self.initial_cash+r['actual_cashflow']-r['actual_fees']))>.005:
            raise RuntimeError('Actual native event fees/cash/account do not reconcile')
        self.done=True;self.state='DONE';self.log('LVS_EXIT_RECEIPT '+json.dumps(self.receipt('Genuine completed native execution')))

    def on_end_of_algorithm(self):
        self.log('LVS_EXIT_RECEIPT '+json.dumps(self.receipt('End of fixed calendar; no synthetic liquidation')))
        if self.forced or self.failure_note:return # Preserve the real existing failure and any broker orders.
        if not self.done:raise RuntimeError('Native execution fixture incomplete; actual exposures retained')
