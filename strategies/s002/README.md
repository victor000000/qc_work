> Reviewed navigation (2026-11-07): use [workspace configuration](../../docs/CONFIGURATION.md), [offline tests](../../docs/CI_CD.md) and [recovery](../../docs/OPERATIONS.md). Dry-run/render/queue commands have different effects; documentation inspection alone does not authorize experiments.

# S002 ETF research

Independent strategy source and mutation tools. Shared execution is provided by
`crates/qc-server`; this strategy's queue and results live in `data/S002.duckdb`.
`QC_DATA_DIR` overrides the runtime directory. Historical bake backups live in
`archive/baselines/`.

The active template is `s002_20260628_ls_base.py`. Tools support direct invocation
from this directory. From the workspace root:

```bash
.venv/bin/python strategies/s002/queue_round.py --help
(cd strategies/s002 && ../../.venv/bin/python -m pytest)
```

Review generated probes with `queue_round.py ROUND --dry-run` before submitting a
research round. Real queue commands are intentional experiment submissions and use
shared QC compute when the server is running.
