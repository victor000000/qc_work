"""Data-quality and feature parity diagnostics without choosing strategy parameters."""
from pathlib import Path
import json,hashlib
import pandas as pd
from local_engine import feature
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'strategies/sstrangle/results/qc_poc_20261027_v087'
p=ROOT/'strategies/sstrangle/results/qc_sizing_poc_20261024/provider/us_prices_full/data.parquet'
legacy=pd.read_parquet(p);legacy=legacy[legacy.symbol=='QQQ'].sort_values('date');old=[[str(r.date),r.high,r.low,r.close] for r in legacy.itertuples()]
new=pd.read_parquet(OUT/'independent_qqq_features.parquet').values.tolist();days=sorted(set(pd.read_parquet(OUT/'local_slots.parquet').day));rows=[]
for day in days:
 a=feature(old,day);b=feature(new,day);rows.append(dict(day=day,legacy=a,independent=b,decision_equal=(a is not None and a>.016380462988098386)==(b is not None and b>.016380462988098386)))
f=pd.DataFrame(rows);f.to_parquet(OUT/'feature_parity.parquet',index=False)
x=pd.read_parquet(OUT/'independent_selection_inputs.parquet');assert all(x.contract_id.str.split(':').str[2]=='SPXW')
d={'feature_days':len(f),'equal_filter_decisions':int(f.decision_equal.sum()),'max_absolute_feature_difference':float((f.legacy-f.independent).abs().max()),'legacy_feature_source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'joined_rows':len(x),'joined_sessions':x.day.nunique(),'joined_minutes':sorted(x.hm.unique().tolist()),'quote_event_timestamps':int(x.quote_ts.notna().sum()),'availability_timestamps':int(x.available_at.notna().sum()),'gamma_values':int(x.gamma.notna().sum()),'contract_root_spxw_only':True,'duplicate_contract_timestamp_rows':int(x.duplicated(['contract_id','interval_ts']).sum()),'limitations':['Raw daily features agree/disagree on values only; historical availability is unverified.','These are returned candidate snapshots, not complete historical listing or selection eligibility proof.']}
(OUT/'diagnostics.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
