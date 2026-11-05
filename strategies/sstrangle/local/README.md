# Local options research with AKQuant

This adapter freezes the original managed QC baseline and replays its fill schedule in AKQuant. It uses shared-provider exports and targeted Alpaca captures through the existing provider transport. It does not regenerate entries, exits, rolls or replacement trades.

Run natively in the workspace Linux/WSL `.venv`; Docker is not required. See the [environment guide](../../../docs/ENVIRONMENT.md).

Install from the workspace root:

```bash
uv pip install --python .venv/bin/python -r requirements-data.txt
uv pip install --python .venv/bin/python -r strategies/sstrangle/local/requirements.txt
```

Use a new result folder for each immutable run:

```bash
.venv/bin/python strategies/sstrangle/local/prepare.py --output <new-result-folder>
.venv/bin/python strategies/sstrangle/local/capture.py <new-result-folder>
.venv/bin/python strategies/sstrangle/local/replay.py <new-result-folder>
.venv/bin/python strategies/sstrangle/local/warehouse.py <new-result-folder>
```

The downloaded QC source is preserved with a hash and reconciled to its audited cash ledger. Capture requests cover only actual baseline contracts/dates. API credentials remain in the provider's normal runtime configuration. Completed responses are cached; failed captures remain retryable. Canonical provider stores are read-only.

The QC-price control verifies execution accounting. Provider scenarios use the latest completed same-day minute trade bar before the scheduled order, without future bars or QC price fallback. Five- and thirty-minute thresholds retain only entire covered cycles. The full same-day scenario is a stale-trade sensitivity. Every scenario checks actual AKQuant fill prices, quantities, fees, final equity and zero residual positions.

Instrument metadata uses actual OCC expiry/right/strike and multiplier 100. The engine uses explicit per-order QC fees, `CurrentClose()` and synthetic execution-only bars with ample matching volume. A premium-based ratio margin configuration permits the frozen schedule; it is not QC's IB margin model or a fresh sizing decision. No broker quotes, spread, combo fill guarantee, assignment model or daily marked equity is inferred from the synthetic bars. Do not use their intermediate drawdown or annualized engine metrics as market-valued results.

The warehouse stores labels separately from entry features and exports each table to checksummed Parquet. Daily features use raw underlying closes from completed prior days, conservatively available at midnight New York time on the following day. Intraday feature construction is a further extension; the provider has historical TLT minutes, while the examined SPY/GLD minute coverage is incomplete for the baseline period. Missing data must remain explicit.

The [recording notes](../../../data/audio/options_backtest_workflow/WORKFLOW.md) describe how this fits the speaker's workflow and why changing a rule requires a new baseline tape. The [completed first run](../results/local_akquant_20261017/LOCAL_RESULTS.md) contains the audited comparisons.
