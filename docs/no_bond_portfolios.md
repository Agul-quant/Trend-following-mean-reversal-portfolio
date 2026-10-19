# Five-ETF portfolio calculations without bonds

## Active scope

The final strategies are **GDX, FXI, QQQ, UNG and FDN**, using the exact previously
selected indicator definitions and saved net account paths. BND is excluded from
allocations, strategy correlations and the joint passive-factor regression.
Underlying sleeve idle cash and its fixed interest convention remain unchanged;
removing bond ETFs is not a request to eliminate cash.

The original six-sleeve/four-portfolio class reports and five-portfolio archive
remain byte-identical historical records. Their weights and statistics must not
be relabeled as these new results. The standalone Maximum CAGR allocation
remains excluded. Current source: [aggregate report](../reports/no_bond_portfolios/report.json),
[definitions](../configs/no_bond_selected_strategies.json),
[allocations](../configs/no_bond_portfolios.json) and
[report index](../reports/no_bond_portfolios/README.md).

## Fit and replay

All **five optimized allocations** are newly fitted on the examined historical
OOS window, **2024-01-01–2026-10-15**, at baseline 1-bp commission plus 3-bp
one-way slippage each way. The objective is daily cash-excess Sharpe, not CAGR:
`sqrt(252) * mean(net_daily_return - matched_cash_return) / sample_sd(excess)`.
There is no CAGR floor or bond-minimum allocation. Multistart analytic-gradient
SLSQP uses 48 deterministic LP starts, seed 1729, objective tolerance 1e-12 and
2,000 maximum iterations. Feasible incumbents are retained if local solvers do
not improve them. These are **best-found**, not globally certified optima.

Each resulting full-precision vector is then used unchanged in independent
$1,000 stage accounts: development **2017–2020**, validation **2021–2023**, and
historical OOS **2024–October 15, 2026**, at each of **1/3/10/25-bp** slippage plus
1-bp commission. Equal initial is 20% per strategy, not a sixth optimizer fit.
Strategies, account execution and dividends are not simulated again.

All fits and strategy choices are conditioned on already examined history.
Backward replay into earlier periods is **not clean portfolio validation**;
the historical OOS label describes the parent strategy period, not an untouched
portfolio test or forward-looking allocation recommendation.

## Static wealth and cap definitions

For cost `c`, date `t` and strategy `i`, use saved normalized wealth `E[c,t,i]`:

```
portfolio_wealth[c,t] = sum_i(initial_weight[i] * E[c,t,i])
capital_share[c,t,i] = initial_weight[i] * E[c,t,i] / portfolio_wealth[c,t]
```

This is **not** constant-weight return mixing. Capital is assigned once; there
are no cross-sleeve trades, cash redistribution or rebalancing, at any frequency.

- Daily cap: initial weights and every fitted historical daily capital share
  are at most one-third, simultaneously across all four costs.
- Weekly cap: initial weights and the last observed New York daily valuation
  in each **ISO year/week**, across all costs.
- Monthly cap: initial weights and the last observed valuation in each **calendar
  year/month**, across all costs.
- Initial cap: only starting weights have the one-third upper bound.
- Uncapped/equal initial: no ongoing share constraint.

The final partial week/month at October 15 is included. Missing calendar days
are not created; holidays and DST follow the authentic saved session timestamps.
Weekly/monthly checkpoints are not generally nested. Intermediate daily breaches
are allowed in those fits. Every report nevertheless displays all daily/weekly/
monthly maxima and breach-day counts for every allocation, period and cost.
Initial status is checked separately; a breach day means at least one sleeve
exceeds one-third plus numerical tolerance 1e-10. Earlier-period replay breaches
are not removed or used to refit weights. No cap guarantees future or intraday
concentration limits.

## Metrics, factors and correlations

Returns include the first return from initial $1,000 and embedded paid terminal
liquidation. CAGR uses exact ACT/365 elapsed time from first open to terminal
valuation. Daily drawdown includes initial capital; annualized volatility uses
252 observations and sample standard deviation. Cash remains **3% nominal
ACT/365 event-compounded**, not 3% APY. Its zero excess variance produces
undefined Sharpe, represented as `null`, not zero.

QQQ-only and joint-five-ETF regressions use **cost-matched passive buy-and-hold
excess returns**, not the active strategies as factors. The joint factors are
GDX, FXI, QQQ, UNG and FDN, without BND. Annual alpha is 252 times the daily OLS
intercept, arithmetic rather than CAGR. Partial betas may be negative despite
long-only sleeves; neither alpha nor fitted Sharpe establishes statistical skill.
Pearson correlations use saved net daily active returns, separately for all
stage/cost combinations. The portfolio correlation matrix also includes passive
QQQ. Identical fitted allocations and overlapping curves are disclosed.

## Audit and reproduction boundaries

The independently audited results contain **72 portfolio**, **24 control**,
**216 checkpoint**, **72 QQQ-only regression** and **72 joint-five-factor
regression** rows, plus **12 five-strategy** and **12 seven-series portfolio/QQQ**
correlation matrices. Original 24 QQQ/cash controls are preserved exactly after
independent path recomputation. An independent implementation checks wealth
mixing, Sharpe, actual-time CAGR, initial-inclusive drawdown, OLS, all calendar
checkpoints and correlations. It does not certify the original intraday fills
or prove a global optimizer solution. No new trade counts are inferred.

The private release binds 413 original input/source records, bounded saved
bundles, implementation, runtime and human scope before numerical access. Every
binding is rechecked after calculations and independent audit. New directories
preserve failures; one presentation-only schema mismatch was repaired without
rerunning any fit or account. Full account paths, releases, data and private
locators stay outside the public tree. Public PNGs contain rasters, not arrays.

```bash
python scripts/verify_no_bond_portfolios.py --public-report reports/no_bond_portfolios/report.json
python scripts/build_no_bond_reports.py --report reports/no_bond_portfolios/report.json \
  --figures-dir reports/no_bond_portfolios --output-dir outputs/rebuilt_no_bond_reports
```

The first command verifies aggregate identities/consistency without private
inputs. It is not a replacement for the separate saved-path audit receipt.
The second rebuilds presentation only, not allocation optimization. Exact private
recalculation uses `scripts/report_no_bond_portfolios.py` with an authenticated
saved-stage manifest and a new explicit hash-bound input release; no API key,
new market download or strategy-engine rerun is part of this calculation.
