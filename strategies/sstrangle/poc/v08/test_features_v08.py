import json,sys
from pathlib import Path
import numpy as np
from feature_engine import FeatureBook
ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'strategies/sstrangle/results/qc_sizing_poc_20261024'
def test_selected_formula_matches_native_range_and_prior_session():
 raw=json.loads((OUT/'raw_inputs.json').read_text());book=FeatureBook(raw['prices'],raw['vix']);rules=json.loads((OUT/'frozen_rules.json').read_text())
 for rule in rules.values():
  symbol=rule['feature'].split('_')[0].upper();rows=[r for r in raw['prices'] if r[0]==symbol]
  for row in rows[1:]:
   value,source=book.value(row[1],rule['feature']);previous=[r for r in rows if r[1]<row[1]][-1]
   assert source==previous[1];assert abs(value-(previous[3]-previous[4])/previous[5])<1e-12

def test_future_mutation_cannot_change_historical_features():
 raw=json.loads((OUT/'raw_inputs.json').read_text());book=FeatureBook(raw['prices'],raw['vix']);before=book.panel.loc[:'2023-12-29'].copy()
 for row in raw['prices']:
  if row[1]>='2024-01-01':row[2:6]=[float(x)*2 for x in row[2:6]]
 for row in raw['vix']:
  if row[0]>='2024-01-01':row[1]*=3
 after=FeatureBook(raw['prices'],raw['vix']).panel.loc[:'2023-12-29'];assert before.equals(after)

def test_stale_features_fail_closed():
 raw=json.loads((OUT/'raw_inputs.json').read_text());book=FeatureBook(raw['prices'],raw['vix']);assert book.value('2026-11-15','qqq_range_pct')[0] is None
