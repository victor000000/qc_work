"""Reproducible narrow transformation of the preserved guarded full-run source."""
import ast,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
PARENT=HERE.parent/'results/strangle_basket-calmar_20261019_163122/cap20_stop1_guard_exit21.py'
METHODS='''    def equity_rv_for(self,symbol,iv):
        cache=getattr(self,'_equity_rv_cache',None)
        if cache is None or cache[0]!=self.time.date():
            cache=(self.time.date(),{});self._equity_rv_cache=cache
        key=(str(symbol.id),float(iv))
        if key not in cache[1]:
            self.counts['equity_rv_history_requests']+=1
            expected=expected_equity_sessions(self.securities[self.spy].exchange.hours,self.time)
            bars=list(self.history[TradeBar](symbol,65,Resolution.DAILY,fill_forward=False,data_normalization_mode=DataNormalizationMode.SCALED_RAW))
            cache[1][key]=(equity_features(bars,str(symbol.id),self.time,expected,iv),expected[-1])
        return cache[1][key]

    def admit_equity_rv(self,candidate,statistics):
        if candidate['future']:
            statistics['rv_policy']='future_original_rules'
            self.counts['equity_rv_future_bypasses']+=1
            return True
        if statistics.get('last_day')!=str(self.time.date()):
            self.decision(candidate['key'],'equity_rv_iv_asof_mismatch');return False
        feature,last_session=self.equity_rv_for(candidate['eq'],statistics['iv'])
        if not equity_rv_admitted(feature,self.CONFIG['min_equity_iv_rv']):
            self.decision(candidate['key'],'equity_rv_unavailable' if not feature.ready else 'equity_iv_rv_below_threshold');return False
        statistics.update(rv_policy='equity_iv_to_max_rv20_rv60',rv20=feature.realized20,rv60=feature.realized60,
            iv_rv=feature.iv_to_max_realized,rv_samples=feature.closes,rv_last_session=str(last_session),
            rv_threshold=self.CONFIG['min_equity_iv_rv'],rv_source='SCALED_RAW')
        self.counts['equity_rv_admitted']+=1
        return True

'''
def render():
 s=PARENT.read_text();tree=ast.parse(s);assign=[n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CONFIG' for t in n.targets)]
 assert len(assign)==1;lines=s.splitlines();a=assign[0];lines[a.lineno-1:a.end_lineno]=['    CONFIG = {}'];s='\n'.join(lines)+'\n'
 s='from equity_rv_features import expected_equity_sessions, equity_features, equity_rv_admitted, validate_equity_rv_threshold\n'+s
 needle='        self.last_risk_check=None';assert s.count(needle)==1
 s=s.replace(needle,"        validate_equity_rv_threshold(cfg['min_equity_iv_rv'])\n        if cfg.get('future_rv_policy')!='original_rules':raise ValueError('All15future roots retain original rules in this equity-only trial')\n        self.settings.daily_precise_end_time=True\n"+needle,1)
 needle='            legs = self.selected_legs(records, expiry)';assert s.count(needle)==1
 s=s.replace(needle,'            if not self.admit_equity_rv(candidate,statistics):\n                continue\n'+needle,1)
 needle='    def selected_legs(self, records, expiry):';assert s.count(needle)==1;s=s.replace(needle,METHODS+needle,1);ast.parse(s);return s
if __name__=='__main__':
 source=render();(HERE/'equity_rv_main.py').write_text(source)
 (HERE/'equity_rv_source_receipt_20261019.json').write_text(json.dumps({'parent':str(PARENT),'parent_sha256':hashlib.sha256(PARENT.read_bytes()).hexdigest(),'generated_sha256':hashlib.sha256(source.encode()).hexdigest(),'strategy_integrated':False,'native_gate_validated':False,'baseline_unchanged':True},indent=2));print('Generated independent equity RV source; parent preserved.')
