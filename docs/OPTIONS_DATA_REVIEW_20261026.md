# Strategy data review and provider handoff

Reviewed 2026-10-26. Default request: **5-minute option quote snapshots**, derived 15m/30m option views, 30m primary underlying signals and 15m comparisons, plus daily context. The OptionOmega 11-ticker addendum adds a 1-minute layer at the 13 entry slots; 5-minute remains the full-day grid. Finer quotes otherwise remain targeted exceptions. Five-minute sampling does not prove quote freshness or minute-exact execution parity.

The consolidated review covers SPXW 0DTE, SS45DTE mechanical research, the separate manual 45DTESS workflow, the historical basket, daily S001/S002 and minute-input SML01/Wang research. Strategy source/configuration differences, current provider evidence and acceptance criteria are recorded in the handoff.

- [Provider requirements](/home/vic/data_providers/docs/requirements/QC_STRATEGY_OPTIONS_DATA_REQUIREMENTS_20261026.md)
- [Machine-readable scope and source hashes](/home/vic/data_providers/docs/requirements/QC_STRATEGY_OPTIONS_DATA_REQUIREMENTS_20261026.json)
- [OptionOmega 11-ticker 5m addendum](/home/vic/data_providers/docs/requirements/QC_0DTE_OO_11_TICKER_5M_REQUIREMENTS_20261026.md) — OO-supported universe, 5m full day plus 1m decision-slot layer; pending inventory and 17-date pilot

SPX coverage requested through 2026-10-22, retaining the original 2026-07-13 boundary. SS45DTE replay covers 2024-01-02 through 2026-10-23 plus IV warmup. Reuse the existing bounded pilots before broader backfills.

New October 26 Theta benchmark receipts report merged sampled quotes, so older blanket no-NBBO statements are stale. Originating quote age remains unknown in that benchmark; SPXW coverage and final publication require reconciliation. This review reads saved evidence, not a new canonical database census.

Requirements are saved in the provider ledger. No acquisition, strategy changes, trading or messages to provider chats were performed by this handoff.
