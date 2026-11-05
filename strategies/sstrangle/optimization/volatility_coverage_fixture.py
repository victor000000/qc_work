"""No-trade aggregate daily/minute source availability; not feature validation."""
from AlgorithmImports import *
from datetime import datetime,timedelta,time
import json
class VolatilityCoverageProbe(QCAlgorithm):
    CONFIG = {}
    def initialize(self):
        self.set_start_date(2017,7,5);self.set_end_date(2017,7,5);self.set_cash(60000)
        self.set_time_zone('America/New_York');self.settings.daily_precise_end_time=True
        self.roots={};self.results=[]
        for root in self.CONFIG['roots']:
            f=self.add_future(root,Resolution.DAILY);f.set_filter(lambda u:u.contracts([]));self.roots[root]=f.symbol
        self.schedule.on(self.date_rules.every_day(),self.time_rules.at(12,0),self.probe)
    def probe(self):
        if self.results:raise RuntimeError('Duplicate availability probe')
        for root,canonical in self.roots.items():
            contracts=sorted(self.futures_chain(canonical),key=lambda c:float(c.volume),reverse=True)[:2]
            if len(contracts)!=2:raise RuntimeError('Missing two native deliveries:'+root)
            for c in contracts:
                symbol=c.symbol;self.add_future_contract(symbol,Resolution.DAILY);sec=self.securities[symbol]
                counts={day:dict(daily=0,minute=0) for day in ['2017-07-03','2017-07-04']}
                for label,res in [('daily',Resolution.DAILY),('minute',Resolution.MINUTE)]:
                    bars=self.history[TradeBar](symbol,datetime(2017,7,3),datetime(2017,7,5),res,fill_forward=False,extended_market_hours=False,data_normalization_mode=DataNormalizationMode.RAW)
                    for b in bars:
                        if b.symbol!=symbol or b.is_fill_forward:raise RuntimeError('Non-native/fill-forward source')
                        # Source timestamps only; no market prices or volumes leave cloud.
                        day=str(b.end_time.date())
                        if day in counts:counts[day][label]+=1
                for day,n in counts.items():
                    close=sec.exchange.hours.get_last_daily_market_close(datetime.fromisoformat(day),False)
                    row=dict(root=root,native_id=str(symbol.id),session=day,daily_rows=n['daily'],minute_rows=n['minute'],calendar_close=str(close),calendar_open_before_close=sec.exchange.hours.is_open(close-timedelta(seconds=1),False))
                    self.results.append(row);self.log('VOLATILITY_AVAILABILITY '+json.dumps(row,sort_keys=True))
        if len(self.results)!=60:raise RuntimeError('Availability root scope incomplete')
        self.set_runtime_statistic('availability_records',str(len(self.results)))
        self.set_runtime_statistic('availability_roots',str(len(self.roots)))
        self.plot('Trading period','Equity',float(self.portfolio.total_portfolio_value))
    def on_end_of_algorithm(self):
        if len(self.results)!=60 or list(self.transactions.get_orders()) or self.portfolio.invested or float(self.portfolio.total_portfolio_value)!=60000:raise RuntimeError('Availability/account proof incomplete')
        self.set_runtime_statistic('availability_no_trades','1')
