# Frozen forward paper portfolio

## What is fixed

The user explicitly chose **Initial allocation; no rebalancing** as the one
primary forward paper portfolio. It is not selected from future results.
Weekly and Monthly corrections remain retrospective comparisons, not alternative
forward winners. The [public freeze](../configs/paper_portfolio_freeze.json)
seals the exact five definitions, full-precision initial weights, operational
source hashes, runtime versions, actual UTC freeze timestamp and start open.
Its canonical SHA256 is an integrity check; the GitHub commit supplies a public
publication record. Neither alone proves an independent trusted timestamp.

- Five sleeves: GDX, FXI, QQQ, UNG and FDN, using the unchanged saved rules.
- Allocate **$1,000 total per cost scenario**, initially flat, at the exact
  saved weights. No rebalancing, cap corrections, deposits, withdrawals or
  cross-sleeve cash redistribution. Whole sleeve weights may drift above 1/3.
- Four independent paper accounts: 1-bp commission plus 1/3/10/25-bp one-way
  slippage each way; **3 bps** is the fixed headline scenario.
- Cash: modeled **3% nominal ACT/365 event-compounded**, not a guaranteed yield.
- Carry causal feature history initialized from verified 2015 daily records;
  require a complete verified seed through the session preceding inception.
  Do not carry historical holdings, orders or confirmation streaks.
- Daily causal indicators, native 30-minute observations, three-trading-hour /
  seven-consecutive-check confirmation; execution only at a later eligible
  observed open. Splits, distributions and the inherited fee-free reinvestment
  proxy follow the explicitly frozen engine.
- Start on **October 21, 2026 at 09:30 America/New_York (13:30 UTC)**, after the
  actual October 20 freeze. Do not count October 16–20 as forward performance.
  If implementation/publication is not complete before this open, do not backdate
  a start: preserve the attempted seal and make a separately disclosed later
  launch, without looking at its subsequent outcomes to choose a date.

This is an **ongoing marked-to-market paper simulation**. There is no forced
terminal sale at each monitoring cutoff. Strategy orders may close positions;
a later decision to end tracking requires an explicit, prospective stop rule.
Matched QQQ buy-and-hold starts at the same future eligible open and pays its
initial purchase costs; it is not sold at each update. The cash control follows
the same event clock. Historical accounts retain their original paid final
liquidation and are never spliced into this forward account.

## Data and observation discipline

Raw ETF prices/actions, feature seeds, per-sleeve holdings, fill ledgers and
capture evidence stay private. Only aggregate net daily portfolio, matched QQQ
and cash RETURNS and non-sensitive tracking status are public.

A sealed private input packet must supply all five native raw regular-session
half-hours, the actual XNYS session grid (holidays, early closes and DST), daily
marks/actions, causal daily seed, availability/capture times, and strict
price-basis/coverage/reconciliation receipts. A declaration of timestamp
completeness alone is not evidence that prices are raw or reconciled. Never
apply fresh adjustment factors to legacy adjusted observations.

No downloader or broker is bundled in the tracker. **An automatic collector /
QA-packet producer is not configured by this release.** The input schema is
implemented, but an attestation with evidence hashes is not an independent
reconciliation audit; the feed operator must supply genuine passing receipts. Scheduled checks are
**read-only consumers of the existing local data feed**: they must not use
credentials, start competing downloads, or change an external queue, its files,
locks, controls or rate. If a certified packet has not arrived, report
**awaiting verified data** and the affected dates. Do not fabricate flat returns,
assume no trades, silently move inception or report a verified running account.

Store observations with both market timestamps and actual processing/capture
receipt times. Updates based on late captures are **delayed fixed-rule paper
reconstructions**, not contemporaneously logged orders or real executable fills.
A point-in-time decision/fill claim needs its prior availability evidence.
Missing data and delayed reconstructions must remain visible, not silently
converted into successful realtime paper days. The fixed model can be tested
forward without claiming broker execution or collection of every historical
revision in realtime.

## Integrity and future changes

Each update verifies the public source/definition seal and prior private packet
prefix. Published returns and prior input records cannot silently change.
Consumed-data revisions are quarantined; corrections require a separately
labeled revision record. Failures preserve prior accounts and do not turn into
new starting weights. Never refit or switch to another policy on later results.
Any model change creates a separately dated experiment and does not rewrite
this frozen track.

Check [current status](../reports/paper_tracking/README.md). The private tracker
writes aggregate results only after validated future inputs exist. A scheduled
check is not evidence of a successful data ingestion. Local scheduled work
requires the computer and app to remain running.

## Evaluation

Report net daily cash-excess Sharpe, exact-elapsed CAGR, daily drawdown including
initial capital, completed round trips, exposure and matched controls at all
four costs. Early Sharpe/t-statistics may be undefined or unstable; retain them
as such. Show sample size and uncertainty, not an annualized promise. Never
combine these future observations with the 2024–2026 in-sample period to call
that earlier period OOS. No automatic winner selection, additional ETFs, leverage,
shorting or live orders are authorized.

[Historical metric reproducibility](../reports/reproducibility/README.md) ·
[Methods](etf_methods.md)

## Private input packet contract

The tracker command is `python scripts/run_paper_tracker.py`; `--help` lists the
private-packet, private-state, freeze and aggregate-output arguments. The
source packet must be JSON with schema `forward_paper_native_packet_v1`:

| Field | Required content |
|---|---|
| `freeze_sha256` | The sealed public payload's canonical SHA256 |
| `created_at_utc` | Actual packet creation timestamp, not before its QA attestation |
| `qa` | Native-raw basis, `adjusted=false`, `extended_hours=false`, interval 30; passing calendar, coverage, price_units, corporate_actions, native_overlap and daily_anchors statuses; available_15_to_30 passed or explicitly unavailable; real evidence SHA256s and actual attestation timestamp |
| `warmup` | Complete XNYS daily records from 2015-01-02 through the session before inception, at least 295; no future rows |
| `sessions` | Complete consecutive XNYS sessions beginning at the sealed first session; never skip a missing day |

Every daily row contains `session` (ISO date), `available_at_utc` (17:00 New
York expressed in UTC), and exactly the five `symbols`. Each symbol record
contains raw daily `close`, positive `split` coefficient and nonnegative cash
`dividend`. A scored session additionally supplies actual calendar
`market_open_utc` / `market_close_utc` and each symbol's ordered native `bars`.
Each bar supplies `start`, `end`, positive `open/high/low/close` with a valid
OHLC envelope, and nonnegative `volume`. The full half-hour grid is checked
against XNYS; no synthetic pre/postmarket or shortened placeholders are accepted.
All supplied marks and attestations must already have occurred when processed.
The packet's assumption that a daily record was available at 17:00 is an
explicit study convention—not proof of an actual vendor capture at that instant.

The producer must retain actual vendor receipts and reconciliation evidence
privately and attest only after checking them. Evidence hash strings alone do
not establish native units. No producer or network request is inferred from
this schema. Once accepted, seed/session prefixes are immutable; keep all
attempts, including rejected ones, private. The updater also checks the sealed
operational sources and exact runtime versions before accepting data.
