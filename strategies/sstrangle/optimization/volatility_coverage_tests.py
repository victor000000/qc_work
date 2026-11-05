import ast,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_coverage_phase_frozen_source_and_scope():
 p=ROOT/'results/strangle_basket-volatility-coverage_20261019_180413';m=json.loads((p/'manifest.json').read_text());cfg=m['variants']['vol_coverage']
 assert len(set(cfg['roots']))==15 and m['evidence_only']
 assert json.loads((p/'extra_files.json').read_text())=={}
 assert (p/'vol_coverage.py').read_text()==(ROOT/'optimization/volatility_coverage_fixture.py').read_text().replace('CONFIG = {}','CONFIG = '+repr(cfg),1)
def test_availability_never_trades_or_exports_market_values():
 s=(ROOT/'optimization/volatility_coverage_fixture.py').read_text();tree=ast.parse(s)
 attrs=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
 assert not any(x in attrs for x in ['market_order','combo_market_order','set_holdings','set_fill_model','set_margin_call_model'])
 assert '.close' not in s and 'fill_forward=False' in s and 'extended_market_hours=False' in s
 assert "len(self.results)!=60" in s and 'Resolution.MINUTE' in s and 'Resolution.DAILY' in s
 assert "calendar_open_before_close=" in s

def sample():
 from volatility_coverage_report import ROOTS
 rows=[dict(root=r,native_id=r+str(i),session=d,daily_rows=0,minute_rows=1,calendar_close=d+' 13:00:00',calendar_open_before_close=True) for r in ROOTS for i in [1,2] for d in ['2017-07-03','2017-07-04']]
 full=dict(statistics={'Total Orders':'0'},runtimeStatistics={'Equity':'$60,000','Fees':'$0','Holdings':'$0','Unrealized':'$0','availability_records':'60','availability_roots':'15','availability_no_trades':'1'})
 return full,rows

def test_complete_aggregate_survey_accepts_real_missing_rows():
 from volatility_coverage_report import audit
 f,rows=sample();log='\n'.join('VOLATILITY_AVAILABILITY '+json.dumps(r) for r in rows)
 assert len(audit(f,[],[],log))==60

def test_incomplete_survey_or_market_price_field_rejected():
 from volatility_coverage_report import audit
 import pytest
 f,rows=sample()
 with pytest.raises(ValueError):audit(f,[],[],'\n'.join('VOLATILITY_AVAILABILITY '+json.dumps(r) for r in rows[:-1]))
 rows[0]['price']=1
 with pytest.raises(ValueError):audit(f,[],[],'\n'.join('VOLATILITY_AVAILABILITY '+json.dumps(r) for r in rows))

def test_source_survey_cannot_hide_trades_or_changed_account():
 from volatility_coverage_report import audit
 import pytest
 f,rows=sample();log='\n'.join('VOLATILITY_AVAILABILITY '+json.dumps(r) for r in rows)
 with pytest.raises(ValueError):audit(f,[{}],[],log)
 f['runtimeStatistics']['Equity']='$59,999'
 with pytest.raises(ValueError):audit(f,[],[],log)
