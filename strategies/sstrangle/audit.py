"""Reconstruct whole strategy cycles from QC order fill events."""
import math
from datetime import datetime


def rejected_roll(orders):
    """Only a wholly rejected, fee-free two-leg roll may be ignored by the ledger."""
    return (len(orders) == 2 and
        all(o.get('tag','').split(';',1)[0].endswith(':ROLL') for o in orders) and
        all(o.get('status') in (5, 7) for o in orders) and
        all(not float(e.get('fillQuantity',0)) and not float(e.get('orderFeeAmount',0))
            for o in orders for e in o.get('events',[])))


def order_group_id(order):
    """Native combo ID, or a negative logical ID for two ordinary closing orders."""
    native = (order.get('groupOrderManager') or {}).get('id')
    m = dict(p.split('=',1) for p in order.get('tag','').split(';')[1:] if '=' in p)
    if native is not None:
        if 'close_pair' in m:
            raise ValueError('Sequential closing order unexpectedly has native combo ID')
        return native
    reason = order.get('tag','').split(';',1)[0].split(':')[-1]
    if (m.get('execution') != 'sequential_close' or reason in ('OPEN','ROLL')
            or order.get('securityType') != 8 or int(m.get('close_pair','0')) <= 0):
        raise ValueError('Ungrouped order is not an identified futures-option close')
    return -int(m['close_pair'])


def validate_sequential_close(orders):
    """Logical pairing never relaxes native fill, quantity, fee or timing checks."""
    if not any(order_group_id(o) < 0 for o in orders):
        return
    if len(orders) != 2 or len({o['tag'] for o in orders}) != 1:
        raise ValueError('Sequential close must have two identically tagged orders')
    if len({o['symbol']['id'] for o in orders}) != 2:
        raise ValueError('Sequential close requires two distinct contracts')
    times = [datetime.fromisoformat(o['time'].replace('Z','+00:00')) for o in orders]
    if (max(times)-min(times)).total_seconds() > 300:
        raise ValueError('Sequential close exceeded five minutes')
    quantities = [sum(float(e.get('fillQuantity',0)) for e in o.get('events',[])) for o in orders]
    if quantities[0] <= 0 or quantities[0] != quantities[1]:
        raise ValueError('Sequential close must buy equal positive quantities')
    for order, quantity in zip(orders, quantities):
        if order.get('status') != 3 or order.get('type') != 0 or float(order['quantity']) != quantity:
            raise ValueError('Sequential close lacks a complete native market fill')


def order_multiplier(order):
    metadata = dict(part.split('=',1) for part in order.get('tag','').split(';')[1:] if '=' in part)
    if 'multiplier' in metadata:
        value = float(metadata['multiplier'])
        if not math.isfinite(value) or value <= 0:
            raise ValueError('Invalid contract multiplier')
        return value
    if order.get('securityType') == 8:
        raise ValueError('Future option requires an explicit contract multiplier')
    return 100.0  # Legacy equity/index-option evidence used standard 100-unit contracts.


def reconstruct(orders):
    groups = {}
    seen = set()
    for order in sorted(orders, key=lambda o: o['id']):
        if order['id'] in seen:
            raise ValueError('Duplicate order in downloaded pages')
        seen.add(order['id'])
        tag = order.get('tag', '')
        multiplier = order_multiplier(order)
        if ':' not in tag:
            raise ValueError('Unexpected order tag: ' + tag)
        ticker, reason = tag.split(':', 1)
        reason = reason.split(';', 1)[0]
        group = order_group_id(order)
        key = (ticker, reason, group)
        record = groups.setdefault(key, dict(ticker=ticker, reason=reason,
            time=order['time'], cash=0.0, fees=0.0, legs=0, orders=[]))
        record['orders'].append(order)
        filled = False
        for event in order.get('events', []):
            quantity = float(event.get('fillQuantity', 0))
            if quantity:
                record['cash'] -= quantity * float(event['fillPrice']) * multiplier
                record['fees'] += float(event.get('orderFeeAmount', 0))
                filled = True
        if filled:
            record['legs'] += 1
    active, cycles = {}, []
    for group in groups.values():
        ticker, reason = group['ticker'], group['reason']
        validate_sequential_close(group['orders'])
        if rejected_roll(group['orders']):
            if ticker not in active:
                raise ValueError('Rejected roll has no active holding')
            continue
        if group['legs'] != 2:
            raise ValueError('Expected two filled legs in each combo')
        if reason == 'OPEN':
            if ticker in active:
                raise ValueError('Overlapping cycles for ' + ticker)
            active[ticker] = dict(ticker=ticker, entry=group['time'], initial_credit=group['cash'],
                                  cash=0.0, fees=0.0, rolls=0)
        cycle = active[ticker]
        cycle['cash'] += group['cash']
        cycle['fees'] += group['fees']
        if reason == 'ROLL':
            cycle['rolls'] += 1
        elif reason != 'OPEN':
            cycle.update(exit=group['time'], reason=reason, pnl=cycle['cash']-cycle['fees'])
            cycles.append(cycle)
            del active[ticker]
    if active:
        raise ValueError('Unclosed cycles in order history')
    return cycles
