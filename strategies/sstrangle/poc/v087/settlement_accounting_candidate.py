"""Unsubmitted accounting-probe candidate; never import into frozen strategies.

Pair this exercise model with SecurityPortfolioModel, NOT OptionPortfolioModel.
The generic portfolio model books the exercise fill at intrinsic exactly once.
Native option portfolio processing would add underlying-based intrinsic again.
"""
from AlgorithmImports import *


class ReferenceCashExercise(DefaultExerciseModel):
    def __init__(self, official_by_expiry=None):
        self.official_by_expiry = official_by_expiry

    def option_exercise(self, option, order):
        if option.exercise_settlement != SettlementType.CASH:
            raise ValueError('Accounting probe permits cash-settled options only')
        expiry = str(option.symbol.id.date.date())
        if self.official_by_expiry is None:
            reference = float(option.underlying.close)
        else:
            # Missing data is an error; never silently fall back to native marks.
            reference = float(self.official_by_expiry[expiry])
        strike = float(option.strike_price)
        intrinsic = max(0.0, reference-strike if option.right == OptionRight.CALL else strike-reference)
        events = list(super().option_exercise(option, order))
        if len(events) != 1 or events[0].symbol != option.symbol:
            raise ValueError('Unexpected physical-delivery or multi-event exercise')
        event = events[0]
        event.fill_price = intrinsic
        event.is_in_the_money = intrinsic >= 0.01
        event.is_assignment = event.is_in_the_money and option.holdings.is_short
        event.message = 'Accounting probe intrinsic reference=' + str(reference)
        return [event]


def install_reference_accounting(security, official_by_expiry=None):
    if security.type != SecurityType.INDEX_OPTION or security.symbol.is_canonical():
        return
    security.set_portfolio_model(SecurityPortfolioModel())
    security.set_option_exercise_model(ReferenceCashExercise(official_by_expiry))
