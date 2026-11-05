"""Build immutable corrected-cost sizing diagnostics from the v3 baseline."""
from pathlib import Path
import hashlib,json
p=Path(__file__).parent
s=(p/'strict_full_v3.py').read_text()
s=s.replace("self.assignment_names=set();self.subscribed=set()", "self.assignment_names=set();self.subscribed=set()\n        self.size_audit={};self.size_seen=set()")
s=s.replace("        if quantity<1:self.counts['skip_size']+=1;return",'''        audit_key=(name,self.time.date(),p['expiry'])
        if audit_key not in self.size_seen:
            self.size_seen.add(audit_key)
            m_one=sum(float(self.securities[r['symbol']].buying_power_model.get_initial_margin_requirement(InitialMarginParameters(self.securities[r['symbol']],-1)).value) for r in p['legs'])
            # Intrinsic loss floor under a +/-20% spot move; independent of IV/time.
            floor_loss=max(sum(max(r['strike']-spot*(1+move) if r['put'] else spot*(1+move)-r['strike'],0)*q[2] for r,q in zip(p['legs'],quotes))-net_credit+2*CONFIG['fee'] for move in [-.2,.2])
            self.size_audit.setdefault(name,[]).append((loss,budget,net_credit,m_one,spot*quotes[0][2],floor_loss))
        if quantity<1:self.counts['skip_size']+=1;return''')
s=s.replace("        self.reconcile();self.report()",'''        self.reconcile();self.report()
        for name,rows in self.size_audit.items():
            self.set_runtime_statistic('audit_'+name+'_n',str(len(rows)))
            for i,label in enumerate(['stress','budget','credit','margin','notional','intrinsic_floor']):
                vals=sorted(x[i] for x in rows)
                summary=[min(vals),vals[(len(vals)-1)//2],vals[int((len(vals)-1)*.9)],max(vals)]
                self.set_runtime_statistic('audit_'+name+'_'+label,','.join(f'{x:.2f}' for x in summary))
            self.set_runtime_statistic('audit_'+name+'_pass_750_1500_3000',','.join(str(sum(x[0]<=b for x in rows)) for b in [750,1500,3000]))
            self.set_runtime_statistic('audit_'+name+'_pass_intrinsic_750',str(sum(x[5]<=750 for x in rows)))''')
s=s.replace('automatic v3; explicit mechanical variant','automatic v4; corrected cost and sizing diagnostics')
file=p/'strict_diagnostic_v4.py';file.write_text(s)
(file.with_suffix('.json')).write_text(json.dumps({'source_sha256':hashlib.sha256(s.encode()).hexdigest(),'purpose':'Aggregate unique symbol/day/expiry sizing diagnostics, min/lower median/p90/max; no raw quotes exported','baseline':'strict_full_v3.py'},indent=2)+'\n')
print(file)
