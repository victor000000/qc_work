"""ss45dte -- 45-DTE entry / 21-DTE exit short strangle on the five measured names.

QuantConnect LEAN algorithm. Self-contained: the queue stores one code blob, so this file
must not import workspace modules.

What it implements, exactly as specified in
dte_21_screener/reports/loss_attribution_2026-10-25/web/strategy.html:

  * monthly expiry nearest 45 DTE, delta-neutral, both legs inside 0.16-0.22
  * size by p5:  contracts = (equity * tail / N) / (2 * vega * p5_sigma)
  * exit everything at 21 DTE
  * MODE controls the single rule under test:
        "exit21"  exit at 21 DTE (the specification)
        "hold"    hold to expiry (the control, A vs B)
        "stop"    exit at 21 DTE, plus close on |delta| > STOP_DELTA
  * no rolling, no re-centring, no adding legs

p5_SIGMA values are the per-name 5th percentile of (implied minus realised) measured on
three years of daily data; see evidence.html E6. Names outside the measured set are not
traded, because an unmeasured p5 would be a guess.
"""
from AlgorithmImports import *
import math

MODE = "exit21"          # exit21 | hold | stop
SHORT_TEST = True        # three-month probe window; set False for the full period
TAIL_BUDGET = 0.05       # share of equity lost if every name hits its p5 at once
DELTA_LO, DELTA_HI = 0.16, 0.22
ENTRY_DTE, EXIT_DTE = 45, 21
STOP_DELTA = 0.35
P5_SIGMA = {"CRWD": 44.7, "EWZ": 12.7, "META": 21.2, "TLT": 2.5, "SWKS": 52.3}
UNIVERSE = list(P5_SIGMA)


class Ss45Dte(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2024, 1, 2)
        self.SetEndDate(2024, 3, 29) if SHORT_TEST else self.SetEndDate(2026, 10, 23)
        self.count = dict(chain=0, band=0, qty=0, entry=0, exit=0)
        self.SetCash(150000)
        self.legs = {}        # ticker -> [call_symbol, put_symbol]
        self.expiry = {}      # ticker -> expiry datetime of the strangle
        self.last_entry = {}  # ticker -> datetime
        self.option = {}
        for ticker in UNIVERSE:
            self.AddEquity(ticker, Resolution.Minute)
            opt = self.AddOption(ticker, Resolution.Minute)
            opt.SetFilter(self._filter)
            self.option[ticker] = opt

    def _filter(self, universe):
        # One monthly expiry near the target, strikes wide enough for a 20-delta pick.
        return universe.Expiration(ENTRY_DTE - 14, ENTRY_DTE + 14).Strikes(-20, 20)

    def OnData(self, slice):
        for ticker in UNIVERSE:
            chain = slice.OptionChains.get(self.option[ticker].Symbol)
            if chain is None:
                continue
            if ticker in self.legs:
                self._manage(ticker)
            elif self._can_enter(ticker):
                self._enter(ticker, chain)

    def _can_enter(self, ticker):
        last = self.last_entry.get(ticker)
        return last is None or (self.Time - last).days >= 5

    def _enter(self, ticker, chain):
        target = self.Time + timedelta(days=ENTRY_DTE)
        expiry = min({c.Expiry for c in chain}, key=lambda e: abs((e - target).days))
        dte = (expiry - self.Time).days
        if abs(dte - ENTRY_DTE) > 12:
            return
        leg = [c for c in chain if c.Expiry == expiry]
        if not leg:
            return
        spot = self.Securities[chain.Underlying.Symbol].Price
        scored = [(c, self._delta(c, spot, dte)) for c in leg]
        scored = [(c, d) for c, d in scored if d is not None]
        calls = [(c, d) for c, d in scored if c.Right == OptionRight.Call and DELTA_LO <= d <= DELTA_HI]
        puts = [(c, d) for c, d in scored if c.Right == OptionRight.Put and DELTA_LO <= -d <= DELTA_HI]
        if not calls or not puts:
            self.count['band'] += 1
            return
        mid = (DELTA_LO + DELTA_HI) / 2
        call = min(calls, key=lambda x: abs(x[1] - mid))[0]
        put = min(puts, key=lambda x: abs(-x[1] - mid))[0]
        qty = self._contracts(ticker, call, put, dte)
        if qty < 1:
            self.count['qty'] += 1
            return
        self.Sell(call.Symbol, qty)
        self.Sell(put.Symbol, qty)
        self.count['entry'] += 1
        self.legs[ticker] = [call.Symbol, put.Symbol]
        self.expiry[ticker] = expiry
        self.last_entry[ticker] = self.Time

    def _delta(self, contract, spot, dte):
        """Delta from LEAN when available, else analytic from the contract's own IV."""
        if contract.Greeks is not None:
            return float(contract.Greeks.Delta)
        iv = contract.ImpliedVolatility
        t = dte / 365.0
        if not iv or iv <= 0 or spot <= 0 or t <= 0 or contract.Strike <= 0:
            return None
        d1 = (math.log(spot / contract.Strike) + 0.5 * iv * iv * t) / (iv * math.sqrt(t))
        nd1 = 0.5 * (1.0 + math.erf(d1 / math.sqrt(2.0)))
        return nd1 if contract.Right == OptionRight.Call else nd1 - 1.0

    def _vega(self, contract, dte):
        """Per-contract vega per 1.00 of vol, from the contract's own implied vol."""
        iv = contract.ImpliedVolatility
        if not iv or iv <= 0:
            return None
        spot = self.Securities[contract.Symbol.Underlying].Price
        t = dte / 365.0
        if spot <= 0 or t <= 0:
            return None
        d1 = (math.log(spot / contract.Strike) + 0.5 * iv * iv * t) / (iv * math.sqrt(t))
        pdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
        return spot * pdf * math.sqrt(t) * 100.0

    def _contracts(self, ticker, call, put, dte):
        vc, vp = self._vega(call, dte), self._vega(put, dte)
        if not vc or not vp:
            return 0
        budget = self.Portfolio.TotalPortfolioValue * TAIL_BUDGET / len(UNIVERSE)
        return int(budget // (2 * max(vc, vp) * P5_SIGMA[ticker]))

    def _manage(self, ticker):
        dte = (self.expiry[ticker] - self.Time).days
        close = dte <= 0
        if MODE != "hold" and dte <= EXIT_DTE:
            close = True
        if MODE == "stop" and not close:
            for symbol in self.legs[ticker]:
                greeks = self.Securities[symbol].Greeks
                if greeks is not None and abs(greeks.Delta) > STOP_DELTA:
                    close = True
        if close:
            for symbol in self.legs[ticker]:
                if self.Securities[symbol].Invested:
                    self.Liquidate(symbol)
            self.count['exit'] += 1
            del self.legs[ticker]
            del self.expiry[ticker]

    def OnEndOfAlgorithm(self):
        for k, v in self.count.items():
            self.SetRuntimeStatistic('n_' + k, str(v))
        self.SetRuntimeStatistic('equity', f'{self.Portfolio.TotalPortfolioValue:.0f}')
