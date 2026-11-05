"""Native ZC held-cycle control versus prospective guard/retry execution.

Entry and scheduled replacement identities replay a known training cycle. This
is an execution experiment, not a newly screened strategy or performance test.
Every fill uses ordinary native broker-checked orders; there are no price setters.
"""
from AlgorithmImports import *
from collections import Counter
from datetime import date, datetime, time, timedelta
import json
from guarded_control_strategy import ResearchShortStrangle as Control
from cross_asset_candidate_strategy import ResearchShortStrangle as Candidate
from rules import close_reason


class ZCRiskGuardRegression(Control):
    CONFIG = {}

    def initialize(self):
        self.set_start_date(2016, 6, 10)
        self.set_end_date(2016, 7, 5)
        self.set_time_zone('America/New_York')
        self.initial_cash = 56740.79
        self.set_cash(self.initial_cash)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.spy = self.add_equity('SPY', Resolution.MINUTE).symbol
        self.securities[self.spy].set_data_normalization_mode(DataNormalizationMode.RAW)
        self.future = Symbol(SecurityIdentifier.Parse('ZC WDW91DY3IAZP'), 'ZC14U16')
        self.key = 'FUT_ZC'
        self.states = {self.key: dict(ticker='ZC', future=True, eq=self.future)}
        self.positions, self.pending_combos, self.exit_requests = {}, {}, {}
        self.counts, self.annual = Counter(), {}
        self.subscribed_underlyings, self.subscribed_options = set(), set()
        self.active_equity, self.closed_pnl = [], []
        self.insolvency, self.last_risk_check, self.last_research_exit_day = None, None, None
        self.time_exit_dte = 21
        self.end = date(2016, 7, 5)
        self.opened, self.managed_days, self.done_rolls = False, set(), set()
        native = [(True, 3.9, '30BJ31SCN55FS', 'OZC   160722P00003900'),
                  (False, 4.85, 'WCF2WEF76GX4', 'OZC   160722C00004850'),
                  (False, 4.55, 'WCF2WEA8KFFS', 'OZC   160722C00004550'),
                  (False, 4.45, 'WCF2WE8L12Y0', 'OZC   160722C00004450'),
                  (False, 4.35, 'WCF2WE6XHQG8', 'OZC   160722C00004350')]
        self.contracts = {(put, strike): Symbol(SecurityIdentifier.Parse(
            'OZC ' + encoded + '|ZC WDW91DY3IAZP'), alias)
            for put, strike, encoded, alias in native}
        self.rolls = {date(2016, 6, 22): 4.55, date(2016, 6, 23): 4.45,
                      date(2016, 6, 27): 4.35}
        self.schedule.on(self.date_rules.every_day(), self.time_rules.at(11, 55), self.prepare_fixture)

    def prospective(self):
        return self.CONFIG['cross_asset_voluntary_guard']

    def voluntary_quote_ready(self, key):
        method = Candidate.voluntary_quote_ready if self.prospective() else Control.voluntary_quote_ready
        if self.prospective() and self.states[key]['future']:
            self.counts['fixture_future_guard_checks'] += 1
        ready = method(self, key)
        if not ready and self.states[key]['future']:
            self.counts['fixture_future_quote_deferrals'] += 1
        return ready

    def process_exit_requests(self):
        method = Candidate.process_exit_requests if self.prospective() else Control.process_exit_requests
        return method(self)

    def intraday_risk_exits(self):
        method = Candidate.intraday_risk_exits if self.prospective() else Control.intraday_risk_exits
        return method(self)

    def prepare_fixture(self):
        self.cleanup()
        today = self.time.date()
        needed = []
        if today == date(2016, 6, 13):
            needed = [self.contracts[(True, 3.9)], self.contracts[(False, 4.85)]]
        if today in self.rolls and self.positions:
            needed.append(self.contracts[(False, self.rolls[today])])
        if needed:
            self.subscribe(self.future, [dict(symbol=s) for s in needed], True)

    def on_data(self, data):
        self.process_pending_combos()
        self.process_exit_requests()
        self.intraday_risk_exits()
        today = self.time.date()
        if self.time.time() < time(12) or today in self.managed_days:
            return
        self.managed_days.add(today)
        if today == date(2016, 6, 13) and not self.opened:
            put, call = self.contracts[(True, 3.9)], self.contracts[(False, 4.85)]
            if not all(self.good_quote(self.securities[s]) for s in (put, call)):
                raise RuntimeError('Original ZC opening lacked actual fresh quotes')
            if any(float(self.securities[s].symbol_properties.contract_multiplier) != 5000 for s in (put, call)):
                raise RuntimeError('Native ZC multiplier differs from genuine source orders')
            self.opened = True
            self.positions[self.key] = dict(put=put, call=call, expiry=date(2016, 7, 22),
                quantity=1, multiplier=5000., cash=0., fees=0., initial=0., rolls=0,
                opened=str(today), entry_metadata='multiplier=5000;quantity=1;engineering_probe=True;entry_replay=True')
            def filled():
                self.positions[self.key]['initial'] = self.positions[self.key]['cash']
                self.counts['fixture_open_completed'] += 1
            self.execute(self.key, [Leg.create(put, -1), Leg.create(call, -1)], 'OPEN', on_filled=filled)
        elif self.key in self.positions and self.key not in self.pending_combos:
            trade = self.positions[self.key]
            securities = [self.securities[trade[side]] for side in ('put', 'call')]
            if all(s.exchange.exchange_open for s in securities):
                dte = (trade['expiry'] - today).days
                reason = 'END' if today >= self.end else 'TIME' if dte <= 21 else None
                if reason is None and self.voluntary_quote_ready(self.key):
                    cost = sum(float(s.ask_price) for s in securities) * trade['multiplier'] * trade['quantity']
                    reason = close_reason(trade['cash'], trade['fees'] + self.close_fees(trade),
                                          cost, trade['initial'], dte, stop_multiple=self.CONFIG['stop_multiple'])
                if reason:
                    self.exit_requests[self.key] = dict(reason=reason, day=today)
                elif today in self.rolls and all(self.good_quote(s) for s in securities):
                    self.submit_roll(self.key, 'call', dict(symbol=self.contracts[(False, self.rolls[today])]))
                    self.done_rolls.add(today)
                self.process_exit_requests()
        self.active_equity.append((str(today), float(self.portfolio.total_portfolio_value)))
        self.plot('Trading period', 'Equity', self.active_equity[-1][1])

    def on_end_of_algorithm(self):
        self.process_pending_combos()
        if (self.positions or self.pending_combos or self.exit_requests or self.portfolio.invested
                or list(self.transactions.get_open_orders())):
            raise RuntimeError('ZC experiment retains actual/logical exposure')
        if self.counts['fixture_open_completed'] != 1 or len(self.closed_pnl) != 1 or self.counts['MARGIN']:
            raise RuntimeError('ZC experiment did not finish one genuine cycle without margin liquidation')
        final = float(self.portfolio.total_portfolio_value)
        if abs(final - self.initial_cash - sum(self.closed_pnl)) > .005:
            raise RuntimeError('Actual ZC cash/fee/cycle account mismatch')
        if not self.prospective() and (len(self.done_rolls) != 3 or self.counts['STOP'] != 1):
            raise RuntimeError('ZC control did not retain original three rolls and stop')
        for key, value in self.counts.items():
            self.set_runtime_statistic(key, str(value))
        self.set_runtime_statistic('fixture_replayed_entry', '1')
        self.set_runtime_statistic('fixture_synthetic_fills', '0')
        self.set_runtime_statistic('fixture_calmar_claim', '0')
        self.set_runtime_statistic('fixture_cycle_net', str(sum(self.closed_pnl)))
        self.set_runtime_statistic('fixture_initial_cash', str(self.initial_cash))
        self.set_runtime_statistic('fixture_guard_and_retry', str(int(self.prospective())))
