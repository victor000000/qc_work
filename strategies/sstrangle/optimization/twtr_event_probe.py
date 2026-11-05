"""No-trade native warning/quote-availability probe for the actual TWTR holding.

Known entry/roll identities select the held pair only for source diagnostics.
No market prices, quote history, inferred settlements or performance are exported.
"""
from AlgorithmImports import *
from collections import Counter, defaultdict
from datetime import date, datetime, time
import hashlib
import json
from execution_base import TranscriptShortStrangle
from voluntary_quote_guard import BuybackQuote, voluntary_market_buyback_guard


def held_put_for(local):
    if local<datetime(2022,9,21,12):return None
    if local<datetime(2022,10,6,12):return 'put31'
    if local<datetime(2022,10,21,12):return 'put43'
    return 'put46'


class TWTRCorporateEventProbe(QCAlgorithm):
    CONFIG = {}

    def initialize(self):
        self.set_start_date(2022,9,20);self.set_end_date(2022,10,31)
        self.set_cash(60000);self.set_time_zone('America/New_York')
        self.spy=self.add_equity('SPY',Resolution.MINUTE).symbol
        self.twtr=Symbol(SecurityIdentifier.Parse('TWTR VLE97YS7S57P'),'TWTR')
        self.add_equity(self.twtr,Resolution.MINUTE).set_data_normalization_mode(DataNormalizationMode.RAW)
        native=[('put31','322PLPRB8BEEE','TWTR  221118P00031000'),
                ('call50','Y3LLKB7QB0W6','TWTR  221118C00050000'),
                ('put43','322PLPRD7REZQ','TWTR  221118P00043000'),
                ('put46','322PLPRDPMF52','TWTR  221118P00046000')]
        self.contracts={}
        for key,encoded,alias in native:
            s=Symbol(SecurityIdentifier.Parse('TWTR '+encoded+'|TWTR VLE97YS7S57P'),alias)
            self.add_option_contract(s,Resolution.MINUTE);self.contracts[key]=s
        self.counts=Counter(underlying_warning_seen=0);self.daily=defaultdict(Counter);self.events=[]
        self.warning_utc=None;self.noon_days=set()

    def source_quality(self):
        put=held_put_for(self.time)
        if put is None:return False,False
        symbols=[self.contracts[put],self.contracts['call50']]
        if not all(self.securities.contains_key(s) for s in symbols):return False,False
        securities=[self.securities[s] for s in symbols]
        if not all(s.exchange.exchange_open and s.is_tradable for s in securities):return False,False
        strict=all(TranscriptShortStrangle.good_quote(self,s) for s in securities)
        snapshots=[]
        for s in securities:
            bar=s.cache.get_data[QuoteBar]()
            snapshots.append(BuybackQuote(str(s.symbol.id),s.local_time,
                bar.end_time if bar is not None else None,
                bool(bar.is_fill_forward) if bar is not None else False,
                bar.ask.close if bar is not None and bar.ask is not None else None,
                s.bid_price,s.ask_price,s.symbol_properties.minimum_price_variation))
        guarded=voluntary_market_buyback_guard('STOP',False,snapshots).allowed
        return strict,guarded

    def on_data(self,data):
        for symbol,event in data.delistings.items():
            sid=str(symbol.id)
            if sid!=str(self.twtr.id) and sid not in {str(s.id) for s in self.contracts.values()}:continue
            record=dict(sid=sid,type=str(event.type),warning=bool(event.type==DelistingType.WARNING),callback_utc=self.utc_time.isoformat(),
                        algorithm_date=str(self.time.date()),source_time=str(event.time))
            self.events.append(record);self.log('TWTR_CORPORATE_EVENT '+json.dumps(record))
            if sid==str(self.twtr.id) and event.type==DelistingType.WARNING and self.warning_utc is None:
                self.warning_utc=self.utc_time;self.counts['underlying_warning_seen']=1
        strict,guarded=self.source_quality();d=self.daily[str(self.time.date())]
        d['data_slices']+=1;d['strict_pair_minutes']+=int(strict);d['guarded_pair_minutes']+=int(guarded)
        d['underlying_bars']+=int(self.twtr in data.bars)
        phase=held_put_for(self.time)
        if phase is not None:
            self.counts['phase_'+phase+'_strict']+=int(strict)
        if self.warning_utc is not None and self.utc_time>=self.warning_utc:
            d['strict_pair_after_warning']+=int(strict);d['guarded_pair_after_warning']+=int(guarded)
        if self.time.time()>=time(12) and self.time.date() not in self.noon_days:
            self.noon_days.add(self.time.date());d['strict_at_noon']=int(strict);d['guarded_at_noon']=int(guarded)
            d['warning_seen_by_noon']=int(self.warning_utc is not None)

    def on_end_of_algorithm(self):
        if list(self.transactions.get_orders()) or self.portfolio.invested or float(self.portfolio.total_portfolio_value)!=60000:
            raise RuntimeError('Corporate-event source probe changed account or traded')
        for day,counts in sorted(self.daily.items()):
            self.log('TWTR_EVENT_DAY '+json.dumps(dict(day=day,**dict(counts))))
        for key in ('strict_pair_after_warning','guarded_pair_after_warning'):
            self.counts[key]=sum(c.get(key,0) for c in self.daily.values())
        self.counts['observed_days']=len(self.daily);self.counts['corporate_events']=len(self.events)
        self.counts['underlying_bars']=sum(c.get('underlying_bars',0) for c in self.daily.values())
        for k,v in self.counts.items():self.set_runtime_statistic('twtr_event_'+k,str(v))
        self.set_runtime_statistic('twtr_event_no_trades','1')
        self.set_runtime_statistic('twtr_event_performance_claim','0')
        digest=hashlib.sha256(json.dumps(dict(events=self.events,daily={d:dict(c) for d,c in sorted(self.daily.items())}),sort_keys=True).encode()).hexdigest()
        self.log('TWTR_EVENT_CHECKSUM '+digest)
