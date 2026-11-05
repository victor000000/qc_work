"""Black-box probe: does the option chain, its expiries, Greeks and IV arrive at all?

Logs are unavailable (QC 100kb/day quota), so this reports through runtime statistics and
through orders: one share order on day one proves the equity pipeline and routing, and one
option order proves the chain is reachable and tradable.
"""
from AlgorithmImports import *

UNIVERSE = ["CRWD", "EWZ", "META", "TLT", "SWKS"]


class Diag2(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2024, 1, 2)
        self.SetEndDate(2024, 3, 29)
        self.SetCash(150000)
        self.n = 0
        self.reported = {}
        self.opt = {}
        for t in UNIVERSE:
            self.AddEquity(t, Resolution.Minute)
            o = self.AddOption(t, Resolution.Minute)
            o.SetFilter(lambda u: u.Expiration(33, 57).Strikes(-8, 8))
            self.opt[t] = o
        self.order_sent = False

    def OnData(self, slice):
        self.n += 1
        if self.n == 1:
            self.MarketOrder("CRWD", 1)

        chains = slice.OptionChains
        if chains is None or len(chains) == 0:
            if self.n == 40:
                self.SetRuntimeStatistic("chains", "none")
            return
        if self.n == 40:
            self.SetRuntimeStatistic("chains", str(len(chains)))

        for t in UNIVERSE:
            if t in self.reported:
                continue
            chain = chains.get(self.opt[t].Symbol)
            if chain is None:
                continue
            contracts = list(chain)
            if not contracts:
                continue
            c = contracts[0]
            greeks = c.Greeks
            iv = c.ImpliedVolatility
            self.reported[t] = True
            self.SetRuntimeStatistic(t + "_n", str(len(contracts)))
            self.SetRuntimeStatistic(t + "_exp", str(len({x.Expiry for x in contracts})))
            self.SetRuntimeStatistic(t + "_grk", "yes" if greeks is not None else "no")
            self.SetRuntimeStatistic(t + "_iv", ("%.3f" % iv) if iv else "0")
            if not self.order_sent:
                self.MarketOrder(c.Symbol, 1)
                self.order_sent = True

    def OnEndOfAlgorithm(self):
        self.SetRuntimeStatistic("reported", str(len(self.reported)))
        self.SetRuntimeStatistic("ondata", str(self.n))
