"""Isolated, unintegrated limit-exit lifecycle prototype; creates NO QC orders.
Adapter must supply reconciled genuine native tickets/events and portfolio holdings.
Neither a fill model nor strategy implementation. Native QC fixture still required.
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR

TERMINAL={'FILLED','CANCELED','INVALID'}
LIVE={'NEW','SUBMITTED','PARTIALLY_FILLED','CANCEL_PENDING','UPDATE_SUBMITTED'}

@dataclass(frozen=True)
class Ticket:
    order_id:int
    symbol:str
    quantity:int
    filled:int
    status:str


def quote_limit(bid,ask,tick,fraction=Decimal('.25')):
    """Research buy limit = midpoint +25% spread, floored to native tick <=ask.
    Price is an order instruction only; it never becomes an assumed fill.
    """
    bid,ask,tick=map(lambda x:Decimal(str(x)),(bid,ask,tick))
    if not all(x.is_finite() for x in (bid,ask,tick)) or bid<=0 or ask<bid or tick<=0:
        raise ValueError('Invalid genuine fresh quote/tick')
    fraction=Decimal(str(fraction))
    if not 0<=fraction<=Decimal('.5'):raise ValueError('Invalid price fraction')
    p=((bid+ask)/2+fraction*(ask-bid))/tick
    return p.to_integral_value(rounding=ROUND_FLOOR)*tick


class LimitExitLifecycle:
    """Two native equity option LIMIT buys, then cancel-ack barrier and residual markets.
    All initial checks are preconditions for a future QC adapter, not inferred here.
    State machine does not suppress errors or mutate economic holdings/accounting.
    """
    def __init__(self,symbols,quantity,reason,start,*,future=False,dte=35,
                 timeout=60,cancel_timeout=60):
        if (future or reason not in {'PROFIT','STOP'} or dte<=21 or len(set(symbols))!=2
            or not isinstance(quantity,int) or quantity<=0 or not 0<timeout<=60
            or not 0<cancel_timeout<=60):raise ValueError('Ineligible voluntary equity exit')
        self.symbols=tuple(symbols);self.quantity=quantity;self.reason=reason
        self.start=start;self.last_now=start;self.timeout=timeout;self.cancel_timeout=cancel_timeout
        self.state='AWAIT_LIMIT_BIND';self.original={};self.orders={};self.previous={}
        self.cancel_started=None;self.urgent_reason=None

    def bind_limit(self,tickets):
        if self.state!='AWAIT_LIMIT_BIND':raise RuntimeError('Duplicate limit submission')
        ts=list(tickets)
        if len(ts)!=2 or {t.symbol for t in ts}!=set(self.symbols):raise RuntimeError('Wrong native pair')
        if any(t.quantity!=self.quantity for t in ts):raise RuntimeError('Wrong buyback quantity')
        self._bind(ts);self.original={t.order_id:t for t in ts};self.state='LIMIT'

    def _bind(self,ts):
        if len({t.order_id for t in ts})!=len(ts):raise RuntimeError('Duplicate native order ID')
        if any(t.order_id in self.orders for t in ts):raise RuntimeError('Reused native order ID')
        for t in ts:self.orders[t.order_id]=t

    def bind_market(self,tickets):
        if self.state!='AWAIT_MARKET_BIND':raise RuntimeError('No authorized fallback')
        ts=list(tickets)
        if {t.symbol:t.quantity for t in ts}!=self.residual or len(ts)!=len(self.residual):
            raise RuntimeError('Wrong actual residual fallback')
        self._bind(ts);self.state='MARKET'

    def advance(self,now,tickets,holdings,*,native_open_ids=(),urgent_reason=None):
        if self.state in {'AWAIT_LIMIT_BIND','AWAIT_MARKET_BIND'}:raise RuntimeError('Native tickets not bound')
        if now<self.last_now:raise RuntimeError('Nonmonotonic clock')
        self.last_now=now
        ts=list(tickets)
        if len({t.order_id for t in ts})!=len(ts) or {t.order_id for t in ts}!=set(self.orders):
            raise RuntimeError('Incomplete/duplicate native ticket snapshot')
        received={s:0 for s in self.symbols}
        for t in ts:
            old=self.orders[t.order_id]
            if t.symbol!=old.symbol or t.quantity!=old.quantity or t.symbol not in received:
                raise RuntimeError('Native identity/quantity changed')
            if t.status not in TERMINAL|LIVE or not 0<=t.filled<=t.quantity or int(t.filled)!=t.filled:
                raise RuntimeError('Invalid fill/status')
            prev=self.previous.get(t.order_id)
            if prev and (t.filled<prev.filled or (prev.status in TERMINAL and t!=prev)):
                raise RuntimeError('Terminal/monotonic fill race requires native diagnosis')
            if t.status=='FILLED' and t.filled!=t.quantity:raise RuntimeError('False filled status')
            self.previous[t.order_id]=t;received[t.symbol]+=t.filled
        if any(received[s]>self.quantity for s in self.symbols):raise RuntimeError('Overclose')
        if set(holdings)!=set(self.symbols) or any(holdings[s]!=-self.quantity+received[s] for s in self.symbols):
            raise RuntimeError('Portfolio differs from genuine cumulative ticket fills')
        expected_open={t.order_id for t in ts if t.status not in TERMINAL}
        if set(native_open_ids)!=expected_open:raise RuntimeError('Native open-order barrier inconsistent')
        self.orders={t.order_id:t for t in ts}
        if all(t.status in TERMINAL for t in ts) and all(v==0 for v in holdings.values()):
            if self.state=='DONE':return []
            self.state='DONE';return [('COMPLETE_ACTUAL_FILL_AUDIT',)]
        if self.state=='DONE':raise RuntimeError('Completed holdings changed')
        if urgent_reason:
            if urgent_reason not in {'TIME','MARGIN','SPLIT','END'}:raise ValueError('Unknown emergency')
            self.urgent_reason=urgent_reason
        if self.state=='LIMIT':
            if self.urgent_reason or now-self.start>=self.timeout or any(t.status=='INVALID' for t in ts):
                self.state='CANCELING';self.cancel_started=now
                ids=tuple(sorted(expected_open))
                if ids:return [('CANCEL_NATIVE_TICKETS',ids)]
            else:return []
        if self.state=='CANCELING':
            if expected_open:
                if now-self.cancel_started>=self.cancel_timeout:raise RuntimeError('Cancel not definitive; cannot fallback')
                return []
            self.residual={s:-holdings[s] for s in self.symbols if holdings[s]<0}
            if not self.residual:raise RuntimeError('Inconsistent flat barrier')
            self.state='AWAIT_MARKET_BIND'
            return [('SUBMIT_DEFAULT_MARGIN_MARKET_RESIDUAL',dict(self.residual),self.urgent_reason or self.reason)]
        if self.state=='MARKET':
            if any(t.status in {'CANCELED','INVALID'} and t.filled<t.quantity for t in ts if t.order_id not in self.original):
                raise RuntimeError('Fallback rejection/partial cancellation remains real unresolved exposure')
            return []
        raise RuntimeError('Unknown lifecycle state')
