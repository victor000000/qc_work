# 0.9.1 bounded margin probe

[Design and pre-implementation self-review](../../research/design_20261107_v091/DESIGN.md).

This diagnostic revision adds bounded immutable observations and native group membership. The v090 axis engine remains the feature implementation. Plans use naive datetimes in the algorithm clock. The example plan is an illustrative historical window, not evidence of native scan ordering. Choose windows using the frozen case under investigation. Missing, error or capacity receipts fail evidence acceptance.

From the workspace root:

```bash
.venv/bin/python -m strategies.sstrangle.poc.v091.build_probe \
  --base strategies/sstrangle/poc/v087/strategy_official_funded.py \
  --plan strategies/sstrangle/poc/v091/example_plan.json \
  --out /absolute/new/probe-directory
.venv/bin/python -m pytest strategies/sstrangle/poc/v091 -q
```

The output is standalone source plus a provenance manifest; assembly submits no cloud jobs. Existing callbacks retain their bodies and return values. A missing margin callback returns the original requests. Publication exceptions are isolated; incomplete receipts cannot be interpreted as successful observations. Order-event observations may precede or follow a fill and never imply fill status. Before interpreting any cloud probe, compare complete orders, cash and equity with its matched baseline and validate native group API compatibility. No trading improvement or margin/IV root-cause resolution is claimed.
