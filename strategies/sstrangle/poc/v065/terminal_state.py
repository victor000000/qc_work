"""QC completion can precede publication of final account statistics."""
def terminal_ready(backtest):
    if not backtest.get('completed'):return False
    if backtest.get('error'):return True
    return ('Total Orders' in (backtest.get('statistics') or {})
            and all(k in (backtest.get('runtimeStatistics') or {}) for k in ['native_net_pnl','ledger_error','filled_episodes']))
