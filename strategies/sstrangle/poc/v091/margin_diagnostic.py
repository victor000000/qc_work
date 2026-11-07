"""Read-only native account diagnostics; never changes liquidation requests."""
import json


def margin_snapshot(algorithm, requests):
    from QuantConnect.Securities.Positions import ReservedBuyingPowerForPositionGroupParameters
    groups = []
    for group in algorithm.portfolio.positions.groups:
        reserved = group.buying_power_model.get_reserved_buying_power_for_position_group(
            ReservedBuyingPowerForPositionGroupParameters(algorithm.portfolio, group))
        groups.append(dict(model=str(group.buying_power_model.GetType().Name),
                           reserved=float(reserved.absolute_used_buying_power),
                           positions=[dict(symbol=str(p.symbol), quantity=float(p.quantity))
                                      for p in group.positions]))
    return dict(time=str(algorithm.time), equity=float(algorithm.portfolio.total_portfolio_value),
                cash=float(algorithm.portfolio.cash), used=float(algorithm.portfolio.total_margin_used),
                remaining=float(algorithm.portfolio.margin_remaining), groups=groups,
                holdings=[dict(symbol=str(s.symbol), quantity=float(s.holdings.quantity),
                               value=float(s.holdings.holdings_value))
                          for s in algorithm.securities.values() if s.invested],
                requests=[dict(symbol=str(r.symbol), quantity=float(r.quantity)) for r in requests])


def observe_margin_call(algorithm, requests):
    # Diagnostic failures must not change native risk management.
    try:
        payload = margin_snapshot(algorithm, requests)
    except Exception as exc:
        payload = dict(error=type(exc).__name__, detail=str(exc)[:200])
    algorithm.debug('MARGIN_DIAGNOSTIC ' + json.dumps(payload, separators=(',', ':')))
    return requests


def record_margin_state(algorithm, prefix, *, once=False, phase=None):
    """Bounded receipt; unique once=True prefixes preserve separate observations.

    A phase is a caller label, not proof that a native margin scan followed it.
    Seal only after all writes succeed; never share prefixes between phases.
    """
    sealed = getattr(algorithm, '_margin_receipt_sealed', set())
    if prefix in sealed:
        return False
    try:
        payload = margin_snapshot(algorithm, [])
    except Exception as exc:
        payload = dict(error=type(exc).__name__, detail=str(exc)[:200])
    if phase is not None:
        payload['phase'] = str(phase)
    raw = json.dumps(payload, separators=(',', ':'))
    if len(raw) > 2880:
        raw = json.dumps(dict(error='capacity', length=len(raw)))
    for i in range(16):
        algorithm.set_runtime_statistic(prefix + str(i).zfill(2), raw[i*180:(i+1)*180] or ' ')
    algorithm.set_runtime_statistic(prefix + 'len', str(len(raw)))
    if once:
        algorithm._margin_receipt_sealed = sealed | {prefix}
    return True
