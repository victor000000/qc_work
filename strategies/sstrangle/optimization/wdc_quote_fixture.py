"""Exact native WDC entry/two rolls and bounded mandatory-session diagnostics.

Known trade replay for engineering only. No strategy search, quote history export,
fill model replacement, stale-price fill, or synthetic final liquidation.
"""
from AlgorithmImports import *
from basket_strategy import BasketShortStrangle
from collections import Counter
from datetime import date, datetime, time, timedelta
import json

FIELDS = ('observations', 'cache_present', 'cache_fresh_real', 'slice_present',
          'slice_fresh_real', 'zero_bid', 'positive_ask', 'positive_bid',
          'strict_pass', 'buyback_pass', 'cache_stale', 'cache_fill_forward',
          'slice_fill_forward', 'clock_matches', 'product_open', 'held_short_one')
CONTRACTS = [(True,40.,'313OA1ZLJM1MU'), (False,57.5,'X4K9WM8RT24M'),
             (True,45.,'313OA1ZSBNMHY'), (True,47.5,'313OA21RFPEKM')]
GOLD = [(date(2019,3,25),True,40.,-1,1.08), (date(2019,3,25),False,57.5,-1,.75),
        (date(2019,4,4),True,40.,1,.37), (date(2019,4,4),True,45.,-1,1.),
        (date(2019,4,17),True,45.,1,.58), (date(2019,4,17),True,47.5,-1,.96)]
DUE = date(2019,4,22)  # Apr19=28DTE is Good Friday; first product-open noon is Apr22.


class WDCQuoteRegression(BasketShortStrangle):
    CONFIG = {}

    def initialize(self):
        self.set_start_date(2019,3,24);self.set_end_date(2019,4,22)
        self.set_time_zone(TimeZones.NEW_YORK)
        self.initial_cash=39557.74;self.set_cash(self.initial_cash)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,AccountType.MARGIN)
        self.underlying=Symbol(SecurityIdentifier.Parse('WDC R735QTJ8XC9X'),'WDC')
        self.add_equity(self.underlying,Resolution.MINUTE).set_data_normalization_mode(DataNormalizationMode.RAW)
        self.key=str(self.underlying.id);self.contracts={}
        for put,strike,encoded in CONTRACTS:
            sid='WDC '+encoded+'|'+self.key
            symbol=Symbol(SecurityIdentifier.Parse(sid),'WDC   190517'+('P' if put else 'C')+str(int(strike*1000)).zfill(8))
            if (str(symbol.id)!=sid or str(symbol.underlying.id)!=self.key
                or symbol.id.date.date()!=date(2019,5,17) or float(symbol.id.strike_price)!=strike):
                raise RuntimeError('Native WDC fixture contract mismatch')
            self.contracts[(put,strike)]=symbol
        self.states={self.key:dict(ticker='WDC',eq=self.underlying,future=False)}
        self.positions={};self.pending_combos={};self.exit_requests={};self.counts=Counter()
        self.active_equity=[];self.closed_pnl=[];self.insolvency=None
        self.subscribed_options=set();self.subscribed_underlyings={self.underlying}
        self.all_tickets=[];self.native_matched=0;self.opened=False;self.started_rolls=set()
        self.quote_counts={'put':Counter(),'call':Counter()};self.closed_at=None
        self.schedule.on(self.date_rules.every_day(),self.time_rules.at(11,55),self.prepare_fixture)
        self.set_runtime_statistic('scope','WDC quote-gate diagnosis only; not strategy performance')

    def prepare_fixture(self):
        needed={date(2019,3,25):[(True,40.),(False,57.5)],date(2019,4,4):[(True,45.)],
                date(2019,4,17):[(True,47.5)]}.get(self.time.date(),[])
        for k in needed:
            symbol=self.contracts[k]
            if symbol not in self.subscribed_options:
                security=self.add_option_contract(symbol,Resolution.MINUTE)
                if float(security.symbol_properties.contract_multiplier)!=100:
                    raise RuntimeError('Unexpected native WDC multiplier')
                self.subscribed_options.add(symbol)

    def record_combo_fills(self,key,tickets):
        super().record_combo_fills(key,tickets)
        for ticket in tickets:
            if self.native_matched<len(GOLD):
                day,put,strike,quantity,price=GOLD[self.native_matched]
                if (self.time!=datetime.combine(day,time(12)) or ticket.symbol!=self.contracts[(put,strike)]
                    or float(ticket.quantity_filled)!=quantity or abs(float(ticket.average_fill_price)-price)>1e-8):
                    raise RuntimeError('WDC first six actual native fills differ from failed trial')
                self.native_matched+=1
            self.all_tickets.append(ticket)

    def observe(self,side,data):
        symbol=self.positions[self.key][side];security=self.securities[symbol]
        bar=security.cache.get_data[QuoteBar]();quotes=data.quote_bars
        present=quotes.contains_key(symbol) if hasattr(quotes,'contains_key') else symbol in quotes
        sliced=quotes[symbol] if present else None
        fresh=lambda b:b is not None and not b.is_fill_forward and security.local_time-timedelta(minutes=5)<=b.end_time<=security.local_time
        bid,ask=float(security.bid_price),float(security.ask_price)
        ask_ok=(fresh(bar) and bar.ask is not None and float(bar.ask.close)>0
                and abs(float(bar.ask.close)-ask)<1e-10 and bid>=0 and ask>=bid and ask>0)
        values=dict(observations=True,cache_present=bar is not None,cache_fresh_real=fresh(bar),
            slice_present=sliced is not None,slice_fresh_real=fresh(sliced),zero_bid=bid==0,
            positive_ask=ask>0,positive_bid=bid>0,strict_pass=self.good_quote(security),buyback_pass=ask_ok,
            cache_stale=bar is not None and bar.end_time<security.local_time-timedelta(minutes=5),
            cache_fill_forward=bar is not None and bar.is_fill_forward,
            slice_fill_forward=sliced is not None and sliced.is_fill_forward,
            clock_matches=security.local_time==self.time,product_open=security.exchange.exchange_open,
            held_short_one=float(security.holdings.quantity)==-1)
        for k,v in values.items():self.quote_counts[side][k]+=int(v)

    def on_data(self,data):
        self.process_pending_combos();today=self.time.date()
        if today==date(2019,3,25) and self.time.time()>=time(12) and not self.opened:
            p,c=self.contracts[(True,40.)],self.contracts[(False,57.5)]
            if not all(self.liquid_security(self.securities[s]) for s in (p,c)):return
            if self.time.time()!=time(12):raise RuntimeError('Original WDC OPEN missed noon')
            self.opened=True
            self.positions[self.key]=dict(put=p,call=c,expiry=date(2019,5,17),quantity=1,multiplier=100.,
                cash=0.,fees=0.,initial=0.,rolls=0,opened=str(today),entry_metadata='multiplier=100;quantity=1;engineering_probe=True')
            self.execute(self.key,[Leg.create(p,-1),Leg.create(c,-1)],'OPEN',
                on_filled=lambda:self.positions[self.key].update(initial=self.positions[self.key]['cash']))
        if today in (date(2019,4,4),date(2019,4,17)) and self.time.time()>=time(12) and today not in self.started_rolls:
            trade=self.positions[self.key];strike=45. if today==date(2019,4,4) else 47.5
            new=self.contracts[(True,strike)];old=self.securities[trade['put']];replacement=self.securities[new]
            if not self.good_quote(old) or not self.good_quote(self.securities[trade['call']]) or not self.liquid_security(replacement):return
            if float(replacement.bid_price)-float(old.ask_price)<float(replacement.symbol_properties.minimum_price_variation):return
            if self.time.time()!=time(12):raise RuntimeError('Original WDC ROLL missed noon')
            self.started_rolls.add(today)
            def rolled():trade['put']=new;trade['rolls']+=1;self.counts['rolls']+=1
            self.execute(self.key,[Leg.create(trade['put'],1),Leg.create(new,-1)],'ROLL',on_filled=rolled)
        if today==DUE and time(12)<=self.time.time()<=time(16) and self.key in self.positions:
            for side in ('put','call'):self.observe(side,data)
            if self.key in self.pending_combos:return
            trade=self.positions[self.key]
            if not all(self.securities[trade[s]].exchange.exchange_open for s in ('put','call')):return
            self.exit_requests.setdefault(self.key,dict(reason='TIME',day=DUE))
            if not all(self.good_quote(self.securities[trade[s]]) for s in ('put','call')):return
            def closed():self.closed_at=self.time;self.finish_close(self.key,'TIME')
            self.execute(self.key,[Leg.create(trade['put'],1),Leg.create(trade['call'],1)],'TIME',on_filled=closed)
            del self.exit_requests[self.key]

    def on_end_of_algorithm(self):
        self.process_pending_combos()
        fees=sum(float(e.order_fee.value.amount) for t in self.all_tickets for e in t.order_events)
        cashflow=sum(-float(t.quantity_filled)*float(t.average_fill_price)*100 for t in self.all_tickets)
        residual={str(s.id):float(self.portfolio[s].quantity) for s in self.subscribed_options if float(self.portfolio[s].quantity)}
        if self.native_matched!=6 or self.pending_combos:raise RuntimeError('WDC native path incomplete')
        if abs(float(self.portfolio.cash)-(self.initial_cash+cashflow-fees))>.0051:raise RuntimeError('WDC actual fill cash reconciliation failed')
        if any(self.quote_counts[s]['observations']==0 for s in ('put','call')):raise RuntimeError('Mandatory-session diagnostic absent')
        receipt=dict(scope='Engineering only; real residuals retained, no synthetic liquidation',fields=list(FIELDS),
            counts={s:[self.quote_counts[s][k] for k in FIELDS] for s in ('put','call')},
            native_first_six_matched=self.native_matched,fees=fees,cashflow=cashflow,residuals=residual,closed_at=str(self.closed_at))
        self.log('WDC_QUOTE_DIAG '+json.dumps(receipt))
        for side in ('put','call'):self.set_runtime_statistic('wdc_'+side,json.dumps(receipt['counts'][side]))
        self.set_runtime_statistic('wdc_native_matched',str(self.native_matched))
        self.set_runtime_statistic('wdc_residual_count',str(len(residual)))
        self.set_runtime_statistic('wdc_closed_at',str(self.closed_at))
        self.set_runtime_statistic('wdc_cash',str(float(self.portfolio.cash)))
        self.set_runtime_statistic('wdc_equity',str(float(self.portfolio.total_portfolio_value)))
