"""Terminal-only protection against a second liquidation of already flat holdings."""
from AlgorithmImports import *
from System.Collections.Generic import List
import math


class FlatInsolvencyMarginModel(DefaultMarginCallModel):
    def __init__(self,algorithm):
        super().__init__(algorithm.portfolio,algorithm.default_order_properties)
        self.algorithm=algorithm

    def execute_margin_call(self,requests):
        a=self.algorithm
        equity=float(a.portfolio.total_portfolio_value)
        if (not getattr(a,'insolvency',None) or not math.isfinite(equity) or equity>0
                or a.positions or a.pending_combos or a.exit_requests
                or a.portfolio.invested or float(a.portfolio.total_margin_used)!=0
                or a.transactions.get_open_orders()):
            raise RuntimeError('Terminal margin protection requires a verified flat bankrupt account')
        if any(float(a.portfolio[r.symbol].quantity)!=0 for r in requests):
            raise RuntimeError('Obsolete liquidation request still has a holding')
        a.counts['terminal_margin_batches_skipped']+=1
        return List[OrderTicket]()
