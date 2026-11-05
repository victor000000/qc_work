"""Native completed-price feature probe; aggregate results ONLY, no trading."""
from AlgorithmImports import *
from collections import Counter
from datetime import date,datetime,time,timedelta
from zoneinfo import ZoneInfo
from completed_volatility import CompletedPrice,CompletedVolatilityWindow
import hashlib,json,math
import numpy as np

class VolatilitySourceProbe(QCAlgorithm):
    CONFIG = {}
    def initialize(self):
        equity=self.CONFIG['probe']=='equity'
        self.set_start_date(*( (2020,8,3) if equity else (2017,7,5) ))
        self.set_end_date(*( (2020,9,4) if equity else (2017,7,7) ))
        self.set_cash(60000);self.set_time_zone('America/New_York')
        self.settings.daily_precise_end_time=True
        self.counts=Counter();self.digest=hashlib.sha256();self.symbols=[];self.delivery_window=CompletedVolatilityWindow()
        if equity:
            for ticker in ['SPY','TSLA']:
                sec=self.add_equity(ticker,Resolution.DAILY);sec.set_data_normalization_mode(DataNormalizationMode.RAW);self.symbols.append(sec.symbol)
        else:
            root=self.add_future('ZW',Resolution.DAILY);root.set_filter(lambda u:u.contracts([]));self.canonical=root.symbol
        self.schedule.on(self.date_rules.every_day(),self.time_rules.at(12,0),self.probe)
        self.set_runtime_statistic('vol_scope','Aggregate source/feature engineering only; synthetic unit IV; no option signals or trades')

    @staticmethod
    def last_completed_session(hours,local):
        closes=set()
        for offset in range(9):
            day=datetime.combine(local.date()-timedelta(days=offset),time())
            close=hours.get_last_daily_market_close(day,False)
            if close<=local:closes.add(close)
        if not closes:raise RuntimeError('No completed native calendar close')
        return max(closes).date()

    @staticmethod
    def contiguous(hours,days):
        # Enumerate daily regular final closes so futures Sunday evening is
        # not mistaken for a completed standalone daily session.
        expected=set();day=days[0]-timedelta(days=8)
        while day<=days[-1]:
            close=hours.get_last_daily_market_close(datetime.combine(day,time()),False)
            if days[0]<=close.date()<=days[-1]:expected.add(close.date())
            day+=timedelta(days=1)
        return days==sorted(expected)

    def probe(self):
        self.plot('Trading period','Equity',float(self.portfolio.total_portfolio_value))
        if self.CONFIG['probe']=='futures' and not self.symbols:
            rows=sorted(self.futures_chain(self.canonical),key=lambda c:float(c.volume),reverse=True)
            for row in rows[:2]:
                symbol=row.symbol
                self.add_future_contract(symbol,Resolution.DAILY);self.symbols.append(symbol)
            if len(self.symbols)!=2:raise RuntimeError('Two actual native deliveries required')
        for symbol in self.symbols:
            sec=self.securities[symbol]
            if not sec.exchange.hours.is_date_open(sec.local_time):continue
            self.probe_symbol(symbol)

    def probe_symbol(self,symbol):
        self.counts['requests']+=1;sec=self.securities[symbol];future=self.CONFIG['probe']=='futures'
        mode=DataNormalizationMode.RAW if future else DataNormalizationMode.SCALED_RAW
        bars=list(self.history[TradeBar](symbol,65,Resolution.DAILY,fill_forward=False,data_normalization_mode=mode))
        exchange_tz=ZoneInfo(str(sec.exchange.time_zone));asof=self.time.replace(tzinfo=ZoneInfo('America/New_York'))
        expected=self.last_completed_session(sec.exchange.hours,sec.local_time)
        points=[]
        epoch=('native_raw' if future else 'scaled_raw')+':'+str(self.time.date())
        for bar in bars:
            if bar.symbol!=symbol:raise RuntimeError('History native identity changed')
            if bar.is_fill_forward:raise RuntimeError('History unexpectedly fill-forward')
            end=bar.end_time.replace(tzinfo=exchange_tz)
            if end>asof:raise RuntimeError('Future completed-price history')
            if end.date()>=self.time.date():raise RuntimeError('Current-day daily bar entered noon feature')
            points.append(CompletedPrice(str(symbol.id),end.date(),end,float(bar.close),epoch))
        points=points[-61:];self.counts['sampled_closes']+=len(points)
        if len(points)!=61:raise RuntimeError('Full61completed source observations required')
        if points[-1].session!=expected:raise RuntimeError('Daily source end label disagrees with native completed-session calendar')
        continuous=self.contiguous(sec.exchange.hours,[p.session for p in points])
        if not continuous:raise RuntimeError('Missing or mislabelled native completed sessions')
        window=CompletedVolatilityWindow();window.replace_rebased_history(points,asof,self.time.date(),consecutive=continuous)
        # 1.0 is an explicit synthetic arithmetic input, never a market IV.
        f=window.features(1.,expected_last_session=expected)
        if not f.ready:raise RuntimeError('Native volatility feature unavailable:'+f.reason)
        returns=np.diff(np.log(np.asarray([p.price for p in points],dtype=float)))
        reference20=float(np.std(returns[-20:],ddof=1)*math.sqrt(252));reference60=float(np.std(returns,ddof=1)*math.sqrt(252))
        if not math.isclose(f.realized20,reference20,rel_tol=1e-10,abs_tol=1e-12) or not math.isclose(f.realized60,reference60,rel_tol=1e-10,abs_tol=1e-12):raise RuntimeError('Independent numpy feature mismatch')
        self.counts['numpy_matches']+=1;self.counts['aligned_windows']+=1
        self.digest.update(json.dumps([str(symbol.id),str(expected),f.realized20,f.realized60],separators=(',',':')).encode())
        if future:
            previous=self.delivery_window.identity
            self.delivery_window.observe(points[-1],asof,self.time.date(),consecutive=True)
            if previous is not None and previous!=str(symbol.id):
                if len(self.delivery_window.points)!=1:raise RuntimeError('Delivery gap became a price return')
                self.counts['native_delivery_resets']+=1
        elif symbol.value=='TSLA' and self.time.date()>=date(2020,9,1):
            raw=list(self.history[TradeBar](symbol,65,Resolution.DAILY,fill_forward=False,data_normalization_mode=DataNormalizationMode.RAW))[-61:]
            raw_returns=np.diff(np.log(np.asarray([float(b.close) for b in raw],dtype=float)))
            if len(raw)!=61:raise RuntimeError('Split-control history incomplete')
            if max(abs(raw_returns))>.9 and max(abs(returns))<.5:self.counts['split_basis_verified']+=1
            else:raise RuntimeError('Expected native split rebase control not established')
        self.counts['equity_windows' if not future else 'futures_windows']+=1

    def on_splits(self,splits):
        for _,split in splits.items():
            if split.type!=SplitType.WARNING:self.counts['actual_split_events']+=1

    def on_end_of_algorithm(self):
        if list(self.transactions.get_orders()) or self.portfolio.invested or abs(float(self.portfolio.total_portfolio_value)-60000)>.001:raise RuntimeError('Source probe changed account or orders')
        if not self.counts['aligned_windows'] or self.counts['numpy_matches']!=self.counts['aligned_windows']:raise RuntimeError('Missing native feature comparisons')
        if self.CONFIG['probe']=='equity' and not(self.counts['split_basis_verified'] and self.counts['actual_split_events']):raise RuntimeError('Corporate-action source control missing')
        if self.CONFIG['probe']=='futures' and not self.counts['native_delivery_resets']:raise RuntimeError('Native delivery reset control missing')
        for key,value in self.counts.items():self.set_runtime_statistic('vol_'+key,str(value))
        # Irreversible aggregate test checksum, never an encoded price export.
        self.log('VOLATILITY_SOURCE_CHECKSUM '+self.digest.hexdigest())
        self.set_runtime_statistic('vol_synthetic_iv_input','1.0; arithmetic only, not a source IV')
        self.set_runtime_statistic('vol_no_trades','1')
