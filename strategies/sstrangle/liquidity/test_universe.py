from datetime import date,timedelta
import pytest
from universe import select_universes
D=[str(date(2020,1,1)+timedelta(days=i)) for i in range(20)]
C='2020-02-03T14:00:00+00:00'
def rows(n=105):
 return [dict(underlying_id=f'ID{i:03}',session_date=d,available_at_utc=d+'T23:00:00+00:00',
   monthly_35_95_volume=200-i,chain_complete=True,volume_complete=True,classification_complete=True)
   for i in range(n) for d in D]
def call(r,n=105):return select_universes(r,D,[f'ID{i:03}' for i in range(n)],C)
def test_nested_universes_and_future_revisions_do_not_leak():
 r=rows();base=call(r);r.append(dict(r[0],monthly_35_95_volume=999999,available_at_utc='2021-01-01T00:00:00Z'))
 actual=call(r)
 assert len(actual['top50'])==50 and len(actual['top100'])==100
 assert actual['top50']==actual['top100'][:50]==base['top50']
 assert actual['future_observations_ignored']==1
 assert actual['top50'][0]['underlying_id']=='ID000'
def test_missing_and_partial_coverage_are_not_zero_or_passes():
 r=rows(3)[1:];r[20]['chain_complete']=False
 a=call(r,3)
 assert [x['underlying_id'] for x in a['top50']]==['ID002']
 assert {x['reason'] for x in a['rejected']}=={'missing_session','unverified_daily_coverage'}
def test_conflict_and_invalid_volume_fail_closed():
 r=rows(1)
 with pytest.raises(ValueError,match='Conflicting'):call(r+[dict(r[0],monthly_35_95_volume=2)],1)
 r[0]['monthly_35_95_volume']=float('nan')
 with pytest.raises(ValueError,match='volume'):call(r,1)
def test_ties_are_identity_order_and_not_row_order():
 r=rows(3)
 for x in r:x['monthly_35_95_volume']=10
 assert [x['underlying_id'] for x in call(list(reversed(r)),3)['top50']]==['ID000','ID001','ID002']
