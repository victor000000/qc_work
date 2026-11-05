import ast,json,hashlib
from pathlib import Path
import pytest
from volatility_minute_report import audit,ROOTS
ROOT=Path(__file__).resolve().parents[1]
def test_frozen_minute_render_scope_and_source_protections():
 p=ROOT/'results/strangle_basket-volatility-minute_20261019_181056';m=json.loads((p/'manifest.json').read_text());cfg=m['variants']['vol_minute'];s=(ROOT/'optimization/volatility_minute_fixture.py').read_text()
 assert m['evidence_only'] and set(cfg['roots'])==ROOTS and (p/'vol_minute.py').read_text()==s.replace('CONFIG = {}','CONFIG = '+repr(cfg),1)
 extra=json.loads((p/'extra_files.json').read_text());assert set(extra)=={'completed_volatility.py','minute_session_closes.py'}
 for name in extra:assert extra[name]==(ROOT/'optimization'/name).read_text()
 calls=[n.func.attr for n in ast.walk(ast.parse(s)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
 assert not any(x in calls for x in ['market_order','combo_market_order','set_holdings','set_fill_model','set_margin_call_model'])
 assert 'fill_forward=False' in s and 'Resolution.MINUTE' in s and "self.counts['unavailable']+=1" in s and "self.counts['requests']!=90" in s

def data():
 rt={'Equity':'$60000','Fees':'$0','Holdings':'$0','Unrealized':'$0','minute_requests':'90','minute_ready':'90','minute_unavailable':'0','minute_numpy_matches':'90','minute_source_minutes':'9000','minute_no_trades':'1','minute_iv_input':'synthetic1.0_not_market_IV'}
 for r in ROOTS:rt['minute_root_attempt_'+r]='6';rt['minute_root_ready_'+r]='6'
 return {'statistics':{'Total Orders':'0'},'runtimeStatistics':rt},'MINUTE_SOURCE_CHECKSUM '+hashlib.sha256(b'actual_aggregate').hexdigest()
def test_complete_probe_audit_is_engineering_not_calmar():
 f,log=data();r=audit(f,[],[],log);assert r['native_adapter_comparisons_verified'] and r['full_futures_feature_coverage_verified'] and not r['strategy_calmar_proven']
def test_missing_root_not_hidden_as_success():
 f,log=data();f['runtimeStatistics']['minute_root_attempt_CL']='0'
 with pytest.raises(ValueError):audit(f,[],[],log)
def test_unavailable_outcomes_are_required_and_reconciled():
 f,log=data();rt=f['runtimeStatistics'];rt.update(minute_ready='89',minute_unavailable='1',minute_numpy_matches='89',minute_root_ready_CL='5')
 with pytest.raises(ValueError):audit(f,[],[],log)
 log+='\nMINUTE_SOURCE_UNAVAILABLE '+json.dumps(dict(root='CL',native_id='native',decision='2017-07-05',missing_count=1,stale_count=0))
 assert audit(f,[],[],log)['aggregate_counts']['unavailable']==1
