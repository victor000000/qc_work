"""Future exact-WBA hook: aggregate clock/type/freshness predicates ONLY.
NO history calls, order submission, quote-price export, timestamp rows or strategy changes.
Pass original native Slice/cache objects without rewriting their data or clock.
"""
from collections import Counter
from datetime import datetime,time,timedelta


def _minute_period(bar):
    period=bar.period
    if hasattr(period,'total_seconds'):return period.total_seconds()==60
    return period.TotalSeconds==60 # .NET TimeSpan fallback, not a logging value.


def _prior_open_session(local,hours):
    d=local.date()-timedelta(days=1)
    for _ in range(10):
        if hours.is_date_open(datetime.combine(d,time())):return d
        d-=timedelta(days=1)
    return None


def _facts(bar,clock,prior,quote_type):
    out={'present':bar is not None}
    if bar is None:return out
    out['quote_type']=isinstance(bar,quote_type)
    out['fill_forward']=bool(bar.is_fill_forward)
    ended=bar.end_time;started=bar.time
    out['period_minute']=_minute_period(bar)
    out['end_equals_start_plus_period']=(ended-started==timedelta(minutes=1)) if out['period_minute'] else False
    out['end_future']=ended>clock
    out['end_stale_gt5m']=ended<clock-timedelta(minutes=5)
    out['end_within5m']=clock-timedelta(minutes=5)<=ended<=clock
    out['end_exact_now']=ended==clock
    out['end_same_calendar_day']=ended.date()==clock.date()
    out['end_prior_calendar_day']=ended.date()<clock.date()
    out['end_prior_open_session']=(prior is not None and ended.date()==prior)
    out['end_older_than_prior_open_session']=(prior is not None and ended.date()<prior)
    out['fresh_nonff']=out['end_within5m'] and not out['fill_forward']
    return out


class WAGQuoteClockDiagnostics:
    def __init__(self):self.counts=Counter()

    def observe(self,side,algorithm_time,security,cache_bar,slice_bar,quote_type,*,slice_has_quote):
        """One observation per actualSlice during2019Nov29 noon-halfday session.
        No prices or timestamps are retained; all source objects remain untouched.
        """
        if side not in {'put','call'}:raise ValueError('Only two original native fixture legs')
        if not (algorithm_time.date()==datetime(2019,11,29).date()
                and time(12)<=algorithm_time.time()<=time(13)):
            raise ValueError('Bounded mandatory-session clock probe only')
        p=side+'_';self.counts[p+'observations']+=1
        local=security.local_time
        self.counts[p+'security_local_equals_algorithm_ny']+=int(local==algorithm_time)
        self.counts[p+'security_local_before_algorithm']+=int(local<algorithm_time)
        self.counts[p+'security_local_after_algorithm']+=int(local>algorithm_time)
        self.counts[p+'security_exchange_open']+=int(bool(security.exchange.exchange_open))
        self.counts[p+'slice_has_quote']+=int(slice_has_quote)
        if bool(slice_has_quote)!=(slice_bar is not None):raise ValueError('Slice membership/object mismatch')
        prior=_prior_open_session(local,security.exchange.hours)
        c=_facts(cache_bar,local,prior,quote_type);s=_facts(slice_bar,local,prior,quote_type)
        for source,values in [('cache',c),('slice',s)]:
            for k,v in values.items():self.counts[p+source+'_'+k]+=int(v)
        for source,bar in [('cache',cache_bar),('slice',slice_bar)]:
            # Distinguish local-clock comparison from algorithm NY without exporting either timestamp.
            if bar is not None:
                self.counts[p+source+'_end_within5m_algorithm_ny']+=int(algorithm_time-timedelta(minutes=5)<=bar.end_time<=algorithm_time)
                self.counts[p+source+'_end_future_algorithm_ny']+=int(bar.end_time>algorithm_time)
                self.counts[p+source+'_end_stale_algorithm_ny']+=int(bar.end_time<algorithm_time-timedelta(minutes=5))
        if cache_bar is not None and slice_bar is not None:
            equal=cache_bar.end_time==slice_bar.end_time
            self.counts[p+'cache_slice_equal_endpoint']+=int(equal)
            self.counts[p+'cache_endpoint_before_slice']+=int(cache_bar.end_time<slice_bar.end_time)
            self.counts[p+'cache_endpoint_after_slice']+=int(cache_bar.end_time>slice_bar.end_time)
            self.counts[p+'stale_cache_fresh_real_slice']+=int(c['end_stale_gt5m'] and s['fresh_nonff'])
            self.counts[p+'stale_cache_fresh_ff_slice']+=int(c['end_stale_gt5m'] and s['end_within5m'] and s['fill_forward'])
        return None

    def observe_native(self,side,algorithm,data,symbol,quote_bar_type):
        """QC-specific read-only bridge; missing expected API must fail visibly.
        Caller supplies AlgorithmImports.QuoteBar, no dependency or hidden feed changes.
        """
        security=algorithm.securities[symbol]
        cache_bar=security.cache.get_data[quote_bar_type]()
        quotes=data.quote_bars
        has=quotes.contains_key(symbol) if hasattr(quotes,'contains_key') else symbol in quotes
        bar=quotes[symbol] if has else None
        self.observe(side,algorithm.time,security,cache_bar,bar,quote_bar_type,slice_has_quote=has)

    def runtime_counts(self):
        """Exactly12 boolean aggregate counters per leg; keep native runtime output bounded."""
        out={}
        names=['observations','cache_end_stale_gt5m','cache_end_future','slice_present',
            'slice_fresh_nonff','cache_slice_equal_endpoint','cache_period_minute',
            'slice_period_minute','security_exchange_open','security_local_equals_algorithm_ny']
        for side in ('put','call'):
            p=side+'_'
            for k in names:out[p+k]=int(self.counts[p+k])
            out[p+'slice_fresh_ff']=int(self.counts[p+'slice_end_within5m']-self.counts[p+'slice_fresh_nonff'])
            out[p+'cache_prior_open_session_or_older']=int(self.counts[p+'cache_end_prior_open_session']+self.counts[p+'cache_end_older_than_prior_open_session'])
        return out

    def summary(self):
        return {'scope':'WBA exact-position Nov29noon-halfday aggregate clock predicates only',
                'counts':dict(sorted(self.runtime_counts().items())),
                'native_qc_clock_cause_proven':False,
                'limitation':'Counts distinguish observed predicates; no prices/timestamps/history exported and no exit-rule relaxation.'}
