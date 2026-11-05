"""Publication gates for QC backtest evidence, independent of success/failure."""


def published_order_count(backtest):
    """None means pending evidence, never a proved empty order tape."""
    if not backtest.get('completed'):
        return None
    value = backtest.get('statistics', {}).get('Total Orders')
    if value is None:
        return None
    count = int(str(value).replace(',', ''))
    if count < 0:
        raise ValueError('Negative published order count')
    return count
