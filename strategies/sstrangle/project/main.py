from AlgorithmImports import *
from collections import deque, Counter
from datetime import date, timedelta
import json
import math
from rules import iv_rank, iv_entry_rejection, correlation, close_reason, roll_side, return_features, entry_filter_reason


class TranscriptShortStrangle(QCAlgorithm):
    # Experiment renderer replaces CONFIG, preserving exact submitted sources.
    CONFIG = {}

    def initialize(self):
        cfg = self.CONFIG
        self.set_start_date(*cfg.get('start', [2022, 12, 1]))
        self.end = date(*cfg.get('end', [2025, 12, 31]))
        self.trade_start = date(*cfg.get('trade_start', [2024, 1, 2]))
        self.set_end_date(self.end.year, self.end.month, self.end.day)
        self.initial_cash = float(cfg.get('initial_cash', 250000))
        self.set_cash(self.initial_cash)
        self.set_benchmark('SPY')
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.iv_min = cfg.get('iv_min', 50)
        self.lookback = cfg.get('lookback', 252)
        self.allow_rolls = cfg.get('rolls', True)
        self.stop_multiple = float(cfg.get('stop_multiple', 2.0))
        self.min_iv_rv = cfg.get('min_iv_rv')
        self.max_trend_z = cfg.get('max_trend_z')
        if self.stop_multiple <= 0:
            raise ValueError('stop_multiple must be positive')
        self.states, self.positions = {}, {}
        self.pending_combos = {}
        self.counts = Counter()
        self.entry_decisions = {}
        self.due, self.last_day = False, None
        self.active_equity = []
        self.closed_pnl = []
        self.first_entry = None
        for ticker in cfg.get('tickers', ['SPY', 'GLD', 'TLT']):
            if ticker == 'SPX':
                equity = self.add_index(ticker, Resolution.MINUTE)
                option = self.add_index_option(equity.symbol, Resolution.MINUTE)
            else:
                equity = self.add_equity(ticker, Resolution.MINUTE)
                equity.set_data_normalization_mode(DataNormalizationMode.RAW)
                option = self.add_option(ticker, Resolution.MINUTE)
            option.set_filter(self.filter_options)
            option.price_model = (OptionPriceModels.black_scholes() if ticker == 'SPX'
                                  else OptionPriceModels.QuantLib.crank_nicolson_fd())
            self.states[ticker] = dict(eq=equity.symbol, opt=option.symbol,
                iv=deque(maxlen=self.lookback), returns={}, previous=None)
        self.schedule.on(self.date_rules.every_day('SPY'),
                         self.time_rules.before_market_close('SPY', 30), self.arm)

    def arm(self):
        self.due = True

    def on_splits(self, splits):
        for symbol, split in splits.items():
            for state in self.states.values():
                if state['eq'] != symbol:
                    continue
                state['split_block_day'] = self.time.date()
                if split.type == SplitType.WARNING:
                    state['split_warning'] = True
                else:
                    state['split_warning'] = False
                    # A mechanical price split is not a realized market return.
                    state['previous'] = None
                    state['returns'].clear()
                    self.counts['split_events'] += 1

    def filter_options(self, universe):
        # Only ATM observations are needed before the trading period.
        width = 1 if self.time.date() < self.trade_start else self.CONFIG.get('strike_width', 40)
        return universe.standards_only().strikes(-width, width).expiration(21, 55)

    def good_quote(self, security):
        # A fresh trade bar must not make a previous day's bid/ask look fresh.
        datum = security.cache.get_data[QuoteBar]()
        # Cached bars use the security's local clock (SPX options use Chicago),
        # while the algorithm clock is New York. Compare within one time zone.
        return (datum is not None and security.local_time - timedelta(minutes=5) <= datum.end_time <= security.local_time
                and float(security.bid_price) > 0
                and float(security.ask_price) >= float(security.bid_price))

    def liquid_contract(self, c):
        bid, ask = float(c.bid_price), float(c.ask_price)
        return (bid >= 0.05 and ask >= bid and ask - bid <= max(0.10, 0.25 * (bid + ask) / 2)
                and c.open_interest >= 100)

    def first_observation(self, state, key, ticker, today):
        if key not in state:
            state[key] = str(today)
            self.set_runtime_statistic(key + '_' + ticker, state[key])

    def on_data(self, data):
        # A synchronous QC order can return while still submitted. Reconcile it
        # on every minute slice, before the once-daily signal/management gate.
        self.process_pending_combos()
        if not self.due or self.last_day == self.time.date():
            return
        self.due, self.last_day = False, self.time.date()
        today = self.time.date()
        chains, ranks = {}, {}
        for ticker, s in self.states.items():
            spot = float(self.securities[s['eq']].price)
            if s['previous'] and spot > 0:
                s['returns'][today] = spot / s['previous'] - 1
                s['returns'] = dict(sorted(s['returns'].items())[-80:])
            s['previous'] = spot
            s['rv20'], s['trend_z'] = return_features(list(s['returns'].values()))
            s['current_iv'] = None
            chain = data.option_chains.get(s['opt'])
            contracts = list(chain) if chain is not None else []
            chains[ticker] = contracts
            if not contracts or spot <= 0:
                self.counts['missing_chain'] += 1
                continue
            self.first_observation(s, 'first_chain', ticker, today)
            self.counts[f'chain_days_{ticker}_{today.year}'] += 1
            contracts = [c for c in contracts if self.good_quote(self.securities[c.symbol])]
            chains[ticker] = contracts
            if not contracts:
                self.counts['no_fresh_chain'] += 1
                self.counts[f'no_fresh_chain_days_{ticker}_{today.year}'] += 1
                continue
            self.counts[f'fresh_chain_days_{ticker}_{today.year}'] += 1
            expiries = sorted({c.expiry for c in contracts
                               if 21 <= (c.expiry.date() - today).days <= 55})
            if not expiries:
                continue
            expiry = min(expiries, key=lambda e: (abs((e.date()-today).days-45), e))
            atm = sorted([c for c in contracts if c.expiry == expiry],
                         key=lambda c: abs(float(c.strike) - spot))[:2]
            values = [float(c.implied_volatility) for c in atm
                      if 0.01 < float(c.implied_volatility) < 5]
            if values:
                current = sum(values) / len(values)
                s['current_iv'] = current
                self.first_observation(s, 'first_valid_iv', ticker, today)
                ranks[ticker] = iv_rank(current, list(s['iv']), self.lookback)
                self.counts[f'valid_iv_days_{ticker}_{today.year}'] += 1
                if ranks[ticker] is not None:
                    self.first_observation(s, 'first_ivr_ready', ticker, today)
                    self.counts[f'ivr_ready_days_{ticker}_{today.year}'] += 1
                s['iv'].append(current)
                self.counts['iv_observations'] += 1
                if today >= self.trade_start:
                    self.counts['active_iv_observations'] += 1
        if today < self.trade_start:
            return
        closed_today = set()
        for ticker in list(self.positions):
            if ticker in self.pending_combos:
                continue
            t = self.positions[ticker]
            stock = self.securities[self.states[ticker]['eq']]
            if stock.invested or t.get('assigned'):
                # Assignment invalidates option-only cycle accounting; expose it.
                self.counts['assignment_exits'] += 1
                self.liquidate(stock.symbol, tag='ASSIGNMENT_STOCK')
                for symbol in [t['put'], t['call']]:
                    if self.portfolio[symbol].invested:
                        self.liquidate(symbol, tag='ASSIGNMENT_OPTION')
                self.log('CYCLE ' + json.dumps(dict(ticker=ticker, reason='ASSIGNMENT',
                    date=str(today), pnl=None)))
                del self.positions[ticker]
                closed_today.add(ticker)
                continue
            put, call = self.securities[t['put']], self.securities[t['call']]
            dte = (t['expiry'].date() - today).days
            # Calendar exits are mandatory; stale marks must not defer them.
            # If QC cannot fill the market combo, execute() fails the run instead
            # of silently keeping an overdue position or inventing an exit.
            mandatory_reason = ('END' if today >= self.end else
                                'TIME' if dte <= 21 else
                                'SPLIT' if self.states[ticker].get('split_warning') else None)
            quotes_good = all(self.good_quote(x) for x in [put, call])
            if not mandatory_reason and not quotes_good:
                self.counts['stale_management'] += 1
                continue
            if mandatory_reason:
                reason = mandatory_reason
                if not quotes_good:
                    self.counts['mandatory_exit_stale_quotes'] += 1
            else:
                close_cost = (float(put.ask_price) + float(call.ask_price)) * 100
                reason = close_reason(t['cash'], t['fees'] + 2.00, close_cost,
                    t['initial'], dte, stop_multiple=self.stop_multiple)
            if reason:
                self.execute(ticker, [Leg.create(t['put'], 1), Leg.create(t['call'], 1)], reason,
                    on_filled=lambda ticker=ticker, reason=reason: self.finish_close(ticker, reason))
                closed_today.add(ticker)
            elif self.allow_rolls and t['rolls'] < 3:
                self.try_roll(ticker, chains[ticker])
        for ticker, s in self.states.items():
            reason = self.entry_decision(ticker, chains[ticker], ranks.get(ticker), closed_today)
            self.counts['decision_' + reason] += 1
            self.entry_decisions.setdefault((ticker, today.year), Counter())[reason] += 1
        value = float(self.portfolio.total_portfolio_value)
        self.active_equity.append((str(today), value))
        self.plot('Trading period', 'Equity', value)

    def entry_decision(self, ticker, contracts, rank, closed_today):
        """One terminal entry decision per ticker/session, including flat skips."""
        today = self.time.date()
        s = self.states[ticker]
        if ticker in closed_today:
            return 'exit_day'
        if ticker in self.positions:
            return 'invested'
        if (self.end - today).days < 7:
            return 'end_window'
        if s.get('split_warning') or s.get('split_block_day') == today:
            self.counts['split_entry_rejected'] += 1
            return 'split'
        rejection = iv_entry_rejection(rank, self.iv_min)
        if rejection:
            self.counts['ivr_rejected'] += 1
            return rejection
        if not contracts:
            return 'no_fresh_chain'
        rejection = entry_filter_reason(s.get('current_iv'), s.get('rv20'), s.get('trend_z'),
            self.min_iv_rv, self.max_trend_z)
        if rejection:
            self.counts[rejection] += 1
            return rejection
        if not self.diversified(ticker):
            self.counts['correlation_rejected'] += 1
            return 'correlation'
        return self.try_entry(ticker, contracts, rank)

    def diversified(self, ticker):
        for other in self.positions:
            corr = correlation(self.states[ticker]['returns'], self.states[other]['returns'])
            if corr is None or abs(corr) > 0.70:
                return False
        return True

    def try_entry(self, ticker, contracts, rank):
        today = self.time.date()
        candidates = [c for c in contracts if 35 <= (c.expiry.date()-today).days <= 55]
        expiries = {c.expiry for c in candidates}
        if not expiries:
            return 'no_entry_expiry'
        expiry = min(expiries, key=lambda e: (abs((e.date()-today).days-45), e))
        spot = float(self.securities[self.states[ticker]['eq']].price)
        selected = {}
        for right, name in [(OptionRight.PUT, 'put'), (OptionRight.CALL, 'call')]:
            choices = [c for c in candidates if c.expiry == expiry and c.right == right
                       and (float(c.strike) < spot if name == 'put' else float(c.strike) > spot)
                       and self.liquid_contract(c) and 0.16 <= abs(float(c.greeks.delta)) <= 0.20]
            if not choices:
                self.counts['no_delta_contract'] += 1
                delta_candidates = [c for c in candidates if c.expiry == expiry and c.right == right
                    and (float(c.strike) < spot if name == 'put' else float(c.strike) > spot)
                    and 0.16 <= abs(float(c.greeks.delta)) <= 0.20]
                return ('illiquid_' if delta_candidates else 'no_delta_') + name
            selected[name] = min(choices, key=lambda c: (abs(abs(float(c.greeks.delta))-0.18), float(c.strike)))
        equity = float(self.portfolio.total_portfolio_value)
        reserve = 0.20 * spot * 100
        total_reserve = sum(0.20 * float(self.securities[self.states[k]['eq']].price) * 100 for k in self.positions)
        if reserve > 0.10 * equity or total_reserve + reserve > 0.25 * equity:
            self.counts['size_rejected'] += 1
            return 'size'
        if float(self.portfolio.margin_remaining) < reserve * 2:
            self.counts['margin_rejected'] += 1
            return 'margin'
        put, call = selected['put'], selected['call']
        t = dict(put=put.symbol, call=call.symbol, expiry=expiry,
                 cash=0.0, fees=0.0, initial=0.0, rolls=0)
        s = self.states[ticker]
        features = dict(ivr=rank, iv=s.get('current_iv'), rv=s.get('rv20'),
            trend_z=s.get('trend_z'), spot=spot, put_delta=float(put.greeks.delta),
            call_delta=float(call.greeks.delta))
        t['entry_metadata'] = ';'.join(f'{k}={v:.6f}' for k, v in features.items() if v is not None)
        self.positions[ticker] = t
        self.execute(ticker, [Leg.create(put.symbol, -1), Leg.create(call.symbol, -1)], 'OPEN',
            on_filled=lambda: self.finish_entry(ticker, features))
        return 'entry_submitted'

    def finish_entry(self, ticker, features):
        t = self.positions[ticker]
        t['initial'] = t['cash']
        if t['initial'] <= 0:
            raise RuntimeError('Short strangle did not open for a credit')
        self.counts['entries'] += 1
        self.counts['entries_' + ticker] += 1
        if self.first_entry is None:
            self.first_entry = str(self.time.date())
        self.log('ENTRY ' + json.dumps(dict(ticker=ticker, date=str(self.time.date()), expiry=str(t['expiry'].date()),
            ivr=round(features['ivr'], 2) if features['ivr'] is not None else None,
            put_delta=features['put_delta'], call_delta=features['call_delta'],
            credit=t['initial'])))

    def finish_close(self, ticker, reason):
        t = self.positions[ticker]
        today = self.time.date()
        pnl = t['cash'] - t['fees']
        self.closed_pnl.append(pnl)
        self.counts[reason] += 1
        if reason == 'TIME':
            dte = (t['expiry'].date() - today).days
            self.counts['time_exit_min_dte'] = min(self.counts.get('time_exit_min_dte', dte), dte)
            self.counts['time_exit_max_dte'] = max(self.counts.get('time_exit_max_dte', dte), dte)
        self.log('CYCLE ' + json.dumps(dict(ticker=ticker, date=str(today),
            reason=reason, pnl=round(pnl, 2), initial=round(t['initial'], 2), rolls=t['rolls'])))
        del self.positions[ticker]

    def try_roll(self, ticker, contracts):
        t = self.positions[ticker]
        by_symbol = {c.symbol: c for c in contracts}
        p, c = by_symbol.get(t['put']), by_symbol.get(t['call'])
        if p is None or c is None:
            self.counts['roll_missing_contract'] += 1
            return
        side = roll_side(float(p.greeks.delta), float(c.greeks.delta))
        if side is None:
            return
        old = p if side == 'put' else c
        spot = float(self.securities[self.states[ticker]['eq']].price)
        choices = [x for x in contracts if x.expiry == t['expiry'] and x.right == old.right
                   and self.liquid_contract(x) and 0.16 <= abs(float(x.greeks.delta)) <= 0.20
                   and (float(p.strike) < float(x.strike) < min(spot, float(c.strike)) if side == 'put'
                        else max(spot, float(p.strike)) < float(x.strike) < float(c.strike))
                   and float(x.bid_price) - float(old.ask_price) >= 0.05]
        if not choices:
            self.counts['roll_no_candidate'] += 1
            return
        new = min(choices, key=lambda x: abs(abs(float(x.greeks.delta)) - 0.18))
        before = t['cash']
        self.execute(ticker, [Leg.create(old.symbol, 1), Leg.create(new.symbol, -1)], 'ROLL',
            on_filled=lambda: self.finish_roll(ticker, side, old, new, before))

    def finish_roll(self, ticker, side, old, new, before):
        t = self.positions[ticker]
        t[side] = new.symbol
        t['rolls'] += 1
        self.counts['rolls'] += 1
        self.log('ROLL ' + json.dumps(dict(ticker=ticker, date=str(self.time.date()),
            side=side, old=float(old.strike), new=float(new.strike), credit=t['cash']-before)))

    def execute(self, ticker, legs, reason, on_filled=None, quantity=1, on_rejected=None):
        if ticker in self.pending_combos:
            raise RuntimeError('Overlapping combo execution: ' + ticker)
        tag = ticker + ':' + reason
        if reason == 'OPEN' and self.positions[ticker].get('entry_metadata'):
            tag += ';' + self.positions[ticker]['entry_metadata']
        tickets = self.combo_market_order(legs, quantity, asynchronous=False, tag=tag)
        terminal_rejection = (len(tickets) == 2 and
            all(t.status in (OrderStatus.INVALID, OrderStatus.CANCELED) for t in tickets) and
            all(float(t.quantity_filled) == 0 for t in tickets))
        if terminal_rejection and on_rejected:
            on_rejected()
            return
        if len(tickets) != 2 or (not on_rejected and
                any(t.status in (OrderStatus.INVALID, OrderStatus.CANCELED) for t in tickets)):
            raise RuntimeError('Incomplete combo execution: ' + ticker + ':' + reason)
        if any(t.status != OrderStatus.FILLED for t in tickets):
            self.pending_combos[ticker] = dict(tickets=tickets, reason=reason,
                submitted=self.time, on_filled=on_filled, on_rejected=on_rejected)
            self.counts['pending_combo_submitted'] += 1
            return
        self.record_combo_fills(ticker, tickets)
        if on_filled:
            on_filled()

    def execute_sequential_close(self, ticker, symbols, reason, quantity, on_filled=None):
        """Buy back both actual shorts with ordinary broker-checked market orders.

        Futures-option combo group margin can charge closing premium as new
        buying power. Single-security closes use LEAN's normal reducing-order
        check. Never alter a margin model or submit the next leg before a fill.
        """
        if ticker in self.pending_combos or len(set(symbols)) != 2 or quantity <= 0:
            raise RuntimeError('Invalid or overlapping sequential close: ' + ticker)
        if any(float(self.securities[s].holdings.quantity) != -quantity for s in symbols):
            raise RuntimeError('Closing quantity differs from actual short holdings: ' + ticker)
        self.counts['sequential_closes_submitted'] += 1
        pair = self.counts['sequential_closes_submitted']
        # Close the larger premium liability first. Both native orders remain
        # visible; the tag joins them only for cycle accounting, never as a fill.
        symbols = sorted(symbols, key=lambda s: float(self.securities[s].price), reverse=True)
        self.pending_combos[ticker] = dict(sequential_close=True, tickets=[], remaining=list(symbols),
            reason=reason, quantity=quantity, submitted=self.time, on_filled=on_filled,
            tag=ticker+':'+reason+';execution=sequential_close;close_pair='+str(pair))
        self.advance_sequential_close(ticker)

    def advance_sequential_close(self, ticker):
        pending = self.pending_combos[ticker]
        while True:
            tickets = pending['tickets']
            if self.time-pending['submitted'] > timedelta(minutes=5):
                raise RuntimeError('Sequential close exceeded five minutes: ' + ticker)
            if tickets:
                last = tickets[-1]
                if last.status in (OrderStatus.INVALID, OrderStatus.CANCELED):
                    raise RuntimeError('Sequential closing order rejected: ' + ticker)
                if last.status != OrderStatus.FILLED:
                    return
                if float(last.quantity_filled) != pending['quantity']:
                    raise RuntimeError('Sequential close filled wrong quantity: ' + ticker)
            if not pending['remaining']:
                self.record_combo_fills(ticker, tickets)
                del self.pending_combos[ticker]
                self.counts['sequential_closes_completed'] += 1
                if pending['on_filled']:
                    pending['on_filled']()
                if self.active_equity and self.active_equity[-1][0] == str(self.time.date()):
                    value = float(self.portfolio.total_portfolio_value)
                    self.active_equity[-1] = (str(self.time.date()), value)
                    self.plot('Trading period', 'Equity', value)
                return
            symbol = pending['remaining'].pop(0)
            if float(self.securities[symbol].holdings.quantity) != -pending['quantity']:
                raise RuntimeError('Holdings changed during sequential close: ' + ticker)
            tickets.append(self.market_order(symbol, pending['quantity'], asynchronous=False,
                tag=pending['tag']))

    def process_pending_combos(self):
        for ticker, pending in list(self.pending_combos.items()):
            if pending.get('sequential_close'):
                self.advance_sequential_close(ticker)
                continue
            tickets = pending['tickets']
            delay = self.time - pending['submitted']
            if (pending.get('on_rejected') and
                    all(t.status in (OrderStatus.INVALID, OrderStatus.CANCELED) for t in tickets) and
                    all(float(t.quantity_filled) == 0 for t in tickets)):
                del self.pending_combos[ticker]
                pending['on_rejected']()
                continue
            if (delay > timedelta(minutes=5) or
                    any(t.status in (OrderStatus.INVALID, OrderStatus.CANCELED) for t in tickets)):
                details = []
                for ticket in tickets:
                    security = self.securities[ticket.symbol]
                    datum = security.get_last_data()
                    details.append(dict(symbol=str(ticket.symbol), status=str(ticket.status),
                        filled=float(ticket.quantity_filled), tradable=bool(security.is_tradable),
                        has_data=bool(security.has_data), local_time=str(security.local_time),
                        data_time=str(datum.end_time) if datum else None,
                        fill_forward=bool(datum.is_fill_forward) if datum else None))
                    # Query only past bars after the run is already invalid.
                    # These observations diagnose data gaps; never use them as fills.
                    if self.CONFIG.get('diagnose_unfilled', False):
                        self.diagnose_unfilled_contract(ticket.symbol)
                raise RuntimeError('Unresolved combo execution: ' + ticker + ':' + pending['reason']
                    + ' ' + json.dumps(details))
            if any(t.status != OrderStatus.FILLED for t in tickets):
                continue
            self.record_combo_fills(ticker, tickets)
            del self.pending_combos[ticker]
            self.counts['pending_combo_completed'] += 1
            self.counts['pending_combo_max_delay_seconds'] = max(
                self.counts['pending_combo_max_delay_seconds'], int(delay.total_seconds()))
            if pending['on_filled']:
                pending['on_filled']()
            # Keep the day's final snapshot consistent with confirmed cash and
            # fees, including a delayed final-day exit.
            if self.active_equity and self.active_equity[-1][0] == str(self.time.date()):
                value = float(self.portfolio.total_portfolio_value)
                self.active_equity[-1] = (str(self.time.date()), value)
                self.plot('Trading period', 'Equity', value)

    def record_combo_fills(self, ticker, tickets):
        trade = self.positions[ticker]
        for ticket in tickets:
            security = self.securities[ticket.symbol]
            multiplier = float(security.symbol_properties.contract_multiplier)
            trade['cash'] -= float(ticket.quantity_filled) * float(ticket.average_fill_price) * multiplier
            for event in ticket.order_events:
                trade['fees'] += float(event.order_fee.value.amount)

    def on_assignment_order_event(self, event):
        self.counts['assignments'] += 1
        for t in self.positions.values():
            if event.symbol in [t['put'], t['call']]:
                t['assigned'] = True

    def on_end_of_algorithm(self):
        self.process_pending_combos()
        if self.pending_combos:
            raise RuntimeError('Unresolved combo orders at end of backtest')
        for ticker,state in self.states.items():
            for key in ('first_chain','first_valid_iv','first_ivr_ready'):
                self.set_runtime_statistic(key+'_'+ticker,state.get(key,'none'))
            decision_total = sum(sum(counts.values()) for (symbol, year), counts in self.entry_decisions.items()
                                 if symbol == ticker)
            if decision_total != len(self.active_equity):
                raise RuntimeError('Entry decision coverage does not match daily snapshots: ' + ticker)
        for (ticker, year), counts in sorted(self.entry_decisions.items()):
            coverage = {kind: self.counts[f'{kind}_{ticker}_{year}'] for kind in
                        ('chain_days', 'fresh_chain_days', 'no_fresh_chain_days', 'valid_iv_days', 'ivr_ready_days')}
            self.log('ENTRY_DECISIONS ' + json.dumps(dict(ticker=ticker, year=year,
                counts=dict(counts), coverage=coverage)))
        for name, number in sorted(self.counts.items()):
            # Prior QC responses omitted annual coverage counters. Preserve
            # those in compact logs and publish aggregate runtime statistics.
            if name.startswith(('chain_days_', 'fresh_chain_days_', 'no_fresh_chain_days_',
                                'valid_iv_days_', 'ivr_ready_days_')):
                continue
            self.set_runtime_statistic(name, str(number))
        self.set_runtime_statistic('entry_policy', 'continuous' if self.iv_min is None else 'high_ivr')
        self.set_runtime_statistic('iv_min', str(self.iv_min))
        self.set_runtime_statistic('open_cycles', str(len(self.positions)))
        self.set_runtime_statistic('closed_cycles', str(len(self.closed_pnl)))
        self.set_runtime_statistic('cycle_net_pnl', f'{sum(self.closed_pnl):.2f}')
        wins = sum(x > 0 for x in self.closed_pnl)
        self.set_runtime_statistic('cycle_win_rate', f'{wins / len(self.closed_pnl):.4f}' if self.closed_pnl else 'n/a')
        self.set_runtime_statistic('min_iv_samples', str(min(len(s['iv']) for s in self.states.values())))
        self.set_runtime_statistic('rolls_enabled', str(self.allow_rolls))
        self.set_runtime_statistic('stop_multiple', str(self.stop_multiple))
        self.set_runtime_statistic('min_iv_rv', str(self.min_iv_rv))
        self.set_runtime_statistic('max_trend_z', str(self.max_trend_z))
        self.set_runtime_statistic('first_entry', self.first_entry or 'none')
        self.set_runtime_statistic('initial_cash', str(self.initial_cash))
        self.set_runtime_statistic('active_snapshots', str(len(self.active_equity)))
        if self.active_equity:
            peak, mdd = self.initial_cash, 0.0
            for _, value in self.active_equity:
                peak = max(peak, value)
                mdd = max(mdd, 1-value/peak)
            value = self.active_equity[-1][1]
            years = (self.end - self.trade_start).days / 365.25
            self.set_runtime_statistic('active_return', f'{value/self.initial_cash-1:.6f}')
            self.set_runtime_statistic('active_cagr', f'{(value/self.initial_cash)**(1/years)-1:.6f}')
            self.set_runtime_statistic('active_daily_mdd', f'{mdd:.6f}')
            returns = []
            previous = self.initial_cash
            for _, nav in self.active_equity:
                returns.append(nav / previous - 1)
                previous = nav
            mean = sum(returns) / len(returns)
            variance = sum((r-mean)**2 for r in returns) / len(returns)
            self.set_runtime_statistic('active_sharpe_zero_rf',
                f'{mean / math.sqrt(variance) * math.sqrt(252):.6f}' if variance > 0 else 'n/a')
            if not self.counts['assignments']:
                difference = value - self.initial_cash - sum(self.closed_pnl)
                self.set_runtime_statistic('pnl_reconciliation_difference', f'{difference:.4f}')
                if not self.positions and abs(difference) > 0.05:
                    raise RuntimeError('Cycle P&L does not reconcile with account equity')
        if self.counts['entries'] == 0 and not self.CONFIG.get('allow_no_trades', False):
            raise RuntimeError('No strangles entered: this is not a valid strategy test')
        if self.positions:
            raise RuntimeError('Unclosed cycles at end: inspect quotes and assignment handling')
        if self.portfolio.invested:
            raise RuntimeError('Residual holdings after final cycle exit')

    def diagnose_unfilled_contract(self, symbol):
        security = self.securities[symbol]
        try:
            days = {}
            for bar in self.history[QuoteBar](symbol, timedelta(days=5), Resolution.MINUTE):
                day = str(bar.end_time.date())
                item = days.setdefault(day, dict(bars=0, actual_bars=0, first=str(bar.end_time), last=None))
                item['bars'] += 1
                item['actual_bars'] += int(not bar.is_fill_forward)
                item['last'] = str(bar.end_time)
            self.log('UNFILLED_DATA ' + json.dumps(dict(symbol=str(symbol),
                subscription_types=[str(config.type) for config in security.subscriptions],
                invested=bool(security.invested), history=days)))
        except Exception as exc:
            self.log('UNFILLED_DATA_ERROR ' + str(exc))
