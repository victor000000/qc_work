"""Audit authentic opening annotations for the explicit equity-only RV rule."""
import math


def audit_equity_rv_annotation(key, metadata, config, expected_last_session):
    threshold = float(config['min_equity_iv_rv'])
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError('Invalid frozen equity IV/RV threshold')
    if config.get('future_rv_policy') != 'original_rules':
        raise ValueError('Undeclared futures RV policy')
    if key.startswith('FUT_'):
        if metadata.get('rv_policy') != 'future_original_rules':
            raise ValueError('Future did not retain original admission rules')
        if any(field in metadata for field in ('rv20', 'rv60', 'iv_rv', 'rv_samples',
                                               'rv_last_session', 'rv_threshold', 'rv_source')):
            raise ValueError('Unvalidated RV feature attached to future entry')
        return
    if metadata.get('rv_policy') != 'equity_iv_to_max_rv20_rv60':
        raise ValueError('Missing declared equity IV/RV policy')
    rv20, rv60, iv, ratio, declared = (
        float(metadata[field]) for field in ('rv20', 'rv60', 'iv', 'iv_rv', 'rv_threshold'))
    if any(not math.isfinite(v) or v <= 0 for v in (rv20, rv60, iv, ratio, declared)):
        raise ValueError('Nonpositive/nonfinite equity volatility feature')
    if (float(metadata['rv_samples']) != 61 or metadata.get('rv_source') != 'SCALED_RAW'
            or metadata.get('rv_last_session') != str(expected_last_session)):
        raise ValueError('Equity source window/normalization/as-of annotation mismatch')
    if (not math.isclose(declared, threshold, rel_tol=0, abs_tol=1e-12)
            or not math.isclose(ratio, iv / max(rv20, rv60), rel_tol=1e-10, abs_tol=1e-12)
            or ratio < threshold):
        raise ValueError('Equity IV/RV admission or configured threshold mismatch')
