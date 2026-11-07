> Current documentation boundary (2026-11-07): this is the workspace-imported SML01 package, distinct from the independently versioned quant-autoresearch repository. [Workspace setup and isolated tests](../../docs/CI_CD.md) are current; program/analysis records below retain their dated scoring gates and findings. Omitted private models/data cannot be reconstructed from historical champion scores. Round/research scripts can contact QC and mutate state; do not use them or their help paths as smoke tests without source inspection. Historical ObjectStore reset evidence is not a present cleanup instruction or current model-availability check.

# Quant Autoresearch Workspace

An autonomous ML quant-research loop (inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch))
applied to ETF trading on QuantConnect. An agent edits the pipeline, backtests on QC, scores on **REAL
out-of-sample Calmar**, and keeps-if-better — behind a stack of honesty gates (permute control,
deflation, leak tests) so the number cannot be gamed.

**Start here:** [`program.md`](program.md) — the contract (goal, the loop, the keep gates, the
look-ahead-leak rules, current champions).

## Cloud storage reset — 2026-10-17

The organization ObjectStore was cleared at the user's explicit request. Earlier cloud
models and caches must be regenerated before inference or champion replay. Local source,
configs, experiment databases and historical results remain available. The round driver
already trains before inference; historical replay scripts require newly saved artifacts.

## Layout

The repo uses an editable install (`pip install -e .` via `pyproject.toml`): all importable code lives
under `src/lb/` (the `lb` package); mutable state (`knowledge.json`, `results/`, etc.) stays at the
repo root, and `lb.paths.ROOT` is derived from the source tree. The QuantConnect ObjectStore keys are
namespaced `autoresearch/{TICKER}/...` (a QC data path, deliberately unchanged).

| Path | Purpose |
|---|---|
| `program.md` | The contract / instructions (read first). |
| `src/lb/harness/` | **LOCKED scorer** — `qc_client.py`, `orchestrator.py`, `psuf.py` (cell-key helpers), `constants.py`. |
| `src/lb/templates/` | `header/footer/infer` `*.py.tmpl` rendered into the QC `main.py`. |
| `src/lb/modules/` | **Editable pipeline** — `bar_builder.py` + `bar_ext.py` (axis), `labeler.py` (labels), `features.py` + `ml_ext.py` (features/reduce/model), `trainer.py` + `sizing_ext.py` (training/sizing). |
| `src/lb/metrics.py` | Drawdown-shape metrics (Ulcer / Pain / Martin / time-under-water). |
| `scripts/run_round.py` | The round driver (2-node A/B tournament). |
| `scripts/audit/` | Honesty stack — DSR, deflated Calmar, regime split, PBO, online-FDR, `honest_audit.py` (writes `docs/analysis/HONEST_AUDIT.md`). |
| `scripts/research/` | Monitors + verifiers — decay/e-value monitors, online-parity proofs (`verify_*`), portfolio rederive, screen-table regenerator, IV harvester. |
| `tests/` | Leak + integrity guards — `test_bar_threshold_leak.py` (look-ahead), `test_psuf_tokens.py` (cell keys), `test_render_budget.py` (QC 64k). |
| `knowledge.json` · `hypotheses.json` | Shared memory (`per_etf_best`, findings) · queued configs per ticker. |
| `results/round_results.csv` | The race ledger (every leg, every round). |
| `docs/analysis/` | Standing evidence — `BACKTEST_AUDIT.md` (online/leak-free proof), `HONEST_AUDIT.md`, `CHAMPION_DECAY.md`, `DEPLOYMENT.md`. |
| `docs/research/ETF_SCREEN_TABLE.md` | Durable universe-screen results (closed 2026-06-12). |
| `qc/` | QC Cloud API client + `.creds.json` (gitignored). |
| `refs/` · `scratch/` | Reference PDFs / transcripts and old experiments (gitignored, excluded from the public repo). |

## Running

```bash
cd strategies/sml01
# explicit round (two CONFIG JSONs, same ETF, raced on the 2 QC nodes):
python3 scripts/run_round.py \
  '{"ticker":"GLD","axis":"logdollar","labeler":"trend_leg+regime_gmm","thresh":0.40,"sizing":"dd_overlay"}' \
  '{"ticker":"GLD","axis":"logdollar","labeler":"ker","thresh":0.45,"sizing":"cdf_overlay"}'
# auto (pick weakest ETF from knowledge.json, read its two configs from hypotheses.json):
python3 scripts/run_round.py
```

A CONFIG is `{ticker, axis, labeler, thresh, sizing}` + optional `{reduce, n_components, features,
model, calibration, horizons, permute_labels}`. The driver renders one TRAIN → one INFER per
hypothesis, logs both legs to `results/round_results.csv`, and updates `knowledge.json.per_etf_best`
iff the keep gates pass (see `program.md`).

The round driver queues jobs in the shared workspace's `data/SML01.duckdb`. Run the Rust
server from the workspace root before starting rounds; it owns project allocation,
compilation, execution deadlines and result collection. Initialize a missing database
with `qc-backtest-server --data-dir ./data init-strategy --strategy sml01`.
`QC_DATA_DIR` or `SML01_DB_PATH` can select another runtime database.

The driver waits up to `SML01_JOB_TIMEOUT` (default 2,400 seconds), including queue wait.
On a driver timeout it cancels a queued job; an already running execution remains owned
by the server and its result is collected there. Splits: train ≤ 2021-08,
val ≤ 2023-08, test ends 2026-07-01.

## Status

Research is exhausted within the current data (2026-06-12). Champions: GLD 4.70 (gold-trend) and
USO 2.82 (oil-reversion) — the two replication-confirmed engines — plus gated candidates DIA/DXJ and
`always_long` decorrelation seats. See the book table in `program.md`.
