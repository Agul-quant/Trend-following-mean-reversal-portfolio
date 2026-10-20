# Retrospective portfolio-selection sample (in-sample)

**Scored dates: 2024-01-01–2026-10-15 · 700 daily observations.**

The five unchanged strategy sleeves are **GDX, FXI, QQQ, UNG and FDN**. This period begins with an independent **$1,000**, flat holdings and empty orders/confirmation streaks; only causal feature history carries over. Fitted models retain the exact saved initial weights. The equal-weight comparator allocates 20% per sleeve once, with no rebalancing. No account, optimizer or performance statistic was rerun to produce this report.

**Retrospective, not untouched portfolio OOS:** the final ETF identities, rules and fitted weights used examined 2024–2026 history. That period is the portfolio-selection / in-sample period; earlier development and validation portfolio backcasts also inherit hindsight selection. The separate frozen forward paper portfolio is unchanged.

## All four cost scenarios

Each paid ETF order incurs **1-bp commission plus the listed 1/3/10/25-bp one-way slippage, each way**. Cash is modeled at **3% nominal ACT/365 event-compounded**, not 3% APY or a guaranteed yield. Sharpe is cash-excess Sharpe, annualized by sqrt(252); CAGR uses actual elapsed ACT/365 time. Drawdown includes initial capital and uses daily marks. The original corporate-action, dividend-reinvestment and paid terminal-liquidation conventions are unchanged.

Trips count completed strategy round trips including terminal exits, not partial correction orders. Equal-weight trips are not inferred from aggregate returns. Extra cap costs are direct correction-order costs; a correction can be an internal cash transfer without an ETF order.

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

## Baseline equity and drawdown curves

Four portfolios and cost-matched QQQ buy-and-hold, each starting from $1,000. The baseline is 1-bp commission plus 3-bp slippage each way.

![Retrospective portfolio-selection sample (in-sample) baseline equity and drawdown](historical_OOS_baseline.png)

## Daily net return plots — baseline costs

Five separate panels show the four portfolios and QQQ buy-and-hold. These are daily net simple total returns in percent, not cumulative wealth, drawdown or cash-excess returns. All observations are retained on a common vertical scale without smoothing, clipping or resampling. The first return begins at initial stage capital; the final return includes paid terminal liquidation.

![Retrospective portfolio-selection sample (in-sample): daily net returns](historical_OOS_daily_net_returns_baseline.png)

## Definitions, full-precision results and verification

- [Exact strategy definitions](../../configs/selected_etf_strategies.json) · [Saved fitted weights and policy](../../configs/final_cap_rebalancing.json) · [Methods](../../docs/etf_methods.md)
- [All-period report and audit context](report.md) · [Pinned aggregate JSON](report.json) · [Fitted performance CSV](performance.csv) · [Matched controls CSV](controls.csv)
- [Equal-weight and IID/HAC statistics](statistical_comparison.csv) · [Released derived daily returns](../reproducibility/README.md) · [This period's return CSV](../reproducibility/historical_OOS.csv)

Raw ETF prices, fills and sleeve-level account paths remain private. Published daily aggregate returns permit independent summary-statistic verification, not a reconstruction of the private market-data-to-signal audit. IID/HAC inference and regression attribution are descriptive and not adjusted for portfolio selection.

From the repository root: `PYTHONPATH=src python scripts/verify_etf_publication.py --report-dir reports/etf_portfolios --config configs/final_cap_rebalancing.json` and `PYTHONPATH=src python scripts/verify_daily_returns.py`.
