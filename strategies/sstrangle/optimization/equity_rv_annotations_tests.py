from datetime import date
import pytest
from equity_rv_annotations import audit_equity_rv_annotation

CONFIG = dict(min_equity_iv_rv=1.2, future_rv_policy='original_rules')
LAST = date(2020, 9, 1)


def annotation():
    return dict(rv_policy='equity_iv_to_max_rv20_rv60', rv20='.20', rv60='.25',
                iv='.30', iv_rv='1.2', rv_samples='61', rv_source='SCALED_RAW',
                rv_last_session=str(LAST), rv_threshold='1.2')


def test_boundary_equity_and_explicit_future_policy_pass():
    audit_equity_rv_annotation('SPY native', annotation(), CONFIG, LAST)
    audit_equity_rv_annotation('FUT_CL', {'rv_policy': 'future_original_rules'}, CONFIG, LAST)


@pytest.mark.parametrize('field,value', [
    ('rv_policy', 'future_original_rules'), ('rv20', 'nan'), ('rv60', '0'),
    ('iv', '.2'), ('iv_rv', '1.1'), ('rv_samples', '60'), ('rv_source', 'RAW'),
    ('rv_last_session', '2020-09-02'), ('rv_threshold', '1.1')])
def test_missing_or_inconsistent_equity_evidence_rejected(field, value):
    m = annotation(); m[field] = value
    with pytest.raises(ValueError): audit_equity_rv_annotation('SPY native', m, CONFIG, LAST)


def test_future_cannot_be_silently_filtered_or_annotated_with_equity_source():
    with pytest.raises(ValueError): audit_equity_rv_annotation('FUT_CL', {}, CONFIG, LAST)
    with pytest.raises(ValueError):
        audit_equity_rv_annotation('FUT_CL', dict(rv_policy='future_original_rules', rv20=.2), CONFIG, LAST)
