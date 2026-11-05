"""Isolated default-margin ownership/cancellation adapter experiment. NO QC imports.
Not production-ready: native atomic cancellation/regeneration has not been proved.
"""
from dataclasses import dataclass

TERMINAL={'FILLED','CANCELED','INVALID'}

@dataclass(frozen=True)
class NativeTicket:
    order_id:int
    sid:str
    requested:int
    filled:int
    status:str

@dataclass(frozen=True)
class MarginRequest:
    sid:str
    quantity:int
    request_id:str

@dataclass(frozen=True)
class Snapshot:
    epoch:int
    holdings:dict
    tickets:tuple
    native_open_ids:frozenset
    event_fill_totals:dict
    margin_remaining:float

@dataclass(frozen=True)
class CallbackDecision:
    returned_requests:object
    status:str
    local_barrier_passed:bool
    reason:str


class MarginOwnershipCoordinator:
    """Single tracked pair; real engine adapter still required.
    adapter contract:
      snapshot() returns coherent native holdings/tickets/events/open IDs epoch.
      cancel_native(id) only REQUESTS cancellation (never counts as acknowledged).
      regenerate_default_margin_requests() calls SAME configured default model,
          not a fabricated quantity adjustment or custom margin/fill model.
    These methods are mocked locally; no runtime deployment claim follows.
    """
    def __init__(self,initial_shorts,limit_ids):
        if len(initial_shorts)!=2 or any(q<=0 or int(q)!=q for q in initial_shorts.values()):
            raise ValueError('Exactly two initial whole-lot shorts required')
        self.initial=dict(initial_shorts);self.limit_ids=frozenset(limit_ids)
        if len(self.limit_ids)!=2:raise ValueError('Two native voluntary limit IDs required')
        self.state='VOLUNTARY';self.cancel_sent=set();self.failure=None
        self.broker_order_ids=set();self.last_epoch=None

    def _check(self,s):
        if set(s.holdings)!=set(self.initial):raise RuntimeError('Unknown native holding scope')
        ts={t.order_id:t for t in s.tickets}
        if len(ts)!=len(s.tickets):raise RuntimeError('Duplicate native ticket ID')
        if not self.limit_ids<=set(ts):raise RuntimeError('Original native limit absent')
        received={sid:0 for sid in self.initial}
        for t in s.tickets:
            if (t.sid not in self.initial or t.requested<=0 or int(t.requested)!=t.requested
                or int(t.filled)!=t.filled or not 0<=t.filled<=t.requested):
                raise RuntimeError('Invalid native identity/fill')
            if t.status=='FILLED' and t.filled!=t.requested:raise RuntimeError('False terminal fill')
            if s.event_fill_totals.get(t.order_id)!=t.filled:raise RuntimeError('Native ticket/event barrier not reconciled')
            received[t.sid]+=t.filled
        if any(s.holdings[sid]!=-q+received[sid] for sid,q in self.initial.items()):
            raise RuntimeError('Native portfolio differs from actual event ledger')
        if any(q>0 for q in s.holdings.values()):raise RuntimeError('Actual overclose retained, never hidden')
        expected={t.order_id for t in s.tickets if t.status not in TERMINAL}
        if s.native_open_ids!=expected:raise RuntimeError('Native open-order barrier inconsistent')
        return ts

    def _invalidate(self,original,reason):
        self.state='INVALID_BROKER_OWNED';self.failure=reason
        # Preserve original callback object; default model remains free to execute.
        # This is an INVALID trial, not a proof that native races cannot overclose.
        return CallbackDecision(original,self.state,False,reason)

    def on_native_margin(self,original_requests,adapter):
        if self.state=='INVALID_BROKER_OWNED':
            return CallbackDecision(original_requests,self.state,False,self.failure or 'Previously invalid native critical section')
        self.state='BROKER_OWNED' # Disables ALL voluntary/fallback submissions immediately.
        try:
            first=adapter.snapshot();ts=self._check(first)
            for i in sorted(self.limit_ids):
                if ts[i].status not in TERMINAL and i not in self.cancel_sent:
                    self.cancel_sent.add(i);adapter.cancel_native(i)
            barrier=adapter.snapshot();ts=self._check(barrier)
            if any(ts[i].status not in TERMINAL for i in self.limit_ids):
                return self._invalidate(original_requests,'Definitive native cancellation unavailable inside margin callback; default liquidation retained')
            if any(i in barrier.native_open_ids for i in self.limit_ids):
                return self._invalidate(original_requests,'Original limit still open after claimed cancellation')
            if barrier.margin_remaining>=0:
                # Official default model skips obsolete requests when its initial margin check is restored.
                # Adapter/native fixture MUST prove this check occurs at the same native state.
                return CallbackDecision(original_requests,self.state,True,'Limits terminal; default model margin-restored guard must be native-proved')
            # Default generated quantities may be stale after partial fills. Never hand-adjust them.
            regenerated=adapter.regenerate_default_margin_requests()
            after=adapter.snapshot();self._check(after)
            if after.epoch!=barrier.epoch:
                return self._invalidate(original_requests,'Native state changed during default request regeneration')
            if not regenerated:
                return self._invalidate(original_requests,'Default negative-margin regeneration returned no request; no fabricated substitute')
            request_ids=set();request_sids=set();aggregate={}
            for r in regenerated:
                if r.request_id in request_ids or r.sid in request_sids:
                    return self._invalidate(original_requests,'Duplicate regenerated native request ID or SID')
                request_ids.add(r.request_id);request_sids.add(r.sid)
                if (r.sid not in after.holdings or r.quantity<=0 or int(r.quantity)!=r.quantity
                        or r.quantity>-after.holdings[r.sid]):
                    return self._invalidate(original_requests,'Default request not reducing actual residual in tracked scope')
                aggregate[r.sid]=aggregate.get(r.sid,0)+r.quantity
            if any(qty>-after.holdings[sid] for sid,qty in aggregate.items()):
                return self._invalidate(original_requests,'Aggregate regenerated requests exceed actual native residual')
            self.last_epoch=after.epoch
            return CallbackDecision(regenerated,self.state,True,'Terminal native cancel barrier; same default model regenerated actual remaining requests; native atomicity unproved')
        except Exception as e:
            return self._invalidate(original_requests,str(e))

    def bind_actual_broker_tickets(self,order_ids):
        if self.state!='BROKER_OWNED':raise RuntimeError('Cannot accept broker fixture success after invalid critical section')
        ids=set(order_ids)
        if not ids or ids&self.limit_ids:raise RuntimeError('Broker IDs must be genuine and distinct')
        self.broker_order_ids|=ids

    def after_native_broker(self,snapshot):
        if self.state!='BROKER_OWNED':raise RuntimeError('Invalid or absent broker ownership')
        ts=self._check(snapshot)
        if not self.broker_order_ids<=set(ts):raise RuntimeError('Broker native tickets missing')
        relevant=self.limit_ids|self.broker_order_ids
        if any(ts[i].status not in TERMINAL for i in relevant) or snapshot.native_open_ids:
            return ('WAIT_NATIVE_BROKER_AND_CANCEL_BARRIER',)
        if any(ts[i].status=='INVALID' and ts[i].filled<ts[i].requested for i in self.broker_order_ids):
            self.state='INVALID_BROKER_OWNED';raise RuntimeError('Broker rejection remains real unresolved exposure')
        residual={sid:-q for sid,q in snapshot.holdings.items() if q<0}
        if residual:
            self.state='RESIDUAL_REQUIRES_NATIVE_DEFAULT_CHECKS'
            return ('REQUIRE_SEPARATE_NATIVE_DEFAULT_CHECKED_RESIDUAL_CLOSE',residual)
        self.state='COMPLETE'
        return ('COMPLETE_ACTUAL_NATIVE_EVENT_CASH_FEE_AUDIT_REQUIRED',)

    def authorize_voluntary_market_fallback(self):
        if self.state!='VOLUNTARY':raise RuntimeError('Broker owns exposure; no duplicate voluntary fallback')
        raise RuntimeError('Normal voluntary path belongs to separate coordinator and full native barrier')
