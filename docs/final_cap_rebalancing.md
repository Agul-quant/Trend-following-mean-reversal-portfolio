# Weekly and Monthly Cap Corrections

This is the current portfolio-layer comparison for **GDX, FXI, QQQ, UNG and FDN**:
Weekly corrections, Monthly corrections and the no-rebalancing Initial allocation
benchmark. Daily corrections are excluded. No bond ETF, short, leverage,
standalone Maximum CAGR model or new optimized allocation is included.

## What changed

The user requested actual costed rebalancing, then removed the Daily correction
variant. The retained results are an **exact saved-result subset**, not another
account simulation or optimization. Every retained full-precision value, matched
control, starting weight, strategy definition and period remains unchanged.
The older static-cap fits remain historical archives, not current alternatives.

The common starting vector is the saved no-bond Initial cap allocation, in order
GDX, FXI, QQQ, UNG, FDN:

`[0.2905130826010515, 0.2799197437112525, 0.06304492619579012, 0.26729328450466966, 0.0992289629872361]`

The complete definition is [the policy config](../configs/final_cap_rebalancing.json).

## Timing and accounting

- Fresh independent $1,000 portfolio at each stage: development **2017–2020**,
  validation **2021–2023**, historical OOS **2024-01-01–2026-10-15**.
- Daily causal indicators, native half-hour observations and the original shared
  three-trading-hour / seven-consecutive-check entry and exit confirmation.
  Feature history is initialized from 2015; account state is not carried.
- Check whole **strategy-account capital**, including its idle cash, at 17:00
  New York on the last actual trading session of the ISO week or calendar month.
  Do not invent a terminal partial-period checkpoint.
- Queue a correction only when a sleeve exceeds one-third. Execute at the next
  simultaneous eligible observed raw bar open, strictly after the decision.
  Corporate actions, original dividend reinvestment and all confirmed normal
  strategy orders occur first. Reassess and cancel if the breach disappeared.
- Redistribute proportionally to current underweight account capital, recursively
  capping oversized recipients. Solve post-cost total wealth self-consistently;
  internal cash transfers sum to zero. Do not restore fixed initial weights.
- Long recipients buy additional ETF shares; flat recipients retain cash.
  Partial orders do not change logical signals or confirmation streaks. No
  cross-sleeve/order netting is assumed.
- Each paid normal, cap or terminal order pays **1 bp commission plus
  1/3/10/25 bps one-way slippage**, each way. Internal cash transfers and the
  inherited fee-free dividend-reinvestment proxy have no trading charge.
- Cash is **3% nominal ACT/365 event-compounded**, not 3% APY. Original split,
  dividend, provider-close valuation and paid terminal native-close liquidation
  conventions are preserved. No taxes or additional market impact are modeled.

A correction can move only cash; correction counts need not equal paid ETF-order
counts. “Extra cap costs” means cap-order commissions/slippage, not the total
cost or return difference versus no rebalancing. Subsequent strategy orders can
have different dollar sizes because capital has moved.

## Interpretation

The cap applies immediately after a correction, **not continuously**. Between
checks and overnight gaps may exceed one-third. It is not a daily-closing cap,
ETF-exposure limit or equal-risk allocation. Daily valuations/opening breaches
are descriptive observed diagnostics, not proof about every intraday tick.

Sharpe is net cash-excess Sharpe with sample standard deviation and annualization
by the square root of 252. CAGR uses ACT/365 elapsed time; daily drawdown includes
initial capital. Annual alpha is the arithmetic annualized regression intercept,
not CAGR; joint-five-ETF betas are partial betas, not portfolio weights.

All strategies and starting weights used already examined historical OOS. These
remain **retrospective** results, not untouched portfolio OOS, an optimal-frequency
claim or live trading authorization.

## Evidence and reproduction boundary

The original disabled-rebalancing replay matched all five frozen sleeve wealth
paths and cash at three periods/four costs before the cap variants ran. A separate
scalar accounting oracle checked all original 48 accounts, actual trades, cap
transfers, cash, corporate actions, statistics and factor regressions. The current
publication retains **36 portfolio-cost-period rows and 15 distinct controls**.

The public subset receipt and manifest bind exact aggregate bytes/digests. The
portable verifier checks scope, integrity, config, CSV/Markdown and raster metadata
without private arrays or an optimizer. It does not independently recover the
unpublished source aggregate from its hash. Full financial reproduction requires
authenticated private raw inputs/event primitives and saved paths. No underlying
prices, daily numerical arrays, credentials or private paths are published.

[Current report](../reports/final_cap_rebalancing/report.md) ·
[Aggregate results](../reports/final_cap_rebalancing/report.json)
