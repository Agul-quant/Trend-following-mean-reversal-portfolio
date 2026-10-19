# Data sources and dataset specification

This document describes the underlying 56-ETF research dataset and distinguishes
it from the six-strategy saved-account snapshot currently published here. It does
not distribute market observations, change a frozen study or release another run.
The [README](../README.md#full-56-etf-universe) lists all 56 tickers by category.

## Sources and roles

| Component | Source | Fields and use |
|---|---|---|
| Daily market records | Alpha Vantage `TIME_SERIES_DAILY_ADJUSTED` | Session date, raw open/high/low/close, adjusted close, volume, dividend amount and split coefficient; daily features, corporate actions and reconciliation anchors |
| Executable observations | Alpha Vantage `TIME_SERIES_INTRADAY`, 30-minute interval | Timestamp and OHLCV; regular-session observations used by the underlying execution study |
| Additional intraday evidence | Alpha Vantage `TIME_SERIES_INTRADAY`, 15-minute interval | Available overlapping OHLCV captures checked against 30-minute records; not a complete all-symbol/all-date panel |
| Session calendar | `exchange_calendars`, XNYS | Session dates, opens/closes, holidays, early closes and daylight-saving transitions; a calendar, not a price feed |
| Cash reference | Study accounting model | Fixed 3% nominal annual rate, ACT/365 and event-time compounding; not a FRED series, realized bank rate or 3% APY |
| Portfolio-layer inputs | Previously saved strategy and cost-matched passive-control accounts | Aligned daily net wealth/returns and cash returns derived by the private execution engine; not a separate market-data vendor |

Official references: [Alpha Vantage API documentation](https://www.alphavantage.co/documentation/)
and [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars).
The historical research uses retained Alpha Vantage captures, not Yahoo Finance
hourly data. A separate present-day signal-monitoring workflow is not an input
to these backtests. Multiple captures and daily anchors from one vendor do not
constitute independent-vendor validation.

## Coverage and study boundaries

| Role | Calendar bounds | Interpretation |
|---|---|---|
| Feature initialization | From 2015-01-01, where the ETF existed and observations are available | Daily indicator history only; at least 295 completed pre-development daily observations required; no fabricated pre-inception history |
| Development | 2017-01-01–2020-12-31 | The unchanged 379 definitions per ETF: 289 trend and 90 long/cash mean-reversion rules |
| Restored validation | 2021-01-01–2023-12-31 | Exact eligible development survivors; only ETFs with more than five development survivors advance, subject to data eligibility |
| Restored historical OOS | 2024-01-01–2026-10-15 | Locked validation survivors in ETFs with more than five validation survivors; fixed endpoint |
| Published six-strategy portfolio snapshot | 2024-01-01–2026-10-15 | Earlier split, 700 common daily valuations from 2024-01-02; restored active portfolio study |

The active report basis is restored to development 2017–2020, validation 2021–2023
and historical OOS 2024–2026-10-15. The alternative validation
**2021-01-01–2024-12-31** / OOS **2025-01-01–2026-10-15** experiment is inactive.
Its private artifacts are preserved but are not inputs or selections for these
reports. No corrected-split portfolio fitting is presented.

The universe has 56 ETFs: 6 US equity indices, 13 international/country equities,
10 broad sectors, 13 industries/subsectors, 9 bond ETFs and 5 commodity/precious-
metal ETFs. There are 21,224 possible ETF/configuration pairs at development and
84,896 candidate-cost evaluations across four costs, excluding controls. These
are research-design dimensions, not a claim that all 56 enter later stages.

Calendar bounds are not observations on weekends or holidays. Regular sessions
normally run 09:30–16:00 America/New_York; early closes shorten the bar grid.
Native local timestamps are interpreted with daylight saving and normalized to
UTC. The study does not require pre-market or after-hours observations. Available
15-minute evidence is supplementary, not a substitute fabricated by resampling.

Feature history is not a claim of complete intraday coverage from 2015 for every
ETF. In particular, XLRE uses its verified available daily history for initialization;
missing pre-development intraday records are not invented. Every scored stage
requires its own calendar, coverage, price-unit and source checks. Timestamp
presence alone is not a certification of usable prices or stage eligibility.

## Price basis, corporate actions and quality controls

- Retain native raw payloads, normalized representations, request metadata and
  capture receipts privately, with hashes identifying the actual input vintage.
- Receipt-verified native intraday captures request unadjusted, regular-session
  prices (`adjusted=false`, `extended_hours=false`). Where legacy adjusted
  intraday bars are used, restore their as-traded price units only with their
  matching historical daily adjustment vintage. Never apply fresh factors to an
  old adjusted series, fit a scale factor or silently call restored data native raw.
- Preserve explicit split/reverse-split, distribution, reinvestment and paid
  terminal-liquidation conventions. Approved source revisions and ETF-specific
  frozen exceptions remain documented privately; exceptions do not transfer to
  other ETFs. Newly downloaded adjusted histories are not assumed identical.
- Check duplicates, missing bars, holidays, early closes, daylight saving,
  available 15-to-30-minute OHLC consistency, native overlaps and monthly daily
  anchors. Do not fill missing executable prices or relax discrepancies to pass.
- A provider's raw daily close is not asserted to be an official auction close
  or identical to the last regular-session half-hour close. Separate captures
  remain same-provider evidence, and the dataset is not claimed to be a complete
  point-in-time record of every revision known on every historical date.
- Each stage starts flat with $1,000, empty orders and confirmation streaks.
  Only feature history carries forward. Each account uses 1-bp commission plus
  1/3/10/25-bp one-way slippage, charged each way, with matched own-ETF buy-and-hold
  and cash controls. Indicators and trades cannot be reconstructed from daily
  adjusted close alone.

## What “full dataset” means here

The complete research input set comprises daily market/action records, native or
matching-vintage-restored half-hour observations, available quarter-hour evidence,
session calendars, coverage/blackout records and private provenance. The saved
portfolio bundle is a **derived subset**, not the original market dataset:

| Array | Published-snapshot shape | Meaning |
|---|---|---|
| `timestamps` | `(700,)` | Aligned daily valuation times |
| `symbols` | `(6,)` | GDX, FXI, QQQ, UNG, FDN, BND |
| `slippage_bps` | `(4,)` | 1, 3, 10, 25 bps each way, in addition to commission |
| `sleeve_normalized_equity` | `(4, 700, 6)` | Net active-strategy wealth, normalized by initial stage capital |
| `buy_and_hold_returns` | `(4, 700, 6)` | Cost-matched passive ETF simple returns |
| `cash_returns` | `(700,)` or `(4, 700)` | Matched event-compounded cash returns |

See the [input contract](input_schema.md) for validation requirements. These
dimensions describe the earlier published snapshot, not a ready-made bundle
for a differently bounded OOS period or the full 56-ETF universe.

## Access and reproducibility

**No public full-data download is provided.** Raw captures, full derived daily
paths, private source maps, authorizations and freezes are intentionally excluded
from Git. Aggregate CSV tables and PNG curves cannot reconstruct original prices
or trades; the public repository alone is not full end-to-end replication.

For equivalent market inputs, obtain Alpha Vantage access appropriate to the
documented daily and historical intraday endpoints, subject to its current access
and usage terms. Historical intraday queries support monthly requests and raw
prices; access is not assumed free. This repository does not provide a downloader
or permission to redistribute the provider's dataset. Fresh downloads may differ
from the retained vintage and must be reconciled separately.

For exact published portfolio-number recomputation, the source holder must supply
the private saved-account bundle matching the [input schema](input_schema.md),
then run the [three-period calculation command](periods.md) at the saved allocations. This
recomputes the portfolio analytics only; it does not reproduce intraday signals,
corporate-action processing or original execution QA. Synthetic tests need no
provider account, credentials or market data and are not performance evidence.
