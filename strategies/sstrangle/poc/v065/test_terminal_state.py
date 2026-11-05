from terminal_state import terminal_ready

def test_completed_flag_without_final_statistics_is_not_a_terminal_artifact():
 assert not terminal_ready({'completed':True,'statistics':{},'runtimeStatistics':{'Equity':'$248768'}})
 assert terminal_ready({'completed':True,'statistics':{'Total Orders':'67570'},'runtimeStatistics':{'native_net_pnl':'154255.02','ledger_error':'0','filled_episodes':'11584'}})
 assert terminal_ready({'completed':True,'error':'native failure'})
 assert not terminal_ready({'completed':False})
