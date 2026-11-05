"""Read-only cloud capability probe for the point-in-time basket baseline."""
from AlgorithmImports import *
from datetime import timedelta
import json


class BasketDataProbe(QCAlgorithm):
    CONFIG = {}

    def initialize(self):
        self.set_start_date(*self.CONFIG['start'])
        self.set_end_date(*self.CONFIG['end'])
        self.set_cash(250000)
        self.spy = self.add_equity('SPY', Resolution.MINUTE).symbol
        self.securities[self.spy].set_data_normalization_mode(DataNormalizationMode.RAW)
        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.screen_inputs)
        self.futures = []
        for root in ['CL','RB','HO','NG','ZN','ZT','ZB','ZC','ZS','ZW','NQ','ES','HG','GC','SI']:
            future = self.add_future(root, Resolution.DAILY)
            future.set_filter(lambda universe: universe.contracts([]))
            self.futures.append(future)
        self.earnings = self.add_universe(EODHDUpcomingEarnings, self.earnings_inputs)
        self.schedule.on(self.date_rules.every_day(self.spy),
                         self.time_rules.after_market_open(self.spy, 150), self.inspect)
        self.days = 0

    def screen_inputs(self, rows):
        rows = list(rows)
        watch = {row.symbol.value:dict(price=float(row.price),volume=float(row.volume),
                    cap=float(row.market_cap),fundamentals=bool(row.has_fundamental_data))
                 for row in rows if row.symbol.value in ('SPY','QQQ','GLD','AAPL')}
        self.log('COARSE_PROBE ' + json.dumps(dict(day=str(self.time.date()),count=len(rows),watch=watch)))
        return []

    def earnings_inputs(self, rows):
        rows = list(rows)
        sample = [dict(symbol=str(row.symbol),time=str(row.end_time),report=str(row.report_date)) for row in rows[:2]]
        self.log('EARNINGS_PROBE ' + json.dumps(dict(day=str(self.time.date()),count=len(rows),sample=sample)))
        return []

    def describe_chain(self, underlying):
        chain = list(self.option_chain(underlying))
        near = sorted(chain,key=lambda c:(abs((c.symbol.id.date.date()-self.time.date()).days-45),
            abs(float(c.strike)-float(c.underlying_last_price))))[:2]
        return dict(underlying=str(underlying),contracts=len(chain),
            valid_iv=sum(float(c.implied_volatility)>0 for c in chain),
            priced=sum(float(c.last_price)>0 for c in chain),
            sample=[dict(symbol=str(c.symbol),
            strike=float(c.strike),id_strike=float(c.symbol.id.strike_price),
            day=str(c.time),price=float(c.last_price),iv=float(c.implied_volatility),
            spot=float(c.underlying_last_price),delta=float(c.greeks.delta),
            volume=float(c.volume),oi=float(c.open_interest)) for c in near])

    def inspect(self):
        self.days += 1
        self.log('OPTION_PROBE ' + json.dumps(self.describe_chain(self.spy)))
        if self.days == 2:
            self.log('UNSUBSCRIBED_PROBE ' + json.dumps(self.describe_chain(Symbol.create('AAPL',SecurityType.EQUITY,Market.USA))))
        for future in self.futures:
            futures = sorted(self.futures_chain(future.symbol),key=lambda c:float(c.volume),reverse=True)
            if futures and self.days == 2:
                self.log('FOP_PROBE ' + json.dumps(self.describe_chain(futures[0].symbol)))
                chain = list(self.option_chain(futures[0].symbol))
                if chain:
                    self.add_future_contract(futures[0].symbol, Resolution.MINUTE)
                    option = self.add_future_option_contract(chain[0].symbol, Resolution.MINUTE)
                    props = option.symbol_properties
                    self.log('FOP_UNITS ' + json.dumps(dict(root=future.symbol.value,
                        symbol=str(option.symbol),strike=float(option.strike_price),
                        multiplier=float(props.contract_multiplier),
                        strike_multiplier=str(getattr(props,'strike_multiplier',None)),
                        price_magnifier=str(getattr(props,'price_magnifier',None)))))
        if self.days == 2:
            canonical = Symbol.create_canonical_option(self.spy)
            hist = list(self.history[OptionUniverse](canonical, timedelta(days=5)))
            self.log('HISTORY_PROBE ' + json.dumps([dict(day=str(row.end_time),
                count=len(list(row.data)),underlying=str(getattr(row, 'underlying', None)),
                sample=[dict(symbol=str(c.symbol),price=float(c.price),
                    iv=float(c.implied_volatility),delta=float(c.greeks.delta))
                    for c in list(row.data)[:1]]) for row in hist]))

    def on_end_of_algorithm(self):
        self.set_runtime_statistic('probe_days',str(self.days))
        self.set_runtime_statistic('scope','Data capability check; no strategy performance')
