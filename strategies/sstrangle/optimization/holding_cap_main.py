from holding_age import validate_max_holding_days, age_exit_due
from fresh_risk_slots import FreshRiskSlots
from equity_rv_features import expected_equity_sessions, equity_features, equity_rv_admitted, validate_equity_rv_threshold
"""Prospective guarded research variant. Not queued; native validation required.
Copied from main.py; original baseline and currently frozen campaign unchanged.
"""
from voluntary_quote_guard import BuybackQuote
from cross_asset_buyback_guard import cross_asset_market_buyback_guard
"""Broad US short-strangle baseline with point-in-time screening and fill accounting."""
from AlgorithmImports import *
from collections import Counter, deque
from datetime import date, datetime, time, timedelta
import json
import math
from functools import wraps
from time import perf_counter
import execution_base
from research_risk_rules import validate_risk, collateral_budget, capped_candidates, capped_quantity
from rules import close_reason, roll_side
from basket_rules import (iv_statistics, high_iv_rank, equity_screen, ordered_candidates,
    available_slots, monthly_expiry, earnings_veto, black76_iv_delta,
    equal_budget_candidates, equal_budget_quantity, can_start_batch, standard_equity_monthly, EquityScreenWindow)


def performance_phase(name):
    """Optional aggregate timings only; never record market-price history."""
    def decorate(method):
        @wraps(method)
        def measured(self, *args, **kwargs):
            if not self.CONFIG.get('profile_performance',False):
                return method(self,*args,**kwargs)
            started=perf_counter()
            try:
                return method(self,*args,**kwargs)
            finally:
                self.counts['perf_calls_'+name]+=1
                self.counts['perf_us_'+name]+=round((perf_counter()-started)*1_000_000)
        return measured
    return decorate


class ResearchShortStrangle(execution_base.TranscriptShortStrangle):
    CONFIG = {}

    def initialize(self):
        cfg = self.CONFIG
        validate_risk(cfg['total_collateral_fraction'],cfg['per_symbol_collateral_fraction'],
            cfg['stop_multiple'],cfg['risk_interval_minutes'])
        self.time_exit_dte = cfg.get('time_exit_dte', 21)
        if type(self.time_exit_dte) is not int or self.time_exit_dte not in (21, 28):
            raise ValueError('Research TIME exit must be explicitly 21 or 28 DTE')
        validate_equity_rv_threshold(cfg['min_equity_iv_rv'])
        self.max_holding_days=validate_max_holding_days(cfg['max_holding_days'])
        if cfg.get('future_rv_policy')!='original_rules':raise ValueError('All15future roots retain original rules in this equity-only trial')
        self.settings.daily_precise_end_time=True
        self.last_risk_check=None
        self.last_research_exit_day=None
        self.set_start_date(*cfg.get('start', [2012, 1, 3]))
        self.end = date(*cfg.get('end', [2026, 9, 30]))
        self.trade_start = date(*cfg.get('trade_start', [2012, 1, 3]))
        self.set_end_date(self.end.year, self.end.month, self.end.day)
        self.initial_cash = float(cfg.get('initial_cash', 60000))
        self.set_cash(self.initial_cash)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_maximum_orders(100000)
        self.lookback = cfg.get('lookback', 504)
        self.min_points = self.lookback
        self.max_basket = 13
        self.positions, self.states, self.pending_combos = {}, {}, {}
        self.exit_requests = {}
        self.counts, self.annual = Counter(), {}
        self.price_volume, self.equity_candidates = {}, {}
        self.earnings_calendar = {}
        self.active_equity, self.closed_pnl = [], []
        self.first_entry = None
        self.batch_id = 0
        self.insolvency = None
        self.monthly_cache = {}
        self.prepared, self.day_chains, self.roll_candidates = [], {}, {}
        self.prepared_day = None
        self.subscribed_options, self.subscribed_underlyings = set(), set()
        self.due, self.last_day = False, None
        self.spy = self.add_equity('SPY', Resolution.MINUTE).symbol
        self.securities[self.spy].set_data_normalization_mode(DataNormalizationMode.RAW)
        self.set_benchmark(self.spy)
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.asynchronous = False
        self.add_universe(self.screen_equities)
        self.add_universe(EODHDUpcomingEarnings, self.screen_earnings)
        self.futures = {}
        for root in ['CL','RB','HO','NG','ZN','ZT','ZB','ZC','ZS','ZW','NQ','ES','HG','GC','SI']:
            future = self.add_future(root, Resolution.DAILY)
            future.set_filter(lambda universe: universe.contracts([]))
            self.futures[root] = future.symbol
        self.schedule.on(self.date_rules.every_day(), self.time_rules.at(11, 55), self.prepare_day)
        self.schedule.on(self.date_rules.every_day(), self.time_rules.at(12, 0), self.arm)

    def decision(self, key, reason):
        self.counts[reason] += 1
        self.annual.setdefault((self.time.year, key), Counter())[reason] += 1

    @performance_phase('screen_equities')
    def screen_equities(self, rows):
        candidates = {}
        row_count=0
        for row in rows:
            row_count+=1
            symbol = row.symbol
            ended=row.end_time
            observed = ended.date()
            if ended > self.time:
                raise RuntimeError('Future equity screen data')
            window=self.price_volume.get(symbol)
            if window is None:
                window=EquityScreenWindow()
                self.price_volume[symbol]=window
            window.append((observed,float(row.price),float(row.volume)))
            info=window.candidate_info(float(row.market_cap))
            if info is not None:
                key = str(symbol.id)
                candidates[key] = dict(key=key, ticker=symbol.value, eq=symbol,
                    future=False, **info)
        self.equity_candidates = candidates
        self.counts['equity_screen_rows']+=row_count
        self.counts['equity_universe_days'] += 1
        self.counts['equity_screen_passes'] += len(candidates)
        return []

    def screen_earnings(self, rows):
        today = self.time.date()
        for row in rows:
            if row.end_time > self.time:
                raise RuntimeError('Future earnings calendar data')
            report = row.report_date.date()
            if report >= today:
                self.earnings_calendar.setdefault(row.symbol, {})[report] = today
        self.earnings_calendar = {s: {d: known for d, known in events.items() if d >= today}
                                 for s, events in self.earnings_calendar.items()}
        return []

    def get_state(self, candidate):
        key = candidate['key']
        if key not in self.states:
            self.states[key] = dict(candidate, iv={}, last_checked=None)
        state = self.states[key]
        # A held future stays tied to its original delivery contract.
        if key not in self.positions:
            state.update(candidate)
        return state

    def contract_record(self, contract, future=False):
        factor=1.
        if future:
            from premium_units import premium_factor
            # OptionUniverse.Time labels the day after the completed session.
            factor=premium_factor(contract.symbol.id.symbol,contract.symbol.underlying.id.symbol,
                contract.time.date()-timedelta(days=1))
            if factor!=1:self.counts['unit_repaired_daily_records']+=1
        return dict(symbol=contract.symbol, expiry=contract.expiry.date(),
            strike=float(contract.strike), put=contract.right == OptionRight.PUT,
            price=float(contract.last_price)*factor, spot=float(contract.underlying_last_price),
            iv=None if future else float(contract.implied_volatility),
            delta=None if future else float(contract.greeks.delta),
            oi=float(contract.open_interest), observed=contract.time.date(), future=future)

    def is_monthly(self, symbol, future=False):
        expiry = symbol.id.date.date()
        key = (symbol.id.symbol if future else 'equity',expiry)
        if key in self.monthly_cache:
            return self.monthly_cache[key]
        if future:
            from QuantConnect.Securities.FutureOption import FuturesOptionsExpiryFunctions
            underlying = symbol.underlying
            canonical = Symbol.create_canonical_option(Symbol.create(underlying.id.symbol,
                SecurityType.FUTURE,underlying.id.market))
            monthly = False
            if symbol.id.symbol == canonical.id.symbol:
                for offset in range(3):
                    month = expiry.year*12+expiry.month-1+offset
                    contract_month = datetime(month//12,month%12+1,1)
                    expected = FuturesOptionsExpiryFunctions.FuturesOptionExpiry(canonical,contract_month)
                    if expected.date() == expiry:
                        monthly = True
                        break
            # FutureOptionSymbol.IsStandard always returns true in LEAN; use
            # the product's actual standard expiry function and default root.
        else:
            first = date(expiry.year,expiry.month,1)
            friday = first+timedelta(days=(4-first.weekday())%7+14)
            closed = not self.securities[self.spy].exchange.hours.is_date_open(
                datetime.combine(friday,datetime.min.time()))
            monthly = standard_equity_monthly(expiry,closed)
        self.monthly_cache[key] = monthly
        return monthly

    def daily_caches(self):
        # option_chain() is a prior-completed-session DAILY universe snapshot.
        # Bound cache lifetime to one algorithm date and preserve delivery SIDs.
        today=self.time.date()
        if getattr(self,'_chain_cache_day',None)!=today:
            self._chain_cache_day=today
            self._chain_record_cache={}
            self._daily_rate_cache={}

    @performance_phase('records_for')
    def records_for(self, underlying, future=False):
        self.daily_caches()
        key=(underlying,future)
        if key in self._chain_record_cache:
            self.counts['daily_chain_cache_hits']+=1
            return self._chain_record_cache[key]
        today=self.time.date()
        records=[]
        self.counts['daily_chain_requests']+=1
        for contract in self.option_chain(underlying):
            self.counts['daily_contracts_seen']+=1
            # Every consumer already limits entry/ATM tenor to <=95 days.
            # Held positions entered inside that bound and only age down.
            if (contract.expiry.date()-today).days>95:
                self.counts['long_tenor_records_skipped']+=1
                continue
            if self.is_monthly(contract.symbol,future):
                records.append(self.contract_record(contract,future))
                self.counts['daily_contracts_materialized']+=1
        self._chain_record_cache[key]=records
        return records

    @performance_phase('model_record')
    def model_record(self, record):
        if record['future']:
            self.daily_caches()
            inputs=(self.time.date(),record['price'],record['spot'],record['strike'],
                record['observed'],record['expiry'],record['put'])
            if record.get('_model_inputs')==inputs:
                self.counts['future_model_cache_hits']+=1
                return record
            observed = datetime.combine(record['observed']-timedelta(days=1), datetime.min.time())
            if observed not in self._daily_rate_cache:
                self._daily_rate_cache[observed]=float(self.risk_free_interest_rate_model.get_interest_rate(observed))
                self.counts['daily_rate_requests']+=1
            rate = self._daily_rate_cache[observed]
            years = (record['expiry']-observed.date()).days/365
            record['iv'], record['delta'] = black76_iv_delta(record['price'], record['spot'],
                record['strike'], years, rate, record['put'])
            record['_model_inputs']=inputs
            self.counts['future_iv_solves']+=1
        return record

    def atm_iv(self, records):
        today = self.time.date()
        eligible = [r for r in records if 21 <= (r['expiry']-today).days <= 95 and r['spot'] > 0]
        if not eligible:
            return None
        expiry = min({r['expiry'] for r in eligible}, key=lambda d: (abs((d-today).days-45), d))
        pair = []
        for put in (True, False):
            choices = [r for r in eligible if r['expiry'] == expiry and r['put'] == put]
            if not choices:
                return None
            record = min(choices, key=lambda r: (abs(r['strike']-r['spot']), r['strike']))
            self.model_record(record)
            if record['iv'] is None or not .0001 < record['iv'] < 5:
                return None
            pair.append(record)
        if pair[0]['observed'] != pair[1]['observed']:
            return None
        return pair[0]['observed'], sum(r['iv'] for r in pair)/2

    @performance_phase('seed_equity_iv')
    def seed_equity_iv(self, state):
        today = self.time.date()
        last = state.get('last_checked')
        if last is not None and (today-last).days <= 5:
            return
        start = max(date(2012, 1, 1), today-timedelta(days=math.ceil(self.lookback*1.6)))
        if last is not None:
            start = max(start, last)
        canonical = Symbol.create_canonical_option(state['eq'])
        self.counts['equity_seed_history_requests']+=1
        # Native history contains the prior completed session, including its underlying mark.
        for chain in self.history[OptionUniverse](canonical,
                datetime.combine(start, datetime.min.time()), self.time):
            self.counts['equity_seed_history_days']+=1
            observed = chain.end_time.date()
            if observed > today:
                raise RuntimeError('Future IV history')
            iv=self.history_atm_iv(chain,observed)
            if iv is not None:
                state['iv'][observed]=iv

    def history_atm_iv(self,chain,observed):
        """Select the same tenor/strikes in one pass, keeping first-equal ties.

        A missing/invalid side at the best tenor remains missing. Never fall
        back to another expiry or strike to manufacture an IV observation.
        """
        underlying=chain.underlying
        spot=float(underlying.price) if underlying else 0
        if not spot>0:return None
        best_expiry=None;pair={};monthly={};seen=0
        for contract in chain.data:
            seen+=1
            symbol=contract.symbol;identifier=symbol.id
            expiry=identifier.date.date();dte=(expiry-observed).days
            if not 21<=dte<=95:continue
            if expiry not in monthly:monthly[expiry]=self.is_monthly(symbol)
            if not monthly[expiry]:continue
            rank=(abs(dte-45),expiry)
            if best_expiry is not None and rank>best_expiry:continue
            if rank!=best_expiry:
                best_expiry=rank;pair={}
            right=identifier.option_right
            if right not in (OptionRight.PUT,OptionRight.CALL):continue
            strike=float(identifier.strike_price)
            score=(abs(strike-spot),strike)
            if right not in pair or score<pair[right][0]:pair[right]=(score,contract)
        self.counts['equity_seed_contracts_seen']+=seen
        ivs=[]
        for right in (OptionRight.PUT,OptionRight.CALL):
            if right not in pair:return None
            iv=float(pair[right][1].implied_volatility)
            if not .0001<iv<5:return None
            ivs.append(iv)
        return sum(ivs)/2

    def add_observation(self, state, records):
        point = self.atm_iv(records)
        if point:
            state['iv'][point[0]] = point[1]
            self.decision(state['key'], 'valid_iv')
        else:
            self.decision(state['key'], 'missing_iv')
        state['iv'] = dict(sorted(state['iv'].items())[-self.lookback:])
        state['last_checked'] = self.time.date()
        statistics = iv_statistics(list(state['iv'].items()), self.time.date(), self.lookback, self.min_points)
        # Do not enter using an old last observation when today's chain is unusable.
        if point is None:
            statistics['ivr'] = None
        state['statistics'] = statistics
        return statistics

    def equity_rv_for(self,symbol,iv):
        cache=getattr(self,'_equity_rv_cache',None)
        if cache is None or cache[0]!=self.time.date():
            cache=(self.time.date(),{});self._equity_rv_cache=cache
        key=(str(symbol.id),float(iv))
        if key not in cache[1]:
            self.counts['equity_rv_history_requests']+=1
            expected=expected_equity_sessions(self.securities[self.spy].exchange.hours,self.time)
            bars=list(self.history[TradeBar](symbol,65,Resolution.DAILY,fill_forward=False,data_normalization_mode=DataNormalizationMode.SCALED_RAW))
            cache[1][key]=(equity_features(bars,str(symbol.id),self.time,expected,iv),expected[-1])
        return cache[1][key]

    def admit_equity_rv(self,candidate,statistics):
        if candidate['future']:
            statistics['rv_policy']='future_original_rules'
            self.counts['equity_rv_future_bypasses']+=1
            return True
        if statistics.get('last_day')!=str(self.time.date()):
            self.decision(candidate['key'],'equity_rv_iv_asof_mismatch');return False
        feature,last_session=self.equity_rv_for(candidate['eq'],statistics['iv'])
        if not equity_rv_admitted(feature,self.CONFIG['min_equity_iv_rv']):
            self.decision(candidate['key'],'equity_rv_unavailable' if not feature.ready else 'equity_iv_rv_below_threshold');return False
        statistics.update(rv_policy='equity_iv_to_max_rv20_rv60',rv20=feature.realized20,rv60=feature.realized60,
            iv_rv=feature.iv_to_max_realized,rv_samples=feature.closes,rv_last_session=str(last_session),
            rv_threshold=self.CONFIG['min_equity_iv_rv'],rv_source='SCALED_RAW')
        self.counts['equity_rv_admitted']+=1
        return True

    def selected_legs(self, records, expiry):
        selected = {}
        for put, name in [(True, 'put'), (False, 'call')]:
            choices = []
            for r in records:
                if r['expiry'] != expiry or r['put'] != put or r['oi'] < 100:
                    continue
                if not (r['strike'] < r['spot'] if put else r['strike'] > r['spot']):
                    continue
                self.model_record(r)
                if r['delta'] is not None and .16 <= abs(r['delta']) <= .22:
                    choices.append(r)
            if not choices:
                return None
            selected[name] = min(choices, key=lambda r: (abs(abs(r['delta'])-.19), r['strike']))
        return selected

    def subscribe(self, underlying, legs, future):
        if underlying not in self.subscribed_underlyings and underlying != self.spy:
            if future:
                self.add_future_contract(underlying, Resolution.MINUTE)
            else:
                self.add_equity(underlying, Resolution.MINUTE).set_data_normalization_mode(DataNormalizationMode.RAW)
            self.subscribed_underlyings.add(underlying)
        for r in legs:
            if r['symbol'] not in self.subscribed_options:
                if future:
                    security=self.add_future_option_contract(r['symbol'], Resolution.MINUTE)
                    from premium_filter import PremiumUnitFilter
                    security.set_data_filter(PremiumUnitFilter(self.counts))
                else:
                    self.add_option_contract(r['symbol'], Resolution.MINUTE)
                self.subscribed_options.add(r['symbol'])

    def cleanup(self):
        held = {t[side] for t in self.positions.values() for side in ('put','call')}
        for symbol in self.subscribed_options-held:
            if not self.portfolio[symbol].invested and not self.transactions.get_open_orders(symbol):
                self.remove_security(symbol)
        self.subscribed_options &= held
        underlying = {self.states[key]['eq'] for key in self.positions}
        for symbol in self.subscribed_underlyings-underlying:
            if not self.portfolio[symbol].invested:
                self.remove_security(symbol)
        self.subscribed_underlyings &= underlying

    @performance_phase('prepare_day')
    def prepare_day(self):
        if getattr(self,'insolvency',None):
            return
        if not self.securities[self.spy].exchange.exchange_open:
            return
        self.cleanup()
        today = self.time.date()
        self.prepared_day = today
        self.prepared, self.day_chains, self.roll_candidates = [], {}, {}
        candidates = list(self.equity_candidates.values())
        for root, canonical in self.futures.items():
            # Highest-volume delivery with a listed standard option >=35 DTE.
            contracts = sorted(self.futures_chain(canonical), key=lambda c: float(c.volume), reverse=True)
            for contract in contracts:
                if float(contract.volume) <= 0:
                    continue
                records = self.records_for(contract.symbol,True)
                expiry = monthly_expiry([r['expiry'] for r in records], today, True)
                if expiry is not None:
                    candidates.append(dict(key='FUT_'+root, ticker=root, eq=contract.symbol,
                        future=True, volume=float(contract.volume), records=records))
                    break
            else:
                self.decision('FUT_'+root, 'no_future_option_expiry')
        for candidate in candidates:
            key = candidate['key']
            state = self.get_state(candidate)
            records = candidate.get('records')
            if records is None:
                records = self.records_for(candidate['eq'])
                self.seed_equity_iv(state)
            statistics = self.add_observation(state, records)
            self.day_chains[key] = records
            if key in self.positions:
                self.decision(key, 'invested')
                continue
            if not high_iv_rank(statistics['ivr']):
                self.decision(key, 'ivr_unavailable' if statistics['ivr'] is None else 'ivr_not_above_70')
                continue
            if not can_start_batch(self.positions,self.pending_combos,self.exit_requests):
                self.decision(key,'wait_for_batch_close')
                continue
            expiry = monthly_expiry([r['expiry'] for r in records], today, candidate['future'])
            if expiry is None:
                self.decision(key, 'no_monthly_expiry')
                continue
            events = [(known, report) for report, known in self.earnings_calendar.get(candidate['eq'], {}).items()]
            if earnings_veto(events, today, expiry):
                self.decision(key, 'known_earnings_veto')
                continue
            if not self.admit_equity_rv(candidate,statistics):
                continue
            legs = self.selected_legs(records, expiry)
            if legs is None:
                self.decision(key, 'no_delta_legs')
                continue
            self.subscribe(candidate['eq'], list(legs.values()), candidate['future'])
            self.prepared.append(dict(candidate, legs=legs, expiry=expiry, statistics=statistics))
        # Holdings remain managed even if price/volume screening removes their underlying.
        for key, trade in self.positions.items():
            state = self.states[key]
            if key not in self.day_chains or state['future']:
                self.day_chains[key] = self.records_for(state['eq'],state['future'])
            by_symbol = {r['symbol']: self.model_record(r) for r in self.day_chains[key]
                         if r['symbol'] in (trade['put'], trade['call'])}
            p, c = by_symbol.get(trade['put']), by_symbol.get(trade['call'])
            if p is None or c is None or p['delta'] is None or c['delta'] is None or trade['rolls'] >= 3:
                continue
            side = roll_side(p['delta'], c['delta'])
            if side:
                choices = []
                for r in self.day_chains[key]:
                    if r['expiry'] != trade['expiry'] or r['put'] != (side == 'put') or r['oi'] < 100:
                        continue
                    self.model_record(r)
                    inside = (p['strike'] < r['strike'] < min(r['spot'], c['strike']) if side == 'put'
                              else max(r['spot'], p['strike']) < r['strike'] < c['strike'])
                    if inside and r['delta'] is not None and .16 <= abs(r['delta']) <= .22:
                        choices.append(r)
                if choices:
                    new = min(choices, key=lambda r: (abs(abs(r['delta'])-.19), r['strike']))
                    self.subscribe(state['eq'], [new], state['future'])
                    self.roll_candidates[key] = (side, new)
        self.prepared = ordered_candidates(self.prepared)

    def good_quote(self, security):
        bar = security.cache.get_data[QuoteBar]()
        return (bar is not None and not bar.is_fill_forward
            and security.local_time-timedelta(minutes=5) <= bar.end_time <= security.local_time
            and float(security.bid_price) > 0 and float(security.ask_price) >= float(security.bid_price))

    def liquid_security(self, security):
        if not self.good_quote(security):
            return False
        bid, ask = float(security.bid_price), float(security.ask_price)
        tick = float(security.symbol_properties.minimum_price_variation)
        return bid >= tick and ask-bid <= max(2*tick, .25*(bid+ask)/2)

    def on_data(self, data):
        if getattr(self,'insolvency',None):
            return
        self.process_pending_combos()
        self.process_exit_requests()
        self.intraday_risk_exits()
        # Calendar schedules can catch up at the next data slice after a weekend.
        # Never consume an old noon trigger at the following morning's open.
        if not self.due or self.time.time() < time(12,0) or self.last_day == self.time.date():
            return
        self.due, self.last_day = False, self.time.date()
        today = self.time.date()
        if today < self.trade_start:
            return
        closed_today = set()
        for key, trade in list(self.positions.items()):
            if key in self.pending_combos:
                continue
            put, call = self.securities[trade['put']], self.securities[trade['call']]
            if not put.exchange.exchange_open or not call.exchange.exchange_open:
                continue
            dte = (trade['expiry']-today).days
            reason = ('END' if today >= self.end else 'TIME' if dte <= self.time_exit_dte else
                      'AGE' if age_exit_due(trade['opened'],today,self.max_holding_days) else
                      'SPLIT' if self.states[key].get('split_warning') else None)
            if reason is None and self.voluntary_quote_ready(key):
                close_cost = (float(put.ask_price)+float(call.ask_price))*trade['multiplier']*trade['quantity']
                reason = close_reason(trade['cash'], trade['fees']+self.close_fees(trade),
                                      close_cost, trade['initial'], dte,stop_multiple=self.CONFIG['stop_multiple'])
            if reason:
                self.exit_requests[key] = dict(reason=reason, day=today)
                closed_today.add(key)
            elif (self.prepared_day == today and key in self.roll_candidates
                  and self.good_quote(put) and self.good_quote(call)):
                self.submit_roll(key, *self.roll_candidates[key])
        self.process_exit_requests()
        if self.securities[self.spy].exchange.exchange_open:
            candidates = []
            may_open = (can_start_batch(self.positions,self.pending_combos,self.exit_requests)
                and self.last_research_exit_day!=today)
            for candidate in (self.prepared if self.prepared_day == today and may_open else []):
                key = candidate['key']
                if key in self.positions or key in closed_today:
                    continue
                if (self.end-today).days < 7:
                    self.decision(key, 'end_window')
                    continue
                if not available_slots(self.positions, self.pending_combos, self.max_basket):
                    self.decision(key, 'basket_full')
                    continue
                securities = [self.securities[candidate['legs'][side]['symbol']] for side in ('put','call')]
                if not all(self.liquid_security(s) for s in securities):
                    self.decision(key, 'entry_quote_or_spread')
                    continue
                unit_margin = self.initial_margin(securities, 1)
                unit_cost = unit_margin+self.order_fees(securities, -1)
                if not math.isfinite(unit_margin) or unit_margin <= 0:
                    self.decision(key, 'invalid_margin')
                    continue
                candidates.append(dict(candidate, unit_margin=unit_margin, unit_cost=unit_cost))
            if candidates:
                equity = float(self.portfolio.total_portfolio_value)
                selected, count = capped_candidates(candidates,len(self.positions),equity,self.max_basket,
                    self.CONFIG['total_collateral_fraction'],self.CONFIG['per_symbol_collateral_fraction'])
                if selected:
                    self.batch_id += 1
                    self.log('BATCH_OPEN '+json.dumps(dict(batch_id=self.batch_id,date=str(today),
                        count=count,equity=equity,budget=collateral_budget(equity,count,self.CONFIG['total_collateral_fraction'],self.CONFIG['per_symbol_collateral_fraction']),
                        keys=[c['key'] for c in selected])))
                for candidate in selected:
                    self.open_candidate(candidate,count,equity)
            self.active_equity.append((str(today), float(self.portfolio.total_portfolio_value)))
            self.plot('Trading period', 'Equity', self.active_equity[-1][1])
            self.plot('Basket', 'Underlyings', len(self.positions))
        self.counts['peak_basket'] = max(self.counts['peak_basket'], len(self.positions))

    def close_fees(self, trade):
        return self.order_fees([self.securities[trade[side]] for side in ('put','call')],trade['quantity'])

    def order_fees(self, securities, quantity):
        return sum(float(s.fee_model.get_order_fee(OrderFeeParameters(
            s,MarketOrder(s.symbol,quantity,self.utc_time))).value.amount) for s in securities)

    def initial_margin(self, securities, quantity):
        return sum(abs(float(s.buying_power_model.get_initial_margin_requirement(
            InitialMarginParameters(s,-quantity)).value)) for s in securities)

    def voluntary_quote_ready(self, key):
        trade = self.positions[key]
        securities = [self.securities[trade[side]] for side in ('put','call')]
        snapshots = []
        for security in securities:
            bar = security.cache.get_data[QuoteBar]()
            snapshots.append(BuybackQuote(str(security.symbol.id),security.local_time,
                bar.end_time if bar is not None else None,
                bool(bar.is_fill_forward) if bar is not None else False,
                bar.ask.close if bar is not None and bar.ask is not None else None,
                security.bid_price,security.ask_price,
                security.symbol_properties.minimum_price_variation))
        decision = cross_asset_market_buyback_guard('STOP',self.states[key]['future'],snapshots)
        if not decision.allowed:
            self.counts['research_voluntary_pair_deferred'] += 1
        return decision.allowed

    def process_exit_requests(self):
        for key, request in list(self.exit_requests.items()):
            if key not in self.positions:
                del self.exit_requests[key]
                continue
            if key in self.pending_combos:
                continue
            trade = self.positions[key]
            reason = request['reason']
            voluntary = reason in ('PROFIT','STOP')
            if voluntary:
                # This request has no submitted order: pending combos returned above.
                # Re-evaluate triggers rather than carrying an old voluntary request.
                mandatory_due = ((trade['expiry']-self.time.date()).days <= self.time_exit_dte
                    or self.time.date() >= self.end or self.states[key].get('split_warning'))
                if request['day'] != self.time.date() or mandatory_due or not self.voluntary_quote_ready(key):
                    del self.exit_requests[key]
                    self.counts['research_unsubmitted_voluntary_deferred'] += 1
                    continue
            if self.time.date() > request['day']:
                raise RuntimeError('Mandatory exit lacked fresh quotes on its eligible session: '+key)
            if not voluntary and not all(self.good_quote(self.securities[trade[side]]) for side in ('put','call')):
                continue
            self.execute(key, [Leg.create(trade['put'],1), Leg.create(trade['call'],1)], reason,
                on_filled=lambda key=key, reason=reason: self.finish_close(key,reason))
            del self.exit_requests[key]

    def intraday_risk_exits(self):
        if getattr(self,'insolvency',None) or not self.positions:return
        slots=getattr(self,'fresh_risk_slots',None)
        if slots is None:
            slots=FreshRiskSlots(self.CONFIG['risk_interval_minutes'])
            self.fresh_risk_slots=slots
        slots.retain(self.positions)
        for key,trade in list(self.positions.items()):
            if not slots.due(key,self.utc_time):continue
            if key in self.pending_combos or key in self.exit_requests:continue
            put,call=[self.securities[trade[s]] for s in ('put','call')]
            if not all(s.exchange.exchange_open for s in (put,call)):continue
            dte=(trade['expiry']-self.time.date()).days
            # Product-open noon TIME exits retain their original priority.
            if dte<=self.time_exit_dte or self.time.date()>=self.end:continue
            if not self.voluntary_quote_ready(key):
                self.counts['research_risk_quote_guard_deferred']+=1;continue
            cost=(float(put.ask_price)+float(call.ask_price))*trade['multiplier']*trade['quantity']
            reason=close_reason(trade['cash'],trade['fees']+self.close_fees(trade),cost,
                trade['initial'],dte,stop_multiple=self.CONFIG['stop_multiple'])
            slots.complete(key,self.utc_time)
            self.counts['research_fresh_risk_evaluations']+=1
            if reason:
                self.exit_requests[key]=dict(reason=reason,day=self.time.date())
        self.process_exit_requests()

    def on_margin_call(self, requests):
        # Replace each broker-requested single-leg reduction with a full paired
        # liquidation. Keep the default margin model and record actual fills.
        keys = set()
        for request in requests:
            matches = [key for key, trade in self.positions.items()
                       if request.symbol in (trade['put'], trade['call'])]
            if len(matches) != 1:
                raise RuntimeError('Untracked margin-call holding: '+str(request.symbol))
            keys.add(matches[0])
        for key in sorted(keys):
            if key in self.pending_combos:
                raise RuntimeError('Margin call overlaps an unresolved combo: '+key)
            trade = self.positions[key]
            if not all(self.good_quote(self.securities[trade[side]]) for side in ('put','call')):
                raise RuntimeError('Margin liquidation lacks fresh paired quotes: '+key)
            self.exit_requests[key] = dict(reason='MARGIN', day=self.time.date())
        if keys:
            self.counts['margin_call_events'] += 1
            self.log('MARGIN_CALL '+json.dumps(dict(date=str(self.time),keys=sorted(keys))))
            self.process_exit_requests()
            if any(key in self.exit_requests for key in keys):
                raise RuntimeError('Margin-call liquidation was not submitted')
            if any(key in self.pending_combos for key in keys):
                raise RuntimeError('Margin-call liquidation must finish before broker execution')
            # The Python event wrapper rejects empty request lists. Return the
            # original list only after restoring buying power: the default
            # model then exits before executing any of these obsolete requests.
            if float(self.portfolio.margin_remaining) < 0:
                if not self.record_insolvency():
                    raise RuntimeError('Paired margin liquidations did not restore buying power')
        return requests

    def record_insolvency(self):
        """Finish a fully closed bankrupt account without resubmitting stale closes."""
        equity=float(self.portfolio.total_portfolio_value)
        if (not math.isfinite(equity) or equity>0 or self.positions or self.pending_combos
                or self.exit_requests or self.portfolio.invested):
            return False
        if (float(self.portfolio.total_margin_used)!=0
                or self.transactions.get_open_orders()):
            raise RuntimeError('Flat insolvency has unresolved margin or orders')
        if getattr(self,'insolvency',None):
            return True
        from terminal_margin import FlatInsolvencyMarginModel
        self.insolvency=dict(utc=self.utc_time.isoformat(),local=self.time.isoformat(),equity=equity)
        # LEAN calls ExecuteMarginCall after this callback, even after Quit.
        # Its Python callback requires a nonempty list. A terminal-only model
        # discards those obsolete requests after independently checking flatness.
        self.portfolio.set_margin_call_model(FlatInsolvencyMarginModel(self))
        day=str(self.time.date())
        if self.active_equity and self.active_equity[-1][0]==day:
            self.active_equity[-1]=(day,equity)
        else:
            self.active_equity.append((day,equity))
        self.plot('Trading period','Equity',equity)
        self.log('INSOLVENCY '+json.dumps(self.insolvency))
        self.quit('Account insolvent after all actual liquidation fills; equity='+str(equity))
        return True

    def on_margin_call_warning(self):
        self.counts['margin_call_warnings'] += 1

    def open_candidate(self, candidate, basket_count, equity):
        if getattr(self,'insolvency',None):
            raise RuntimeError('Entry attempted after account insolvency')
        key, legs = candidate['key'], candidate['legs']
        securities = [self.securities[legs[side]['symbol']] for side in ('put','call')]
        if not all(self.liquid_security(s) for s in securities):
            self.decision(key, 'entry_quote_or_spread')
            return
        state = self.states[key]
        if state.get('split_warning') or state.get('split_block_day') == self.time.date():
            self.decision(key, 'split')
            return
        multipliers = {float(s.symbol_properties.contract_multiplier) for s in securities}
        if len(multipliers) != 1:
            raise RuntimeError('Strangle legs have different multipliers')
        multiplier = multipliers.pop()
        spot = float(self.securities[candidate['eq']].price)
        allocation = collateral_budget(equity,basket_count,self.CONFIG['total_collateral_fraction'],self.CONFIG['per_symbol_collateral_fraction'])
        pending_reserve = sum(self.positions[k]['reserve'] for k,p in self.pending_combos.items()
                              if p['reason'] == 'OPEN')
        remaining = max(0,float(self.portfolio.margin_remaining)-pending_reserve)
        quantity = capped_quantity(equity,basket_count,candidate['unit_cost'],remaining,
            self.CONFIG['total_collateral_fraction'],self.CONFIG['per_symbol_collateral_fraction'])
        while quantity:
            reserve = self.initial_margin(securities,quantity)
            entry_fees = self.order_fees(securities,-quantity)
            if reserve+entry_fees <= min(allocation,remaining)+1e-7:
                break
            quantity -= 1
        if not quantity:
            self.decision(key, 'margin')
            return
        features = dict(candidate['statistics'], volume=candidate['volume'], spot=spot,
            put_delta=legs['put']['delta'], call_delta=legs['call']['delta'], multiplier=multiplier,
            quantity=quantity,basket_count=basket_count,allocation_equity=equity,
            allocation_budget=allocation,estimated_initial_margin=reserve,estimated_entry_fees=entry_fees,
            allocation_mode='research_capped_collateral_budget',
            total_collateral_fraction=self.CONFIG['total_collateral_fraction'],
            per_symbol_collateral_fraction=self.CONFIG['per_symbol_collateral_fraction'],batch_id=self.batch_id,
            max_holding_days=self.max_holding_days,monthly_only=True)
        self.positions[key] = dict(put=legs['put']['symbol'], call=legs['call']['symbol'],
            expiry=candidate['expiry'], cash=0., fees=0., initial=0., rolls=0,
            multiplier=multiplier, reserve=reserve, quantity=quantity, opened=str(self.time.date()),
            entry_metadata=';'.join(f'{k}={v}' for k,v in features.items() if v is not None))
        self.execute(key, [Leg.create(legs['put']['symbol'],-1), Leg.create(legs['call']['symbol'],-1)],
            'OPEN', on_filled=lambda key=key,features=features: self.finish_entry(key,features))
        self.decision(key, 'entry_submitted')

    def finish_entry(self, key, features):
        trade = self.positions[key]
        trade['initial'] = trade['cash']
        if trade['initial'] <= 0:
            raise RuntimeError('Noncredit strangle')
        self.counts['entries'] += 1
        self.counts['future_entries' if self.states[key]['future'] else 'equity_entries'] += 1
        self.first_entry = self.first_entry or str(self.time.date())
        self.log('ENTRY '+json.dumps(dict(key=key,ticker=self.states[key]['ticker'],
            date=str(self.time.date()),expiry=str(trade['expiry']),credit=trade['initial'],**features)))

    def finish_close(self, key, reason):
        self.last_research_exit_day=self.time.date()
        trade = self.positions[key]
        pnl = trade['cash']-trade['fees']
        self.closed_pnl.append(pnl)
        self.counts[reason] += 1
        self.log('CYCLE '+json.dumps(dict(key=key,ticker=self.states[key]['ticker'],
            date=str(self.time.date()),entry=trade['opened'],expiry=str(trade['expiry']),
            dte=(trade['expiry']-self.time.date()).days,reason=reason,pnl=pnl,
            initial=trade['initial'],fees=trade['fees'],rolls=trade['rolls'],quantity=trade['quantity'])))
        del self.positions[key]

    def submit_roll(self, key, side, new):
        trade = self.positions[key]
        old = self.securities[trade[side]]
        replacement = self.securities[new['symbol']]
        if not self.liquid_security(replacement):
            return
        tick = float(replacement.symbol_properties.minimum_price_variation)
        if float(replacement.bid_price)-float(old.ask_price) < tick:
            return
        quantity = trade['quantity']
        margin_increase = max(0,self.initial_margin([replacement],quantity)
                                -self.initial_margin([old],quantity))
        fees = self.order_fees([old],quantity)+self.order_fees([replacement],-quantity)
        if float(self.portfolio.margin_remaining) < margin_increase+fees:
            self.decision(key,'roll_margin')
            return
        before = trade['cash']
        def filled():
            trade[side] = new['symbol']
            trade['rolls'] += 1
            self.counts['rolls'] += 1
            self.log('ROLL '+json.dumps(dict(key=key,date=str(self.time.date()),side=side,
                credit=trade['cash']-before)))
        self.execute(key,[Leg.create(trade[side],1),Leg.create(new['symbol'],-1)],
            'ROLL',on_filled=filled)

    def execute(self, key, legs, reason, on_filled=None):
        # Every order carries its multiplier; downstream accounting must never assume 100.
        trade = self.positions[key]
        on_rejected = None
        if reason == 'ROLL':
            def on_rejected():
                self.counts['rejected_rolls'] += 1
                self.log('ROLL_REJECTED '+json.dumps(dict(key=key,date=str(self.time),
                    quantity=trade['quantity'],reason='broker rejected both unfilled legs')))
        if reason != 'OPEN':
            # The parent adds metadata only for OPEN; add multiplier to the reason itself.
            reason += ';multiplier='+str(trade['multiplier'])
        if self.states[key]['future'] and reason.split(';',1)[0] not in ('OPEN','ROLL'):
            self.execute_sequential_close(key,[trade['put'],trade['call']],reason,
                trade['quantity'],on_filled)
            return
        kwargs = dict(quantity=trade['quantity'])
        if on_rejected:
            kwargs['on_rejected'] = on_rejected
        super().execute(key,legs,reason,on_filled,**kwargs)

    def on_splits(self, splits):
        for symbol, split in splits.items():
            for state in self.states.values():
                if state['eq'] == symbol:
                    state['split_warning'] = split.type == SplitType.WARNING
                    state['split_block_day'] = self.time.date()

    def on_assignment_order_event(self, event):
        raise RuntimeError('Assignment requires a separate underlying ledger; baseline invalid: '+str(event.symbol))

    def on_end_of_algorithm(self):
        self.process_pending_combos()
        if self.positions or self.pending_combos or self.exit_requests or self.portfolio.invested:
            raise RuntimeError('Residual positions or unfilled exits invalidate baseline')
        final = float(self.portfolio.total_portfolio_value)
        difference = final-self.initial_cash-sum(self.closed_pnl)
        if abs(difference) > .05:
            raise RuntimeError('Fill/account P&L does not reconcile: '+str(difference))
        for (year,key),counts in sorted(self.annual.items()):
            self.log('SCREEN_COUNTS '+json.dumps(dict(year=year,key=key,counts=dict(counts))))
        for key,value in sorted(self.counts.items()):
            self.set_runtime_statistic(key,str(value))
        terminal=getattr(self,'insolvency',None)
        for key,value in dict(baseline_outcome='insolvent' if terminal else 'period_complete',
                insolvency_utc=terminal['utc'] if terminal else 'none',
                insolvency_equity=terminal['equity'] if terminal else 'none',
                observed_end=str(self.time.date())).items():
            self.set_runtime_statistic(key,str(value))
        for key,value in dict(closed_cycles=len(self.closed_pnl),open_cycles=0,
                cycle_net_pnl=sum(self.closed_pnl),initial_cash=self.initial_cash,
                first_entry=self.first_entry or 'none',active_snapshots=len(self.active_equity),
                ivr_lookback=self.lookback,ivr_minimum_history=self.min_points,
                ivr_formula='range_rank',ivr_threshold='strictly >70',
                max_basket=self.max_basket,pnl_reconciliation_difference=difference,
                sizing='research capped collateral budgets; whole contracts; no rebalancing',
                entries_policy='new batch only after all positions and pending orders close',
                monthly_only=True,batches=self.batch_id,
                earnings_coverage='known events only; historical feed roughly next 7 days',
                future_iv_model='Black76 on prior close; American exercise approximation',
                engineering_smoke=self.CONFIG.get('engineering_smoke',False)).items():
            self.set_runtime_statistic(key,str(value))
        if self.active_equity:
            peak,drawdown=self.initial_cash,0
            for day,value in self.active_equity:
                peak=max(peak,value)
                drawdown=max(drawdown,1-value/peak)
            self.set_runtime_statistic('active_return',str(final/self.initial_cash-1))
            self.set_runtime_statistic('active_daily_mdd',str(drawdown))
