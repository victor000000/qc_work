"""Diagnostic probe for ss45dte: why does the option chain yield nothing?

Two-month window at minute resolution, heavy logging, no trading. Reads the same universe
and filter as strategy.py so the finding transfers.
"""
from AlgorithmImports import *
import math

UNIVERSE = ["CRWD", "EWZ", "META", "TLT", "SWKS"]


class Diag(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2024, 1, 2)
        self.SetEndDate(2024, 3, 29)
        self.SetCash(150000)
        self.seen = 0
        self.opt = {}
        for t in UNIVERSE:
            self.AddEquity(t, Resolution.Minute)
            o = self.AddOption(t, Resolution.Minute)
            o.SetFilter(lambda u: u.Expiration(33, 57).Strikes(-8, 8))
            self.opt[t] = o
        self.Debug("DIAG init: universe=" + ",".join(UNIVERSE))

    def OnData(self, slice):
        self.seen += 1
        chains = slice.OptionChains
        n = 0 if chains is None else len(chains)
        if self.seen <= 3 or self.seen % 500 == 0:
            self.Debug(f"DIAG day={self.Time:%Y-%m-%d} chains={n} seen={self.seen}")
        for t in UNIVERSE:
            chain = slice.OptionChains.get(self.opt[t].Symbol) if chains else None
            if chain is None:
                continue
            contracts = list(chain)
            if not contracts:
                continue
            c0 = contracts[0]
            spot = self.Securities[c0.Symbol.Underlying].Price
            greeks_ok = c0.Greeks is not None
            iv = c0.ImpliedVolatility
            expiries = sorted({c.Expiry for c in contracts})
            self.Debug(f"DIAG {self.Time:%Y-%m-%d} {t} n={len(contracts)} spot={spot:.2f} "
                       f"greeks={greeks_ok} iv={iv if iv else 0:.4f} expiries={len(expiries)} "
                       f"first={expiries[0]:%Y-%m-%d} last={expiries[-1]:%Y-%m-%d}")

    def OnEndOfAlgorithm(self):
        self.Debug(f"DIAG end: ondata_calls={self.seen}")
