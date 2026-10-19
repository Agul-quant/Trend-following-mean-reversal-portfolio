# Methodology

## Scope and chronology

The portfolio layer uses six unchanged active strategy account series: GDX, FXI,
QQQ, UNG, FDN and BND. See the exact indicator definitions in `configs/`.
All are unlevered and long/cash; there is no shorting or synthetic leverage.

The parent strategy study's development/validation/historical-OOS dates are
2017–2020 / 2021–2023 / 2024-01-01–2026-10-15. The portfolio dataset contains
700 common daily observations from 2024-01-02 through 2026-10-15, aligned to
17:00 America/New_York using exact UTC instants across DST transitions. Every
first return is measured from a fresh initial account, and the final observation
includes the parent's paid terminal liquidation.

Config selection, OOS-survivor display filters, removal of SMH and XLK, and
portfolio fitting occurred **after examination of these historical outcomes**.
The portfolio window is therefore retrospective, even though its input accounts
originated in a separately released historical-OOS stage. There is no newly
untouched portfolio holdout or claimed forward validation.

## Parent-account mechanics (inputs, not rerun here)

- Daily causal indicators with native half-hour observations; three trading
  hours/seven consecutive checks for entry and exit; next eligible bar-open fill.
- A 2015 feature seed and independent $1,000 long/cash stage starts. Feature
  history is carried, but not holdings, orders or confirmation streaks.
- Cash: 3% nominal ACT/365, compounded at account events. Use the **saved matched
  daily cash-return path**, not an assumed 3% APY or a constant 3%/252 deduction.
- Costs: 1-bp commission plus 1/3/10/25-bp one-way slippage on both entry and exit.
  Baseline slippage is 3 bps. Passive buy-and-hold accounts are ETF-specific and
  cost-matched. Corporate actions, distributions/reinvestment and paid terminal
  liquidation follow the original account conventions and are already embedded.
- Reconciled inputs and their revision decisions remain in private, immutable
  study records. These portable functions do not certify new raw price units,
  repair missing bars, download data or reconstruct intraday executions.

## Portfolio accounting

Let `E[c,t,i]` be the saved dollar equity of sleeve `i` divided by its original
$1,000, after all its costs and cash accrual. Let `w[i] >= 0` and `sum(w) = 1`.
The portfolio's initial normalized wealth is 1 and thereafter:

```text
V[c,t] = sum_i w[i] * E[c,t,i]
r[c,t] = V[c,t] / V[c,t-1] - 1      (V[c,-1] = 1)
sleeve_capital_share[c,t,i] = w[i] * E[c,t,i] / V[c,t]
```

This allocates capital once and lets sleeve shares drift. It is **not** the
constant-daily-weight return formula `sum_i w[i] * r[c,t,i]`, which would imply
cross-sleeve daily rebalancing with no modeled rebalance costs. Cash remains
inside its own sleeve; there is no redistribution, double cash accrual or second
deduction of the embedded strategy transaction costs.

Scaling assumes fractional shares and proportional basis-point costs, without
fixed fees or capital-dependent impact. This is a research accounting convention,
not a broker order-sizing or tax model.

## Statistics

With the actual matched cash return `cash[t]`:

```text
x[t] = portfolio_net_return[t] - cash[t]
cash_excess_Sharpe = sqrt(252) * mean(x) / sample_std(x, ddof=1)
CAGR = V[last] ** (1 / elapsed_ACT365_years) - 1
max_drawdown = min_t (V[t] / max(1, V[0], ..., V[t]) - 1)
```

CAGR uses **2.787043378995434 ACT/365 years**, from the fresh account's
2024-01-02 14:30 UTC start to 2026-10-15 21:00 UTC terminal valuation. It does
not use `700/252` or January 1 calendar labels as the elapsed investment time.
Drawdown includes the initial value of 1 and is a **daily-valuation** statistic.
Undefined Sharpe is retained as undefined/null; it is not promoted to a winner.

Correlation tables are Pearson correlations of the aligned daily **net active
strategy returns**, with all 700 observations and no pairwise deletion. Passive
factor correlations in the attribution diagnostics are separately labeled and
use passive **cash-excess** returns; they are not the active strategy matrix.

## Allocation objectives and constraints

The same baseline-fitted full-precision weights are evaluated unchanged at all
four costs. No scenario gets its own weight reselection.

1. **Current daily-capped maximum Sharpe:** nonnegative initial weights summing
   to 1, each initially at most 1/3, and each historical daily sleeve-capital share
   at most 1/3 across **all four** cost scenarios. In wealth units this is linear:
   `sum_j w[j]*E[c,t,j] - 3*w[i]*E[c,t,i] >= 0`, for all `c,t,i` (16,800 rows).
   There is no rebalance enforcement; weights are selected to satisfy the observed
   paths. Future, intraday, actual ETF-holdings and risk-contribution caps are not
   implied.
2. **Initial-only cap comparison:** the same baseline Sharpe objective and 1/3
   initial bounds, without historical daily-share constraints. Later drift can
   and does violate 1/3.
3. **Uncapped maximum Sharpe:** only the nonnegative unit simplex. The selected
   high-Sharpe solution is mostly allocated to a BND strategy that is mainly cash;
   it is not equivalent to continuously holding that allocation in passive bonds.
4. **Equal initial weights:** 1/6 per strategy, also static—not daily equal weight.
5. **Maximum CAGR comparison:** unconstrained beyond the nonnegative unit simplex.
   Terminal wealth is linear in initial weights and CAGR increases with terminal
   wealth, so a maximal-terminal-wealth sleeve vertex is an exact optimum under
   this model. The historical vertex is 100% GDX **strategy**. This proof does not
   apply to dynamically rebalanced portfolios or an added 1/3 cap.

Maximum-Sharpe weights were challenged with multiple starts, boundary/face
searches and independent numerical checks in the private calculation. The
wealth-ratio Sharpe objective is nonlinear; these results are **best-found**, not
global-optimum certificates. A portable optimizer rerun may find a different local
solution; it must be reported as a new experiment, not a revision of saved weights.

## Alpha and beta

For each scenario, use the same portfolio and the corresponding scenario's
**passive ETF buy-and-hold** accounts, subtracting the identical cash reference
from both sides:

```text
y[t] = r_portfolio_net[t] - cash[t]
X[t,j] = r_passive_BH_net[t,j] - cash[t]
y[t] = alpha_daily + sum_j beta[j]*X[t,j] + residual[t]
annualized_arithmetic_alpha = 252 * alpha_daily
```

The joint model includes an intercept and all six factors simultaneously.
Separate pairwise models include just one passive ETF each; their slopes must
not be added together as a decomposition. The QQQ-only tables reproduce the QQQ
pairwise specification. The active-strategy supplementary tables change the
dependent account, **not** the passive explanatory factors.

Report `R² = 1 - SSE/SST` and adjusted `R² = 1 - (1-R²)*(n-1)/(n-k-1)` for `k`
factors. No ranks are silently dropped or signs constrained. Factor-rank,
condition-number and VIF diagnostics accompany the joint results.

Joint betas are **conditional partial sensitivities**, not weights, causal effects
or evidence of actual shorting. Alpha is an arithmetic annualization of a daily
intercept, not CAGR, a compounded return, unexplained variance or proof of skill.
The ETF factors are not an exhaustive economic risk model or canonical
Fama–French factors. Higher in-sample R² after adding regressors is expected and
does not establish better forecasting. Post-selection uncertainty, serial
dependence, omitted/nonlinear exposures and changing strategy exposure remain;
no significance, confidence interval or forward alpha guarantee is asserted.
