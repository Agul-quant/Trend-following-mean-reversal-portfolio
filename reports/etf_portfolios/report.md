# Trend Following and Mean Reversion ETF Portfolios

## Scope and method

The comparison contains **Initial allocation; no rebalancing**, **Equal weight; no rebalancing**, **Weekly corrections** and **Monthly corrections**. All use the same five strategies. The original 36 fitted-allocation results plus 12 released equal-weight comparisons give 48 portfolio/cost/period outcomes. No account or optimizer was rerun; saved full-precision results are unchanged.

The long/cash strategy universe is **GDX, FXI, QQQ, UNG and FDN**, used consistently throughout this publication. No shorts, leverage or standalone Maximum CAGR allocation are used. Each period starts independently with **$1,000**, flat accounts and empty orders/confirmation streaks; causal feature history alone carries across stages.

### Saved fitted starting weights; unchanged across periods and costs

| Strategy sleeve | Initial weight |
|---|---:|
| GDX | 29.051308260% |
| FXI | 27.991974371% |
| QQQ | 6.304492620% |
| UNG | 26.729328450% |
| FDN | 9.922896299% |

**Equal weight; no rebalancing** instead starts at **20% per sleeve**, once at each stage's inception. Capital then drifts. It uses the same rules and costs, is not periodically rebalanced, and does not change the frozen fitted-weight forward portfolio.


At the last actual trading session of each ISO week or calendar month, the **17:00 New York** valuation queues a correction only when a sleeve's whole strategy-account capital (ETF plus cash) exceeds one-third. October 15, 2026 is not an artificial week/month end. Execution waits for the next simultaneous eligible observed native 30-minute bar open, strictly after the decision. Corporate actions, original dividend reinvestment and normal confirmed strategy fills occur first; a vanished breach cancels the intent.

At execution, trim oversized sleeves and redistribute excess proportionally to the other sleeves' **current capital**, recursively respecting the one-third post-cost limit. This is **not a reset to starting weights**. Long-signal recipients buy ETF shares; cash-signal recipients remain in cash. Partial cap orders do not alter logical signals or restart the original seven-consecutive-check/three-trading-hour confirmation.

Cash earns **3% nominal ACT/365 event-compounded**, not 3% APY. Paid strategy, cap and terminal ETF orders pay **1 bp commission plus 1/3/10/25 bps one-way slippage, each way**; baseline slippage is 3 bps. The inherited **fee-free dividend-reinvestment proxy** is unchanged. Internal cash transfers have no trading fee. Original corporate-action and paid terminal-close liquidation conventions remain; no order netting, taxes or additional market impact are modeled.

**Not a continuous cap:** between-check drift, daily closing breaches and overnight gaps remain possible. The one-third limit is tested immediately after an executed correction, not at every market tick. It concerns sleeve capital, not ETF exposure or risk contribution.

**Retrospective evidence:** strategy identities and starting weights used previously examined OOS history. The historical stage names do not make this an untouched portfolio holdout, optimal-frequency finding or live trading instruction.

## All periods and four cost scenarios

Sharpe is net **cash-excess** Sharpe: sqrt(252) times mean daily portfolio return minus matched cash return divided by its sample standard deviation (ddof 1), not excess over buy-and-hold. CAGR uses the actual initial-to-terminal ACT/365 elapsed time. Drawdown uses daily marked wealth including initial capital, not intraday extrema. Undefined metrics remain undefined. Each stage restarts; stages are not spliced.

Trips are completed strategy round trips including paid terminal exits. Partial cap orders are separate orders, not extra completed trips. Cap executions can be cash transfers without an ETF order. Extra cap costs are direct cap-order commissions plus slippage, not the change in total costs versus the comparator; later strategy-order sizes may also change.

### Development-period portfolio backcast (retrospective) — 2017-01-01 to 2020-12-31

[Focused period report](development_report.md)

| Portfolio / control | Slippage (bp) | Sharpe | CAGR | Max DD | Trips | Cap executions / ETF orders | Extra cap costs ($) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Initial allocation; no rebalancing | 1 | 1.303 | 16.24% | -8.48% | 38 | 0 / 0 | 0.0000 |
| Weekly corrections | 1 | 1.303 | 16.24% | -8.48% | 38 | 0 / 0 | 0.0000 |
| Monthly corrections | 1 | 1.303 | 16.24% | -8.48% | 38 | 0 / 0 | 0.0000 |
| Equal weight; no rebalancing | 1 | 1.511 | 19.68% | -7.36% | — | 0 / 0 | 0.0000 |
| QQQ buy-and-hold | 1 | 1.063 | 28.40% | -28.56% | 1 | — | — |
| Initial allocation; no rebalancing | 3 | 1.295 | 16.14% | -8.48% | 38 | 0 / 0 | 0.0000 |
| Weekly corrections | 3 | 1.295 | 16.14% | -8.48% | 38 | 0 / 0 | 0.0000 |
| Monthly corrections | 3 | 1.295 | 16.14% | -8.48% | 38 | 0 / 0 | 0.0000 |
| Equal weight; no rebalancing | 3 | 1.504 | 19.59% | -7.39% | — | 0 / 0 | 0.0000 |
| QQQ buy-and-hold | 3 | 1.063 | 28.39% | -28.56% | 1 | — | — |
| Initial allocation; no rebalancing | 10 | 1.267 | 15.80% | -8.49% | 38 | 0 / 0 | 0.0000 |
| Weekly corrections | 10 | 1.267 | 15.80% | -8.49% | 38 | 0 / 0 | 0.0000 |
| Monthly corrections | 10 | 1.267 | 15.80% | -8.49% | 38 | 0 / 0 | 0.0000 |
| Equal weight; no rebalancing | 10 | 1.479 | 19.29% | -7.49% | — | 0 / 0 | 0.0000 |
| QQQ buy-and-hold | 10 | 1.061 | 28.35% | -28.56% | 1 | — | — |
| Initial allocation; no rebalancing | 25 | 1.205 | 15.08% | -8.51% | 38 | 0 / 0 | 0.0000 |
| Weekly corrections | 25 | 1.205 | 15.08% | -8.51% | 38 | 0 / 0 | 0.0000 |
| Monthly corrections | 25 | 1.205 | 15.08% | -8.51% | 38 | 0 / 0 | 0.0000 |
| Equal weight; no rebalancing | 25 | 1.426 | 18.64% | -7.71% | — | 0 / 0 | 0.0000 |
| QQQ buy-and-hold | 25 | 1.058 | 28.25% | -28.56% | 1 | — | — |
| Matched cash | — | Undefined | 3.05% | 0.00% | 0 | — | — |

#### Baseline equity and drawdown curves

Four portfolios and cost-matched QQQ buy-and-hold, each starting from $1,000. The baseline is 1-bp commission plus 3-bp slippage each way.

![Development-period portfolio backcast (retrospective) baseline equity and drawdown](development_baseline.png)

#### Daily net return plots — baseline costs

Five separate panels show the four portfolios and QQQ buy-and-hold. These are daily net simple total returns in percent, not cumulative wealth, drawdown or cash-excess returns. All observations are retained on a common vertical scale without smoothing, clipping or resampling. The first return begins at initial stage capital; the final return includes paid terminal liquidation.

![Development-period portfolio backcast (retrospective): daily net returns](development_daily_net_returns_baseline.png)

### Validation-period portfolio backcast (retrospective) — 2021-01-01 to 2023-12-31

[Focused period report](validation_report.md)

| Portfolio / control | Slippage (bp) | Sharpe | CAGR | Max DD | Trips | Cap executions / ETF orders | Extra cap costs ($) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Initial allocation; no rebalancing | 1 | 0.429 | 7.90% | -19.22% | 46 | 0 / 0 | 0.0000 |
| Weekly corrections | 1 | 0.480 | 8.45% | -17.53% | 46 | 4 / 5 | 0.0083 |
| Monthly corrections | 1 | 0.474 | 8.37% | -17.70% | 46 | 3 / 1 | 0.0004 |
| Equal weight; no rebalancing | 1 | 0.535 | 8.66% | -15.64% | — | 0 / 0 | 0.0000 |
| QQQ buy-and-hold | 1 | 0.388 | 9.86% | -35.12% | 1 | — | — |
| Initial allocation; no rebalancing | 3 | 0.419 | 7.77% | -19.24% | 46 | 0 / 0 | 0.0000 |
| Weekly corrections | 3 | 0.470 | 8.32% | -17.54% | 46 | 4 / 5 | 0.0167 |
| Monthly corrections | 3 | 0.464 | 8.24% | -17.71% | 46 | 3 / 1 | 0.0007 |
| Equal weight; no rebalancing | 3 | 0.524 | 8.53% | -15.67% | — | 0 / 0 | 0.0000 |
| QQQ buy-and-hold | 3 | 0.387 | 9.84% | -35.12% | 1 | — | — |
| Initial allocation; no rebalancing | 10 | 0.385 | 7.30% | -19.33% | 46 | 0 / 0 | 0.0000 |
| Weekly corrections | 10 | 0.436 | 7.86% | -17.57% | 46 | 4 / 5 | 0.0467 |
| Monthly corrections | 10 | 0.430 | 7.79% | -17.74% | 46 | 3 / 1 | 0.0020 |
| Equal weight; no rebalancing | 10 | 0.485 | 8.07% | -15.79% | — | 0 / 0 | 0.0000 |
| QQQ buy-and-hold | 10 | 0.385 | 9.79% | -35.12% | 1 | — | — |
| Initial allocation; no rebalancing | 25 | 0.311 | 6.32% | -19.52% | 46 | 0 / 0 | 0.0000 |
| Weekly corrections | 25 | 0.362 | 6.90% | -17.65% | 46 | 4 / 5 | 0.1143 |
| Monthly corrections | 25 | 0.357 | 6.83% | -17.82% | 46 | 3 / 1 | 0.0050 |
| Equal weight; no rebalancing | 25 | 0.403 | 7.09% | -16.03% | — | 0 / 0 | 0.0000 |
| QQQ buy-and-hold | 25 | 0.381 | 9.68% | -35.12% | 1 | — | — |
| Matched cash | — | Undefined | 3.05% | 0.00% | 0 | — | — |

#### Baseline equity and drawdown curves

Four portfolios and cost-matched QQQ buy-and-hold, each starting from $1,000. The baseline is 1-bp commission plus 3-bp slippage each way.

![Validation-period portfolio backcast (retrospective) baseline equity and drawdown](validation_baseline.png)

#### Daily net return plots — baseline costs

Five separate panels show the four portfolios and QQQ buy-and-hold. These are daily net simple total returns in percent, not cumulative wealth, drawdown or cash-excess returns. All observations are retained on a common vertical scale without smoothing, clipping or resampling. The first return begins at initial stage capital; the final return includes paid terminal liquidation.

![Validation-period portfolio backcast (retrospective): daily net returns](validation_daily_net_returns_baseline.png)

### Retrospective portfolio-selection sample (in-sample) — 2024-01-01 to 2026-10-15

[Focused period report](historical_OOS_report.md)

| Portfolio / control | Slippage (bp) | Sharpe | CAGR | Max DD | Trips | Cap executions / ETF orders | Extra cap costs ($) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Initial allocation; no rebalancing | 1 | 2.499 | 24.71% | -4.66% | 34 | 0 / 0 | 0.0000 |
| Weekly corrections | 1 | 2.526 | 24.74% | -4.66% | 34 | 5 / 11 | 0.0160 |
| Monthly corrections | 1 | 2.527 | 24.79% | -4.66% | 34 | 3 / 8 | 0.0104 |
| Equal weight; no rebalancing | 1 | 2.224 | 23.52% | -5.04% | — | 0 / 0 | 0.0000 |
| QQQ buy-and-hold | 1 | 0.997 | 23.95% | -22.77% | 1 | — | — |
| Initial allocation; no rebalancing | 3 | 2.487 | 24.57% | -4.67% | 34 | 0 / 0 | 0.0000 |
| Weekly corrections | 3 | 2.514 | 24.60% | -4.67% | 34 | 5 / 11 | 0.0317 |
| Monthly corrections | 3 | 2.516 | 24.65% | -4.67% | 34 | 3 / 8 | 0.0202 |
| Equal weight; no rebalancing | 3 | 2.213 | 23.39% | -5.04% | — | 0 / 0 | 0.0000 |
| QQQ buy-and-hold | 3 | 0.996 | 23.93% | -22.77% | 1 | — | — |
| Initial allocation; no rebalancing | 10 | 2.447 | 24.08% | -4.69% | 34 | 0 / 0 | 0.0000 |
| Weekly corrections | 10 | 2.472 | 24.12% | -4.69% | 34 | 5 / 11 | 0.0848 |
| Monthly corrections | 10 | 2.474 | 24.17% | -4.69% | 34 | 3 / 8 | 0.0510 |
| Equal weight; no rebalancing | 10 | 2.173 | 22.95% | -5.06% | — | 0 / 0 | 0.0000 |
| QQQ buy-and-hold | 10 | 0.993 | 23.87% | -22.77% | 1 | — | — |
| Initial allocation; no rebalancing | 25 | 2.358 | 23.04% | -4.74% | 34 | 0 / 0 | 0.0000 |
| Weekly corrections | 25 | 2.380 | 23.10% | -4.74% | 34 | 5 / 11 | 0.1882 |
| Monthly corrections | 25 | 2.383 | 23.15% | -4.74% | 34 | 2 / 5 | 0.1103 |
| Equal weight; no rebalancing | 25 | 2.087 | 22.01% | -5.10% | — | 0 / 0 | 0.0000 |
| QQQ buy-and-hold | 25 | 0.988 | 23.73% | -22.77% | 1 | — | — |
| Matched cash | — | Undefined | 3.05% | 0.00% | 0 | — | — |

#### Baseline equity and drawdown curves

Four portfolios and cost-matched QQQ buy-and-hold, each starting from $1,000. The baseline is 1-bp commission plus 3-bp slippage each way.

![Retrospective portfolio-selection sample (in-sample) baseline equity and drawdown](historical_OOS_baseline.png)

#### Daily net return plots — baseline costs

Five separate panels show the four portfolios and QQQ buy-and-hold. These are daily net simple total returns in percent, not cumulative wealth, drawdown or cash-excess returns. All observations are retained on a common vertical scale without smoothing, clipping or resampling. The first return begins at initial stage capital; the final return includes paid terminal liquidation.

![Retrospective portfolio-selection sample (in-sample): daily net returns](historical_OOS_daily_net_returns_baseline.png)

## Baseline cap diagnostics

These observations cover daily valuations and common eligible opens only. Opening breaches are measured after normal strategy orders and before a cap correction. They are not an every-tick risk test.

| Period | Model | Daily breach days | Max daily sleeve share | Observed open breaches | Max observed open share | Max share after correction |
|---|---|---:|---:|---:|---:|---:|
| Development-period portfolio backcast (retrospective) | Initial allocation; no rebalancing | 0 | 29.43% | 0 | 30.51% | — |
| Development-period portfolio backcast (retrospective) | Weekly corrections | 0 | 29.43% | 0 | 30.51% | — |
| Development-period portfolio backcast (retrospective) | Monthly corrections | 0 | 29.43% | 0 | 30.51% | — |
| Validation-period portfolio backcast (retrospective) | Initial allocation; no rebalancing | 128 | 38.24% | 1649 | 38.23% | — |
| Validation-period portfolio backcast (retrospective) | Weekly corrections | 20 | 35.06% | 242 | 35.39% | 33.3333% |
| Validation-period portfolio backcast (retrospective) | Monthly corrections | 46 | 36.22% | 577 | 36.22% | 33.3333% |
| Retrospective portfolio-selection sample (in-sample) | Initial allocation; no rebalancing | 134 | 38.56% | 1752 | 38.67% | — |
| Retrospective portfolio-selection sample (in-sample) | Weekly corrections | 17 | 34.87% | 249 | 36.25% | 33.3333% |
| Retrospective portfolio-selection sample (in-sample) | Monthly corrections | 56 | 37.26% | 743 | 37.37% | 33.3333% |

## Audit and portable verification

The completed financial audit checked disabled-rebalancing equivalence to all five original frozen sleeve paths and matched cash across all periods/costs, then independently checked chronological cash, corporate actions, inherited dividend reinvestment, signal fills, cap orders, self-financing transfers, post-cost caps and daily statistics. Those sources and completed results remain unchanged.

This publication's verifier checks the exact 36 saved rows, 15 original controls, saved weights, metadata and canonical full-precision digest using only public aggregate artifacts. It does **not** reproduce the private financial audit or derive results anew. Derived aggregate daily returns and an independent summary-statistic verifier are [published separately](../reproducibility/README.md); raw ETF inputs and sleeve paths remain private. The [equal-initial and IID/HAC comparison](statistical_comparison.csv) is descriptive and not selection-adjusted. Alpha and betas in JSON are descriptive regressions; annual alpha is the arithmetic intercept times 252, not CAGR. Joint beta order is GDX, FXI, QQQ, UNG, FDN.

- Completed source aggregate SHA256: `2a940582ceac6b9a108e3a9baf9319ef26b1c74eff29bedddf66e3bfd3472171`
- Prior saved aggregate presentation SHA256: `394c21a2497a4411a90b9c576a67abff5611a0de5de2726e3e889aa6c4e72630`
- Canonical retained payload SHA256: `6757f4c392301fb31089809aa5af96bdcd61dffe7b402263e18da5896f77fde9`
- [Exact aggregate results](report.json) · [Full-precision performance CSV](performance.csv) · [Controls CSV](controls.csv) · [Detached subset audit](source_subset_audit.json)

From the repository root: `PYTHONPATH=src python scripts/verify_etf_publication.py --report-dir reports/etf_portfolios --config configs/final_cap_rebalancing.json`.
