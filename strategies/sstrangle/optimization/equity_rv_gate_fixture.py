"""Native test of actual prospective strategy admission methods; no trading."""
from AlgorithmImports import *
from collections import Counter
import hashlib,json,math
from equity_rv_strategy import ResearchShortStrangle
class EquityRVGateProbe(QCAlgorithm):
    CONFIG = {}
    def initialize(self):
        self.set_start_date(2020,8,31);self.set_end_date(2020,9,2);self.set_cash(60000);self.set_time_zone('America/New_York')
        self.settings.daily_precise_end_time=True
        self.spy=self.add_equity('SPY',Resolution.MINUTE).symbol;self.securities[self.spy].set_data_normalization_mode(DataNormalizationMode.RAW)
        self.symbols=[self.spy]+[Symbol.create(t,SecurityType.EQUITY,Market.USA) for t in ['TSLA','WBA','AMD']]
        self.counts=Counter();self.digest=hashlib.sha256()
        self.schedule.on(self.date_rules.every_day(),self.time_rules.at(12,0),self.probe)
    def equity_rv_for(self,symbol,iv):return ResearchShortStrangle.equity_rv_for(self,symbol,iv)
    def decision(self,key,reason):self.counts[reason]+=1
    def probe(self):
        for symbol in self.symbols:
            if symbol!=self.spy and not self.securities.contains_key(symbol):self.counts['unsubscribed_symbol_windows']+=1
            f,last=self.equity_rv_for(symbol,1.)
            if not f.ready:raise RuntimeError('Native equity RV window unavailable:'+f.reason)
            high=2*max(f.realized20,f.realized60);low=.5*max(f.realized20,f.realized60)
            candidate=dict(future=False,key=str(symbol.id),eq=symbol)
            good=dict(last_day=str(self.time.date()),iv=high);bad=dict(last_day=str(self.time.date()),iv=low)
            if not ResearchShortStrangle.admit_equity_rv(self,candidate,good):raise RuntimeError('Actual strategy failed high synthetic-IV gate')
            if ResearchShortStrangle.admit_equity_rv(self,candidate,bad):raise RuntimeError('Actual strategy admitted low synthetic-IV gate')
            if good['rv_samples']!=61 or good['rv_last_session']!=str(last) or not math.isclose(good['iv_rv'],2.,rel_tol=1e-12):raise RuntimeError('Actual source annotations disagree')
            self.counts['gate_pass_reject_pairs']+=1
            self.digest.update(json.dumps([str(symbol.id),str(last),good['rv20'],good['rv60'],good['iv_rv']],separators=(',',':')).encode())
        before=self.counts['equity_rv_history_requests'];metadata={}
        if not ResearchShortStrangle.admit_equity_rv(self,dict(future=True),metadata) or metadata!={'rv_policy':'future_original_rules'} or self.counts['equity_rv_history_requests']!=before:raise RuntimeError('Future original-rule branch changed')
        self.counts['verified_future_bypasses']+=1
        self.plot('Trading period','Equity',float(self.portfolio.total_portfolio_value))
    def on_end_of_algorithm(self):
        if self.counts['gate_pass_reject_pairs']!=12 or self.counts['verified_future_bypasses']!=3 or self.counts['unsubscribed_symbol_windows']!=9:raise RuntimeError('Native admission scope incomplete')
        if list(self.transactions.get_orders()) or self.portfolio.invested or float(self.portfolio.total_portfolio_value)!=60000:raise RuntimeError('Admission probe changed account')
        for key,value in self.counts.items():self.set_runtime_statistic('rv_gate_'+key,str(value))
        self.set_runtime_statistic('rv_gate_synthetic_IV','1');self.set_runtime_statistic('rv_gate_no_trades','1')
        self.log('EQUITY_RV_GATE_CHECKSUM '+self.digest.hexdigest())
