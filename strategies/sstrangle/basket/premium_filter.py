"""Apply verified source-unit conversion before LEAN caching, fills and margin."""
from AlgorithmImports import *
from premium_units import premium_factor


class PremiumUnitFilter(SecurityDataFilter):
    def __init__(self,counts):
        super().__init__()
        self.counts=counts
        self.seen={}

    def filter(self,security,data):
        # Fill-forward clones inherit the already corrected source bar.
        if data.is_fill_forward or not isinstance(data,(QuoteBar,TradeBar)):
            return True
        symbol=security.symbol
        factor=premium_factor(symbol.id.symbol,symbol.underlying.id.symbol,data.time.date())
        if factor==1:return True
        kind='quote' if isinstance(data,QuoteBar) else 'trade'
        key=(str(symbol.id),kind)
        token=(data.end_time,int(data.GetHashCode()))
        if self.seen.get(key)==token:return True
        self.seen[key]=token
        if isinstance(data,QuoteBar):
            for side in (data.bid,data.ask):
                if side:
                    side.open=float(side.open)*factor;side.high=float(side.high)*factor
                    side.low=float(side.low)*factor;side.close=float(side.close)*factor
            data.value=float(data.value)*factor
        else:
            data.open=float(data.open)*factor;data.high=float(data.high)*factor
            data.low=float(data.low)*factor;data.close=float(data.close)*factor
        self.counts['unit_repaired_'+kind+'_bars']+=1
        return True
