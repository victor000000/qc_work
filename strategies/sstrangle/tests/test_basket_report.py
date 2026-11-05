from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).parents[1]))
from basket_report import audit_batches


def base36(value):
    chars='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';result=''
    while value:
        value,remainder=divmod(value,36);result=chars[remainder]+result
    return result


def combo(group,key,reason,batch=1,count=2,quantity=1,day='2020-01-02',volume=100):
    annotation=(f';batch_id={batch};basket_count={count};quantity={quantity};monthly_only=True;'
        f'ivr=80;samples=504;iv=.42;iv_low=.1;iv_high=.5;allocation_equity=60000;'
        f'allocation_budget={60000/count};estimated_initial_margin=1000;estimated_entry_fees=1;volume={volume}')
    rows=[]
    put=int('2Z43H5BGXLVAE',36)
    for side in (0,1):
        rows.append(dict(id=group*2+side,time=day+'T17:00:00Z',
            tag=key+':'+reason+(annotation if reason=='OPEN' else ''),
            symbol={'id':'HD '+base36(put if side==0 else put-10**19)},
            groupOrderManager={'id':group},events=[dict(fillQuantity=(-quantity if reason=='OPEN' else quantity))]))
    return rows


def test_report_verifies_full_nonoverlapping_batches():
    rows=combo(1,'A','OPEN')+combo(2,'B','OPEN',volume=99)+combo(3,'A','TIME')+combo(4,'B','TIME')
    entries,batches,peak=audit_batches(rows,504)
    assert len(entries)==2 and len(batches)==1 and peak==2


def test_report_rejects_new_batch_while_a_position_remains():
    rows=combo(1,'A','OPEN')+combo(2,'B','OPEN',volume=99)+combo(3,'A','TIME')
    with pytest.raises(ValueError,match='every previous holding'):
        audit_batches(rows+combo(4,'C','OPEN',batch=2,count=1),504)
    with pytest.raises(ValueError,match='Replacement entry'):
        audit_batches(rows+combo(4,'C','OPEN',batch=1),504)


def test_report_rejects_silent_quantity_change():
    rows=combo(1,'A','OPEN',count=1,quantity=5)+combo(2,'A','TIME',quantity=1)
    with pytest.raises(ValueError,match='quantity changed'):
        audit_batches(rows,504)


def test_rejected_roll_is_a_nonexecuted_attempt_and_margin_exit_closes_batch():
    rejected=combo(2,'A','ROLL',quantity=0)
    for r in rejected:r.update(status=7)
    rows=combo(1,'A','OPEN',count=1)+rejected+combo(3,'A','MARGIN')
    entries,batches,peak=audit_batches(rows,504)
    assert len(entries)==1 and len(batches)==1 and peak==1
    rejected[0]['events'][0]['fillQuantity']=1
    with pytest.raises(ValueError,match='Unequal leg quantities'):
        audit_batches(rows,504)


def test_insolvent_performance_keeps_debt_without_inventing_cagr():
    from datetime import date
    from basket_report import basket_performance_window
    result=basket_performance_window({date(2020,3,9):872.71,date(2020,3,12):-42.29},
        872.71,date(2020,3,9),date(2020,3,12))
    assert result['net_pnl']==-915
    assert result['return_fraction']<-1
    assert result['max_daily_drawdown']>1
    assert result['cagr'] is None


def test_cross_run_fill_comparison_retains_price_fee_and_event_suffix():
    from performance_report import cross_run_signature
    a=dict(event_id='runA-1-2',qc_price=1.5,fee=1,quantity=-5)
    b=dict(a,event_id='runB-1-2')
    assert cross_run_signature([a])==cross_run_signature([b])
    for field,value in [('qc_price',1.6),('fee',2),('quantity',-4),('event_id','runB-1-3')]:
        assert cross_run_signature([a])!=cross_run_signature([dict(b,**{field:value})])
