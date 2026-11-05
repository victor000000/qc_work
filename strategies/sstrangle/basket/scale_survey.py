"""Infer CL premium units from cross-strike put/call parity; aggregate diagnostics."""
from AlgorithmImports import *
from datetime import date
from collections import Counter,defaultdict
import statistics,json,math


class CLScaleSurvey(QCAlgorithm):
    CONFIG = {}
    def initialize(self):
        self.set_start_date(2015,12,1);self.set_end_date(2026,9,30);self.set_cash(60000)
        self.future=self.add_future('CL',Resolution.DAILY)
        self.future.set_filter(lambda u:u.contracts([]))
        self.days=set();self.results=defaultdict(Counter);self.failures=[]
        self.schedule.on(self.date_rules.every_day(),self.time_rules.at(12,0),self.inspect)
    def inspect(self):
        today=self.time.date()
        # Dense around the discontinuity, monthly samples thereafter.
        if not (today<date(2016,2,1) or today.day<=7):return
        if (today.year,today.month) in self.days and today>=date(2016,2,1):return
        contracts=sorted(self.futures_chain(self.future.symbol),key=lambda c:float(c.volume),reverse=True)
        for future in contracts:
            records=list(self.option_chain(future.symbol))
            eligible=[r for r in records if 21<=(r.expiry.date()-today).days<=95]
            if not eligible:continue
            expiry=min({r.expiry for r in eligible},key=lambda e:abs((e.date()-today).days-45))
            pairs=defaultdict(dict)
            for r in eligible:
                spot=float(r.underlying_last_price);k=float(r.strike)
                if r.expiry==expiry and spot>0 and .02*spot<abs(k-spot)<.2*spot and float(r.last_price)>0:
                    pairs[k][r.right]=(float(r.last_price),spot)
            errors={1:[],.01:[],100:[]}
            for k,p in pairs.items():
                if OptionRight.CALL not in p or OptionRight.PUT not in p:continue
                call,f=p[OptionRight.CALL];put,_=p[OptionRight.PUT]
                for factor in errors:errors[factor].append(abs(factor*(call-put)-(f-k))/f)
            if len(errors[1])<4:continue
            scores={factor:statistics.median(values) for factor,values in errors.items()}
            best=min(scores,key=scores.get)
            self.results[today.year][str(best) if scores[best]<.03 else 'unresolved']+=1
            self.log('PARITY_UNITS '+json.dumps(dict(day=str(today),pairs=len(errors[1]),best_factor=best,
                median_relative_errors={str(k):v for k,v in scores.items()})))
            self.days.add((today.year,today.month));break
    def on_end_of_algorithm(self):
        self.log('UNIT_SURVEY '+json.dumps({str(k):dict(v) for k,v in self.results.items()}))
        self.set_runtime_statistic('scope','Unit-consistency diagnostics; no raw historical quote export')
