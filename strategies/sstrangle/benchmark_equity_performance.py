"""Synthetic equity screen/504-day seeding parity and CPU benchmark vs frozen QC code."""
from collections import Counter,deque
from datetime import date,datetime,timedelta
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
import time
from types import SimpleNamespace as NS
import duckdb
import pandas as pd
from benchmark_performance import load_algorithms,HERE


class Identifier:
    def __init__(self,expiry,strike,right,counts):
        self.expiry,self.strike,self.right,self.counts=expiry,strike,right,counts
    @property
    def date(self):self.counts['date_reads']+=1;return self.expiry
    @property
    def strike_price(self):self.counts['strike_reads']+=1;return self.strike
    @property
    def option_right(self):self.counts['right_reads']+=1;return self.right


class NativeSymbol:
    def __init__(self,identifier,monthly,counts):self.identifier,self.monthly,self.counts=identifier,monthly,counts
    @property
    def id(self):self.counts['symbol_id_reads']+=1;return self.identifier


class History:
    def __init__(self,chains):self.chains=chains
    def __getitem__(self,kind):return lambda canonical,start,end:self.chains


def main():
    old,new,old_rules,new_rules=load_algorithms();rng=random.Random(515);counts=Counter();chains=[]
    for day in range(504):
        observed=date(2018,1,1)+timedelta(days=day);contracts=[]
        for dte in [7,20,21,30,45,60,95,96,365,52]:
            expiry=datetime.combine(observed+timedelta(days=dte),datetime.min.time())
            for strike in (90,98,100,102,110):
                for right in ('P','C'):
                    identifier=Identifier(expiry,strike,right,counts)
                    contracts.append(NS(symbol=NativeSymbol(identifier,dte!=52,counts),
                        implied_volatility=.2+day/100000+(right=='C')*.01+strike/10000))
        rng.shuffle(contracts)
        chains.append(NS(end_time=datetime.combine(observed,datetime.min.time()),
            underlying=NS(price=100),data=contracts))
    results=[];decisions=[];operations=[]
    for name,cls in [('reference',old),('optimized',new)]:
        mod=sys.modules[cls.__module__];mod.Symbol=NS(create_canonical_option=lambda x:x);mod.OptionUniverse=object
        runs=[];counts.clear()
        for _ in range(5):
            a=cls();a.time=datetime(2020,1,2,11,55);a.CONFIG={};a.lookback=504;a.counts=Counter()
            a.history=History(chains);a.is_monthly=lambda symbol:symbol.monthly
            state=dict(eq='SYNTHETIC',last_checked=None,iv={})
            started=time.perf_counter();a.seed_equity_iv(state);runs.append(time.perf_counter()-started)
        results.append(dict(case='history_504_days',version=name,median_seconds=statistics.median(runs)))
        operations.append(dict(version=name,**counts));decisions.append(state['iv'])
    assert len(decisions[0])==504 and decisions[0]==decisions[1],'Historical IV observations changed'
    stats=old_rules.iv_statistics(list(decisions[0].items()),date(2020,1,2),504,504)
    assert stats==new_rules.iv_statistics(list(decisions[1].items()),date(2020,1,2),504,504)
    points=[(date(2012,1,1)+timedelta(days=i),rng.uniform(29,35),rng.uniform(4e6,7e6)) for i in range(20000)]
    screen_outputs=[]
    for name in ('reference','optimized'):
        runs=[]
        for _ in range(5):
            output=[];rows=deque(maxlen=20);window=new_rules.EquityScreenWindow();started=time.perf_counter()
            for point in points:
                if name=='reference':
                    # This includes the original eager setdefault allocation.
                    deque(maxlen=20)
                    rows.append(point);output.append(old_rules.equity_screen(list(rows),1e10))
                else:
                    window.append(point);output.append(window.screen(1e10))
            runs.append(time.perf_counter()-started)
        results.append(dict(case='daily_equity_screen',version=name,median_seconds=statistics.median(runs)))
        screen_outputs.append(output)
    assert screen_outputs[0]==screen_outputs[1],'Screen result or exact floating averages changed'
    candidate_inputs=[]
    for i in range(60000):
        symbol=i%200;day=i//200
        candidate_inputs.append((symbol,(date(2018,1,1)+timedelta(days=day),
            (10 if symbol%4==0 else 100)+day/1000,
            (7e6 if symbol%5==0 else 1e6)+day),1e12))
    candidate_outputs=[]
    for name in ('reference','optimized'):
        runs=[]
        for _ in range(5):
            windows={};output=[];started=time.perf_counter()
            for symbol,point,cap in candidate_inputs:
                if name=='reference':
                    rows=windows.setdefault(symbol,deque(maxlen=20));rows.append(point)
                    reason,info=old_rules.equity_screen(list(rows),cap)
                    output.append(info if reason is None else None)
                else:
                    window=windows.get(symbol)
                    if window is None:window=new_rules.EquityScreenWindow();windows[symbol]=window
                    window.append(point);output.append(window.candidate_info(cap))
            runs.append(time.perf_counter()-started)
        results.append(dict(case='universe_candidates',version=name,median_seconds=statistics.median(runs)))
        candidate_outputs.append(output)
    assert candidate_outputs[0]==candidate_outputs[1],'Universe candidate membership or features changed'
    def speed(case):
        t={r['version']:r['median_seconds'] for r in results if r['case']==case}
        return t['reference']/t['optimized']
    summary=dict(scope='Synthetic equity CPU components only; not total-cloud speedup',history_days=504,
        history_iv_and_full_window_rank_identical=True,screen_samples=len(points),screen_outputs_identical=True,
        universe_candidate_samples=len(candidate_inputs),universe_candidates_identical=True,
        universe_candidate_speedup=speed('universe_candidates'),
        history_component_speedup=speed('history_504_days'),screen_component_speedup=speed('daily_equity_screen'),
        timings=results,history_native_property_counts=operations,
        historical_series_sha256=hashlib.sha256(repr(sorted(decisions[0].items())).encode()).hexdigest(),
        source_sha256={str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (HERE/'basket/main.py',HERE/'basket/basket_rules.py')})
    out=HERE/'results/performance_fix_20261018';out.mkdir(exist_ok=True)
    with duckdb.connect(str(out/'equity_benchmarks.duckdb')) as c:
        for name,frame in [('equity_timings',pd.DataFrame(results)),('native_property_counts',pd.DataFrame(operations))]:
            frame.to_parquet(out/(name+'.parquet'),index=False);frame.to_csv(out/(name+'.csv'),index=False)
            c.register('frame',frame);c.execute('CREATE OR REPLACE TABLE '+name+' AS SELECT * FROM frame')
    (out/'equity_summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
