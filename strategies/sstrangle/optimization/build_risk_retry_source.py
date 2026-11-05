"""Generate an unqueued prospective retry variant; preserve the active run."""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE / 'equity_rv_main.py'
METHOD = '''    def intraday_risk_exits(self):
        if getattr(self,'insolvency',None) or not self.positions:return
        slots=getattr(self,'fresh_risk_slots',None)
        if slots is None:
            slots=FreshRiskSlots(self.CONFIG['risk_interval_minutes'])
            self.fresh_risk_slots=slots
        slots.retain(self.positions)
        for key,trade in list(self.positions.items()):
            if not slots.due(key,self.utc_time):continue
            if key in self.pending_combos or key in self.exit_requests:continue
            put,call=[self.securities[trade[s]] for s in ('put','call')]
            if not all(s.exchange.exchange_open for s in (put,call)):continue
            dte=(trade['expiry']-self.time.date()).days
            # Product-open noon TIME exits retain their original priority.
            if dte<=self.time_exit_dte or self.time.date()>=self.end:continue
            if not self.voluntary_quote_ready(key):
                self.counts['research_risk_quote_guard_deferred']+=1;continue
            cost=(float(put.ask_price)+float(call.ask_price))*trade['multiplier']*trade['quantity']
            reason=close_reason(trade['cash'],trade['fees']+self.close_fees(trade),cost,
                trade['initial'],dte,stop_multiple=self.CONFIG['stop_multiple'])
            slots.complete(key,self.utc_time)
            self.counts['research_fresh_risk_evaluations']+=1
            if reason:
                self.exit_requests[key]=dict(reason=reason,day=self.time.date())
        self.process_exit_requests()
'''


def render():
    source = PARENT.read_text()
    tree = ast.parse(source)
    methods = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
               and n.name == 'intraday_risk_exits']
    if len(methods) != 1:
        raise ValueError('Expected one actual parent risk method')
    method = methods[0]
    lines = source.splitlines()
    lines[method.lineno - 1:method.end_lineno] = METHOD.rstrip().splitlines()
    result = 'from fresh_risk_slots import FreshRiskSlots\n' + '\n'.join(lines) + '\n'
    ast.parse(result)
    return result


if __name__ == '__main__':
    source = render()
    (HERE / 'risk_retry_main.py').write_text(source)
    receipt = dict(parent=str(PARENT), parent_sha256=hashlib.sha256(PARENT.read_bytes()).hexdigest(),
                   generated_sha256=hashlib.sha256(source.encode()).hexdigest(),
                   queued=False, native_validated=False, strategy_calmar_proven=False,
                   scope='Only intraday_risk_exits changes; per-position fresh evaluation consumes the fixed UTC interval. No quote/threshold/execution changes.')
    (HERE / 'risk_retry_source_receipt_20261019.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('Generated unqueued retry research source; active campaign unchanged.')
