# Option Omega twelve-ticker data requirements

Updated 2026-10-27, revision 1.1. Supersedes the 2026-10-26 consumer summary for future data work; frozen v0.8.5 evidence is unchanged.

Canonical provider request: [QC_0DTE_OO_12_TICKER_5M_REQUIREMENTS_20261027.md](/home/vic/data_providers/docs/requirements/QC_0DTE_OO_12_TICKER_5M_REQUIREMENTS_20261027.md). Machine-readable [JSON](/home/vic/data_providers/docs/requirements/QC_0DTE_OO_12_TICKER_5M_REQUIREMENTS_20261027.json) and [ticker CSV](/home/vic/data_providers/docs/requirements/QC_0DTE_OO_12_TICKER_5M_REQUIREMENTS_20261027.csv).

Universe: SPX (SPXW PM only), SPY, QQQ, IWM, AAPL, AMZN, GLD, MSFT, NVDA, TLT, TSLA, IBIT. IBIT is delivery Tier C/P2. All Q0–Q10 requirements apply: full-chain 5m quotes, 1m decision windows, timestamp/availability evidence, IV/Greeks including gamma, contract master, settlement/assignment, underlying, OI, trades and actions.

| Current regular schedule | Tickers |
|---|---|
| Every weekday | SPX, SPY, QQQ, IWM, GLD |
| Mon/Wed/Fri | AAPL, AMZN, MSFT, NVDA, TSLA, TLT, IBIT |

GLD added Tue/Thu in August 2026. The five single stocks added Mon/Wed in January 2026. IBIT options launched 2024-11-19; Mon/Wed eligibility changed during 2026, including a Q3 interruption and August restoration. These are schedules, not a substitute for actual per-session listings. See the canonical request for sources, transition dates and exceptions.

History remains 2022-05-16–2026-10-22 except IBIT options start no earlier than 2024-11-19 and its underlying warm-up no earlier than 2024-01-11. Request the original 17-date pilot plus transition probes with explicit no-expiry/prelaunch statuses. No nearest-expiry substitution or synthetic history. Twelve-ticker size/cost remains pending Q0; the old 332.8M-row estimate excludes IBIT.

Provider next action: inventory, capability matrix, pilot and cost estimate. Preserve existing acquisition gates and source receipts.
