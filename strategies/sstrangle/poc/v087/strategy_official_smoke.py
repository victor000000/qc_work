"""Unsubmitted accounting-probe candidate; never import into frozen strategies.

Pair this exercise model with SecurityPortfolioModel, NOT OptionPortfolioModel.
The generic portfolio model books the exercise fill at intrinsic exactly once.
Native option portfolio processing would add underlying-based intrinsic again.
"""
from AlgorithmImports import *


class ReferenceCashExercise(DefaultExerciseModel):
    def __init__(self, official_by_expiry=None):
        self.official_by_expiry = official_by_expiry

    def option_exercise(self, option, order):
        if option.exercise_settlement != SettlementType.CASH:
            raise ValueError('Accounting probe permits cash-settled options only')
        expiry = str(option.symbol.id.date.date())
        if self.official_by_expiry is None:
            reference = float(option.underlying.close)
        else:
            # Missing data is an error; never silently fall back to native marks.
            reference = float(self.official_by_expiry[expiry])
        strike = float(option.strike_price)
        intrinsic = max(0.0, reference-strike if option.right == OptionRight.CALL else strike-reference)
        events = list(super().option_exercise(option, order))
        if len(events) != 1 or events[0].symbol != option.symbol:
            raise ValueError('Unexpected physical-delivery or multi-event exercise')
        event = events[0]
        event.fill_price = intrinsic
        event.is_in_the_money = intrinsic >= 0.01
        event.is_assignment = event.is_in_the_money and option.holdings.is_short
        event.message = 'Official cash settlement Underlying: ' + str(reference)
        return [event]


def install_reference_accounting(security, official_by_expiry=None):
    if security.type != SecurityType.INDEX_OPTION or security.symbol.is_canonical():
        return
    security.set_portfolio_model(SecurityPortfolioModel())
    security.set_option_exercise_model(ReferenceCashExercise(official_by_expiry))

OFFICIAL_SETTLEMENTS = {'2022-09-30': 3585.62, '2022-10-03': 3678.43, '2022-09-29': 3640.47}
"""QC adaptation of the audio's Option Omega demo; native orders and cash settlement."""
from AlgorithmImports import *
"""Pure per-decision feature evaluation from completed pinned daily rows only."""
import math
from datetime import date,timedelta

def feature_value(rows,day,feature):
    # Each row is [ISO session day, high, low, close, volume].
    # At intraday NY decisions, prior-session rows were available at next midnight.
    past=[r for r in rows if r[0]<day]
    if not past:return None,None
    latest=past[-1];age=(date.fromisoformat(day)-date.fromisoformat(latest[0])-timedelta(days=1)).days
    if age>=7:return None,latest[0]
    if feature.endswith('_range_pct'):
        value=(float(latest[1])-float(latest[2]))/float(latest[3])
    elif feature.endswith('_volume_z20'):
        if len(past)<20:return None,latest[0]
        vals=[float(x[4]) for x in past[-20:]];mean=math.fsum(vals)/20
        variance=math.fsum((x-mean)**2 for x in vals)/19
        value=(vals[-1]-mean)/math.sqrt(variance) if variance>0 else None
    else:raise ValueError('Unsupported frozen feature: '+feature)
    if value is None or not math.isfinite(value):return None,latest[0]
    return value,latest[0]

def rule_pass(value,threshold,side):
    if value is None:return False
    if side=='above':return value>threshold
    if side=='below':return value<=threshold
    raise ValueError('Unknown rule direction')

"""Bounded, readable aggregate telemetry; raw native orders remain authoritative."""
import json

def bounded_statistics(core, counts, annual):
    result={str(k):str(v) for k,v in core.items()}
    for year,value in sorted(annual.items()):result['episodes_'+str(year)]=str(value)
    direct={'filled_episodes','submitted_episodes','rejected_episodes','native_fill_events',
            'native_expiry_events','scheduled_slots','original_wing_skips','recovered_filled_episodes'}
    chunk={};chunks=[]
    for key,value in sorted(counts.items()):
        if key in direct:result[key]=str(value);continue
        candidate=dict(chunk);candidate[key]=value
        if len(json.dumps(candidate,separators=(',',':')))>180:
            if not chunk:raise ValueError('Aggregate statistic exceeds quota')
            chunks.append(chunk);chunk={key:value}
        else:chunk=candidate
    if chunk:chunks.append(chunk)
    for i,chunk in enumerate(chunks,1):result['counts_'+str(i).zfill(2)]=json.dumps(chunk,separators=(',',':'))
    result['counts_chunks']=str(len(chunks))
    if len(result)>50 or any(len(k)>200 or len(v)>200 for k,v in result.items()):
        raise ValueError('QC runtime statistic quota exceeded')
    return result

from collections import Counter
from datetime import date, timedelta
import json
import math


"""Pure exact-width pair selection used by the QC adapter and local regression."""
def choose_exact_pairs(puts,calls,by_key,put_right,call_right,put_target,call_target,width=20):
    """Candidates and keyed wings must already pass the same as-of quote gate."""
    paired_puts=[c for c in puts if (put_right,float(c.strike)-width) in by_key]
    paired_calls=[c for c in calls if (call_right,float(c.strike)+width) in by_key]
    if not paired_puts or not paired_calls:return None
    put=min(paired_puts,key=lambda c:(abs(float(c.greeks.delta)+put_target),float(c.strike)))
    call=min(paired_calls,key=lambda c:(abs(float(c.greeks.delta)-call_target),float(c.strike)))
    return put,call,by_key[put_right,float(put.strike)-width],by_key[call_right,float(call.strike)+width]


class AbsoluteEntrySlippage:
    def get_slippage_approximation(self, asset, order):
        return 0.05


class OmegaMidpointFill(FillModel):
    """Documented OO midpoint convention; native quote gating/orders/margin remain."""
    def __init__(self, legs=4):
        super().__init__()
        self.slip=0.05/legs

    def market_fill(self, security, order):
        fill=super().market_fill(security,order)
        if float(fill.fill_quantity):
            mid=(float(security.bid_price)+float(security.ask_price))/2
            fill.fill_price=mid+(self.slip if float(fill.fill_quantity)>0 else -self.slip)
            if fill.fill_price<=0: raise RuntimeError('Nonpositive midpoint modeled fill')
            fill.message=(fill.message or '')+f';oo_mid={mid:.8f};oo_slip={self.slip:.8f}'
        return fill

    def combo_market_fill(self, order, parameters):
        fills = super().combo_market_fill(order, parameters)
        assets = {pair.Key.Id: pair.Value for pair in parameters.securities_for_orders}
        for fill in fills:
            security = assets[fill.order_id]
            mid = (float(security.bid_price)+float(security.ask_price))/2
            # Equal allocation of the documented 0.05 package slippage to 4 legs.
            price = mid + (self.slip if float(fill.fill_quantity)>0 else -self.slip)
            if price <= 0:
                raise RuntimeError('Nonpositive midpoint modeled fill')
            fill.fill_price = price
            fill.message = (fill.message or '')+f';oo_mid={mid:.8f};oo_slip={self.slip:.8f}'
        return fills


class DemoFeeModel(FeeModel):
    def get_order_fee(self, parameters):
        # Explicit assumption: screenshot fee is per contract per market fill.
        # Expiry incurs no invented closing commission; native exercise fee is zero.
        amount = 0 if parameters.order.type == OrderType.OPTION_EXERCISE else abs(float(parameters.order.quantity))*1.18
        return OrderFee(CashAmount(amount, 'USD'))


class OptionOmegaAudioDemo(QCAlgorithm):
    CONFIG = {}

    def initialize(self):
        cfg = self.CONFIG
        self.alpha_rows=[]
        if cfg.get("alpha_enabled",False):
            from feature_inputs import DAILY_ROWS
            self.alpha_rows=DAILY_ROWS
        self.alpha_value=None;self.alpha_source_day=None
        self.fill_convention = cfg.get('fill_convention', 'oo_midpoint_package')
        self.first = date(*cfg.get('start', [2024, 1, 2]))
        self.last_entry = date(*cfg.get('last_entry', [2024, 1, 12]))
        self.set_start_date(self.first.year, self.first.month, self.first.day)
        end = min(self.last_entry + timedelta(days=4),date(2026,10,24))
        self.set_end_date(end.year, end.month, end.day)
        self.set_time_zone(TimeZones.NEW_YORK)
        self.kind=cfg.get('strategy_kind','condor')
        self.leg_count={'condor':4,'strangle':2,'put':1,'put_spread':2}[self.kind]
        self.start_capital=float(cfg.get('start_capital',100000))
        self.set_cash(self.start_capital)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_security_initializer(self.initialize_security)
        self.index = self.add_index('SPX', Resolution.MINUTE).symbol
        option = self.add_index_option(self.index, 'SPXW', Resolution.MINUTE)
        option.set_filter(lambda u: u.include_weeklys().strikes(-60, 60).expiration(0, 0))
        option.price_model = OptionPriceModels.black_scholes()
        self.option = option.symbol
        self.set_benchmark(self.index)
        self.slots = [(10,0)] if self.kind=='put_spread' else [(9,35)] + [(h,m) for h in range(10,16) for m in (0,30)]
        self.previous_close_equity = self.start_capital
        self.attempted, self.pending, self.episodes = set(), {}, {}
        self.counts, self.annual = Counter(), Counter()
        self.day = None
        self.close_spot = {}
        self.expiry_spots = {}
        self.native_cash = 0.0
        self.total_fees = 0.0
        self.max_reconciliation_error = 0.0
        self.max_margin_used=0.0
        self.min_margin_remaining=self.start_capital
        self.schedule.on(self.date_rules.every_day(self.index),
                         self.time_rules.after_market_open(self.index, 1), self.audit_settled_day)
        self.schedule.on(self.date_rules.every_day(self.index),
                         self.time_rules.before_market_close(self.index, 0), self.capture_close)

    def initialize_security(self, security):
        if security.type==SecurityType.INDEX_OPTION:
            if security.symbol.id.option_style!=OptionStyle.EUROPEAN:
                raise RuntimeError('This adapter requires European SPXW options')
            # Suppress intraday discretionary assignment simulations. Native
            # expiry/delisting still settles cash and is independently audited.
            security.set_option_assignment_model(NullOptionAssignmentModel())
            install_reference_accounting(security,OFFICIAL_SETTLEMENTS)
        security.set_fee_model(DemoFeeModel())
        if self.fill_convention == 'oo_midpoint_package':
            security.set_slippage_model(ConstantSlippageModel(0))
            security.set_fill_model(OmegaMidpointFill(self.leg_count))
        elif self.fill_convention == 'quote_side_per_leg':
            security.set_slippage_model(AbsoluteEntrySlippage())
        else:
            raise ValueError('Unknown fill convention')

    def emit(self, kind, payload):
        self.log(kind + ' ' + json.dumps(payload, separators=(',', ':')))

    def capture_close(self):
        self.close_spot[str(self.time.date())] = float(self.securities[self.index].close)
        self.emit('SESSION_CLOSE', dict(day=str(self.time.date()), time=str(self.time),
            spot=float(self.securities[self.index].close)))

    def audit_settled_day(self):
        self.process_pending()
        holdings = [(str(s.symbol),float(s.holdings.quantity)) for s in self.securities.values()
                    if s.invested]
        if holdings:
            raise RuntimeError('Prior expiry left invested holdings: '+str(holdings))
        equity = float(self.portfolio.total_portfolio_value)
        error = equity - self.start_capital - self.native_cash
        self.max_reconciliation_error = max(self.max_reconciliation_error, abs(error))
        if abs(error) > 0.05:
            raise RuntimeError('Native settlement ledger mismatch: '+str(error))
        self.previous_close_equity = equity
        self.emit('FLAT_ACCOUNT', dict(time=str(self.time), equity=equity,
                                     net_cash=self.native_cash, error=error))

    def fresh(self, contract):
        security = self.securities[contract.symbol]
        quote = security.cache.get_data[QuoteBar]()
        return (quote is not None and not quote.is_fill_forward
                and security.local_time-timedelta(minutes=2) <= quote.end_time <= security.local_time
                and float(contract.ask_price) > 0
                and 0 <= float(contract.bid_price) <= float(contract.ask_price)
                and float(contract.ask_price)-float(contract.bid_price) <= 3)

    def on_data(self, data):
        self.process_pending()
        self.max_margin_used=max(self.max_margin_used,float(self.portfolio.total_margin_used))
        self.min_margin_remaining=min(self.min_margin_remaining,float(self.portfolio.margin_remaining))
        today = self.time.date()
        if not self.first <= today <= self.last_entry:
            return
        slot = (self.time.hour, self.time.minute)
        if slot not in self.slots or (today, slot) in self.attempted:
            return
        self.attempted.add((today, slot))
        self.counts['scheduled_slots'] += 1
        if self.CONFIG.get('alpha_enabled',False):
            self.alpha_value,self.alpha_source_day=feature_value(self.alpha_rows,str(today),self.CONFIG['alpha_feature'])
            if self.alpha_value is None:
                self.counts['skip_alpha_missing']+=1
                return
            if not rule_pass(self.alpha_value,float(self.CONFIG['alpha_threshold']),self.CONFIG['alpha_side']):
                self.counts['skip_alpha_filter']+=1
                return
            self.counts['alpha_admitted_slots']+=1
        chain = data.option_chains.get(self.option)
        if not chain:
            self.counts['skip_no_chain'] += 1
            return
        contracts = [c for c in chain if c.expiry.date() == today and self.fresh(c)]
        spot = float(self.securities[self.index].price)
        puts = [c for c in contracts if c.right == OptionRight.PUT and float(c.strike) < spot
                and math.isfinite(float(c.greeks.delta)) and -0.40 < float(c.greeks.delta) < -0.01]
        calls = [c for c in contracts if c.right == OptionRight.CALL and float(c.strike) > spot
                 and math.isfinite(float(c.greeks.delta)) and 0.01 < float(c.greeks.delta) < 0.30]
        if not puts or (self.kind not in ('put','put_spread') and not calls):
            self.counts['skip_missing_delta_or_quotes'] += 1
            return
        put = min(puts, key=lambda c:(abs(float(c.greeks.delta)+float(self.CONFIG.get('put_target',0.20))), float(c.strike)))
        call = min(calls, key=lambda c:(abs(float(c.greeks.delta)-float(self.CONFIG.get('call_target',0.08))), float(c.strike))) if self.kind not in ('put','put_spread') else None
        original_put,original_call=put,call
        recovered=False
        if self.kind=='condor':
            by_key = {(c.right,float(c.strike)):c for c in contracts}
            long_put = by_key.get((OptionRight.PUT,float(put.strike)-20))
            long_call = by_key.get((OptionRight.CALL,float(call.strike)+20))
            if long_put is None or long_call is None:
                self.counts['original_wing_skips']+=1
                self.counts['original_wing_year_'+str(today.year)]+=1
                raw={(c.right,float(c.strike)):c for c in chain if c.expiry.date()==today}
                failures=[]
                for side,right,strike,wing in [('put',OptionRight.PUT,float(put.strike)-20,long_put),('call',OptionRight.CALL,float(call.strike)+20,long_call)]:
                    if wing is not None: continue
                    candidate=raw.get((right,strike))
                    reason='absent_chain'
                    if candidate is not None:
                        sec=self.securities[candidate.symbol];quote=sec.cache.get_data[QuoteBar]()
                        if quote is None:reason='no_quote'
                        elif quote.is_fill_forward:reason='fill_forward'
                        elif not sec.local_time-timedelta(minutes=2)<=quote.end_time<=sec.local_time:
                            reason='age'
                            age=(sec.local_time-quote.end_time).total_seconds()/60
                            bucket='future' if age<0 else ('3to5' if age<=5 else ('6to15' if age<=15 else ('16to60' if age<=60 else 'over60')))
                            self.counts['wing_age_'+bucket]+=1
                        elif float(candidate.ask_price)<=0:reason='zero_ask'
                        elif not 0<=float(candidate.bid_price)<=float(candidate.ask_price):reason='crossed'
                        elif float(candidate.ask_price)-float(candidate.bid_price)>3:reason='spread'
                        else:reason='unclassified'
                    failures.append(side+'_'+reason)
                    self.counts['wing_'+side+'_'+reason]+=1
                self.counts['wing_reason_'+','.join(sorted(failures))]+=1
                if self.CONFIG.get('wing_policy','paired_exact' if self.kind=='condor' else 'original')!='paired_exact':
                    self.counts['skip_missing_20point_wing']+=1
                    return
                # Search only the exact-width packages with both legs already
                # passing the unchanged original quote-admission predicate.
                pair=choose_exact_pairs(puts,calls,by_key,OptionRight.PUT,OptionRight.CALL,
                    float(self.CONFIG.get('put_target',.20)),float(self.CONFIG.get('call_target',.08)))
                if pair is None:
                    self.counts['skip_no_admissible_exact_pair']+=1
                    return
                put,call,long_put,long_call=pair
                recovered=True
                self.counts['recovered_pair_candidates']+=1
                self.counts['recovered_pair_year_'+str(today.year)]+=1
            else:self.counts['original_wing_admitted']+=1
            selected=[(long_put,1),(put,-1),(call,-1),(long_call,1)]
        elif self.kind=='put_spread':
            by_key = {(c.right,float(c.strike)):c for c in contracts}
            pairs = [(c,by_key.get((OptionRight.PUT,float(c.strike)-20))) for c in puts]
            pairs = [(short,long) for short,long in pairs if long is not None]
            if not pairs:
                self.counts['skip_no_admissible_exact_pair'] += 1
                return
            put,long_put = min(pairs,key=lambda pair:(abs(float(pair[0].greeks.delta)+float(self.CONFIG['put_target'])),float(pair[0].strike)))
            recovered = put.symbol != original_put.symbol
            selected=[(long_put,1),(put,-1)]
        elif self.kind=='strangle': selected=[(put,-1),(call,-1)]
        else: selected=[(put,-1)]
        tolerance = float(self.CONFIG.get('delta_tolerance', .02)) if self.kind in ('condor','put_spread') else 1.0
        if (abs(float(put.greeks.delta)+float(self.CONFIG.get('put_target',.20))) > tolerance+1e-12
                or (call is not None and abs(float(call.greeks.delta)-float(self.CONFIG.get('call_target',.08))) > tolerance+1e-12)):
            self.counts['skip_delta_tolerance'] += 1
            return
        if self.fill_convention == 'oo_midpoint_package':
            credit = -sum(q*(float(c.ask_price)+float(c.bid_price))/2 for c,q in selected)-0.05
        else:
            credit = -sum(q*(float(c.ask_price) if q>0 else float(c.bid_price)) for c,q in selected)-0.05*self.leg_count
        if credit <= 0 or (self.kind in ('condor','put_spread') and credit >= 20):
            self.counts['skip_nonpositive_or_invalid_credit'] += 1
            return
        # Conservative sum of per-episode maximum losses. Actual QC buying power
        # and aggregate position groups still govern every submitted order.
        day_reserve = sum(x['max_loss'] for x in self.episodes.values() if x['day'] == str(today))
        max_loss = (20-credit)*100+self.leg_count*1.18 if self.kind in ('condor','put_spread') else 0
        if self.kind=='put_spread' and max_loss > self.previous_close_equity*.02:
            self.counts['skip_previous_equity_risk_cap']+=1
            return
        if self.kind in ('condor','put_spread') and day_reserve+max_loss > float(self.portfolio.total_portfolio_value)*float(self.CONFIG.get('capital_fraction',1.0)):
            self.counts['skip_capital'] += 1
            return
        if not self.is_market_open(self.index):
            self.counts['skip_session_closed']+=1
            return
        episode = today.strftime('%Y%m%d')+f'{slot[0]:02d}{slot[1]:02d}'
        tag = (f'oo05;e={episode};r=OPEN;v=expiry6;d={self.time.isoformat()}'
               f';pd={float(put.greeks.delta):.8f};cd={(float(call.greeks.delta) if call else 0.0):.8f};spot={spot:.6f}'
               f';recovered={int(recovered)};anchor_pd={float(original_put.greeks.delta):.8f};anchor_cd={(float(original_call.greeks.delta) if original_call else 0.0):.8f}')
        if self.CONFIG.get('alpha_enabled',False):
            tag+=f';af={self.CONFIG["alpha_feature"]};av={self.alpha_value:.17g};asof={self.alpha_source_day}'
        record = dict(episode=episode,day=str(today),decision=str(self.time),spot=spot,
            put_delta=float(put.greeks.delta),call_delta=(float(call.greeks.delta) if call else 0.0),
            max_loss=max_loss,quoted_credit=credit,recovered=recovered,
            legs=[dict(symbol=str(c.symbol),sid=str(c.symbol.id),strike=float(c.strike),
                       right='P' if c.right==OptionRight.PUT else 'C',quantity=q) for c,q in selected])
        self.episodes[episode] = record
        if self.leg_count==1:
            tickets=[self.market_order(put.symbol,-1,asynchronous=True,tag=tag)]
        else:
            tickets = self.combo_market_order([Leg.create(c.symbol,q) for c,q in selected],
                                               1, asynchronous=True, tag=tag)
        self.pending[episode] = dict(tickets=tickets,submitted=self.time,record=record)
        self.counts['submitted_episodes'] += 1

    def process_pending(self):
        for episode, p in list(self.pending.items()):
            tickets = p['tickets']
            if len(tickets) != self.leg_count:
                raise RuntimeError('Wrong native ticket count: '+episode)
            if (all(t.status in (OrderStatus.INVALID,OrderStatus.CANCELED) for t in tickets)
                    and all(float(t.quantity_filled) == 0 for t in tickets)):
                self.counts['skip_native_rejected_zero_fill'] += 1
                self.emit('REJECTED_EPISODE', dict(episode=episode,reason=str(tickets[-1].get_most_recent_order_response())))
                del self.episodes[episode]
                del self.pending[episode]
                continue
            if any(t.status in (OrderStatus.INVALID,OrderStatus.CANCELED) for t in tickets):
                raise RuntimeError('Native combo rejection: '+episode+' '+str([(str(t.status),str(t.get_most_recent_order_response())) for t in tickets]))
            if all(t.status == OrderStatus.FILLED for t in tickets):
                record = p['record']
                record['order_ids'] = [t.order_id for t in tickets]
                record['fill_cash'] = -sum(float(t.quantity_filled)*float(t.average_fill_price)*100 for t in tickets)
                record['fees'] = sum(float(e.order_fee.value.amount) for t in tickets for e in t.order_events)
                if any(abs(float(t.quantity_filled)) != 1 for t in tickets):
                    raise RuntimeError('Wrong filled quantity: '+episode)
                self.counts['filled_episodes'] += 1
                if record['recovered']:self.counts['recovered_filled_episodes']+=1
                self.annual[record['day'][:4]] += 1
                if self.CONFIG.get('verbose', False):
                    self.emit('EPISODE_OPEN', record)
                del self.pending[episode]
            elif self.time-p['submitted'] > timedelta(minutes=3):
                raise RuntimeError('Unresolved native combo: '+episode)

    def on_order_event(self, event):
        if event.status not in (OrderStatus.FILLED,OrderStatus.PARTIALLY_FILLED):
            return
        order = self.transactions.get_order_by_id(event.order_id)
        if order.type != OrderType.OPTION_EXERCISE and not order.tag.startswith('oo05;'):
            raise RuntimeError('Unexpected non-demo fill (margin intervention or exit): '+str(order.tag))
        fee = float(event.order_fee.value.amount)
        self.total_fees += fee
        cash = -float(event.fill_quantity)*float(event.fill_price)*100-fee
        self.counts['native_fill_events'] += 1
        if order.type == OrderType.OPTION_EXERCISE:
            if 'before expiration' in (event.message or '').lower():
                raise RuntimeError('Unexpected premature European assignment')
            option = self.securities[event.symbol]
            spot = OFFICIAL_SETTLEMENTS[str(event.symbol.id.date.date())]
            strike = float(event.symbol.id.strike_price)
            intrinsic = max(0,spot-strike) if event.symbol.id.option_right == OptionRight.CALL else max(0,strike-spot)
            if abs(float(event.fill_price)-intrinsic)>1e-7:
                raise RuntimeError('Official exercise fill-price mismatch')
            # Cash was booked once from the intrinsic-priced exercise event above.
            self.counts['native_expiry_events'] += 1
            expiry_day = str(event.symbol.id.date.date())
            if expiry_day not in self.expiry_spots:
                self.expiry_spots[expiry_day] = spot
                self.emit('SETTLEMENT_SPOT', dict(day=expiry_day,spot=spot,time=str(self.time)))
            elif abs(self.expiry_spots[expiry_day]-spot)>0.00001:
                raise RuntimeError('Different native settlement spots on same expiry day')
            if self.CONFIG.get('verbose', False):
                self.emit('NATIVE_EXPIRY', dict(order_id=event.order_id,symbol=str(event.symbol),
                sid=str(event.symbol.id),time=str(self.time),quantity=float(order.quantity),
                spot=spot,intrinsic=intrinsic,cash=cash,fee=fee))
        self.native_cash += cash

    def on_end_of_algorithm(self):
        self.process_pending()
        if self.pending or self.portfolio.invested:
            raise RuntimeError('Unresolved orders or residual holdings at end')
        equity = float(self.portfolio.total_portfolio_value)
        error = equity-self.start_capital-self.native_cash
        if abs(error)>0.05:
            raise RuntimeError('Final native ledger mismatch: '+str(error))
        core={}
        def record(k,v):core[k]=v
        record('ledger_error',f'{error:.6f}')
        record('native_net_pnl',f'{self.native_cash:.6f}')
        record('fees',f'{self.total_fees:.6f}')
        record('max_flat_ledger_error',f'{self.max_reconciliation_error:.6f}')
        record('exit_policy','native_cash_settled_expiry')
        record('baseline',self.kind+'_spx_0dte_'+str(len(self.slots))+'slots')
        record('max_margin_used_1m',f'{self.max_margin_used:.2f}')
        record('min_margin_remaining_1m',f'{self.min_margin_remaining:.2f}')
        record('wing_policy',self.CONFIG.get('wing_policy','paired_exact' if self.kind=='condor' else 'original'))
        record('settlement_policy','official_intrinsic_generic_portfolio')
        record('assignment_policy','european_no_discretionary_early_assignment_native_expiry')
        record('session_policy','index_open_at_submission')
        record('strategy_kind',self.kind)
        record('leg_count',str(self.leg_count))
        record('start_capital',str(self.start_capital))
        record('put_target',str(self.CONFIG.get('put_target',0.20)))
        record('call_target',str(self.CONFIG.get('call_target',0.08)))
        record('fill_convention',self.fill_convention)
        record('cost_assumption',
            '1.18_per_contract;0.05_package_midpoint_slip;zero_expiry_fee'
            if self.fill_convention == 'oo_midpoint_package' else
            '1.18_per_contract;0.05_per_leg_quote_side_slip;zero_expiry_fee')
        for key,value in bounded_statistics(core,self.counts,self.annual).items():
            self.set_runtime_statistic(key,value)
        if not self.counts['filled_episodes']:
            raise RuntimeError('No filled baseline episodes')
