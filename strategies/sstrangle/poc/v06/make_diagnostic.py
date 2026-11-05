from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'strategies/sstrangle/results/qc_three_demo_poc_20261023'
s=(ROOT/'strategies/sstrangle/poc/optionomega_demo.py').read_text()
cfg=dict(start=[2022,5,16],last_entry=[2026,7,13],fill_convention='oo_midpoint_package',capital_fraction=1.,verbose=False)
s=s.replace('CONFIG = {}','CONFIG = '+repr(cfg))
s=s.replace("        selected = [(long_put,1),(put,-1),(call,-1),(long_call,1)]", "        self.counts['diag_admitted_original'] += 1\n        return\n        selected = [(long_put,1),(put,-1),(call,-1),(long_call,1)]")
s=s.replace("            self.counts['skip_missing_20point_wing'] += 1",'''            self.counts['skip_missing_20point_wing'] += 1
            self.counts['wing_skip_year_'+str(today.year)] += 1
            self.counts['wing_skip_hour_'+str(slot[0])] += 1
            raw = {(c.right,float(c.strike)):c for c in chain if c.expiry.date()==today}
            failures=[]
            for side,right,strike,wing in [('put',OptionRight.PUT,float(put.strike)-20,long_put),('call',OptionRight.CALL,float(call.strike)+20,long_call)]:
                if wing is not None: continue
                candidate=raw.get((right,strike))
                reason='absent_chain'
                if candidate is not None:
                    security=self.securities[candidate.symbol]
                    quote=security.cache.get_data[QuoteBar]()
                    if quote is None: reason='no_quote'
                    elif quote.is_fill_forward: reason='fill_forward'
                    elif not security.local_time-timedelta(minutes=2)<=quote.end_time<=security.local_time: reason='age'
                    elif float(candidate.ask_price)<=0: reason='zero_ask'
                    elif not 0<=float(candidate.bid_price)<=float(candidate.ask_price): reason='crossed'
                    elif float(candidate.ask_price)-float(candidate.bid_price)>3: reason='spread'
                    else: reason='unclassified'
                failures.append(side+'_'+reason)
                self.counts['wing_'+side+'_'+reason]+=1
            self.counts['wing_reason_'+','.join(sorted(failures))]+=1
            valid_puts=[c for c in puts if (OptionRight.PUT,float(c.strike)-20) in by_key]
            valid_calls=[c for c in calls if (OptionRight.CALL,float(c.strike)+20) in by_key]
            if valid_puts and valid_calls: self.counts['wing_recoverable_pair_search']+=1''')
s=s.replace("        if not self.counts['filled_episodes']:","        if False:")
s=s.replace("self.set_runtime_statistic('baseline','audio_spx_20put_8call_20w_13slots')","self.set_runtime_statistic('baseline','diagnostic_no_orders_original_admission')")
name='SSTRANGLE_OO06_20261023_DIAG_V1'
p=OUT/'diag_v1.py';p.write_text(s)
(OUT/'diag_v1_manifest.json').write_text(json.dumps(dict(name=name,config=cfg,source_sha256=hashlib.sha256(s.encode()).hexdigest(),role='Replay original admission only; no orders; explanatory counts, not performance'),indent=2))
print(p)
