# 0.9.2 verified diagnostic receipts

[Design and self-review](../../research/design_20261107_v092/DESIGN.md). Preserves v091 and the v090 feature engine. Adds digest-last receipt publication and independent strict decoding, freezes caller plans, and rejects ambiguous callback bindings. Method docstrings and indentation are preserved. At most four checkpoints use 72 runtime-statistic keys.

From `/home/vic/qc_work`:

```bash
.venv/bin/python -m strategies.sstrangle.poc.v092.build_probe \
  --base strategies/sstrangle/poc/v087/strategy_official_funded.py \
  --plan strategies/sstrangle/poc/v092/example_plan.json \
  --out /absolute/new/probe-directory
.venv/bin/python -m strategies.sstrangle.poc.v092.receipt \
  --statistics /absolute/exported-runtime-statistics.json \
  --plan /absolute/capture-plan.json
```

The decoder expects the runtime-statistics dictionary itself. All planned checkpoints must be present, internally consistent, and valid snapshots in their own windows/phases. Error/capacity receipts and pending digests fail. SHA256 detects corruption; it neither authenticates origin nor proves engine callback ordering. Concurrent exported reads can fail verification and require a fresh complete export. The example windows remain illustrative. Plans use the algorithm clock and make no pre-trigger claim. Native group API compatibility, runtime-statistic capacity in cloud, exact matched cloud account parity, historical margin/IV cause, strict provider inputs and economic acceptance remain unverified. Source assembly submits nothing.

Dynamic class/module mutation, custom metaclasses and monkey patching are outside the assembler's supported static source contract; review the base source before cloud use. Local syntax/AST checks do not prove semantic equivalence for arbitrary Python programs.
