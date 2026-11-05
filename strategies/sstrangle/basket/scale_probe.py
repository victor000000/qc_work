"""In-cloud CL unit-consistency diagnostics; exports metadata and aggregates only."""
from AlgorithmImports import *
from collections import defaultdict
from datetime import datetime
import json
import statistics


class CLScaleProbe(QCAlgorithm):
    CONFIG = {}

    def initialize(self):
        self.set_start_date(2015,12,17)
        self.set_end_date(2015,12,30)
        self.set_cash(60000)
        self.future=Symbol(SecurityIdentifier.Parse('CL W7DWN4VXAQPT'),'CL20G16')
        self.add_future_contract(self.future,Resolution.MINUTE)
        self.symbols=[]
        for identifier in ['LO 306C040UEPLZ8|CL W7DWN4VXAQPT','LO W77ZYKW75SW4|CL W7DWN4VXAQPT']:
            symbol=Symbol(SecurityIdentifier.Parse(identifier),'LO')
            security=self.add_future_option_contract(symbol,Resolution.MINUTE)
            self.symbols.append(symbol)
            props=security.symbol_properties
            self.log('UNIT_METADATA '+json.dumps(dict(symbol_id=str(symbol.id),
                multiplier=float(props.contract_multiplier),tick=float(props.minimum_price_variation),
                price_magnifier=str(getattr(props,'price_magnifier',None)),
                strike_multiplier=str(getattr(props,'strike_multiplier',None)),
                quote_currency=str(security.quote_currency.symbol))))
        self.stats=defaultdict(lambda:defaultdict(list))
        self.references={}
        self.schedule.on(self.date_rules.every_day(),self.time_rules.at(11,55),self.reference)

    def reference(self):
        for contract in self.option_chain(self.future):
            if contract.symbol in self.symbols:
                self.references[contract.symbol]=float(contract.last_price)

    def on_data(self,data):
        for symbol in self.symbols:
            quote=data.quote_bars.get(symbol)
            if quote is None or quote.is_fill_forward:continue
            key=(str(self.time.date()),str(symbol.id))
            row=self.stats[key]
            row['quote_count'].append(1)
            security=self.securities[symbol]
            if quote.bid and float(quote.bid.close)>0:
                row['cache_bid_to_slice_bid'].append(float(security.bid_price)/float(quote.bid.close))
            trade=data.bars.get(symbol)
            if trade is not None and not trade.is_fill_forward and float(trade.close)>0:
                row['quote_mid_to_trade'].append(float(quote.close)/float(trade.close))
            ref=self.references.get(symbol)
            if ref and ref>0:row['quote_mid_to_prior_chain'].append(float(quote.close)/ref)
            strike=float(symbol.id.strike_price)
            row['quote_exceeds_strike'].append(float(quote.close)>strike)

    def on_end_of_algorithm(self):
        for (day,symbol),stats in sorted(self.stats.items()):
            report={}
            for key,values in stats.items():
                report[key]=dict(n=len(values),minimum=min(values),median=statistics.median(values),maximum=max(values))
            self.log('UNIT_CONSISTENCY '+json.dumps(dict(day=day,symbol_id=symbol,statistics=report)))
        self.set_runtime_statistic('scope','Unit metadata and consistency aggregates; no historical quote export')
        self.set_runtime_statistic('diagnostic_days',str(len({d for d,s in self.stats})))
