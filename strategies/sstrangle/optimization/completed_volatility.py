"""Prospective completed-session volatility features, not a strategy or price feed.

Caller must supply consecutive completed sessions for ONE native instrument and
one normalization epoch. Equity scale-factor changes require correctly rebased
history; futures delivery switches require a new native identity. This helper
never requests history, changes a quote, trades, or substitutes an IV source.
"""
from dataclasses import dataclass
from datetime import date,datetime
import math
from statistics import stdev
from collections import deque

@dataclass(frozen=True)
class CompletedPrice:
    native_id:str
    session:date
    end_time:datetime
    price:float
    normalization_epoch:str

@dataclass(frozen=True)
class VolatilityFeatures:
    closes:int
    returns:int
    realized20:float|None
    realized60:float|None
    iv_to_max_realized:float|None
    ready:bool
    reason:str

class CompletedVolatilityWindow:
    def __init__(self):
        self.points=deque(maxlen=61)
        self.identity=None
        self.epoch=None
        self.rebase_required=False

    @staticmethod
    def _validate(point,asof,decision_session):
        if not point.native_id or not point.normalization_epoch:raise ValueError('Identity/normalization provenance required')
        if not math.isfinite(point.price) or point.price<=0:raise ValueError('Positive finite close required')
        try:future=point.end_time>asof
        except TypeError as e:raise ValueError('Comparable timezone-aware source/decision clocks required') from e
        if point.end_time.tzinfo is None or asof.tzinfo is None:raise ValueError('Timezone-aware clocks required')
        if future or point.session>=decision_session:raise ValueError('Only completed prior sessions allowed')

    def observe(self,point,asof,decision_session,*,consecutive):
        if type(consecutive) is not bool:raise ValueError('Explicit exchange-calendar continuity required')
        self._validate(point,asof,decision_session)
        # A corporate scale change cannot be repaired by mixing raw old/new
        # prices. Native delivery switches and missing sessions start fresh.
        if self.points and point.native_id==self.identity and point.session<self.points[-1].session:raise ValueError('Out-of-order source cannot reset normalization')
        changed_identity=self.identity is not None and point.native_id!=self.identity
        changed_epoch=self.epoch is not None and point.normalization_epoch!=self.epoch
        if changed_identity or changed_epoch or not consecutive:
            self.points.clear()
            self.rebase_required=bool(changed_epoch and not changed_identity)
        self.identity=point.native_id;self.epoch=point.normalization_epoch
        if self.points and point.session<=self.points[-1].session:
            if point==self.points[-1]:return False
            raise ValueError('Conflicting duplicate or out-of-order completed session')
        self.points.append(point)
        # A sufficient NEW contiguous window is valid even without reseeding.
        if len(self.points)==61:self.rebase_required=False
        return True

    def replace_rebased_history(self,points,asof,decision_session,*,consecutive):
        """Atomic source-history replacement. Caller proves adjustment semantics.

        `consecutive` is a REQUIRED exchange-calendar result, not inferred from
        weekdays or supplied automatically. No missing session is manufactured.
        """
        items=list(points)
        if type(consecutive) is not bool or not consecutive or not items:raise ValueError('Consecutive actual source sessions required')
        for p in items:self._validate(p,asof,decision_session)
        if len({(p.native_id,p.normalization_epoch) for p in items})!=1:raise ValueError('Mixed identity or normalization history')
        if any(a.session>=b.session for a,b in zip(items,items[1:])):raise ValueError('History must be strictly ordered')
        # A history seed may not secretly switch the requested live identity.
        if self.identity is not None and items[-1].native_id!=self.identity:raise ValueError('Seed native identity mismatch')
        if self.epoch is not None and items[-1].normalization_epoch!=self.epoch:raise ValueError('Seed normalization epoch mismatch')
        if self.points and items[-1].session<self.points[-1].session:raise ValueError('Seed omits latest known completed session')
        self.points=deque(items[-61:],maxlen=61);self.identity=items[-1].native_id;self.epoch=items[-1].normalization_epoch
        self.rebase_required=False

    def features(self,iv,*,expected_last_session):
        n=len(self.points)
        if n<61 or self.rebase_required:return VolatilityFeatures(n,max(0,n-1),None,None,None,False,'need61consecutive_same_basis_closes')
        if self.points[-1].session!=expected_last_session:return VolatilityFeatures(n,n-1,None,None,None,False,'missing_last_completed_session')
        try:valid=not isinstance(iv,bool) and math.isfinite(iv) and iv>0
        except (TypeError,ValueError):valid=False
        if not valid:return VolatilityFeatures(n,n-1,None,None,None,False,'invalid_iv_value')
        prices=[p.price for p in self.points]
        returns=[math.log(b/a) for a,b in zip(prices,prices[1:])]
        rv20=stdev(returns[-20:])*math.sqrt(252)
        rv60=stdev(returns)*math.sqrt(252)
        largest=max(rv20,rv60)
        if largest<=0:return VolatilityFeatures(n,n-1,rv20,rv60,None,False,'zero_observed_volatility')
        return VolatilityFeatures(n,n-1,rv20,rv60,iv/largest,True,'computed_from_completed_source_sessions')
