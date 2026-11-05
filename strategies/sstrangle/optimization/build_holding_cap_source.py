"""Generate unqueued full-scope holding-cap research from the guarded parent."""
import ast,hashlib,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
PARENT=HERE/'cross_asset_guard_main.py'


def render():
    source=PARENT.read_text()
    source='from holding_age import validate_max_holding_days, age_exit_due\n'+source
    needle="        validate_equity_rv_threshold(cfg['min_equity_iv_rv'])"
    if source.count(needle)!=1:raise ValueError('Expected original initialization gate')
    source=source.replace(needle,needle+"\n        self.max_holding_days=validate_max_holding_days(cfg['max_holding_days'])",1)
    needle="                      'SPLIT' if self.states[key].get('split_warning') else None)"
    if source.count(needle)!=1:raise ValueError('Expected original product-noon management branch')
    source=source.replace(needle,"                      'AGE' if age_exit_due(trade['opened'],today,self.max_holding_days) else\n"+needle,1)
    needle='            monthly_only=True)'
    if source.count(needle)!=1:raise ValueError('Expected original opening annotation dictionary')
    source=source.replace(needle,'            max_holding_days=self.max_holding_days,monthly_only=True)',1)
    ast.parse(source);return source


if __name__=='__main__':
    text=render();(HERE/'holding_cap_main.py').write_text(text)
    receipt=dict(parent=str(PARENT),parent_sha256=hashlib.sha256(PARENT.read_bytes()).hexdigest(),generated_sha256=hashlib.sha256(text.encode()).hexdigest(),queued=False,native_age_exit_verified=False,strategy_calmar_proven=False,scope='Initialize validates deadline; on_data adds product-noon AGE after END/TIME precedence; open_candidate adds only the declared max_holding_days annotation. No symbol/date bans, settlement cash or input-price changes. Proposed full scope retains all equities/ETFs and15future roots.')
    (HERE/'holding_cap_source_receipt_20261019.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('Generated unqueued holding-cap source; frozen attempts preserved.')
