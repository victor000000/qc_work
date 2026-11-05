"""Correct European expiry semantics and close-boundary entry admission."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];p=ROOT/'strategies/sstrangle/poc/v06/three_demos.py';s=p.read_text()
s=s.replace('    def initialize_security(self, security):\n        security.set_fee_model', '''    def initialize_security(self, security):
        if security.type==SecurityType.INDEX_OPTION:
            if security.symbol.id.option_style!=OptionStyle.EUROPEAN:
                raise RuntimeError('This adapter requires European SPXW options')
            # Suppress intraday discretionary assignment simulations. Native
            # expiry/delisting still settles cash and is independently audited.
            security.set_option_assignment_model(NullOptionAssignmentModel())
        security.set_fee_model''')
s=s.replace("        episode = today.strftime", """        if not self.is_market_open(self.index):
            self.counts['skip_session_closed']+=1
            return
        episode = today.strftime""")
s=s.replace("        if order.type == OrderType.OPTION_EXERCISE:\n            option", """        if order.type == OrderType.OPTION_EXERCISE:
            if 'before expiration' in (event.message or '').lower():
                raise RuntimeError('Unexpected premature European assignment')
            option""")
s=s.replace("        self.set_runtime_statistic('strategy_kind',self.kind)", "        self.set_runtime_statistic('assignment_policy','european_no_discretionary_early_assignment_native_expiry')\n        self.set_runtime_statistic('session_policy','index_open_at_submission')\n        self.set_runtime_statistic('strategy_kind',self.kind)")
p.write_text(s);compile(s,str(p),'exec');print('Added European assignment and early-close guard')
