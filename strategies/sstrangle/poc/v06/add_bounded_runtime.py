"""Final rebuild step; changes telemetry only, never rewrites frozen run sources."""
from pathlib import Path
P=Path(__file__).resolve().parent;p=P/'three_demos.py';s=p.read_text()
if 'def bounded_statistics(' in s:raise RuntimeError('Already applied; rebuild original steps first')
helper=(P/'runtime_export.py').read_text();s=s.replace('from AlgorithmImports import *','from AlgorithmImports import *\n'+helper)
a=s.index('        for k,v in sorted(self.counts.items()):',s.index('    def on_end_of_algorithm'))
b=s.index("        if not self.counts['filled_episodes']:",a)
block=s[a:b];start=block.index("        self.set_runtime_statistic('ledger_error'")
block=block[start:].replace('self.set_runtime_statistic(', 'record(')
s=s[:a]+"        core={}\n        def record(k,v):core[k]=v\n"+block+"        for key,value in bounded_statistics(core,self.counts,self.annual).items():\n            self.set_runtime_statistic(key,value)\n"+s[b:]
compile(s,str(p),'exec');p.write_text(s)
print('Bounded runtime telemetry applied; frozen primary sources unchanged')
