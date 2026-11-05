"""Benchmark synthetic hot paths against the frozen running baseline; no quote export."""
import importlib.util
import json
import random
import statistics
import sys
import time
from collections import Counter
from datetime import date,datetime,timedelta
from pathlib import Path
from types import ModuleType,SimpleNamespace as NS
import hashlib
import duckdb
import pandas as pd

HERE=Path(__file__).resolve().parent
FROZEN=HERE/'results/strangle_basket_20261018_173739'


def module(name,source):
    m=ModuleType(name);sys.modules[name]=m;exec(compile(source,name,'exec'),m.__dict__);return m


def load_algorithms():
    imports=ModuleType('AlgorithmImports');imports.QCAlgorithm=object
    imports.OptionRight=NS(PUT='P',CALL='C');sys.modules['AlgorithmImports']=imports
    extras=json.loads((FROZEN/'extra_files.json').read_text())
    module('rules',extras['rules.py']);module('premium_units',extras['premium_units.py'])
    module('execution_base',extras['execution_base.py'])
    old_rules=module('basket_rules',extras['basket_rules.py'])
    old=module('frozen_basket', (FROZEN/'basket.py').read_text()).BasketShortStrangle
    new_rules=module('basket_rules',(HERE/'basket/basket_rules.py').read_text())
    new=module('faster_basket',(HERE/'basket/main.py').read_text()).BasketShortStrangle
    return old,new,old_rules,new_rules


class NativeContract:
    def __init__(self,symbol,expiry,strike,put,price,today,counters):
        self.symbol,self.expiry,self.strike=symbol,datetime.combine(expiry,datetime.min.time()),strike
        self.right='P' if put else 'C';self.last_price=price;self.underlying_last_price=100
        self.open_interest=1000;self.time=datetime.combine(today,datetime.min.time());self.counters=counters
    @property
    def implied_volatility(self):
        self.counters['unused_native_iv_reads']+=1;return 0
    @property
    def greeks(self):
        self.counters['unused_native_greeks_reads']+=1;return NS(delta=0)


def algorithm(cls,rules):
    a=cls();a.time=datetime(2020,1,2,11,55);a.counts=Counter();a.CONFIG={}
    a.native_counts=Counter();today=a.time.date();a.chains={}
    a.is_monthly=lambda symbol,future=False:symbol.monthly
    for underlying in range(8):
        rows=[]
        for dte in [30,45,75,105,135,165,195,225,255,285,315,345,38,52]:
            expiry=today+timedelta(days=dte)
            for strike in range(76,125,2):
                for put in (False,True):
                    sid=f'{underlying}:{dte}:{strike}:{put}'
                    symbol=NS(id=NS(symbol='OZW'),underlying=NS(id=NS(symbol='ZW')),
                        monthly=dte not in (38,52),value=sid)
                    price=rules.black76_price_delta(100,strike,(dte+1)/365,.3,.03,put)[0]
                    rows.append(NativeContract(symbol,expiry,strike,put,price,today,a.native_counts))
        a.chains[underlying]=rows
    def chain(underlying):a.native_counts['chain_reads']+=1;return a.chains[underlying]
    def rate(observed):a.native_counts['rate_reads']+=1;return .03
    a.option_chain=chain;a.risk_free_interest_rate_model=NS(get_interest_rate=rate)
    return a


def workload(a):
    decisions=[]
    for underlying in a.chains:
        records=a.records_for(underlying,True)
        point=a.atm_iv(records)
        expiry=a.time.date()+timedelta(days=45)
        legs=a.selected_legs(records,expiry)
        # Repeat the daily-chain access and leg modeling in the holding path.
        again=a.records_for(underlying,True)
        second=a.atm_iv(again)
        for leg in legs.values():a.model_record(leg);a.model_record(leg)
        decisions.append(dict(underlying=underlying,iv_point=str(point),second_point=str(second),
            put=legs['put']['symbol'].value,call=legs['call']['symbol'].value,
            put_iv=legs['put']['iv'],call_iv=legs['call']['iv'],
            put_delta=legs['put']['delta'],call_delta=legs['call']['delta']))
    return decisions


def main():
    old,new,old_rules,new_rules=load_algorithms();rng=random.Random(73)
    vectors=[]
    for i in range(3000):
        f=rng.uniform(2,5000);k=f*rng.uniform(.7,1.3);y=rng.uniform(7,95)/365
        rate=rng.uniform(-.01,.1);put=bool(i%2);vol=rng.uniform(.05,1.5)
        price=old_rules.black76_price_delta(f,k,y,vol,rate,put)[0]
        vectors.append((price,f,k,y,rate,put))
    vectors.extend([(0,100,100,.1,.03,False),(1000,100,100,.1,.03,True),
        (float('nan'),100,100,.1,.03,False),(1,-1,100,.1,.03,False)])
    gold=[old_rules.black76_iv_delta(*v) for v in vectors]
    optimized=[new_rules.black76_iv_delta(*v) for v in vectors]
    assert optimized==gold,'Numerical IV/delta output changed'
    times=[]
    for label,solver in [('frozen',old_rules.black76_iv_delta),('optimized',new_rules.black76_iv_delta)]:
        runs=[]
        for _ in range(5):
            start=time.perf_counter()
            for v in vectors:solver(*v)
            runs.append(time.perf_counter()-start)
        times.append(dict(case='solver',version=label,median_seconds=statistics.median(runs)))
    outputs=[];counts=[]
    for label,cls in [('frozen',old),('optimized',new)]:
        runs=[]
        for _ in range(5):
            a=algorithm(cls,old_rules);started=time.perf_counter();decisions=workload(a)
            runs.append(time.perf_counter()-started)
        outputs.append(decisions);counts.append(dict(version=label,**a.native_counts,**a.counts))
        times.append(dict(case='chain_and_selection',version=label,median_seconds=statistics.median(runs)))
    assert outputs[0]==outputs[1],'ATM selection, IV, delta or selected strikes changed'
    out=HERE/'results/performance_fix_20261018';out.mkdir(exist_ok=True)
    frames={'benchmark_timings':pd.DataFrame(times),'operation_counts':pd.DataFrame(counts).fillna(0),
        'synthetic_decisions':pd.DataFrame(outputs[1])}
    with duckdb.connect(str(out/'benchmarks.duckdb')) as c:
        for name,frame in frames.items():
            frame.to_parquet(out/(name+'.parquet'),index=False);frame.to_csv(out/(name+'.csv'),index=False)
            c.register('frame',frame);c.execute('CREATE OR REPLACE TABLE '+name+' AS SELECT * FROM frame')
    def speedup(case):
        rows={r['version']:r['median_seconds'] for r in times if r['case']==case}
        return rows['frozen']/rows['optimized']
    summary=dict(scope='Synthetic CPU hot-path benchmark; NOT measured full-cloud speedup or performance',
        frozen_campaign=str(FROZEN),vector_count=len(vectors),numerically_identical=True,
        selected_contracts_iv_delta_identical=True,solver_speedup=speedup('solver'),
        chain_selection_speedup=speedup('chain_and_selection'),timings=times,operations=counts,
        cloud_validation='Pending; running cloud baseline is immutable and unchanged',
        source_sha256={str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (HERE/'basket/main.py',HERE/'basket/basket_rules.py')})
    if (out/'summary.json').exists():
        prior=json.loads((out/'summary.json').read_text());prior.update(summary);summary=prior
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
