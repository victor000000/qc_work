"""Full admission-only replay with bounded, readable aggregate statistics."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023'
s=(OUT/'diag_v1.py').read_text()
a=s.index('        self.schedule.on(');b=s.index('\n    def initialize_security',a);s=s[:a]+s[b:]
a=s.index('    def on_end_of_algorithm(self):')
s=s[:a]+'''    def on_end_of_algorithm(self):
        # These are our own aggregate decision counts, never market quote history.
        # Readable JSON objects stay below QC's documented 200-character value
        # bound and use fewer than 50 custom statistics in total.
        headlines=['scheduled_slots','skip_missing_20point_wing','diag_admitted_original',
                    'wing_recoverable_pair_search','skip_no_chain','skip_missing_delta_or_quotes']
        for key in headlines:self.set_runtime_statistic(key,str(self.counts[key]))
        chunks=[];chunk={}
        for key,value in sorted(self.counts.items()):
            trial=dict(chunk);trial[key]=value
            if len(json.dumps(trial,separators=(',',':')))>180:
                chunks.append(chunk);chunk={key:value}
            else:chunk=trial
        if chunk:chunks.append(chunk)
        if len(chunks)+len(headlines)+2>50:raise RuntimeError('Diagnostic statistics quota exceeded')
        for i,chunk in enumerate(chunks):self.set_runtime_statistic('admission_'+str(i+1).zfill(2),json.dumps(chunk,separators=(',',':')))
        self.set_runtime_statistic('admission_chunks',str(len(chunks)))
        self.set_runtime_statistic('scope','Original admission replay; no orders or account-performance claim')
'''
name='SSTRANGLE_OO06_20261023_DIAG_FULL_V2';p=OUT/'diag_full_v2.py';p.write_text(s);compile(s,str(p),'exec')
(OUT/'diag_full_v2_manifest.json').write_text(json.dumps(dict(name=name,source_sha256=hashlib.sha256(s.encode()).hexdigest(),role='Recover complete original-policy admission counts within documented runtime-statistic quotas; no orders'),indent=2)+'\n')
print(p)
