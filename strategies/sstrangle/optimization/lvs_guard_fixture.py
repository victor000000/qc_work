"""Prospective native voluntary-guard fixture, NOT queued or cloud validated.
Original parent supplies actual subscriptions/opening/event and holdings accounting.
The guarded branch starts at the known Aug19 training observation; no prior-path
or full-strategy performance equivalence is claimed. No limit orders are used.
"""
from AlgorithmImports import *
from collections import Counter
from datetime import date,datetime,time,timedelta
import json
from lvs_original_fixture import LVSExitRegression
from guarded_strategy import ResearchShortStrangle as Guarded


class LVSGuardRegression(LVSExitRegression):
    CONFIG = {}
    voluntary_quote_ready = Guarded.voluntary_quote_ready
    process_exit_requests = Guarded.process_exit_requests
    intraday_risk_exits = Guarded.intraday_risk_exits
    close_fees = Guarded.close_fees
    order_fees = Guarded.order_fees

    def initialize(self):
        super().initialize()
        self.guard_key='LVS_FIXTURE'
        self.states={self.guard_key:dict(future=False)}
        self.positions={};self.pending_combos={};self.exit_requests={};self.counts=Counter()
        self.last_risk_check=None;self.insolvency=None
        self.time_exit_dte=28;self.end=date(2015,9,1)
        self.guard_context_ready=False;self.guard_first_deferred=False
        self.close_reason_observed=None;self.close_filled_callback=None

    def good_quote(self,value):
        # Parent accepts a Symbol; the actual research risk methods pass Security.
        return super().good_quote(value.symbol if hasattr(value,'cache') else value)

    def ensure_guard_context(self):
        if self.guard_context_ready:return
        self.check_open_fills();self.reconcile()
        if any(float(self.portfolio[s].quantity)!=-2 for s in self.contracts.values()):
            raise RuntimeError('Guard context requires the two actual held native shorts')
        self.positions[self.guard_key]=dict(put=self.contracts['put'],call=self.contracts['call'],
            expiry=date(2015,9,18),quantity=2,multiplier=100.,cash=246.,fees=2.6,initial=246.)
        self.guard_context_ready=True

    def execute(self,key,legs,reason,on_filled=None):
        if key!=self.guard_key or self.pending_combos or self.state!='HELD':
            raise RuntimeError('Unexpected or overlapping guarded fixture execution')
        if reason not in ('STOP','PROFIT','TIME'):raise RuntimeError('Unexpected fixture exit reason')
        if any(float(self.portfolio[s].quantity)!=-2 for s in self.contracts.values()):
            raise RuntimeError('Native quantities changed before actual guarded close')
        self.pending_bind=True
        try:
            self.bind(self.combo_market_order(legs,2,asynchronous=False,
                tag='LVS_FIXTURE:'+reason+';attempt=guard_market;multiplier=100'),'CLOSE')
        finally:self.pending_bind=False
        self.pending_combos[key]=True;self.close_filled_callback=on_filled
        self.close_reason_observed=reason;self.state='GUARD_MARKET'
        self.market_deadline=self.time+timedelta(minutes=5)

    def finish_close(self,key,reason):
        if not self.phase_complete():raise RuntimeError('Logical close before native fills')
        self.positions.pop(key);self.pending_combos.pop(key)
        self.counts[reason]+=1

    def settle_guard_orders(self):
        if self.state!='GUARD_MARKET':return
        if any(t.status in (OrderStatus.INVALID,OrderStatus.CANCELED) for t in self.phase_tickets):
            raise RuntimeError('Actual guarded market close rejected; exposure retained')
        if self.phase_complete():
            self.reconcile()
            if self.close_filled_callback:self.close_filled_callback()
            self.finish_actual()
        elif self.time>=self.market_deadline:
            raise RuntimeError('Actual guarded close not complete within five minutes')

    def on_data(self,data):
        if not self.CONFIG.get('voluntary_guard',False):return super().on_data(data)
        if self.pending_bind:return
        if self.failure_note:raise RuntimeError(self.failure_note)
        self.reconcile()
        if self.done:return
        if self.state in ('WAIT_OPEN','OPEN_PENDING'):
            super().on_data(data);return
        if self.state=='GUARD_MARKET':self.settle_guard_orders();return
        if self.state!='HELD':raise RuntimeError('Unexpected guarded fixture state')
        if self.time.date()<date(2015,8,19):return
        self.ensure_guard_context()
        if self.triggered_at is None:
            if self.time!=datetime(2015,8,19,9,31):raise RuntimeError('Original training STOP clock not reproduced')
            if not all(self.good_quote(s) for s in self.contracts.values()):raise RuntimeError('Original native quote gate not reproduced')
            actual_cost=sum(float(self.securities[s].ask_price) for s in self.contracts.values())*200
            if 246-2.6-2.6-actual_cost>-246:raise RuntimeError('Original ask-based STOP condition absent')
            self.triggered_at=self.time
            before=set(self.tickets);self.intraday_risk_exits()
            if set(self.tickets)!=before or self.pending_combos or self.exit_requests:
                raise RuntimeError('Guard did not defer original wide-quote voluntary submission')
            if not self.counts['research_risk_quote_guard_deferred']:
                raise RuntimeError('Missing actual risk-layer guard deferral')
            if any(float(self.portfolio[s].quantity)!=-2 for s in self.contracts.values()):
                raise RuntimeError('Position lost during unsubmitted guard deferral')
            self.guard_first_deferred=True
            self.set_runtime_statistic('guard_first_deferred','1')
            self.set_runtime_statistic('guard_original_holdings_retained','1')
            return
        self.process_exit_requests();self.intraday_risk_exits()
        if self.state=='HELD' and (date(2015,9,18)-self.time.date()).days<=self.time_exit_dte and self.time.time()>=time(12):
            if all(self.securities[s].exchange.exchange_open for s in self.contracts.values()):
                self.exit_requests.setdefault(self.guard_key,dict(reason='TIME',day=self.time.date()))
                self.process_exit_requests()
        self.settle_guard_orders()

    def receipt(self,note):
        result=super().receipt(note)
        if self.CONFIG.get('voluntary_guard',False):
            result.update(variant='voluntary_spread_guard_no_limits',guard_first_deferred=self.guard_first_deferred,
                close_reason_observed=self.close_reason_observed,guard_counts=dict(self.counts),
                scope='Isolated native held-position continuation from Aug19; no earlier alternative-path claim')
        return result

    def finish_actual(self):
        if not self.CONFIG.get('voluntary_guard',False):return super().finish_actual()
        self.reconcile()
        if self.transactions.get_open_orders() or not self.all_terminal(self.tickets.values()):
            raise RuntimeError('Unresolved native orders at guarded completion')
        if self.positions or self.pending_combos or self.exit_requests or self.portfolio.invested:
            raise RuntimeError('Native/logical exposure remains at guarded completion')
        if len(self.open_ids)!=2 or len(self.close_ids)!=2 or not self.guard_first_deferred:
            raise RuntimeError('Guarded actual opening/deferral/closing path incomplete')
        result=self.receipt('Actual guarded completion')
        if abs(result['equity']-(self.initial_cash+result['actual_cashflow']-result['actual_fees']))>.005:
            raise RuntimeError('Actual guarded account/fees/cashflow mismatch')
        self.done=True;self.state='DONE'
        self.set_runtime_statistic('guard_actual_exit_reason',self.close_reason_observed)
        self.set_runtime_statistic('guard_actual_closed','1')
        self.log('LVS_EXIT_RECEIPT '+json.dumps(self.receipt('Genuine guarded native execution')))
