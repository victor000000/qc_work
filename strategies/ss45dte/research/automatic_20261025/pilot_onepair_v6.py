"""SS45DTE mechanical research baseline, independent of SSTRANGLE.

Prior-session QC OptionUniverse for selection/IVR; fresh minute QuoteBars for
execution. Explicit variant switches never silently relax a filter. Backtest only.
"""
from AlgorithmImports import *
from collections import Counter
from datetime import date, datetime, time, timedelta
import math
import json

CONFIG = {'start': [2024, 1, 2], 'end': [2026, 10, 23], 'names': ['CRWD', 'EWZ', 'META', 'TLT', 'SWKS'], 'cash': 150000, 'ivr_gate': True, 'risk_sizing': True, 'delta_stop': False, 'spread_cap': 0.05, 'min_oi': 500, 'trade_budget': 0.01, 'cluster_budget': 0.01, 'book_budget': 0.02, 'margin_cap': 0.2, 'fee': 1.0, 'slippage': 0.01, 'max_pairs': 1, 'lookback': 252, 'min_iv_points': 60, 'trade_margin_cap': 0.05, 'max_open_pairs': 2}


def normal(x):
    return .5*(1+math.erf(x/math.sqrt(2)))


def option_value(spot, strike, years, vol, put, rate=.04):
    """European BSM sensitivity approximation, not the QC execution price/model."""
    if years <= 0:
        return max(strike-spot if put else spot-strike, 0.)
    if min(spot,strike,vol) <= 0:
        raise ValueError('Invalid model input')
    root=vol*math.sqrt(years)
    d1=(math.log(spot/strike)+(rate+.5*vol*vol)*years)/root
    d2=d1-root
    value=(strike*math.exp(-rate*years)*normal(-d2)-spot*normal(-d1) if put
           else spot*normal(d1)-strike*math.exp(-rate*years)*normal(d2))
    return value


def implied_vol(price,spot,strike,years,put):
    lo,hi=.005,5.
    if not years>0 or not min(price,spot,strike)>0:return None
    if not option_value(spot,strike,years,lo,put)<=price<=option_value(spot,strike,years,hi,put):return None
    for _ in range(45):
        mid=(lo+hi)/2
        if option_value(spot,strike,years,mid,put)>price:hi=mid
        else:lo=mid
    return (lo+hi)/2


def model_delta(spot,strike,years,vol,put):
    d1=(math.log(spot/strike)+(.04+.5*vol*vol)*years)/(vol*math.sqrt(years))
    return normal(d1)-(1 if put else 0)


def iv_rank(values,current):
    low,high=min(values),max(values)
    return None if high<=low else 100*(current-low)/(high-low)


def quantity_for(loss,budget,cap):
    if not math.isfinite(loss) or loss<=0 or budget<=0:return 0
    return max(0,min(cap,int(budget//loss)))


def standalone_margin(values):
    """QC initial margins are signed; reserve positive cash for each short leg."""
    vals=[float(v) for v in values]
    if not vals or any(not math.isfinite(v) or v==0 for v in vals):return float('inf')
    return sum(abs(v) for v in vals)


def target_exit(expiry,is_full_session,exit_dte=21):
    day=expiry-timedelta(days=exit_dte)
    while not is_full_session(day):day-=timedelta(days=1)
    return day


class AbsoluteSlippage:
    def get_slippage_approximation(self, asset, order):
        return CONFIG['slippage']


class ContractFee(FeeModel):
    def get_order_fee(self, parameters):
        return OrderFee(CashAmount(abs(float(parameters.order.quantity))*CONFIG['fee'],'USD'))


class Ss45Dte(QCAlgorithm):
    def initialize(self):
        if self.live_mode:raise RuntimeError('Research algorithm: live execution disabled')
        self.set_start_date(*CONFIG['start']);self.set_end_date(*CONFIG['end'])
        self.set_cash(CONFIG['cash']);self.set_time_zone(TimeZones.NEW_YORK)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,AccountType.MARGIN)
        self.counts=Counter();self.states={};self.iv={};self.eq={};self.candidates={}
        self.earnings={};self.earnings_seen=None;self.last_attempt={};self.realized=[]
        self.episode=0;self.total_fee=0.;self.last_tick=None;self.last_day=None
        self.min_margin=CONFIG['cash'];self.peak=CONFIG['cash'];self.halt=False
        self.end=date(*CONFIG['end']);self.last_daily={};self.daily_records={};self.seeded=set()
        self.assignment_names=set();self.subscribed=set()
        for name in CONFIG['names']:
            sec=self.add_equity(name,Resolution.MINUTE)
            sec.set_data_normalization_mode(DataNormalizationMode.RAW)
            self.eq[name]=sec.symbol;self.iv[name]={}
        self.spy=self.add_equity('SPY',Resolution.MINUTE).symbol
        self.securities[self.spy].set_data_normalization_mode(DataNormalizationMode.RAW)
        self.set_benchmark(self.spy)
        self.universe_settings.resolution=Resolution.DAILY
        self.universe_settings.asynchronous=False
        self.add_universe(EODHDUpcomingEarnings,self.earnings_universe)
        self.schedule.on(self.date_rules.every_day(self.spy),self.time_rules.after_market_open(self.spy,30),self.prepare)
        self.schedule.on(self.date_rules.every_day(self.spy),self.time_rules.before_market_close(self.spy,30),self.review)
        self.set_runtime_statistic('spec','SS45DTE automatic v6; cumulative stress and corrected costs')

    def earnings_universe(self, rows):
        self.earnings_seen=self.time.date()
        for r in rows:
            if r.end_time>self.time:raise RuntimeError('Future earnings observation')
            if r.symbol in self.eq.values():
                self.earnings.setdefault(r.symbol,{})[r.report_date.date()]=self.time.date()
        return []

    def full_session(self,day):
        hours=self.securities[self.spy].exchange.hours
        dt=datetime.combine(day,time.min)
        if not hours.is_date_open(dt):return False
        close=hours.get_next_market_close(dt,False)
        return close.date()==day and close.hour>=16

    def monthly(self,expiry):
        first=date(expiry.year,expiry.month,1)
        third=first+timedelta(days=(4-first.weekday())%7+14)
        while not self.securities[self.spy].exchange.hours.is_date_open(datetime.combine(third,time.min)):
            third-=timedelta(days=1)
        return expiry==third

    def records(self,name):
        today=self.time.date()
        if self.last_daily.get(name)==today:return self.daily_records[name]
        out=[]
        for c in self.option_chain(self.eq[name]):
            exp=c.expiry.date();dte=(exp-today).days
            if not 1<=dte<=65:continue
            observed=c.time.date()
            if observed>today:raise RuntimeError('Future chain')
            out.append(dict(symbol=c.symbol,expiry=exp,strike=float(c.strike),put=c.right==OptionRight.PUT,
                            iv=float(c.implied_volatility),delta=float(c.greeks.delta),oi=float(c.open_interest),
                            spot=float(c.underlying_last_price),observed=observed))
        self.counts['chain_days']+=1
        self.last_daily[name]=today;self.daily_records[name]=out
        return out

    def atm(self,records,today):
        eligible=[r for r in records if 20<=(r['expiry']-today).days<=60 and r['spot']>0 and r['iv']>0]
        if not eligible:return None
        exp=min({r['expiry'] for r in eligible},key=lambda e:(abs((e-today).days-30),e))
        sides=[]
        for put in [True,False]:
            rs=[r for r in eligible if r['expiry']==exp and r['put']==put]
            if not rs:return None
            sides.append(min(rs,key=lambda r:(abs(r['strike']-r['spot']),r['strike'])))
        return sum(r['iv'] for r in sides)/2

    def seed_iv(self,name):
        if name in self.seeded:return
        self.seeded.add(name)
        if not CONFIG['ivr_gate']:return
        canonical=Symbol.create_canonical_option(self.eq[name])
        for chain in self.history[OptionUniverse](canonical,self.time-timedelta(days=410),self.time):
            day=chain.end_time.date()
            if day>self.time.date():raise RuntimeError('Future IV history')
            if not chain.underlying:continue
            spot=float(chain.underlying.price)
            rec=[]
            for c in chain.data:
                sid=c.symbol.id;exp=sid.date.date()
                if 20<=(exp-day).days<=60:
                    rec.append(dict(expiry=exp,strike=float(sid.strike_price),put=sid.option_right==OptionRight.PUT,
                                    spot=spot,iv=float(c.implied_volatility)))
            value=self.atm(rec,day)
            if value is not None:self.iv[name][day]=value
        self.counts['seed_days']+=len(self.iv[name])

    def upcoming(self,name,exit_day):
        return any(self.time.date()<=d<=exit_day+timedelta(days=1) for d in self.earnings.get(self.eq[name],{}))

    def prepare(self):
        self.review()
        today=self.time.date()
        self.counts['decision_windows']+=1
        if self.last_day!=today:
            self.counts['sessions']+=1;self.last_day=today
        if self.halt:return
        for name in CONFIG['names']:
            if name in self.states or name in self.candidates:continue
            if self.last_attempt.get(name)==today:continue
            # Finish all cycles before the sample ends; no forced artificial final liquidation.
            if (self.end-today).days<35:continue
            rec=self.records(name)
            self.seed_iv(name)
            atm=self.atm(rec,today)
            if atm is not None:self.iv[name][today]=atm
            values=[v for d,v in sorted(self.iv[name].items()) if d<=today][-CONFIG['lookback']:]
            rank=iv_rank(values,values[-1]) if len(values)>=CONFIG['min_iv_points'] else None
            if CONFIG['ivr_gate'] and (rank is None or rank<=50):
                self.counts['skip_ivr']+=1;continue
            possible=[r for r in rec if 40<=(r['expiry']-today).days<=50 and self.monthly(r['expiry'])]
            if not possible:self.counts['skip_expiry']+=1;continue
            exp=min({r['expiry'] for r in possible},key=lambda e:(abs((e-today).days-45),e))
            exit_day=target_exit(exp,self.full_session)
            if name not in ['EWZ','TLT']:
                if self.earnings_seen!=today:self.counts['skip_event_feed']+=1;continue
                if self.upcoming(name,exit_day):self.counts['skip_event']+=1;continue
            pair=[]
            for put in [True,False]:
                choices=[r for r in possible if r['expiry']==exp and r['put']==put and .16<=abs(r['delta'])<=.22
                         and r['iv']>0 and r['oi']>CONFIG['min_oi']]
                if not choices:break
                pair.append(min(choices,key=lambda r:(abs(abs(r['delta'])-.19),r['strike'])))
            if len(pair)!=2:self.counts['skip_delta_oi']+=1;continue
            self.last_attempt[name]=today
            for r in pair:
                if r['symbol'] not in self.subscribed:
                    sec=self.add_option_contract(r['symbol'],Resolution.MINUTE)
                    sec.set_fee_model(ContractFee());sec.set_slippage_model(AbsoluteSlippage())
                    self.subscribed.add(r['symbol'])
            self.candidates[name]=dict(legs=pair,expiry=exp,exit_day=exit_day,prepared=self.time,ivr=rank)
        self.report()

    def quote(self,r):
        s=self.securities[r['symbol']];bar=s.cache.get_data[QuoteBar]()
        if bar is None or bar.is_fill_forward or not s.local_time-timedelta(minutes=2)<=bar.end_time<=s.local_time:return None
        bid,ask=float(s.bid_price),float(s.ask_price)
        if not math.isfinite(bid+ask) or bid<=0 or ask<bid:return None
        return bid,ask,float(s.symbol_properties.contract_multiplier)

    def pair_stress(self,name,legs,credit):
        spot=float(self.securities[self.eq[name]].price)
        years=(legs[0]['expiry']-self.time.date()).days/365
        models=[]
        for r in legs:
            quote=self.quote(r)
            if quote is None:return None
            bid,ask,mult=quote
            iv=implied_vol((bid+ask)/2,spot,r['strike'],years,r['put'])
            if iv is None:return None
            models.append((r,iv,mult,ask-bid))
        losses=[]
        for move in [-.20,-.10,0,.10,.20]:
            for shock in [0,.10,.20]:
                for days in [0,1,max(0,(legs[0]['expiry']-self.time.date()).days-21)]:
                    debit=sum((option_value(spot*(1+move),r['strike'],max(years-days/365,0),iv+shock,r['put'])+spread/2+CONFIG['slippage'])*mult for r,iv,mult,spread in models)
                    losses.append(debit-credit+2*CONFIG['fee'])
        return max(0,max(losses))

    def cluster(self,name):return 'technology' if name in ['CRWD','META','SWKS'] else name

    def try_entry(self,name,p):
        if len(self.states)>=CONFIG['max_open_pairs']:self.counts['skip_positions']+=1;return
        quotes=[self.quote(r) for r in p['legs']]
        if any(q is None for q in quotes):self.counts['skip_quote']+=1;return
        if any((a-b)/((a+b)/2)>=CONFIG['spread_cap'] for b,a,m in quotes):self.counts['skip_spread']+=1;return
        spot=float(self.securities[self.eq[name]].price);years=(p['expiry']-self.time.date()).days/365
        for r,(b,a,m) in zip(p['legs'],quotes):
            iv=implied_vol((a+b)/2,spot,r['strike'],years,r['put'])
            if iv is None or not .16<=abs(model_delta(spot,r['strike'],years,iv,r['put']))<=.22:
                self.counts['skip_live_delta']+=1;return
        net_credit=sum((b-CONFIG['slippage'])*m for b,a,m in quotes)-2*CONFIG['fee']
        if net_credit<=0:return
        loss=self.pair_stress(name,p['legs'],net_credit)
        if loss is None or loss<=0:self.counts['skip_model']+=1;return
        nav=float(self.portfolio.total_portfolio_value)
        # Sum standalone stress losses gives no diversification credit; not a VaR bound.
        book=sum(s.get('stress',0)*s['quantity'] for s in self.states.values())
        cluster=sum(s.get('stress',0)*s['quantity'] for n,s in self.states.items() if self.cluster(n)==self.cluster(name))
        budget=min(nav*CONFIG['trade_budget'],nav*CONFIG['book_budget']-book,nav*CONFIG['cluster_budget']-cluster)
        quantity=quantity_for(loss,budget,CONFIG['max_pairs']) if CONFIG['risk_sizing'] else 1
        if quantity<1:self.counts['skip_size']+=1;return
        # Conservative standalone initial margins; native combo buying-power check still applies.
        margin=standalone_margin(self.securities[r['symbol']].buying_power_model.get_initial_margin_requirement(InitialMarginParameters(self.securities[r['symbol']],-quantity)).value for r in p['legs'])
        if margin>nav*CONFIG['trade_margin_cap'] or float(self.portfolio.total_margin_used)+margin>nav*CONFIG['margin_cap']:
            self.counts['skip_margin']+=1;return
        self.episode+=1
        s=dict(p,quantity=quantity,status='opening',tickets=[],stress=loss,entry_day=self.time.date(),cashflow=0.,fees=0.,id=self.episode,reason='',opened=False)
        self.states[name]=s
        del self.candidates[name]
        # Positive per-leg ratio and negative combo quantity represent selling both legs.
        tickets=self.combo_market_order([Leg.create(r['symbol'],1) for r in p['legs']],-quantity,asynchronous=True,tag=f"SS45|{s['id']}|OPEN|{name}")
        s['tickets']=[t.order_id for t in tickets]
        self.counts['entry_submitted']+=1

    def close(self,name,reason):
        s=self.states[name]
        if s['status']=='closing':return
        s['exit_requested']=reason
        if any(self.portfolio[r['symbol']].invested and self.quote(r) is None for r in s['legs']):
            self.counts['exit_wait_quote']+=1;return
        s['reason']=reason;s['status']='closing';s['tickets']=[]
        quantities=[float(self.portfolio[r['symbol']].quantity) for r in s['legs']]
        if quantities[0]==quantities[1] and quantities[0]<0:
            tickets=self.combo_market_order([Leg.create(r['symbol'],1) for r in s['legs']],int(-quantities[0]),asynchronous=True,tag=f"SS45|{s['id']}|CLOSE|{reason}")
            s['tickets']=[t.order_id for t in tickets]
        else:
            for r in s['legs']:
                if self.portfolio[r['symbol']].invested:
                    ticket=self.market_order(r['symbol'],-self.portfolio[r['symbol']].quantity,asynchronous=True,tag=f"SS45|{s['id']}|RECOVERY|{reason}")
                    s['tickets'].append(ticket.order_id)
        if self.portfolio[self.eq[name]].invested:
            tickets=self.liquidate(self.eq[name],tag=f"SS45|{s['id']}|ASSIGNMENT")
            s['tickets'] += [t.order_id for t in tickets]
        self.counts['exit_'+reason]+=1

    def reconcile(self):
        for name,s in list(self.states.items()):
            tickets=[self.transactions.get_order_ticket(i) for i in s['tickets']]
            pending=any(t.status not in [OrderStatus.FILLED,OrderStatus.CANCELED,OrderStatus.INVALID] for t in tickets)
            if pending:continue
            qty=[float(self.portfolio[r['symbol']].quantity) for r in s['legs']]
            assigned=self.portfolio[self.eq[name]].invested
            if s['status']=='opening':
                if qty==[-s['quantity'],-s['quantity']] and not assigned:
                    s['status']='open';s['opened']=True;self.counts['opened']+=1
                elif any(qty) or assigned:
                    s['status']='open';self.close(name,'partial_or_assignment')
                else:
                    self.counts['entry_failed']+=1;del self.states[name]
            elif s['status']=='closing':
                if not any(qty) and not assigned:
                    net=s['cashflow']-s['fees'];self.realized.append(net)
                    self.counts['closed']+=1;self.counts['wins']+=int(net>0)
                    self.counts['closed_'+name]+=1
                    self.assignment_names.discard(name)
                    del self.states[name]
                else:
                    s['status']='open';self.counts['close_retry']+=1;self.close(name,s['reason'])

    def review(self):
        self.reconcile()
        nav=float(self.portfolio.total_portfolio_value);self.peak=max(self.peak,nav)
        self.min_margin=min(self.min_margin,float(self.portfolio.margin_remaining))
        if nav<=.90*self.peak:self.halt=True
        for name,s in list(self.states.items()):
            if s['status']!='open':continue
            reason=None
            if self.time.date()>=s['exit_day']:reason='21dte'
            elif name in self.assignment_names or self.portfolio[self.eq[name]].invested:reason='assignment'
            elif self.upcoming(name,s['exit_day']):reason='event'
            elif self.halt:reason='drawdown'
            elif float(self.portfolio.total_margin_used)>nav*CONFIG['margin_cap']:reason='margin'
            if reason:self.close(name,reason);continue
            marks=[self.quote(r) for r in s['legs']]
            if any(q is None for q in marks):self.counts['risk_missing_quote']+=1;continue
            liquidation=sum(a*m*s['quantity'] for b,a,m in marks)
            pnl=s['cashflow']-s['fees']-liquidation-2*s['quantity']*CONFIG['fee']
            if CONFIG['risk_sizing'] and -pnl>nav*CONFIG['trade_budget']:
                self.close(name,'loss');continue
            # Evaluate loss since actual entry, including fees, without resetting the loss basis.
            stress=self.pair_stress(name,s['legs'],(s['cashflow']-s['fees'])/s['quantity'])
            if stress is not None:s['stress']=stress
            if CONFIG['risk_sizing'] and (stress is None or stress*s['quantity']>nav*CONFIG['trade_budget']):
                self.close(name,'stress');continue
            if CONFIG['delta_stop']:
                spot=float(self.securities[self.eq[name]].price);years=(s['expiry']-self.time.date()).days/365
                for r,(b,a,m) in zip(s['legs'],marks):
                    iv=implied_vol((a+b)/2,spot,r['strike'],years,r['put'])
                    if iv and years>0 and abs(model_delta(spot,r['strike'],years,iv,r['put']))>.35:
                        self.close(name,'delta');break
        # Aggregate stress limits use a conservative sum, with no diversification credit.
        if CONFIG['risk_sizing']:
            remaining={n:s for n,s in self.states.items() if s['status']=='open'}
            for name,s in sorted(remaining.items(),key=lambda item:item[1]['stress']*item[1]['quantity'],reverse=True):
                total=sum(x['stress']*x['quantity'] for x in remaining.values())
                cluster=sum(x['stress']*x['quantity'] for n,x in remaining.items() if self.cluster(n)==self.cluster(name))
                if total>nav*CONFIG['book_budget'] or cluster>nav*CONFIG['cluster_budget']:
                    self.close(name,'portfolio_stress');remaining.pop(name)
        self.report()

    def on_data(self,data):
        # Management is independent of entry-chain availability.
        if self.last_tick==self.time:return
        self.last_tick=self.time
        self.reconcile()
        for name,s in list(self.states.items()):
            if s['status']=='open' and s.get('exit_requested'):self.close(name,s['exit_requested'])
        if self.time.hour<10 or self.time.hour>=16:return
        for name,p in list(self.candidates.items()):
            if self.time-p['prepared']>timedelta(minutes=15):
                del self.candidates[name];self.counts['candidate_timeout']+=1;continue
            if not self.halt:self.try_entry(name,p)
        # Assignment/failed-close recovery does not wait for daily option selection.
        for name in list(self.assignment_names):
            if name in self.states and self.states[name]['status']=='open':self.close(name,'assignment')
        # Closing at 15:30 permits another decision, only after confirmed flat.
        if self.time.hour==15 and self.time.minute==35:self.prepare()

    def on_order_event(self,event):
        if event.status==OrderStatus.INVALID:self.counts['invalid_orders']+=1
        if event.fill_quantity==0:return
        fee=float(event.order_fee.value.amount);self.total_fee+=fee
        for name,s in self.states.items():
            symbols=[r['symbol'] for r in s['legs']]+[self.eq[name]]
            if event.symbol in symbols:
                mult=float(self.securities[event.symbol].symbol_properties.contract_multiplier)
                s['cashflow']-=float(event.fill_quantity)*float(event.fill_price)*mult
                s['fees']+=fee
                break
        self.counts['fills']+=1

    def on_assignment_order_event(self,event):
        self.counts['assignments']+=1
        for name in CONFIG['names']:
            if event.symbol.underlying==self.eq[name]:self.assignment_names.add(name)

    def report(self):
        for k,v in self.counts.items():self.set_runtime_statistic('ss_'+k,str(v))
        self.set_runtime_statistic('ss_open_pairs',str(len(self.states)))
        self.set_runtime_statistic('ss_net_closed',f'{sum(self.realized):.2f}')
        self.set_runtime_statistic('ss_min_margin',f'{self.min_margin:.2f}')
        self.set_runtime_statistic('ss_fee',f'{self.total_fee:.2f}')
        self.set_runtime_statistic('ss_risk_sizing',str(CONFIG['risk_sizing']))
        self.set_runtime_statistic('ss_ivr_gate',str(CONFIG['ivr_gate']))

    def on_end_of_algorithm(self):
        self.reconcile();self.report()
        self.set_runtime_statistic('ss_residual_holdings',str(sum(1 for h in self.portfolio.values() if h.invested)))
        self.set_runtime_statistic('ss_halted',str(self.halt))
