"""Add exact-width feasibility before delta selection; preserve original predicate."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
p=ROOT/'strategies/sstrangle/poc/v06/three_demos.py'
s=p.read_text()
a=s.index("        if self.kind=='condor':\n            by_key")
b=s.index("        elif self.kind=='strangle':",a)
s=s[:a]+'''        original_put,original_call=put,call
        recovered=False
        if self.kind=='condor':
            by_key = {(c.right,float(c.strike)):c for c in contracts}
            long_put = by_key.get((OptionRight.PUT,float(put.strike)-20))
            long_call = by_key.get((OptionRight.CALL,float(call.strike)+20))
            if long_put is None or long_call is None:
                self.counts['original_wing_skips']+=1
                self.counts['original_wing_year_'+str(today.year)]+=1
                raw={(c.right,float(c.strike)):c for c in chain if c.expiry.date()==today}
                failures=[]
                for side,right,strike,wing in [('put',OptionRight.PUT,float(put.strike)-20,long_put),('call',OptionRight.CALL,float(call.strike)+20,long_call)]:
                    if wing is not None: continue
                    candidate=raw.get((right,strike))
                    reason='absent_chain'
                    if candidate is not None:
                        sec=self.securities[candidate.symbol];quote=sec.cache.get_data[QuoteBar]()
                        if quote is None:reason='no_quote'
                        elif quote.is_fill_forward:reason='fill_forward'
                        elif not sec.local_time-timedelta(minutes=2)<=quote.end_time<=sec.local_time:
                            reason='age'
                            age=(sec.local_time-quote.end_time).total_seconds()/60
                            bucket='future' if age<0 else ('3to5' if age<=5 else ('6to15' if age<=15 else ('16to60' if age<=60 else 'over60')))
                            self.counts['wing_age_'+bucket]+=1
                        elif float(candidate.ask_price)<=0:reason='zero_ask'
                        elif not 0<=float(candidate.bid_price)<=float(candidate.ask_price):reason='crossed'
                        elif float(candidate.ask_price)-float(candidate.bid_price)>3:reason='spread'
                        else:reason='unclassified'
                    failures.append(side+'_'+reason)
                    self.counts['wing_'+side+'_'+reason]+=1
                self.counts['wing_reason_'+','.join(sorted(failures))]+=1
                if self.CONFIG.get('wing_policy','paired_exact' if self.kind=='condor' else 'original')!='paired_exact':
                    self.counts['skip_missing_20point_wing']+=1
                    return
                # Search only the exact-width packages with both legs already
                # passing the unchanged original quote-admission predicate.
                paired_puts=[c for c in puts if (OptionRight.PUT,float(c.strike)-20) in by_key]
                paired_calls=[c for c in calls if (OptionRight.CALL,float(c.strike)+20) in by_key]
                if not paired_puts or not paired_calls:
                    self.counts['skip_no_admissible_exact_pair']+=1
                    return
                put=min(paired_puts,key=lambda c:(abs(float(c.greeks.delta)+float(self.CONFIG.get('put_target',.20))),float(c.strike)))
                call=min(paired_calls,key=lambda c:(abs(float(c.greeks.delta)-float(self.CONFIG.get('call_target',.08))),float(c.strike)))
                long_put=by_key[(OptionRight.PUT,float(put.strike)-20)]
                long_call=by_key[(OptionRight.CALL,float(call.strike)+20)]
                recovered=True
                self.counts['recovered_pair_candidates']+=1
                self.counts['recovered_pair_year_'+str(today.year)]+=1
            else:self.counts['original_wing_admitted']+=1
            selected=[(long_put,1),(put,-1),(call,-1),(long_call,1)]
''' +s[b:]
s=s.replace("f';pd={float(put.greeks.delta):.8f};cd={(float(call.greeks.delta) if call else 0.0):.8f};spot={spot:.6f}')", "f';pd={float(put.greeks.delta):.8f};cd={(float(call.greeks.delta) if call else 0.0):.8f};spot={spot:.6f}'\n               f';recovered={int(recovered)};anchor_pd={float(original_put.greeks.delta):.8f};anchor_cd={(float(original_call.greeks.delta) if original_call else 0.0):.8f}')")
s=s.replace("            max_loss=max_loss,quoted_credit=credit,", "            max_loss=max_loss,quoted_credit=credit,recovered=recovered,")
s=s.replace("                self.counts['filled_episodes'] += 1", "                self.counts['filled_episodes'] += 1\n                if record['recovered']:self.counts['recovered_filled_episodes']+=1")
s=s.replace("        self.set_runtime_statistic('strategy_kind',self.kind)","        self.set_runtime_statistic('wing_policy',self.CONFIG.get('wing_policy','paired_exact' if self.kind=='condor' else 'original'))\n        self.set_runtime_statistic('strategy_kind',self.kind)")
a=s.index('                paired_puts=');b=s.index('                recovered=True',a)
s=s[:a]+'''                pair=choose_exact_pairs(puts,calls,by_key,OptionRight.PUT,OptionRight.CALL,
                    float(self.CONFIG.get('put_target',.20)),float(self.CONFIG.get('call_target',.08)))
                if pair is None:
                    self.counts['skip_no_admissible_exact_pair']+=1
                    return
                put,call,long_put,long_call=pair
''' +s[b:]
helper=(ROOT/'strategies/sstrangle/poc/v06/selection.py').read_text()
s=s.replace('class AbsoluteEntrySlippage:',helper+'\n\nclass AbsoluteEntrySlippage:')
p.write_text(s);compile(s,str(p),'exec')
print('Added paired_exact policy and original-admission shadow counters')
