"""Download market-data references for an existing baseline; never places orders."""
from AlgorithmImports import *
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
from reference_tape import ROWS


class BaselineDataReference(QCAlgorithm):
    CONFIG = {}

    def initialize(self):
        self.set_start_date(2026,9,30)
        self.set_end_date(2026,9,30)
        self.set_cash(250000)
        self.executions = ROWS
        self.symbols = {}
        for ticker in sorted({r['underlying'] for r in self.executions}):
            security = self.add_equity(ticker, Resolution.MINUTE)
            security.set_data_normalization_mode(DataNormalizationMode.RAW)
            self.symbols[ticker] = security.symbol
        self.schedule.on(self.date_rules.every_day(),self.time_rules.at(10,0),self.export_reference)

    def export_reference(self):
        rows = self.executions
        start = datetime.fromisoformat(min(r['timestamp'][:10] for r in rows))
        end = datetime.fromisoformat(max(r['timestamp'][:10] for r in rows))+timedelta(days=1)
        daily, quotes = [], []
        for ticker,symbol in self.symbols.items():
            for bar in self.history[TradeBar](symbol,start,end,Resolution.DAILY):
                daily.append(dict(symbol=ticker,date=str(bar.time.date()),open=float(bar.open),
                    high=float(bar.high),low=float(bar.low),close=float(bar.close),volume=float(bar.volume),
                    end_time=str(bar.end_time),fill_forward=bool(bar.is_fill_forward)))
        ny = ZoneInfo('America/New_York')
        for row in rows:
            when = datetime.fromisoformat(row['timestamp']).astimezone(ny).replace(tzinfo=None)
            symbol = Symbol.create_option(self.symbols[row['underlying']],Market.USA,OptionStyle.AMERICAN,
                OptionRight.PUT if row['call_put']=='P' else OptionRight.CALL,
                row['strike'],datetime.fromisoformat(row['expiry']))
            bars = [b for b in self.history[QuoteBar](symbol,when-timedelta(minutes=5),when,
                        Resolution.MINUTE,fill_forward=False)
                    if b.end_time <= when and not b.is_fill_forward and b.bid is not None and b.ask is not None]
            record = dict(order_id=row['order_id'],symbol=row['symbol'],timestamp=row['timestamp'],
                          qc_fill=row['qc_price'],quantity=row['quantity'],bars=len(bars))
            if bars:
                bar = max(bars,key=lambda b:b.end_time)
                record.update(bar_end=bar.end_time.replace(tzinfo=ny).isoformat(),
                    bid=float(bar.bid.close),ask=float(bar.ask.close),
                    age_minutes=(when-bar.end_time).total_seconds()/60)
            quotes.append(record)
        payload = dict(source='QuantConnect historical reference, independent of baseline fills',
            baseline=self.CONFIG['baseline'],price_basis='raw',underlying_daily=daily,option_quotes=quotes)
        encoded = json.dumps(payload)
        if not self.object_store.save(self.CONFIG['object_key'],encoded):
            raise RuntimeError('Could not save data reference')
        self.set_runtime_statistic('reference_key',self.CONFIG['object_key'])
        self.set_runtime_statistic('underlying_daily_rows',str(len(daily)))
        self.set_runtime_statistic('execution_quote_checks',str(len(quotes)))
        self.set_runtime_statistic('execution_quotes_found',str(sum(r['bars']>0 for r in quotes)))
        self.log('REFERENCE '+json.dumps(dict(key=self.CONFIG['object_key'],bytes=len(encoded))))
