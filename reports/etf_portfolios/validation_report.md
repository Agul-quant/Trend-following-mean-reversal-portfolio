# Validation-period portfolio backcast (retrospective)

**Scored dates: 2021-01-01–2023-12-31 · 753 daily observations.**

The five unchanged strategy sleeves are **GDX, FXI, QQQ, UNG and FDN**. This period begins with an independent **$1,000**, flat holdings and empty orders/confirmation streaks; only causal feature history carries over. Fitted models retain the exact saved initial weights. The equal-weight comparator allocates 20% per sleeve once, with no rebalancing. No account, optimizer or performance statistic was rerun to produce this report.

**Retrospective, not untouched portfolio OOS:** the final ETF identities, rules and fitted weights used examined 2024–2026 history. That period is the portfolio-selection / in-sample period; earlier development and validation portfolio backcasts also inherit hindsight selection. The separate frozen forward paper portfolio is unchanged.

## All four cost scenarios

Each paid ETF order incurs **1-bp commission plus the listed 1/3/10/25-bp one-way slippage, each way**. Cash is modeled at **3% nominal ACT/365 event-compounded**, not 3% APY or a guaranteed yield. Sharpe is cash-excess Sharpe, annualized by sqrt(252); CAGR uses actual elapsed ACT/365 time. Drawdown includes initial capital and uses daily marks. The original corporate-action, dividend-reinvestment and paid terminal-liquidation conventions are unchanged.

Trips count completed strategy round trips including terminal exits, not partial correction orders. Equal-weight trips are not inferred from aggregate returns. Extra cap costs are direct correction-order costs; a correction can be an internal cash transfer without an ETF order.

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

## Baseline equity and drawdown curves

Four portfolios and cost-matched QQQ buy-and-hold, each starting from $1,000. The baseline is 1-bp commission plus 3-bp slippage each way.

![Validation-period portfolio backcast (retrospective) baseline equity and drawdown](validation_baseline.png)

## Daily net return plots — baseline costs

Five separate panels show the four portfolios and QQQ buy-and-hold. These are daily net simple total returns in percent, not cumulative wealth, drawdown or cash-excess returns. All observations are retained on a common vertical scale without smoothing, clipping or resampling. The first return begins at initial stage capital; the final return includes paid terminal liquidation.

![Validation-period portfolio backcast (retrospective): daily net returns](validation_daily_returns_baseline.png)

## Definitions, full-precision results and verification

- [Exact strategy definitions](../../configs/selected_etf_strategies.json) · [Saved fitted weights and policy](../../configs/final_cap_rebalancing.json) · [Methods](../../docs/etf_methods.md)
- [All-period report and audit context](report.md) · [Pinned aggregate JSON](report.json) · [Fitted performance CSV](performance.csv) · [Matched controls CSV](controls.csv)
- [Equal-weight and IID/HAC statistics](statistical_comparison.csv) · [Released derived daily returns](../reproducibility/README.md) · [This period's return CSV](../reproducibility/validation.csv)

Raw ETF prices, fills and sleeve-level account paths remain private. Published daily aggregate returns permit independent summary-statistic verification, not a reconstruction of the private market-data-to-signal audit. IID/HAC inference and regression attribution are descriptive and not adjusted for portfolio selection.

From the repository root: `PYTHONPATH=src python scripts/verify_etf_publication.py --report-dir reports/etf_portfolios --config configs/final_cap_rebalancing.json` and `PYTHONPATH=src python scripts/verify_daily_returns.py`.
