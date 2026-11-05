"""Generate unqueued cross-asset voluntary guard research with fresh retries."""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE / 'risk_retry_main.py'


def render():
    source = PARENT.read_text()
    changes = [
        ('from voluntary_quote_guard import BuybackQuote, voluntary_market_buyback_guard',
         'from voluntary_quote_guard import BuybackQuote\nfrom cross_asset_buyback_guard import cross_asset_market_buyback_guard'),
        ("        if self.states[key]['future']:\n            return all(self.good_quote(security) for security in securities)\n", ''),
        ("decision = voluntary_market_buyback_guard('STOP',False,snapshots)",
         "decision = cross_asset_market_buyback_guard('STOP',self.states[key]['future'],snapshots)"),
        ("voluntary = reason in ('PROFIT','STOP') and not self.states[key]['future']",
         "voluntary = reason in ('PROFIT','STOP')")]
    for old, new in changes:
        if source.count(old) != 1:
            raise ValueError('Expected one preserved source transformation: ' + old)
        source = source.replace(old, new, 1)
    ast.parse(source)
    return source


if __name__ == '__main__':
    source = render()
    (HERE / 'cross_asset_guard_main.py').write_text(source)
    receipt = dict(parent=str(PARENT), parent_sha256=hashlib.sha256(PARENT.read_bytes()).hexdigest(),
                   generated_sha256=hashlib.sha256(source.encode()).hexdigest(),
                   queued=False, native_validated=False, strategy_calmar_proven=False,
                   scope='Extend identical native quote-side/spread validation to voluntary futures-option exits; retain all mandatory/broker-forced predicates and sequential futures closes. Includes prospective fresh-risk retry parent.')
    (HERE / 'cross_asset_guard_source_receipt_20261019.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('Generated unqueued cross-asset guard source; active campaign unchanged.')
