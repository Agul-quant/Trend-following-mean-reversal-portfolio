# Five ETF portfolios without bonds

Six new static initial allocations across GDX, FXI, QQQ, UNG and FDN. Development 2017–2020; validation 2021–2023; historical OOS 2024–15 October 2026.

All five optimized allocations were refitted on the already examined historical OOS sample; Equal initial assigns 20% to each strategy. This is retrospective allocation research, not an untouched portfolio test or live trading recommendation.

## Read the reports

- [Development report](development.html)
- [Validation report](validation.html)
- [Historical OOS report](historical_OOS.html)
- [Combined full tables](combined_report.md)

Each offline HTML embeds its seven-series baseline equity/drawdown PNG and includes all four cost scenarios, matched QQQ/cash controls, QQQ and joint-five-ETF alpha/beta, capital-share diagnostics and both correlation matrices. No numerical daily paths are embedded.

## Historical OOS baseline comparison

| Allocation or control | Cash excess Sharpe | CAGR | Daily max drawdown |
| --- | --- | --- | --- |
| Daily cap fit | 2.476 | 23.85% | -4.91% |
| Weekly cap fit | 2.476 | 23.85% | -4.91% |
| Monthly cap fit | 2.476 | 23.87% | -4.91% |
| Initial cap fit | 2.487 | 24.57% | -4.67% |
| Uncapped fit | 2.487 | 24.57% | -4.67% |
| Equal initial | 2.213 | 23.39% | -5.04% |
| QQQ buy and hold | 0.996 | 23.93% | -22.77% |

Baseline costs: 1-bp commission plus 3-bp slippage each way. Cash: 3% nominal ACT/365 event-compounded. The same full-precision initial weights are used in every period and cost, without rebalancing.

Daily/weekly/monthly caps are historical checkpoint constraints. Weekly and monthly fits use separate, non-nested week-end/month-end sets, including the terminal incomplete period. Between-checkpoint daily breaches are allowed. Initial-only cap has no later enforcement; no model guarantees future or intraday compliance.

Original four-portfolio class-project reports and six-sleeve source records remain unchanged archives. Bond ETFs and the standalone Maximum CAGR portfolio are absent from the active comparison. See the accompanying aggregate source JSON and render manifest for inspectable full precision and SHA256 bindings.
