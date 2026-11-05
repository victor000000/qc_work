"""All-root genuine regular-session minute close adapter; no trades/raw export."""
from AlgorithmImports import *
from datetime import datetime,time,timedelta
from zoneinfo import ZoneInfo
from collections import Counter
import hashlib,json,math
import numpy as np
from minute_session_closes import SessionBounds,MinuteTrade,session_closes
from completed_volatility import CompletedVolatilityWindow
class MinuteVolatilityProbe(QCAlgorithm):
    CONFIG = {}
    def initialize(self):
        self.set_start_date(2017,7,5);self.set_end_date(2017,7,7);self.set_cash(60000);self.set_time_zone('America/New_York')
        self.roots={};self.symbols={};self.counts=Counter();self.digest=hashlib.sha256()
        for root in self.CONFIG['roots']:
            f=self.add_future(root,Resolution.DAILY);f.set_filter(lambda u:u.contracts([]));self.roots[root]=f.symbol
        self.schedule.on(self.date_rules.every_day(),self.time_rules.at(12,0),self.probe)
    def probe(self):
        self.plot('Trading period','Equity',float(self.portfolio.total_portfolio_value))
        if not self.symbols:
            for root,canonical in self.roots.items():
                selected=sorted(self.futures_chain(canonical),key=lambda c:float(c.volume),reverse=True)[:2]
                if len(selected)!=2 or len({str(c.symbol.id) for c in selected})!=2:raise RuntimeError('Two native deliveries required:'+root)
                for c in selected:self.add_future_contract(c.symbol,Resolution.DAILY);self.symbols[c.symbol]=root
        for symbol,root in self.symbols.items():self.probe_symbol(symbol,root)
    def probe_symbol(self,symbol,root):
        sec=self.securities[symbol];tz=ZoneInfo(str(sec.exchange.time_zone));asof=self.time.replace(tzinfo=ZoneInfo('America/New_York'));sessions=[]
        for offset in range(130,0,-1):
            day=datetime.combine(sec.local_time.date()-timedelta(days=offset),time())
            opened=sec.exchange.hours.get_next_market_open(day,False);closed=sec.exchange.hours.get_last_daily_market_close(day,False)
            if opened.date()==day.date() and closed.date()==day.date() and opened<closed<=sec.local_time:
                sessions.append(SessionBounds(day.date(),opened.replace(tzinfo=tz),closed.replace(tzinfo=tz)))
        sessions=sessions[-61:]
        if len(sessions)!=61:raise RuntimeError('Actual native session calendar incomplete')
        begin=datetime.combine(sessions[0].session,time());end=datetime.combine(sec.local_time.date(),time())
        actual=[];reference={}
        for b in self.history[TradeBar](symbol,begin,end,Resolution.MINUTE,fill_forward=False,extended_market_hours=False,data_normalization_mode=DataNormalizationMode.RAW):
            item=MinuteTrade(str(b.symbol.id),b.time.replace(tzinfo=tz),b.end_time.replace(tzinfo=tz),float(b.close),bool(b.is_fill_forward));actual.append(item)
            if item.end.date() not in reference or item.end>reference[item.end.date()].end:reference[item.end.date()]=item
        r=session_closes(actual,sessions,str(symbol.id),'native_RAW_minute_RTH',asof,sec.local_time.date())
        self.counts['requests']+=1;self.counts['root_attempt_'+root]+=1;self.counts['source_minutes']+=r.source_bars
        if not r.ready:
            self.counts['unavailable']+=1;self.counts['missing_sessions']+=len(r.missing);self.counts['stale_sessions']+=len(r.stale)
            self.log('MINUTE_SOURCE_UNAVAILABLE '+json.dumps(dict(root=root,native_id=str(symbol.id),decision=str(self.time.date()),missing_count=len(r.missing),stale_count=len(r.stale)),sort_keys=True));return
        for p in r.points:
            if p.price!=reference[p.session].close or p.end_time!=reference[p.session].end:raise RuntimeError('Native actual final minute mismatch')
        w=CompletedVolatilityWindow();w.replace_rebased_history(r.points,asof,sec.local_time.date(),consecutive=True);f=w.features(1.,expected_last_session=sessions[-1].session)
        if not f.ready:raise RuntimeError('Source-ready volatility calculation unavailable')
        returns=np.diff(np.log(np.asarray([p.price for p in r.points])));v20=float(np.std(returns[-20:],ddof=1)*math.sqrt(252));v60=float(np.std(returns,ddof=1)*math.sqrt(252))
        if not math.isclose(f.realized20,v20,rel_tol=1e-10,abs_tol=1e-12) or not math.isclose(f.realized60,v60,rel_tol=1e-10,abs_tol=1e-12):raise RuntimeError('Independent numpy mismatch')
        self.counts['ready']+=1;self.counts['numpy_matches']+=1;self.counts['root_ready_'+root]+=1
        self.digest.update(json.dumps([str(symbol.id),str(self.time.date()),f.realized20,f.realized60],separators=(',',':')).encode())
    def on_end_of_algorithm(self):
        if list(self.transactions.get_orders()) or self.portfolio.invested or float(self.portfolio.total_portfolio_value)!=60000:raise RuntimeError('Minute source probe traded')
        if any(self.counts['root_attempt_'+r]!=6 for r in self.CONFIG['roots']) or self.counts['requests']!=90:raise RuntimeError('All-root attempt scope incomplete')
        if self.counts['ready']+self.counts['unavailable']!=90 or self.counts['numpy_matches']!=self.counts['ready']:raise RuntimeError('Missing source outcomes')
        for key,value in self.counts.items():self.set_runtime_statistic('minute_'+key,str(value))
        self.set_runtime_statistic('minute_no_trades','1');self.set_runtime_statistic('minute_iv_input','synthetic1.0_not_market_IV')
        self.log('MINUTE_SOURCE_CHECKSUM '+self.digest.hexdigest())
