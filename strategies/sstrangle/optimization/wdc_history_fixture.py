"""Bounded end-of-session quote availability counts; never quotes or new fills."""
from AlgorithmImports import QuoteBar,Resolution
from datetime import datetime
import json
from wdc_original_fixture import WDCQuoteRegression

HISTORY_FIELDS=('bars','same_session','minute','fill_forward','future','positive_bid','positive_ask','noncrossed')


class WDCHistoryRegression(WDCQuoteRegression):
    CONFIG = {}

    def history_summary(self,symbol,start,end):
        if end>self.time or end<=start:raise RuntimeError('Invalid retrospective-only history bound')
        counts=dict.fromkeys(HISTORY_FIELDS,0)
        for bar in self.history[QuoteBar](symbol,start,end,Resolution.MINUTE,fill_forward=False):
            counts['bars']+=1
            counts['same_session']+=int(bar.end_time.date()==start.date())
            counts['minute']+=int((bar.end_time-bar.time).total_seconds()==60)
            counts['fill_forward']+=int(bar.is_fill_forward)
            counts['future']+=int(bar.end_time>end)
            bid=bar.bid.close if bar.bid is not None else 0
            ask=bar.ask.close if bar.ask is not None else 0
            counts['positive_bid']+=int(bid>0);counts['positive_ask']+=int(ask>0)
            counts['noncrossed']+=int(ask>=bid)
        return [counts[k] for k in HISTORY_FIELDS]

    def on_end_of_algorithm(self):
        self.process_pending_combos()
        before=(float(self.portfolio.cash),float(self.portfolio.total_portfolio_value),
                tuple(sorted((str(s.id),float(self.portfolio[s].quantity)) for s in self.subscribed_options)),len(self.all_tickets))
        results={}
        end=min(self.time,datetime(2019,4,22,16))
        for side,strike in [('put',47.5),('call',57.5)]:
            symbol=self.contracts[(side=='put',strike)]
            for label,start,stop in [('prior',datetime(2019,4,18,12),datetime(2019,4,18,16)),
                                      ('due',datetime(2019,4,22,12),end)]:
                results[side+'_'+label]=self.history_summary(symbol,start,stop)
        after=(float(self.portfolio.cash),float(self.portfolio.total_portfolio_value),
               tuple(sorted((str(s.id),float(self.portfolio[s].quantity)) for s in self.subscribed_options)),len(self.all_tickets))
        if before!=after:raise RuntimeError('Retrospective history changed actual account/orders')
        for key,values in results.items():self.set_runtime_statistic('wdch_'+key,json.dumps(values))
        self.set_runtime_statistic('wdch_unchanged','1')
        super().on_end_of_algorithm()
