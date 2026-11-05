from pathlib import Path
import ast,json,hashlib
P=Path(__file__).parent
base=(P.parent/'automatic_20261025/onepair_cost_v6.py').read_text()
base=base.replace("self.assignment_names=set();self.subscribed=set()", "self.assignment_names=set();self.subscribed=set()\n        self.funnel_seen=set();self.funnel=Counter()")
pos=base.index('    def prepare(self):')
base=base[:pos]+'''    def stage(self,name,label):
        key=(name,self.time.date(),label)
        if key not in self.funnel_seen:
            self.funnel_seen.add(key);self.funnel[(name,label)]+=1

'''+base[pos:]
base=base.replace("        for name in CONFIG['names']:\n            if name in self.states", "        for name in CONFIG['names']:\n            self.stage(name,'calendar')\n            if name in self.states")
base=base.replace("            rec=self.records(name)","            self.stage(name,'available')\n            rec=self.records(name)")
base=base.replace("            if CONFIG['ivr_gate'] and (rank is None or rank<=50):", "            if rank is not None:self.stage(name,'iv_known')\n            if CONFIG['ivr_gate'] and (rank is None or rank<=50):")
base=base.replace("            possible=[r for r in rec", "            self.stage(name,'ivr')\n            possible=[r for r in rec")
base=base.replace("            exp=min({r['expiry'] for r in possible}", "            self.stage(name,'expiry')\n            exp=min({r['expiry'] for r in possible}")
base=base.replace("            pair=[]", "            self.stage(name,'event')\n            if all(any(r['expiry']==exp and r['put']==put and .16<=abs(r['delta'])<=.22 and r['iv']>0 for r in possible) for put in [True,False]):self.stage(name,'delta')\n            pair=[]")
base=base.replace("            self.last_attempt[name]=today", "            self.stage(name,'oi')\n            self.last_attempt[name]=today")
base=base.replace("        if any((a-b)/((a+b)/2)", "        self.stage(name,'quote')\n        if any((a-b)/((a+b)/2)")
base=base.replace("        spot=float(self.securities[self.eq[name]].price);years=(p['expiry']", "        self.stage(name,'spread')\n        spot=float(self.securities[self.eq[name]].price);years=(p['expiry']")
base=base.replace("        net_credit=sum((b-CONFIG", "        self.stage(name,'live_delta')\n        net_credit=sum((b-CONFIG")
base=base.replace("        # Conservative standalone initial margins", "        self.stage(name,'size')\n        # Conservative standalone initial margins")
base=base.replace("        self.episode+=1", "        self.stage(name,'margin')\n        self.episode+=1")
base=base.replace("        self.counts['entry_submitted']+=1", "        self.stage(name,'order')\n        self.counts['entry_submitted']+=1")
base=base.replace("        self.set_runtime_statistic('ss_halted',str(self.halt))", """        self.set_runtime_statistic('ss_halted',str(self.halt))
        stages=['calendar','available','iv_known','ivr','expiry','event','delta','oi','quote','spread','live_delta','size','margin','order']
        self.set_runtime_statistic('f_labels',','.join(stages))
        for name in CONFIG['names']:
            self.set_runtime_statistic('f_'+name,','.join(str(self.funnel[(name,k)]) for k in stages))""")
i=base.index('CONFIG = ');j=base.index('\n',i);cfg=ast.literal_eval(base[i+9:j])
added=['SPY','QQQ','IWM','DIA','EFA','EEM','XLF','XLE','XLV','GLD','SLV','HYG']
variants=[('FIVE_BASE',{},False),('FIVE_NO_IVR',{'ivr_gate':False},False),('FIVE_SPREAD10',{'spread_cap':.10},False),('FIVE_RETRY',{},True),('BROAD17',{'names':cfg['names']+added},False)]
manifest=[]
for label,overrides,retry in variants:
 c=cfg|overrides;s=base.replace('CONFIG = '+repr(cfg),'CONFIG = '+repr(c))
 s=s.replace("if name not in ['EWZ','TLT']:","if name not in "+repr(['EWZ','TLT']+added)+":")
 if retry:
  s=s.replace('self.last_attempt.get(name)==today','self.last_attempt.get(name)==(today,self.time.hour>=15)').replace('self.last_attempt[name]=today','self.last_attempt[name]=(today,self.time.hour>=15)')
 name='SS45DTE_FUNNEL_'+label+'_V1';f=P/(name+'.py');f.write_text(s)
 manifest.append({'name':name,'file':str(f),'source_sha256':hashlib.sha256(s.encode()).hexdigest(),'config':c,'second_window_retry':retry})
(P/'manifest.json').write_text(json.dumps({'batch':'ss45dte_funnel_20261026','denominator':'Unique symbol/session reaching each stage at least once; conditional sequential funnel, not causal independent rejection probabilities','universe':'Original five plus predeclared broad market/sector/commodity/bond ETFs; static surviving universe, correlated exposures, not unbiased market-wide selection','runs':manifest},indent=2)+'\n')
print([x['name'] for x in manifest])
