"""Freeze corrected margin baseline and a predeclared one-pair pilot."""
from pathlib import Path
import ast,hashlib,json
p=Path(__file__).parent
base=(p/'strict_full_v3.py').read_text()
start=base.index('CONFIG = ');end=base.index('\n',start)
cfg=ast.literal_eval(base[start+9:end]);cfg.update(trade_margin_cap=.5,max_open_pairs=5)
base=base[:start]+'CONFIG = '+repr(cfg)+base[end:]
base=base.replace('\n\ndef target_exit', '''\n\ndef standalone_margin(values):
    """QC initial margins are signed; reserve positive cash for each short leg."""
    vals=[float(v) for v in values]
    if not vals or any(not math.isfinite(v) or v==0 for v in vals):return float('inf')
    return sum(abs(v) for v in vals)


def target_exit''')
base=base.replace("        quotes=[self.quote(r) for r in p['legs']]", "        if len(self.states)>=CONFIG['max_open_pairs']:self.counts['skip_positions']+=1;return\n        quotes=[self.quote(r) for r in p['legs']]")
base=base.replace("margin=sum(float(self.securities[r['symbol']].buying_power_model.get_initial_margin_requirement(InitialMarginParameters(self.securities[r['symbol']],-quantity)).value) for r in p['legs'])", "margin=standalone_margin(self.securities[r['symbol']].buying_power_model.get_initial_margin_requirement(InitialMarginParameters(self.securities[r['symbol']],-quantity)).value for r in p['legs'])")
base=base.replace("        if float(self.portfolio.total_margin_used)+margin>nav*CONFIG['margin_cap']:", "        if margin>nav*CONFIG['trade_margin_cap'] or float(self.portfolio.total_margin_used)+margin>nav*CONFIG['margin_cap']:")
base=base.replace('automatic v3; explicit mechanical variant','automatic v5; corrected cost and positive margin')
# Preserve the strict research baseline as the canonical implementation.
(p.parents[1]/'strategy.py').write_text(base)
for name,overrides in [('onepair_cost_v5',{'risk_sizing':False}),('pilot_onepair_v5',{'trade_budget':.01,'cluster_budget':.01,'book_budget':.02,'margin_cap':.20,'trade_margin_cap':.05,'max_pairs':1,'max_open_pairs':2})]:
 c=cfg|overrides;s=base.replace('CONFIG = '+repr(cfg),'CONFIG = '+repr(c))
 (p/(name+'.py')).write_text(s)
 (p/(name+'.json')).write_text(json.dumps({'config':c,'source_sha256':hashlib.sha256(s.encode()).hexdigest(),'declared_before_run':True,'note':'Pilot changes risk tolerance; not a live approval or performance-optimized rule'},indent=2)+'\n')
print('Frozen corrected baseline and one-pair pilot; canonical strict budget remains 0.5%.')
