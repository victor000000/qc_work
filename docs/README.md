> Latest 0.9.0 validation (2026-11-05): [C0 margin and IV evidence](../strategies/sstrangle/results/margin_verified_v090_20261105/RESULTS.md). 427 tests passed. Cloud-tested diagnostic/API and publication-race fixes preserve exact native account parity. C0 still fails on margin; IV replay passes but historical root cause remains open. Pre-trigger margin state, full sidecar/feature parity, strict provider inputs and economic acceptance remain gaps.

> Updated 2026-11-05: [0.9.0 clock fix confirmed](../strategies/sstrangle/results/fix_v090_20261105/RESULTS.md). 421 tests passed; four fresh QC runs confirm 390/390 regular and 210/210 early-close coverage, valid finalization, exact orders/cash/equity parity. Independent sidecar readback, warmed-axis/C1/P1 validation, strict provider inputs and native IV robustness remain open.

# Documentation guide

Latest follow-up: [2026-11-05 provider audit and six QC cloud runs](../strategies/sstrangle/results/validation_v090_20261105/RESULTS.md). Regular account parity passed; full observer/data acceptance remains open.

Updated 2026-10-31. Current SSTRANGLE design: **[0.9.0](../strategies/sstrangle/research/design_20261030_v090/DESIGN.md)**. [Recorded results](../strategies/sstrangle/results/custom_axis_v090_20261030/RESULTS.md): 417 tests passed; synthetic and sampled real-data PoCs completed. Strict provider acceptance, native cloud parity and funded economics remain open.

Read in this order:

1. [Project handbook](PROJECT_HANDBOOK.md): detailed setup, workspace/code map, contracts, commands, troubleshooting and handoff.
2. [Current work](CURRENT_WORK.md): dated evidence and limitations.
3. [Next steps](TODO.md): ordered acceptance dependencies.
4. [0.9.0 design](../strategies/sstrangle/research/design_20261030_v090/DESIGN.md) and [implementation](../strategies/sstrangle/poc/v090/README.md): behavior and executable interfaces.
5. [CLI usage](../USAGE.md) before executor operations.

## Working references

| Need | Document |
|---|---|
| Set up the workspace | [Native environment guide](ENVIRONMENT.md), [workspace README](../README.md) |
| Use the Rust QC executor | [CLI usage](../USAGE.md) |
| Understand existing infrastructure | [Architecture](ARCHITECTURE.md) |
| Navigate options research | [Short-strangle README](../strategies/sstrangle/README.md) |
| Understand existing local replay limits | [Local engine README](../strategies/sstrangle/local/README.md) |
| Review design changes and source interpretation | [Comment resolution](../strategies/sstrangle/research/design_20261023_v6/COMMENT_RESOLUTION.txt), [audio demo extraction](../strategies/sstrangle/research/design_20261023_v5/DEMO_STRATEGY_EXTRACTION.txt) |
| Understand storage migration | [DuckDB migration](DUCKDB_MIGRATION.md), [path migration](MIGRATION.md) |
| Find older verification | [Dated verification](VERIFICATION.md), [October 18 review](PROJECT_REVIEW_20261018.md) |
| Review the OptionOmega 0DTE data request | [Consumer summary](OPTIONOMEGA_0DTE_5M_DATA_REQUIREMENTS_20261026.md), [canonical provider requirements](/home/vic/data_providers/docs/requirements/QC_0DTE_OO_11_TICKER_5M_REQUIREMENTS_20261026.md) |

## Keeping docs useful

- Update **Current work** when a result, blocker or working direction changes. Update **Next steps** when work starts or finishes.
- Keep instructions in README/USAGE, present status in Current work, and future work in Next steps. Link rather than copy long explanations.
- Date evidence and identify its scope. A draft, prototype, local test and audited cloud result are different states.
- Preserve frozen campaign sources, failed evidence and reviewed design versions. Create a new design revision when its substance changes.
- Historical reports and archived continuation fields are evidence, not instructions to restart old jobs. Current work identifies the intended next step; inspect live execution state before any operational action.
- Never store credentials in documentation. Keep provider ownership and requirements in the data providers project; link to them here.

Placeholder vocabulary: **TODO** = unfinished work; **Detail design** = specification needed; **Ref** = supporting source; **Decision** = unresolved choice; **PoC** = measured feasibility experiment; **Acceptance** = pass/fail evidence required; **Data gap** = missing input or coverage. Each backlog item should name a concrete deliverable and dependency.
