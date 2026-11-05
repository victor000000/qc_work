"""Prospective calendar holding deadline; exchange/noon eligibility is external."""
from datetime import date


def validate_max_holding_days(days):
    if type(days) is not int or not 1<=days<=45:
        raise ValueError('An explicit integer holding deadline from1to45days is required')
    return days


def age_exit_due(opened,today,days):
    validate_max_holding_days(days)
    opened=date.fromisoformat(opened) if isinstance(opened,str) else opened
    if type(opened) is not date or type(today) is not date or today<opened:
        raise ValueError('Ordered native entry/decision dates are required')
    return (today-opened).days>=days
