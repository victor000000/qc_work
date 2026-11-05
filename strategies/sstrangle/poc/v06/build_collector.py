from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
s=(ROOT/'strategies/sstrangle/poc/collect_demo.py').read_text().replace('parents[3]','parents[4]')
s=s.replace('from qc_api_check import credentials, request','from qc_api_check import credentials\nfrom transport import request')
s=s.replace('    ids, event_ids, position =',"    kind=runtime.get('strategy_kind','condor')\n    n={'condor':4,'strangle':2,'put':1}[kind]\n    if int(runtime.get('leg_count',n))!=n: raise ValueError('Strategy leg-count mismatch')\n    ids, event_ids, position =")
s=s.replace("len(group)!=4 or len({o['symbol']['id'] for o in group})!=4","len(group)!=n or len({o['symbol']['id'] for o in group})!=n")
s=s.replace("'Episode does not have four distinct native orders'","'Episode has wrong distinct native order count'")
s=s.replace("        if (len(combo_ids)!=1", "        if n==1 and (group[0]['type']!=0 or managers[0]):\n            raise ValueError('Single put lacks native market-order identity')\n        if n>1 and (len(combo_ids)!=1")
s=s.replace("m.get('count')!=4", "m.get('count')!=n")
a=s.index("        if set(strikes)!=");b=s.index("        if runtime.get('fill_convention')",a)
s=s[:a]+'''        expected={'condor':{('P',1),('P',-1),('C',-1),('C',1)},'strangle':{('P',-1),('C',-1)},'put':{('P',-1)}}[kind]
        if set(strikes)!=expected: raise ValueError('Wrong strategy leg signs')
        if kind=='condor' and (strikes['P',-1]-strikes['P',1]!=20 or strikes['C',1]-strikes['C',-1]!=20):
            raise ValueError('Wrong wing widths')
        if kind!='put' and strikes['P',-1]>=strikes['C',-1]: raise ValueError('Wrong strike ordering')
''' +s[b:]
s=s.replace('if not 0<entry_cash<2000:',"if entry_cash<=0 or (kind=='condor' and entry_cash>=2000):")
s=s.replace('len(group)!=4 or any', 'len(group)!=n or any')
s=s.replace("len(frame)*4*1.18","len(frame)*int(native_runtime['leg_count'])*1.18")
s=s.replace("'0.5-audio-poc'","'0.6-three-demo-poc'")
s=s.replace("(frame.put_delta+0.20)","(frame.put_delta+float(cfg.get('put_target',0.20)))")
s=s.replace("(frame.call_delta-0.08)","(frame.call_delta-float(cfg.get('call_target',0.08)))")
# Runtime strategy metadata is validated against the frozen submitted source before auditing.
s=s.replace("    frame,legs,events,annual,audit=audit_orders", "    if native_runtime.get('strategy_kind')!=cfg.get('strategy_kind','condor'): raise ValueError('Submitted strategy kind mismatch')\n    frame,legs,events,annual,audit=audit_orders")
s=s.replace("        for event in order.get('events',[]):", "        for event in order.get('events',[]):\n            if runtime.get('assignment_policy') and 'before expiration' in (event.get('message') or '').lower():\n                raise ValueError('Unexpected premature European assignment event')",1)
s=s.replace("if r.trades!=int(runtime.get('episodes_'+str(r.year),0)):","if 'episodes_'+str(r.year) in runtime and r.trades!=int(runtime['episodes_'+str(r.year)]):")
s=s.replace("if abs(float(runtime['ledger_error']))>0.05:","if 'ledger_error' in runtime and abs(float(runtime['ledger_error']))>0.05:")
s=s.replace("runtime_max_flat_ledger_error=float(runtime['max_flat_ledger_error']),", "runtime_max_flat_ledger_error=float(runtime['max_flat_ledger_error']) if 'max_flat_ledger_error' in runtime else None,\n        omitted_runtime_counters=[k for k in ['ledger_error','max_flat_ledger_error']+['episodes_'+str(y) for y in annual.year] if k not in runtime],\n        annual_count_source='Complete native opening order groups; cross-checked against each exported annual runtime counter',")
(ROOT/'strategies/sstrangle/poc/v06/collect_three.py').write_text(s)
compile(s,'collect_three.py','exec')
