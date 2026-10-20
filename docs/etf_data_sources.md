# ETF Data Sources and Research Scope

This publication covers the following **47 ETFs**. The table is a
scope-restricted presentation of previously examined research, **not a newly
run 47-ETF campaign**, a fresh selection exercise or proof that every listed
ETF advanced through every stage. It does not recompute historical membership
counts or performance. The current portfolio uses **GDX, FXI, QQQ, UNG and FDN**.

## Published research universe

| Category | Count | Products |
|---|---:|---|
| US equity indices | 6 | SPY, QQQ, DIA, IWM, MDY, VTI |
| International / country equities | 13 | EEM, EFA, EWA, EWC, EWJ, EWT, EWW, EWY, EWZ, FXI, INDA, MCHI, VGK |
| Broad US sectors | 10 | XLB, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY |
| Industries / subsectors | 13 | FDN, GDX, GDXJ, IBB, ITB, KBE, KRE, SMH, SOXX, XBI, XHB, XOP, XRT |
| Commodities / precious metals | 5 | DBC, GLD, SLV, UNG, USO |

## Sources and their roles

| Component | Source | Use |
|---|---|---|
| Daily prices and corporate actions | Retained Alpha Vantage `TIME_SERIES_DAILY_ADJUSTED` captures | Raw OHLC, adjusted close, volume, distribution amount and split coefficient; causal daily features, actions and reconciliation anchors |
| Executable observations | Retained Alpha Vantage `TIME_SERIES_INTRADAY`, 30-minute interval | Native raw regular-session OHLCV, or explicitly restored legacy records using the matching historical adjustment vintage |
| Supplementary intraday evidence | Available Alpha Vantage 15-minute captures | Overlap and 15-to-30-minute OHLC consistency checks; not a complete universe-wide panel |
| Trading calendar | `exchange_calendars`, XNYS | Sessions, holidays, early closes, daylight-saving transitions and scheduled checkpoint dates; not a price feed |
| Cash reference | Accounting model | Fixed 3% nominal ACT/365 event-compounded cash; not a downloaded interest-rate series, realized deposit yield or 3% APY |
| Portfolio inputs | Previously audited strategy events, account paths and matched controls | Source-bound inputs for the completed portfolio calculations; not an additional market-data vendor |

Source references: [Alpha Vantage documentation](https://www.alphavantage.co/documentation/)
and [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars).
Retained historical captures, rather than present-day signal-monitoring data,
underlie this research. Multiple captures, daily anchors and intraday intervals
from the same provider are **not independent-vendor verification**.

## Time boundaries and initialization

| Role | Calendar bounds | Account treatment |
|---|---|---|
| Feature initialization | From 2015-01-01, subject to actual inception and verified availability | At least 295 completed pre-development daily observations; no fabricated pre-inception prices |
| Development | 2017-01-01–2020-12-31 | Fresh, flat account; feature history only carries forward |
| Validation | 2021-01-01–2023-12-31 | Independently restarted account and unchanged released definitions |
| Historical OOS | 2024-01-01–2026-10-15 | Independently restarted account; fixed complete-session endpoint |

Each underlying ETF/configuration study begins with $1,000. Each reported
portfolio also begins independently with **$1,000 total**, divided among its
five cash sleeves at the saved initial weights—not $1,000 in each sleeve.
Holdings, orders and confirmation streaks do not carry between stages.

Calendar labels are not promises of observations on weekends or holidays.
Regular sessions normally run 09:30–16:00 America/New_York; early closes shorten
the executable bar grid. Native local timestamps are interpreted across daylight
saving and normalized to UTC. Portfolio marks occur at 17:00 New York.

Initialization uses available verified daily history, not invented intraday
records. For example, XLRE's available pre-development daily history is used
without filling absent initialization-period half-hours. Every scored stage
still requires its own strict session coverage and price-basis evidence.

## Price basis and quality checks

- Preserve capture receipts, request metadata, normalized payloads and hashes
  privately so each input has an identifiable source vintage.
- Receipt-verified native intraday inputs use unadjusted regular-session prices
  (`adjusted=false`, `extended_hours=false`). Restore legacy adjusted bars only
  with their **matching historical adjustment factors**. Fresh adjustment
  factors must not be applied to old adjusted bars, and restored records must
  not be mislabeled native raw.
- Reconcile splits and reverse splits, distributions, duplicates, missing bars,
  holidays, early closes, daylight saving, available 15-to-30-minute overlaps,
  native-source overlaps and monthly daily anchors. Timestamp completeness by
  itself does not certify prices or stage eligibility.
- Keep approved source revisions and ETF-specific exceptions documented in the
  original private evidence. Exceptions do not transfer between ETFs. Unexplained
  discrepancies remain failures; missing executable prices are not interpolated.
- A provider's daily raw close is not asserted to be an official auction close
  or identical to the final half-hour close. The captures are not claimed to
  reconstruct every provider revision available at every historical instant.
- Preserve the original action, reinvestment and paid terminal-liquidation
  conventions. A fresh download is not automatically equivalent to the retained
  vintage, and adjusted daily closes alone cannot reconstruct the study's trades.

## Public access and reproducibility boundary

**No raw market data or complete numerical account paths are distributed.**
Private captures, event primitives, source maps, authorizations, credentials,
freezes and full daily arrays remain outside Git. Public CSV/JSON tables contain
aggregate outcomes. Published PNG curves visualize saved paths without embedding
the daily numerical series or private input locations.

Public source and synthetic tests allow inspection of accounting and scope
checks, but the public repository alone is **not full end-to-end financial
replication**. Exact financial reproduction additionally requires the source
holder's authenticated, reconciled, stage-bounded private inputs and audit chain.
Access to equivalent provider data is subject to the provider's current terms;
fresh captures require separate reconciliation and are not promised to recreate
the saved figures exactly.

[Methods](etf_methods.md) ·
[Current aggregate report](../reports/etf_portfolios/report.md) ·
[Selected strategy definitions](../configs/selected_etf_strategies.json)
