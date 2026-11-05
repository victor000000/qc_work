"""Account-result drawdown bounds; no market prices or simulated fills."""
import math
from datetime import datetime,timezone
from zoneinfo import ZoneInfo

def chart_drawdown(response,initial,begin,end):
    series=response['chart']['series'];candidate=series.get('Equity') or series.get('Equity Sum')
    if candidate is None:raise ValueError('Missing account equity series')
    observations=[]
    for point in candidate['values']:
        if isinstance(point,dict):
            stamp=point['x']
            if 'close' in point:fields=[point.get('open',point['close']),point.get('high',point['close']),point.get('low',point['close']),point['close']]
            else:
                value=point['y']
                fields=[value.get(k,value['close']) for k in ('open','high','low','close')] if isinstance(value,dict) else [value]*4
        else:
            stamp=point[0];fields=point[1:5] if len(point)==5 else [point[1]]*4
        day=datetime.fromtimestamp(float(stamp),timezone.utc).astimezone(ZoneInfo('America/New_York')).date()
        if begin<=day<=end:observations.append((float(stamp),*[float(v) for v in fields]))
    observations.sort(key=lambda x:x[0]);peak=float(initial);lower=upper=0.;minimum=None
    if not math.isfinite(peak) or peak<=0:raise ValueError('Positive finite opening equity required')
    for stamp,o,h,l,c in observations:
        if not all(math.isfinite(x) for x in (o,h,l,c)) or not l<=min(o,c)<=max(o,c)<=h:raise ValueError('Invalid account OHLC')
        minimum=l if minimum is None else min(minimum,l)
        preceding_peak=max(peak,o)
        lower=max(lower,1-l/preceding_peak,1-c/max(preceding_peak,h))
        upper=max(upper,1-l/max(preceding_peak,h));peak=max(peak,h)
    return dict(observations=len(observations),minimum_observed_equity=minimum,
        sampled_mdd_lower_bound=lower,sampled_mdd_upper_bound=upper,
        bounds_scope='Available account chart observations only; unknown intrabar high/low ordering. Upper bound does not bound unobserved account marks.')

def include_chart_drawdown(metrics,audits):
    """Only strengthen full-account qualification; do not rewrite frozen training selection."""
    active=[a for a in audits if a['observations']]
    metrics['account_chart_audits']=audits
    observed=max((a['sampled_mdd_lower_bound'] for a in active),default=0.)
    conservative=max((a['sampled_mdd_upper_bound'] for a in active),default=0.)
    metrics['observed_account_chart_mdd_lower_bound']=observed
    metrics['observed_account_chart_mdd_upper_bound']=conservative
    metrics['account_chart_denominator_policy']='Use sampled OHLC upper bound when intrabar ordering is unknown; unobserved marks remain outside chart coverage.'
    if metrics['denominator_mdd'] is not None:metrics['denominator_mdd']=max(metrics['denominator_mdd'],conservative)
    if any(a['minimum_observed_equity']<=0 for a in active):
        metrics.update(available=False,positive_equity=False,cagr=None,calmar=None,
            unavailable_reason='Nonpositive actual intraday account equity; funded CAGR and Calmar unavailable')
    elif metrics['cagr'] is not None:
        metrics['calmar']=metrics['cagr']/metrics['denominator_mdd'] if metrics['denominator_mdd']>0 else None
    return metrics
