> Superseded for future data work by [twelve-ticker revision 1.1](OPTIONOMEGA_0DTE_5M_DATA_REQUIREMENTS_20261027.md), dated 2026-10-27. Historical text below is retained.

# OptionOmega 0DTE 5-minute data requirements — consumer summary

Date: 2026-10-26 · Status: requirement drafted; provider inventory and pilot pending. No purchase or download was started.

Canonical provider request: [QC 0DTE OptionOmega-universe 5-minute data requirements](/home/vic/data_providers/docs/requirements/QC_0DTE_OO_11_TICKER_5M_REQUIREMENTS_20261026.md) · [ticker matrix](/home/vic/data_providers/docs/requirements/QC_0DTE_OO_11_TICKER_5M_REQUIREMENTS_20261026.csv) · [scope JSON](/home/vic/data_providers/docs/requirements/QC_0DTE_OO_11_TICKER_5M_REQUIREMENTS_20261026.json).

## The short version

- **Universe:** exactly the 11 underlyings OptionOmega supports for backtesting — SPX (SPXW PM only), SPY, QQQ, IWM, AAPL, AMZN, GLD, MSFT, NVDA, TLT, TSLA.
- **Tiers:** A = SPX, SPY, QQQ, IWM; B = TSLA, NVDA; C = AAPL, AMZN, MSFT, GLD, TLT.
- **Window:** 2022-05-16 through 2026-10-22, daily warm-up from 2021-01-01; only sessions with an actually listed same-day expiry.
- **Primary data:** 5-minute option quote snapshots, 09:30–16:00 ET, all listed same-day strikes and both rights; 79 snapshots / 78 underlying bars on a normal day, 43 / 42 on a 13:00 close.
- **Timing layer:** 1-minute quotes for the six minutes ending at each of the 13 entry slots (09:35, 10:00, 10:30 … 15:30). 5-minute alone cannot supply a pre-decision quote at a 5-minute boundary.
- **Fields:** NBBO bid/ask and sizes, quote timestamps/age, IV, delta, **gamma**, theta, vega, rho; underlying 5-minute bars; official settlement; daily OI; separate option trade volume; contract master; rates/dividends/actions; VIX/VIX9D.
- **Pilot:** 17 dates across all 11 tickers, then Tier A → Tier B → Tier C full history.

## The critical caveat

OptionOmega does **not** ingest third-party option chains. Its CSV upload is a custom entry/exit signal file only. Its native backtest resolution is **1 minute**, with 1-second IMSL only for SPX/SPY stop research. The provider data is for independent selection, quote-quality, settlement and reconciliation — it is not "the data OptionOmega uses" and cannot be loaded into OO as a chain.

A 5-minute panel is a sampled research dataset. It does not establish OO parity at the 13 entry slots. That is why the request adds the 1-minute decision-window layer. If only one grid can be bought, buy 1-minute and derive 5-minute.

## Planning volume

At 1,100 sessions and 79 snapshots, the 5-minute panel is roughly:

| Scope | Contract-sessions/session | 5m rows | Retained estimate |
|---|---:|---:|---:|
| Tier A | 2,450 | 212.9M | 32–64 GB |
| Tier A+B | 2,950 | 256.4M | 38–77 GB |
| All 11 | 3,830 | 332.8M | 50–100 GB |

These are planning assumptions using 150–300 bytes/row for raw + indexed DuckDB + one Parquet release + Greeks. The measured QQQ 0DTE quote-only Parquet was 141 MB for 23.95M rows (~5.9 bytes/row), so the retained estimate is conservative. The 1-minute slot layer roughly doubles the row count; full 1-minute is about 5×.

## Next action

Provider returns:

1. Q0 per-date 0DTE listing inventory and capability matrix.
2. A 17-date pilot with Q0–Q10 datasets and QA.
3. Cost/time estimate for the full backfill.

No bulk acquisition until the inventory and pilot are reviewed.
