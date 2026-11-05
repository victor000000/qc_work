"""Unsubmitted accounting-probe candidate; never import into frozen strategies.

Pair this exercise model with SecurityPortfolioModel, NOT OptionPortfolioModel.
The generic portfolio model books the exercise fill at intrinsic exactly once.
Native option portfolio processing would add underlying-based intrinsic again.
"""
from AlgorithmImports import *
from datetime import date
import json


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


CONFIG = {}

class SettlementAccountingProbe(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2022,9,30)
        self.set_end_date(2022,10,4)
        self.set_cash(100000)
        self.set_time_zone(TimeZones.NEW_YORK)
        self.mode=CONFIG.get('accounting_mode','native_default')
        self.set_security_initializer(self.initialize_security)
        self.spx=self.add_index('SPX',Resolution.MINUTE).symbol
        option=self.add_index_option(self.spx,'SPXW',Resolution.MINUTE)
        option.set_filter(lambda u:u.include_weeklys().strikes(-100,100).expiration(0,0))
        self.chain_symbol=option.symbol
        self.sent=False
        self.filled=0
        self.expired=0
        self.expected_cash=100000.0
        self.records=[]
        self.targets=[(OptionRight.PUT,3585,2),(OptionRight.PUT,3590,-2),
                      (OptionRight.PUT,3600,1),(OptionRight.PUT,3605,-1),
                      (OptionRight.CALL,3585,1),(OptionRight.CALL,3590,-1),
                      (OptionRight.CALL,3600,-2),(OptionRight.CALL,3605,2)]

    def initialize_security(self, security):
        if security.type==SecurityType.INDEX_OPTION:
            security.set_fee_model(ConstantFeeModel(0))
            if self.mode=='native_reference':
                install_reference_accounting(security)

    def on_data(self,data):
        if self.sent or self.time.date()!=date(2022,9,30) or self.time.hour!=10 or self.time.minute!=0:return
        chain=data.option_chains.get(self.chain_symbol)
        if chain is None:raise RuntimeError('Missing fixed-contract chain')
        lookup={(x.right,float(x.strike)):x for x in chain if x.expiry.date()==self.time.date()}
        if any((right,strike) not in lookup for right,strike,qty in self.targets):raise RuntimeError('Missing preregistered contract')
        self.sent=True
        # Buy all hedges first; preserve the same sequence in both accounts.
        for right,strike,qty in sorted(self.targets,key=lambda x:x[2]<0):
            self.market_order(lookup[right,strike].symbol,qty,tag='accounting_probe_open')

    def on_order_event(self,event):
        if event.status!=OrderStatus.FILLED:return
        order=self.transactions.get_order_by_id(event.order_id)
        sec=self.securities[event.symbol]
        qty=float(event.fill_quantity)
        price=float(event.fill_price)
        fee=float(event.order_fee.value.amount)
        reference=None
        if order.type==OrderType.OPTION_EXERCISE:
            self.expired+=1
            reference=float(sec.underlying.close)
            intrinsic=max(0.0,reference-float(sec.strike_price) if sec.right==OptionRight.CALL else float(sec.strike_price)-reference)
            if self.mode=='native_reference' and abs(price-intrinsic)>1e-8:raise RuntimeError('Intrinsic event mismatch')
            cash=-qty*intrinsic*100-fee
        else:
            if order.tag!='accounting_probe_open':raise RuntimeError('Unexpected intervention')
            self.filled+=1
            cash=-qty*price*100-fee
        self.expected_cash+=cash
        self.records.append([str(event.symbol),qty,price,cash,reference])

    def on_end_of_algorithm(self):
        residual=sum(abs(float(x.holdings.quantity)) for x in self.securities.values() if x.type==SecurityType.INDEX_OPTION)
        error=float(self.portfolio.cash)-self.expected_cash
        core={'mode':self.mode,'opens':self.filled,'expiries':self.expired,'cash':float(self.portfolio.cash),'expected_cash':self.expected_cash,'cash_error':error,'residual':residual,'equity':float(self.portfolio.total_portfolio_value),'realized':float(self.portfolio.total_profit)}
        for key,value in core.items():self.set_runtime_statistic('AC_'+key,str(value))
        raw=json.dumps(self.records,separators=(',',':'))
        if len(raw)>4800:raise RuntimeError('Accounting telemetry capacity')
        for i in range(30):self.set_runtime_statistic('AR'+str(i).zfill(2),raw[i*160:(i+1)*160] or ' ')
        self.set_runtime_statistic('ARlen',str(len(raw)))
        if self.filled!=8 or self.expired!=8 or residual!=0 or abs(error)>0.01:raise RuntimeError('Accounting reconciliation failed')
