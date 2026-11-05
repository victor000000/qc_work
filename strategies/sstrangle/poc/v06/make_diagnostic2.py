from pathlib import Path
import hashlib,json,ast,subprocess
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023'
s=(OUT/'diag_smoke_v1.py').read_text()
s=s.replace("elif not security.local_time-timedelta(minutes=2)<=quote.end_time<=security.local_time: reason='age'", """elif not security.local_time-timedelta(minutes=2)<=quote.end_time<=security.local_time:
                        reason='age'
                        age=(security.local_time-quote.end_time).total_seconds()/60
                        age_bucket=str(int(age)) if abs(age)<=120 else ('older120' if age>0 else 'future120')
                        self.counts['age_minutes_'+age_bucket]+=1
                        self.counts['age_security_tz_'+str(security.exchange.time_zone)]+=1
                        if self.counts['age_sample']<5:
                            self.counts['age_sample']+=1
                            self.emit('AGE_DIAGNOSTIC',dict(algorithm_time=str(self.time),security_time=str(security.local_time),quote_end=str(quote.end_time),age_minutes=age,is_fill_forward=quote.is_fill_forward))""")
s=s.replace("elif not 0<=float(candidate.bid_price)<=float(candidate.ask_price): reason='crossed'", """elif not 0<=float(candidate.bid_price)<=float(candidate.ask_price):
                        reason='crossed'
                        self.counts['crossed_security_too' if float(security.bid_price)>float(security.ask_price) else 'crossed_contract_only']+=1""")
s=s.replace("            self.counts['wing_reason_'", "            self.counts['wing_reason_'")
name='SSTRANGLE_OO06_20261023_DIAG_SMOKE_V2';p=OUT/'diag_smoke_v2.py';p.write_text(s)
cfg=next(ast.literal_eval(n.value) for n in ast.walk(ast.parse(s)) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CONFIG' for t in n.targets))
(OUT/'diag_smoke_v2_manifest.json').write_text(json.dumps(dict(name=name,config=cfg,source_sha256=hashlib.sha256(s.encode()).hexdigest(),role='Age-clock and crossed-quote attribution; no orders'),indent=2))
subprocess.run([str(ROOT/'target/release/qc-backtest-server'),'queue','--strategy','sstrangle','--name',name,'--code-file',str(p),'--batch','oo06_20261023','--priority','0'],check=True)
