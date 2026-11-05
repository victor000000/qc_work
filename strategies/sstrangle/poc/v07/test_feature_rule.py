from feature_rule import feature_value,rule_pass

def test_future_rows_and_today_cannot_change_previous_completed_feature():
 rows=[['2024-01-02',102,98,100,1000],['2024-01-03',500,1,400,100000]]
 assert feature_value(rows,'2024-01-03','qqq_range_pct')==(.04,'2024-01-02')
 rows[-1][1]=99999
 assert feature_value(rows,'2024-01-03','qqq_range_pct')==(.04,'2024-01-02')

def test_intraday_seven_day_age_limit_and_boundaries():
 rows=[['2024-01-02',102,98,100,1000]]
 assert feature_value(rows,'2024-01-10','qqq_range_pct')[0] is None
 assert not rule_pass(.04,.04,'above') and rule_pass(.04,.04,'below')
 assert not rule_pass(None,.04,'above')
