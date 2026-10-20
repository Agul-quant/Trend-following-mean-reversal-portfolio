# Development-period portfolio backcast (retrospective)

**Scored dates: 2017-01-01–2020-12-31 · 1,007 daily observations.**

The five unchanged strategy sleeves are **GDX, FXI, QQQ, UNG and FDN**. This period begins with an independent **$1,000**, flat holdings and empty orders/confirmation streaks; only causal feature history carries over. Fitted models retain the exact saved initial weights. The equal-weight comparator allocates 20% per sleeve once, with no rebalancing. No account, optimizer or performance statistic was rerun to produce this report.

**Retrospective, not untouched portfolio OOS:** the final ETF identities, rules and fitted weights used examined 2024–2026 history. That period is the portfolio-selection / in-sample period; earlier development and validation portfolio backcasts also inherit hindsight selection. The separate frozen forward paper portfolio is unchanged.

## All four cost scenarios

Each paid ETF order incurs **1-bp commission plus the listed 1/3/10/25-bp one-way slippage, each way**. Cash is modeled at **3% nominal ACT/365 event-compounded**, not 3% APY or a guaranteed yield. Sharpe is cash-excess Sharpe, annualized by sqrt(252); CAGR uses actual elapsed ACT/365 time. Drawdown includes initial capital and uses daily marks. The original corporate-action, dividend-reinvestment and paid terminal-liquidation conventions are unchanged.

Trips count completed strategy round trips including terminal exits, not partial correction orders. Equal-weight trips are not inferred from aggregate returns. Extra cap costs are direct correction-order costs; a correction can be an internal cash transfer without an ETF order.

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

## Baseline equity and drawdown curves

Four portfolios and cost-matched QQQ buy-and-hold, each starting from $1,000. The baseline is 1-bp commission plus 3-bp slippage each way.

![Development-period portfolio backcast (retrospective) baseline equity and drawdown](development_baseline.png)

## Daily net return plots — baseline costs

Five separate panels show the four portfolios and QQQ buy-and-hold. These are daily net simple total returns in percent, not cumulative wealth, drawdown or cash-excess returns. All observations are retained on a common vertical scale without smoothing, clipping or resampling. The first return begins at initial stage capital; the final return includes paid terminal liquidation.

![Development-period portfolio backcast (retrospective): daily net returns](development_daily_net_returns_baseline.png)

## Definitions, full-precision results and verification

- [Exact strategy definitions](../../configs/selected_etf_strategies.json) · [Saved fitted weights and policy](../../configs/final_cap_rebalancing.json) · [Methods](../../docs/etf_methods.md)
- [All-period report and audit context](report.md) · [Pinned aggregate JSON](report.json) · [Fitted performance CSV](performance.csv) · [Matched controls CSV](controls.csv)
- [Equal-weight and IID/HAC statistics](statistical_comparison.csv) · [Released derived daily returns](../reproducibility/README.md) · [This period's return CSV](../reproducibility/development.csv)

Raw ETF prices, fills and sleeve-level account paths remain private. Published daily aggregate returns permit independent summary-statistic verification, not a reconstruction of the private market-data-to-signal audit. IID/HAC inference and regression attribution are descriptive and not adjusted for portfolio selection.

From the repository root: `PYTHONPATH=src python scripts/verify_etf_publication.py --report-dir reports/etf_portfolios --config configs/final_cap_rebalancing.json` and `PYTHONPATH=src python scripts/verify_daily_returns.py`.
