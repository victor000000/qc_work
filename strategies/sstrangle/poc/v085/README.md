# 0.8.5 — native baseline, bounded local research, funded QC verification

This directory contains the completed SPXW iron-condor research pipeline and a rejected two-leg put-credit-spread add-on. The spread passed its smoke but stopped on a native margin call on July 12, 2022 in the full baseline. `scope_amendment.json` excludes that failed tape before selection; only 13 condor rules are evaluated. Frozen older versions remain unchanged. Both new accounts start with $100,000, one-lot entries and 20-point protection; native buying power applies. The put spread is an explicit 0DTE adaptation of Tom's credit-spread ideas, not a source-exact replication.

The experiment contract was saved before new baseline outcomes. It permits 13 rules per strategy and excludes later-period counts from selection. `research.py` filters native episode payoffs; it does not simulate an independent options market. All dates are historical development/evaluation evidence. Raw features and outcome labels are saved separately; the joined research table is never uploaded.

Run from `/home/vic/qc_work`, with the existing shared worker running and credentials configured:

```bash
.venv/bin/python strategies/sstrangle/poc/v085/campaign.py baseline
PYTHONPATH=scripts:strategies/sstrangle/poc/v085 .venv/bin/python -m pytest strategies/sstrangle/poc/v085 -q
.venv/bin/python strategies/sstrangle/poc/v085/research.py
.venv/bin/python strategies/sstrangle/poc/v085/campaign.py final
.venv/bin/python strategies/sstrangle/poc/v085/verify.py
.venv/bin/python strategies/sstrangle/poc/v085/settlement_audit.py
.venv/bin/python strategies/sstrangle/poc/v085/settlement_rule_sensitivity.py
.venv/bin/python strategies/sstrangle/poc/v085/analyze.py
.venv/bin/python strategies/sstrangle/research/design_20261026_v085/build_report.py
```

The first command submits a put-spread smoke and two full baselines. The attempted spread baseline exits with a failure; inspect `put_spread_failure.json` and the recorded scope amendment. Research must finish before the final command submits the frozen condor candidate. `campaign.py` resumes existing identities and never deliberately duplicates a queue name. Do not start a second controller concurrently. A failed or uncertain native create needs identity inspection, not resubmission. Completed source snapshots are preserved before the next serial submission.

`collect.py` extends the archived native collector to audit two-put spread geometry, exact combo identities, one-lot quantities, modeled slippage, fees, cash expiry, annual counts and residual holdings. `payoff.py` independently recalculates every expiry payoff from native contract/fill/settlement observations. `verify.py` reconciles common trades and actual funding rejections; it also checks legacy condor reproduction and raw feature decisions.

`settlement_audit.py` is a separate outcome-only sensitivity against saved official Cboe archives. It must not silently replace the native ledger. Differences and uncovered dates remain explicit. These archives do not certify historical publication clocks.

Evidence lives in `../../results/qc_poc_20261026_v085/`; final design and measured findings live in `../../research/design_20261026_v085/`. A successful pipeline does not imply economic improvement, official-settlement equivalence, positive margin headroom, or live readiness. Read the separate gates in `final_verification.json` and `decision_record.json`.
