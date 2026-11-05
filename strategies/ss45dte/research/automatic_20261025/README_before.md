# ss45dte — a 45-DTE entry / 21-DTE exit short strangle

Created 2026-10-25 from `dte_21_screener` to test the specification in
`reports/loss_attribution_2026-10-25/web/strategy.html`. This is a **new, isolated strategy**:
it has its own database (`data/SS45DTE.duckdb`) and touches no other strategy's queue.

## What is here

| File | Purpose |
| --- | --- |
| `strategy.py` | Self-contained LEAN algorithm (the queue stores one code blob, so no workspace imports) |
| `README.md` | This file |

## What the algorithm does

- Universe: the five names whose p5 was actually measured — CRWD, EWZ, META, TLT, SWKS.
  Names without a measured p5 are deliberately excluded: an unmeasured tail would be a guess.
- Monthly expiry nearest 45 DTE, delta-neutral, both legs inside 0.16–0.22.
- Size by tail, not margin:
  `contracts = (equity × 5% ÷ 5 names) ÷ (2 × vega × p5_Δσ)`, where vega is computed
  analytically from the contract's own implied vol.
- Exit at 21 DTE. No rolling, no re-centring, no adding legs.
- `MODE` selects the variant under test: `exit21` (the specification), `hold` (control),
  `stop` (exit21 plus close on |delta| > 0.35).

## How to run

```bash
cd /home/vic/qc_work

# 1. register / queue a variant (duplicate names are rejected, so bump the suffix)
./target/release/qc-backtest-server queue \
  --strategy ss45dte --name SS45DTE_A_exit21_v3 \
  --code-file strategies/ss45dte/strategy.py \
  --batch ss45dte_20261025 --priority 1 \
  --description "A: 45-DTE entry, 21-DTE exit, p5 sizing" \
  --hypothesis "isolates the 21-DTE exit"

# 2. run it (foreground; the server holds a write lock on the strategy DB while serving)
./target/release/qc-backtest-server serve

# 3. inspect
./target/release/qc-backtest-server show --strategy ss45dte --name SS45DTE_A_exit21_v3
```

To compare A against the control, edit `MODE = "hold"` in `strategy.py`, queue it under a new
name, and compare `show` output. The difference between the two isolates the single rule the
specification currently justifies by derivation alone.

## Status, 2026-10-25 (test log)

The harness works end to end; the strategy itself has not yet produced a result.

| Run | Outcome | What it taught |
| --- | --- | --- |
| `A_exit21` | failed at 09:31 on the first session | `Greeks.ImpliedVolatility` does not exist; the attribute is on the contract |
| `A_exit21_v2` | completed, **zero orders**, ~2h at minute resolution | the pipeline runs, but no entry ever fired |
| `DIAG_v1` | zero orders, empty log | QC caps logs at 100 kb per backtest and per day, so `Debug` is not a usable channel here |
| `DIAG_v2` | failed | `SetRuntimeStatistics(dict)` does not exist in this LEAN build |
| `DIAG_v3` | **success** | chains=5; per name 40-48 contracts, 2 expiries, `Greeks=yes`, IV present (SWKS 0.364, TLT 0.165) |
| `A_probe_v6` | running | wide strike filter + counters; pending |

**Root cause of the zero-order runs.** The option filter used `Strikes(-8, 8)`. A 45-DTE
20-delta strike on a $250 name at 55% vol sits about 9-11 strikes out, so the filtered chain
never contained a contract in the 0.16-0.22 band. Widened to `Strikes(-20, 20)`.

**Two environment facts worth keeping.**
- Runtime statistics are the only output channel available once the log quota is gone; the
  strategy now reports `n_entry`, `n_band`, `n_qty`, `n_exit` as statistics.
- This workspace has a single QC backtest node. An abandoned minute-resolution run held it for
  about two hours and made later creates fail with "remote create outcome is uncertain"; the
  QC API exposes no abort endpoint through this client. The run finished on its own.

