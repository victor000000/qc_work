"""Exact prior WBA control plus aggregate-only cache/Slice clock observations."""
from AlgorithmImports import QuoteBar
from wag_original_fixture import WAGExitRegression
from wag_quote_clock_diagnostics import WAGQuoteClockDiagnostics


class WAGClockRegression(WAGExitRegression):
    CONFIG = {}

    def initialize(self):
        self.clock_observer = WAGQuoteClockDiagnostics()
        self.clock_slice = None
        super().initialize()

    def on_data(self, data):
        self.clock_slice = data
        super().on_data(data)

    def diagnose(self, side, symbol):
        super().diagnose(side, symbol)
        self.clock_observer.observe_native(side, self, self.clock_slice, symbol, QuoteBar)
        # Observer values are cumulative. Assignment avoids counting them twice.
        for key, value in self.clock_observer.runtime_counts().items():
            self.predicates['clock_' + key] = value
