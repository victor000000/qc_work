"""Decode exported LEAN option identifiers without guessing from mapped aliases.

Decimal property layout and OLE date epoch follow LEAN SecurityIdentifier.cs:
https://github.com/QuantConnect/Lean/blob/master/Common/SecurityIdentifier.cs
"""
from datetime import date, datetime, timedelta, timezone
import math
from audit import order_multiplier,order_group_id


def option_identity(symbol):
    root,encoded=symbol['id'].split('|',1)[0].rsplit(' ',1)
    properties=int(encoded,36)
    security_type=properties%100
    if security_type not in (2,8,9):
        raise ValueError('Identifier is not an option')
    days=properties//10**14%100000
    right=properties//10**19%10
    if not days or right not in (0,1):
        raise ValueError('Invalid or canonical option identifier')
    unscaled=properties//10**7%1000000
    negative=bool(unscaled & (1<<19))
    if negative:
        unscaled ^= 1<<19
    strike=unscaled*10.0**(properties//10**5%100-6)*(-1 if negative else 1)
    return dict(option_root=root,expiry=str(date(1899,12,30)+timedelta(days=days)),
                call_put='P' if right else 'C',strike=strike,security_type=security_type)


def execution_rows(orders):
    rows,seen=[],set()
    for order in sorted(orders,key=lambda o:o['id']):
        if order['id'] in seen:
            raise ValueError('Duplicate order')
        seen.add(order['id'])
        events=order.get('events') or []
        if not isinstance(events,list):
            raise ValueError('Order events must be a complete event list')
        quantities=[float(event.get('fillQuantity',0)) for event in events]
        if any(not math.isfinite(q) for q in quantities):
            raise ValueError('Nonfinite actual fill quantity')
        status=str(order.get('status','')).replace('_','').replace(' ','').lower()
        # Live QC exports can report Filled while omitting every execution event.
        # Empty decoder output must never certify zero actual trades or cashflow.
        if status in ('2','partiallyfilled','3','filled'):
            if not any(quantities):
                raise ValueError('Filled/partially-filled order lacks genuine fill events')
            requested=float(order['quantity']);actual=sum(quantities)
            if (not math.isfinite(requested) or requested==0 or actual*requested<=0
                    or abs(actual)>abs(requested)+1e-9):
                raise ValueError('Actual fill quantities disagree with native order')
            if status in ('3','filled') and not math.isclose(actual,requested,rel_tol=0,abs_tol=1e-9):
                raise ValueError('Filled order has incomplete genuine fill events')
        identity=option_identity(order['symbol'])
        key,reason=order['tag'].split(';',1)[0].split(':',1)
        for event in events:
            quantity=float(event.get('fillQuantity',0))
            if not quantity:
                continue
            if event.get('isAssignment') or event.get('fillPriceCurrency')!='USD':
                raise ValueError('Assignment/non-USD execution requires separate accounting')
            if 'orderFeeAmount' not in event:
                raise ValueError('Genuine fill event lacks explicit fee evidence')
            fee=float(event['orderFeeAmount'])
            if not math.isfinite(fee):
                raise ValueError('Nonfinite actual fill fee')
            price=float(event['fillPrice'])
            if not math.isfinite(price) or price<0:
                raise ValueError('Invalid actual option fill price')
            underlying=order['symbol'].get('underlying',{})
            underlying_id=order['symbol']['id'].split('|',1)[1]
            rows.append(dict(order_id=order['id'],event_id=event['id'],
                timestamp=datetime.fromtimestamp(event['time'],timezone.utc).isoformat(),
                strategy_key=key,reason=reason,symbol_id=order['symbol']['id'],
                symbol=order['symbol']['value'],underlying=underlying_id.rsplit(' ',1)[0],
                underlying_id=underlying_id,underlying_alias=underlying.get('value',''),**identity,
                quantity=quantity,qc_price=price,
                multiplier=order_multiplier(order),fee=fee,
                group_id=order_group_id(order),tag=order['tag']))
    return rows


def execution_signature(rows):
    # Rust's typed Symbol omits the optional nested display alias. The native SID
    # still preserves the actual underlying identity, including future delivery.
    return [{k:v for k,v in row.items() if k!='underlying_alias'} for row in rows]
