"""Build telemetry-only native expiry diagnostic; immutable existing accounts remain untouched."""
import ast,hashlib,json
from pathlib import Path
P=Path(__file__).parent
source=(P/'strategy.py').read_text()
needle="            self.counts['native_expiry_events'] += 1"
extra='''            expiry_key = str(event.symbol.id.date.date())
            if expiry_key not in self.expiry_spots:
                underlying_bar = option.underlying.get_last_data()
                self.emit('EXPIRY_REFERENCE_CLOCK', dict(day=expiry_key,
                    algorithm_time=str(self.time), utc_time=str(self.utc_time),
                    underlying_bar_time=str(underlying_bar.time) if underlying_bar else None,
                    underlying_bar_end_time=str(underlying_bar.end_time) if underlying_bar else None,
                    underlying_resolution_type=type(underlying_bar).__name__ if underlying_bar else None,
                    underlying_fill_forward=bool(underlying_bar.is_fill_forward) if underlying_bar else None,
                    own_expiry_reference=spot, own_event_message=str(event.message)))
'''
assert source.count(needle)==1
result=source.replace(needle,extra+needle);ast.parse(result)
f=P/'strategy_settlement_diagnostic.py'
assert not f.exists() or f.read_text()==result
f.write_text(result)
plan=json.loads((P/'settlement_diagnostic_plan.json').read_text());plan['adapter_sha256']=hashlib.sha256(result.encode()).hexdigest();plan['tests']=[]
for window,start,last in [('eom',[2022,9,29],[2022,10,3]),('stress',[2025,4,8],[2025,4,10])]:
 for key,kind in [('c0','condor'),('p1','put_spread')]:plan['tests'].append(dict(key=f'{key}_settlement_{window}',kind=kind,overrides=dict(start=start,last_entry=last)))
(P/'settlement_diagnostic_execution_plan.json').write_text(json.dumps(plan,indent=2)+'\n')
print('Diagnostic source compiled; four short tests preregistered')
