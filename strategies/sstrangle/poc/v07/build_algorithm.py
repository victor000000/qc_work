"""Add the frozen pre-order alpha gate to the unchanged native adapters."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];P=Path(__file__).parent
s=(ROOT/'strategies/sstrangle/poc/v065/three_demos.py').read_text()
s=s.replace('from AlgorithmImports import *','from AlgorithmImports import *\n'+(P/'feature_rule.py').read_text())
s=s.replace('        cfg = self.CONFIG','        cfg = self.CONFIG\n        self.alpha_rows=[]\n        if cfg.get("alpha_enabled",False):\n            from feature_inputs import DAILY_ROWS\n            self.alpha_rows=DAILY_ROWS\n        self.alpha_value=None;self.alpha_source_day=None')
needle="        self.counts['scheduled_slots'] += 1\n"
gate='''        if self.CONFIG.get('alpha_enabled',False):
            self.alpha_value,self.alpha_source_day=feature_value(self.alpha_rows,str(today),self.CONFIG['alpha_feature'])
            if self.alpha_value is None:
                self.counts['skip_alpha_missing']+=1
                return
            if not rule_pass(self.alpha_value,float(self.CONFIG['alpha_threshold']),self.CONFIG['alpha_side']):
                self.counts['skip_alpha_filter']+=1
                return
            self.counts['alpha_admitted_slots']+=1
'''
assert s.count(needle)==1;s=s.replace(needle,needle+gate)
# The tolerance is only imposed on the condor; original naked baselines are preserved.
s=s.replace("        tolerance = float(self.CONFIG.get('delta_tolerance', .02))", "        tolerance = float(self.CONFIG.get('delta_tolerance', .02)) if self.kind=='condor' else 1.0")
s=s.replace("        record = dict(episode=episode,day=str(today),decision=str(self.time),spot=spot,", "        if self.CONFIG.get('alpha_enabled',False):\n            tag+=f';af={self.CONFIG[\"alpha_feature\"]};av={self.alpha_value:.17g};asof={self.alpha_source_day}'\n        record = dict(episode=episode,day=str(today),decision=str(self.time),spot=spot,")
(P/'three_demos.py').write_text(s)
