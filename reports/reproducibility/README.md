# Daily-return reproducibility release

This release publishes **derived net aggregate daily returns**, not raw ETF prices,
holdings, sleeve wealth, fills or account paths. It was extracted from the existing
saved accounts: **no account rerun, strategy change, optimizer refit or new market
observations** were used. The original 36 model-cost-period metrics remain unchanged.

**2024–2026 is the portfolio-selection sample, in-sample.** ETF/rule/pruning/weight
choices used this history. The internal `historical_OOS` key is retained only for
compatibility with the original ETF-stage records. Neither this release, the
statistical tests nor the equal-initial comparator creates an untouched portfolio
out-of-sample result. Earlier periods are retrospective diagnostics of the final
chosen portfolio.

## Files and scope

- [Development returns](development.csv): 2017–2020, 1,007 daily observations per cost.
- [Validation returns](validation.csv): 2021–2023, 753 observations per cost.
- [Portfolio-selection sample returns](historical_OOS.csv): January 2024–October 15, 2026,
  700 observations per cost; in-sample for the portfolio.
- [Release manifest](manifest.json): exact stage clocks, definitions, row counts,
  file byte counts and SHA256 hashes.
- [Statistical comparison JSON](../etf_portfolios/statistical_comparison.json) and
  [CSV](../etf_portfolios/statistical_comparison.csv): all 72 series-cost-period summaries.
- [Independent verification script](../../scripts/verify_daily_returns.py) and
  [arithmetic module](../../src/trend_portfolio/return_verification.py).

There are **9,840 dated cost-scenario rows and 59,040 return values**. Each CSV
contains four separate cost scenarios: 1-bp commission plus 1, 3, 10 or 25-bp
one-way slippage on each paid trade. Baseline slippage is 3 bps. Do not concatenate
cost scenarios as though they were consecutive trading days.

Each row contains stage, ISO date, explicit UTC daily valuation timestamp,
commission/slippage and six simple return columns:

| Column prefix | Meaning |
|---|---|
| `initial_allocation` | Exact fitted initial weights; thereafter no rebalancing |
| `weekly_corrections` | Existing costed weekly cap-correction account |
| `monthly_corrections` | Existing costed monthly cap-correction account |
| `equal_initial` | 20% each in GDX, FXI, QQQ, UNG and FDN once at stage start; then drift |
| `QQQ_buy_and_hold` | Matched cost-scenario passive QQQ control |
| `matched_cash` | Matched 3% nominal ACT/365 event-compounded cash account |

The equal-initial comparator uses the same five selected rules and their saved
net sleeve paths; it is **not periodically rebalanced**, and it does not remove
ETF/rule-selection bias. Its 12 saved aggregate outcomes were separately matched
before release. The cash series is repeated identically across costs for convenient
alignment; it is not a fourth traded ETF or an assumed constant 3%/252 return.

## Reproduce without private data

From a checkout of this repository:

```sh
python3 -S scripts/verify_daily_returns.py
```

The verifier uses **only Python's standard library**. No installed project package,
NumPy, credentials, download, prices, Git metadata or private account files are
required. It validates hashes, complete series/cost/stage identities, aligned
strictly increasing clocks, valid finite returns and the two statistical summary
formats. It independently reconstructs wealth from the released returns, recomputes
all 72 statistic rows, and compares the original 36 model rows plus the distinct
15 cost-matched QQQ/cash controls against the unchanged historical aggregate report.
It does not claim to reconstruct the private fills or prove that the market data
or trading simulation were correct.

The separate [export script](../../scripts/export_portfolio_daily_returns.py) is a
reporting tool for the author: explicit private saved-input arguments and NumPy are
needed to create a new export. It never executes a strategy engine or optimizer.
Those inputs are intentionally **not** distributed or required by the verifier.

## Exact arithmetic and clocks

For each stage/cost/series separately, start normalized wealth at **1 before the
first published row**, then compound `wealth *= 1 + return`. The first return is
from the fresh stage-start account/open to its first daily valuation, not from
one daily close to the next. Returns already embed trading costs, distributions,
cap transfers where applicable, cash accrual and paid terminal liquidation.
Daily valuations are 17:00 America/New_York, stored as UTC (therefore changing
with DST). Overnight/weekend intervals are preserved, not filled with synthetic
trading rows.

- **Cash-excess Sharpe:** `sqrt(252) * mean(r - cash) / sample_sd(r - cash)`,
  with `ddof=1`. It is neither total-return Sharpe with a zero cash rate nor
  Sharpe relative to QQQ. A zero-variance cash-excess series is undefined (`null`
  in JSON and empty in the summary CSV), not zero.
- **CAGR:** `terminal_wealth ** (1 / elapsed_ACT365_years) - 1`. Exact elapsed
  seconds between the initial open and final valuation are divided by 365 days;
  neither `observations/252` nor inclusive calendar-year counting is substituted.
- **Maximum drawdown:** minimum `wealth / running_peak - 1`, including the
  initial wealth of 1. In particular, a first-day loss counts as drawdown.

## Mean-excess t-statistics: descriptive, not selection-adjusted

The reported statistic tests the mean of daily net returns **minus matched cash**.
It is **not** a factor-regression alpha t-statistic.

- **IID:** `mean(excess) / (sample_sd(excess) / sqrt(n))`, equivalently
  `cash_excess_sharpe * sqrt(n/252)` under the stated IID assumptions.
- **HAC/Newey–West:** intercept-only, Bartlett weights, with fixed sample-size lag
  rule `L = min(n-1, floor(4*(n/100)^(2/9)))`. This yields **L=6** in all three
  present periods. The HC1 finite-sample correction is `n/(n-1)`; setting L=0
  agrees with the conventional IID mean t-statistic.
- Sensitivity summaries at L=0, 5, 10, 20 and the primary L (deduplicated and
  bounded by n−1) are included in the JSON; lags were not selected for a favorable
  statistic.

For residuals `u_t = excess_t - mean(excess)`, the exact variance used is
`[sum(u_t^2) + 2*sum_{l=1..L}((1-l/(L+1))*sum_{t=l..n-1}(u_t*u_{t-l}))] / [n*(n-1)]`.
The t-statistic is the mean divided by the square root of this variance.

Serial dependence changes inference; see Andrew Lo,
[*The Statistics of Sharpe Ratios*](https://rpc.cfainstitute.org/research/financial-analysts-journal/2002/the-statistics-of-sharpe-ratios)
and Newey and West's
[original HAC covariance paper](https://www.nber.org/papers/t0055).
**Neither IID nor HAC corrects retrospective ETF/rule/weight selection, multiple
testing, regime instability or the small count of completed trades.** No p-values,
selection-adjusted significance, independent-trade count or future performance
claim is inferred. Daily observations are not independent strategy discoveries.

### Baseline portfolio-selection sample, 2024–October 15, 2026

| Model | Cash-excess Sharpe | CAGR | Max drawdown | IID mean-excess t | HAC t (L=6) |
|---|---:|---:|---:|---:|---:|
| Initial allocation, no rebalancing | 2.487 | 24.57% | −4.67% | 4.145 | 4.209 |
| Weekly corrections | 2.514 | 24.60% | −4.67% | 4.190 | 4.235 |
| Monthly corrections | 2.516 | 24.65% | −4.67% | 4.193 | 4.240 |
| Equal initial weights, no rebalancing | 2.213 | 23.39% | −5.04% | 3.688 | 3.840 |
| QQQ buy-and-hold | 0.996 | 23.93% | −22.77% | 1.660 | 1.848 |

The three fitted-weight accounts each have **34 completed strategy round trips**
(including paid terminal exits), not 700 independent trades. Their mean ETF
exposures are respectively **25.21%, 25.36% and 25.33%**; the remainder is modeled
cash. Round trips and exposure are saved aggregate-account diagnostics, not
quantities that can be recovered from aggregate returns alone. Assumed cash growth
is subtracted in cash-excess statistics, but contributes to total CAGR. Cash's
realized annualized growth in this sample is approximately 3.045%, reflecting
nominal event compounding rather than a promised 3% APY or observed broker yield.
