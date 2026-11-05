"""Independently reject late, undeclared and incorrectly prioritised holding exits."""
import copy
import json
from pathlib import Path
import pytest
import report
from holding_source_chain import freeze_chain,verify_chain,HELPERS,HERE


def fixture(day='2022-10-17',reason='AGE',expiry='2022-11-18',clock='16:00:00'):
    entry='2022-09-21T16:00:00Z'
    cycles=[dict(ticker='TWTR VLE97YS7S57P',entry=entry,exit=day+'T'+clock+'Z',
        expiry=expiry,entry_dte=58,rolls=1,reason=reason)]
    entries=[dict(key=cycles[0]['ticker'],entry=entry,batch_id=1,quantity=2,
        allocation_budget=2000,max_holding_days='24')]
    return cycles,entries


def test_weekend_deadline_uses_first_product_open_noon():
    cycles,entries=fixture();report.audit_dates(cycles,entries,21,24)
    assert cycles[0]['first_eligible_age_exit_date']=='2022-10-17'


@pytest.mark.parametrize('day,clock',[('2022-10-14','16:00:00'),('2022-10-17','15:59:00'),
    ('2022-10-17','16:06:00'),('2022-10-18','16:00:00')])
def test_age_wrong_day_or_time_rejected(day,clock):
    with pytest.raises(ValueError):report.audit_dates(*fixture(day,clock=clock),21,24)


def test_other_exit_cannot_hide_overdue_age():
    with pytest.raises(ValueError,match='survived maximum'):
        report.audit_dates(*fixture('2022-10-18',reason='STOP'),21,24)


def test_earlier_real_stop_is_allowed():report.audit_dates(*fixture('2022-10-14',reason='STOP'),21,24)


def test_time_precedence_and_original_dte_deadline_survive():
    cycles,entries=fixture('2022-09-30',expiry='2022-10-21')
    entries[0]['max_holding_days']='9'
    with pytest.raises(ValueError,match='TIME precedence'):
        report.audit_dates(cycles,entries,21,9)
    cycles[0]['reason']='TIME'
    report.audit_dates(cycles,entries,21,9)
    with pytest.raises(ValueError,match='survived mandatory DTE'):
        report.audit_dates(*fixture(expiry='2022-10-21'),21,24)


def test_no_undeclared_age_and_missing_annotation_rejected():
    with pytest.raises(ValueError,match='Undeclared AGE'):report.audit_dates(*fixture())
    cycles,entries=fixture();entries[0].pop('max_holding_days')
    with pytest.raises(ValueError,match='annotation|audited opening'):report.audit_dates(cycles,entries,21,24)


def test_frozen_source_and_helper_tamper_rejected(tmp_path):
    extras={name:(HERE/name).read_text() for name in HELPERS}
    freeze_chain(tmp_path,extras);source=(HERE/'holding_cap_main.py').read_text()
    verify_chain(tmp_path,source,extras)
    bad=copy.deepcopy(extras);bad['holding_age.py']+='\n#changed\n'
    with pytest.raises(ValueError,match='dependency'):verify_chain(tmp_path,source,bad)
    with pytest.raises(ValueError,match='implementation'):verify_chain(tmp_path,source+'\n',extras)
    root=tmp_path/'source_chain/root.py';root.write_text(root.read_text()+'\n')
    with pytest.raises(ValueError,match='hash mismatch'):verify_chain(tmp_path,source,extras)


def test_actual_full_dry_render_and_queued_source_proof():
    import hashlib
    campaign=HERE.parent/'results/strangle_basket-calmar_20261019_204028'
    manifest=json.loads((campaign/'manifest.json').read_text())
    assert len(manifest['variants'])==1
    key,cfg=next(iter(manifest['variants'].items()))
    assert cfg['max_holding_days']==24 and cfg['lookback']==504
    assert cfg['start']==[2012,1,3] and cfg['end']==[2026,9,30] and cfg['initial_cash']==60000
    source=(campaign/(key+'.py')).read_text();extras=(campaign/'extra_files.json').read_text()
    assert source==(HERE/'holding_cap_main.py').read_text().replace('CONFIG = {}','CONFIG = '+repr(cfg),1)
    row=dict(code=source,extra_files=extras,code_hash='dry-run-only')
    proof=report.verify_frozen_source(campaign,key,cfg,row)
    assert proof['queued_code_and_helpers_identical']
    assert hashlib.sha256((HERE.parent/'basket/main.py').read_bytes()).hexdigest()=='430c1186b7d049ee3adf91b229602d71518d3dd6b5728cf4afa4a24b5b78bf6c'
    bad=copy.deepcopy(cfg);bad['fresh_risk_retry']=False
    changed=source.replace('CONFIG = '+repr(cfg),'CONFIG = '+repr(bad),1)
    temp=campaign/(key+'.py')
    # Never change frozen campaign sources, even for negative tests.
    assert temp.read_text()==source
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as directory:
        folder=Path(directory);(folder/(key+'.py')).write_text(changed)
        (folder/'extra_files.json').write_text(extras)
        with pytest.raises(ValueError,match='configuration mismatch'):
            report.verify_frozen_source(folder,key,bad,dict(row,code=changed))


def test_real_closed_cycle_envelope_requires_declared_age_annotation():
    # Unit-test copies only: genuine original orders remain untouched.
    campaign=HERE.parent/'results/strangle_basket-calmar_20261019_182746'
    manifest=json.loads((campaign/'manifest.json').read_text())
    cfg=next(iter(manifest['variants'].values()));cfg=dict(cfg,max_holding_days=24)
    path=campaign/'SSTRANGLE_20261019_182746_cap20_stop1_guard_rv12_exit21/orders.json'
    original=path.read_bytes();orders=json.loads(original)[:8]
    with pytest.raises(ValueError,match='holding-duration annotation'):
        report.audit_budget_annotations(orders,cfg)
    for order in orders[:2]:order['tag']+=';max_holding_days=24'
    entries,batches,peak=report.audit_budget_annotations(orders,cfg)
    assert peak==1 and len(entries)==1 and len(batches)==1
    assert path.read_bytes()==original
    for order in orders[:2]:order['tag']=order['tag'].replace('max_holding_days=24','max_holding_days=25')
    with pytest.raises(ValueError,match='holding-duration annotation'):
        report.audit_budget_annotations(orders,cfg)
