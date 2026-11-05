"""Build a versioned three-demo adapter without changing frozen Draft 0.5 source."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
s=(ROOT/'strategies/sstrangle/poc/optionomega_demo.py').read_text()
s=s.replace('    def combo_market_fill(self, order, parameters):','''    def __init__(self, legs=4):
        super().__init__()
        self.slip=0.05/legs

    def market_fill(self, security, order):
        fill=super().market_fill(security,order)
        if float(fill.fill_quantity):
            mid=(float(security.bid_price)+float(security.ask_price))/2
            fill.fill_price=mid+(self.slip if float(fill.fill_quantity)>0 else -self.slip)
            if fill.fill_price<=0: raise RuntimeError('Nonpositive midpoint modeled fill')
            fill.message=(fill.message or '')+f';oo_mid={mid:.8f};oo_slip={self.slip:.8f}'
        return fill

    def combo_market_fill(self, order, parameters):''')
s=s.replace('(0.0125 if float(fill.fill_quantity)>0 else -0.0125)','(self.slip if float(fill.fill_quantity)>0 else -self.slip)')
s=s.replace("f';oo_mid={mid:.8f};oo_slip=0.01250000'","f';oo_mid={mid:.8f};oo_slip={self.slip:.8f}'")
s=s.replace('        self.set_cash(100000)','''        self.kind=cfg.get('strategy_kind','condor')
        self.leg_count={'condor':4,'strangle':2,'put':1}[self.kind]
        self.start_capital=float(cfg.get('start_capital',100000))
        self.set_cash(self.start_capital)''')
s=s.replace('security.set_fill_model(OmegaMidpointFill())','security.set_fill_model(OmegaMidpointFill(self.leg_count))')
s=s.replace('equity - 100000 - self.native_cash','equity - self.start_capital - self.native_cash').replace('equity-100000-self.native_cash','equity-self.start_capital-self.native_cash')
s=s.replace('        if not puts or not calls:',"        if not puts or (self.kind!='put' and not calls):")
s=s.replace('abs(float(c.greeks.delta)+0.20)',"abs(float(c.greeks.delta)+float(self.CONFIG.get('put_target',0.20)))")
s=s.replace("        call = min(calls, key=lambda c:(abs(float(c.greeks.delta)-0.08), float(c.strike)))", "        call = min(calls, key=lambda c:(abs(float(c.greeks.delta)-float(self.CONFIG.get('call_target',0.08))), float(c.strike))) if self.kind!='put' else None")
a=s.index('        by_key =');b=s.index("        if self.fill_convention == 'oo_midpoint_package':",a)
s=s[:a]+'''        if self.kind=='condor':
            by_key = {(c.right,float(c.strike)):c for c in contracts}
            long_put = by_key.get((OptionRight.PUT,float(put.strike)-20))
            long_call = by_key.get((OptionRight.CALL,float(call.strike)+20))
            if long_put is None or long_call is None:
                self.counts['skip_missing_20point_wing'] += 1
                return
            selected=[(long_put,1),(put,-1),(call,-1),(long_call,1)]
        elif self.kind=='strangle': selected=[(put,-1),(call,-1)]
        else: selected=[(put,-1)]
''' +s[b:]
s=s.replace('if credit <= 0 or credit >= 20:',"if credit <= 0 or (self.kind=='condor' and credit >= 20):")
s=s.replace('max_loss = (20-credit)*100+4*1.18',"max_loss = (20-credit)*100+4*1.18 if self.kind=='condor' else 0")
s=s.replace('if day_reserve+max_loss >',"if self.kind=='condor' and day_reserve+max_loss >")
s=s.replace("float(call.greeks.delta)","(float(call.greeks.delta) if call else 0.0)")
s=s.replace("v=expiry5","v=expiry6")
s=s.replace("        tickets = self.combo_market_order([Leg.create(c.symbol,q) for c,q in selected],\n                                           1, asynchronous=True, tag=tag)","""        if self.leg_count==1:
            tickets=[self.market_order(put.symbol,-1,asynchronous=True,tag=tag)]
        else:
            tickets = self.combo_market_order([Leg.create(c.symbol,q) for c,q in selected],
                                               1, asynchronous=True, tag=tag)""")
s=s.replace('if len(tickets) != 4:', 'if len(tickets) != self.leg_count:').replace("'Combo did not return four tickets: '","'Wrong native ticket count: '")
s=s.replace("        self.set_runtime_statistic('baseline','audio_spx_20put_8call_20w_13slots')", """        self.set_runtime_statistic('baseline',self.kind+'_spx_0dte_13slots')
        self.set_runtime_statistic('strategy_kind',self.kind)
        self.set_runtime_statistic('leg_count',str(self.leg_count))
        self.set_runtime_statistic('start_capital',str(self.start_capital))
        self.set_runtime_statistic('put_target',str(self.CONFIG.get('put_target',0.20)))
        self.set_runtime_statistic('call_target',str(self.CONFIG.get('call_target',0.08)))""")
s=s.replace('        self.max_reconciliation_error = 0.0', '        self.max_reconciliation_error = 0.0\n        self.max_margin_used=0.0\n        self.min_margin_remaining=self.start_capital')
s=s.replace('    def on_data(self, data):\n        self.process_pending()', '    def on_data(self, data):\n        self.process_pending()\n        self.max_margin_used=max(self.max_margin_used,float(self.portfolio.total_margin_used))\n        self.min_margin_remaining=min(self.min_margin_remaining,float(self.portfolio.margin_remaining))')
s=s.replace("        self.set_runtime_statistic('strategy_kind',self.kind)", "        self.set_runtime_statistic('max_margin_used_1m',f'{self.max_margin_used:.2f}')\n        self.set_runtime_statistic('min_margin_remaining_1m',f'{self.min_margin_remaining:.2f}')\n        self.set_runtime_statistic('strategy_kind',self.kind)")
(ROOT/'strategies/sstrangle/poc/v06/three_demos.py').write_text(s)
compile(s,'three_demos.py','exec')
print('Built three_demos.py')
