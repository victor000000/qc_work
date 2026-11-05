"""Descriptive axis diagnostics; no automatic recipe or profit optimization."""
import math
from statistics import mean, pstdev


def acf(values, lag=1):
    if len(values)<=lag or not values:return None
    avg=mean(values);den=sum((v-avg)**2 for v in values)
    return sum((values[i]-avg)*(values[i-lag]-avg) for i in range(lag,len(values)))/den if den else None


def describe(values):
    if not values:return dict(count=0)
    v=sorted(values)
    return dict(count=len(v),mean=mean(v),std=pstdev(v),minimum=v[0],maximum=v[-1],
                p50=v[(len(v)-1)//2],p95=v[int((len(v)-1)*.95)])


def audit(bars):
    complete=[b for b in bars if b['is_complete']]
    returns=[math.log(b['close']/b['open']) for b in complete]
    by_session={}
    for b in complete:by_session.setdefault(b['session'],[]).append(b)
    return dict(complete_bars=len(complete),incomplete_bars=len(bars)-len(complete),
                duration_seconds=describe([b['duration_seconds'] for b in complete]),
                activity=describe([b['activity'] for b in complete]),
                overshoot=describe([b['overshoot'] for b in complete]),returns=describe(returns),
                session_counts={d:len(v) for d,v in by_session.items()},
                session_dependence={d:dict(return_acf1=acf([math.log(b['close']/b['open']) for b in v]),
                    squared_return_acf1=acf([math.log(b['close']/b['open'])**2 for b in v])) for d,v in by_session.items()},
                interpretation='Descriptive diagnostics; no IID, profitability or axis-selection acceptance')
