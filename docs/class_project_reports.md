# Class project reports

## Scope and reading order

The active report set uses the original three-period basis expressly requested
for the four retained ETF portfolios. It does not substitute another study's
splits, rerun the underlying strategy accounts or fit new allocations.

| Report | Scored calendar period | Daily return observations | Purpose |
|---|---|---:|---|
| Development and robustness | 2017-01-01–2020-12-31 | 1,007 | Explain the research design and inspect the same four allocations retrospectively |
| Validation and frozen selection | 2021-01-01–2023-12-31 | 753 | Show transfer, failure cases and capital-share diagnostics without reselection |
| Historical OOS and conclusions | 2024-01-01–2026-10-15 | 700 | Describe the examined historical account window and the limitations of fitting portfolios to it |

Read the [three-report index](../final_reports/README.md) in order. Each report
has a PDF edition and an equivalent standalone offline HTML edition. The
[three-period aggregate evidence](../reports/four_portfolios_three_periods/)
contains 48 portfolio/cost rows, 24 control/cost rows and 48 capital-share rows.
Full-precision definitions remain in the [four-portfolio configuration](../configs/four_portfolios.json)
and [selected six-strategy registry](../configs/selected_strategies.json).

The standalone maximum-CAGR allocation of 100% to the GDX **strategy** is excluded
from this active four-portfolio report set. GDX remains an underlying sleeve.
The original five-portfolio snapshot is historical evidence, not a fifth active
comparison or a source of replacement weights.

## Reference format and course requirements

The presentation is inspired by the public
[Cryptocurrency statistical arbitrage report set](https://github.com/Agul-quant/Cryptocurrency-statistical-arbitrage/tree/5d4fb259b0ca3d448bb6a55d09445063d1f48add/final_reports),
inspected at commit `5d4fb259b0ca3d448bb6a55d09445063d1f48add`.
That reference supplies a three-report reading order, A4 PDF and offline HTML
editions, executive summaries, evidence-led sections, compact tables, figures,
attribution appendices and explicit conclusions. Its prose, numerical results,
strategies, calendars and statistical claims are not copied into this study.
The reports retain this project's own methods and evidence.

The previously supplied class-project brief is an assignment outline, not a
completed empirical report. Its crypto example motivates the following adapted
requirements; it does not authorize exchange execution or supply ETF fee rules.

| Course requirement | Treatment in the ETF project |
|---|---|
| Project Goal | Test the research hypothesis that selected long/cash trend and oversold-recovery accounts can offer different return and risk characteristics from passive QQQ |
| Research Outline | State the tested indicator horizons, confirmation process, correlation comparisons and fixed-allocation comparisons; separate untested ideas from completed experiments |
| Data | Describe the ETF universe, daily and native half-hour inputs, feature seed, source-vintage reconciliation, calendars and the distinction between private account evidence and public exports |
| Backtesting | Explain causal previews, seven consecutive checks, next eligible bar-open execution, corporate actions, fresh stage accounts and independent stage clocks |
| Execution and Slippage | Retain 1-bp commission plus 1/3/10/25-bp one-way slippage, charged each way, and matched passive/cash controls |
| Weighting | Compare the same four saved initial allocations by mixing sleeve wealth, with no daily portfolio rebalancing or new optimization |
| Performance Evaluation | Report return/CAGR, volatility, cash-excess Sharpe, daily drawdown, QQQ-only and joint-six-passive-factor alpha/betas, cost sensitivities and limitations |

The brief's suggested “unconstrained” classroom backtest is not a sufficiently
specified engine to reproduce. This implementation instead has explicit
unlevered, long/cash restrictions. The ETFs are not a market-neutral statistical
arbitrage book. Volume/news filters, seasonality, identified liquidation flows,
mechanical rebalancing events, correlated-spread trades and macro-conditioned
signals remain proposed extensions, not accomplished tests. Asset themes provide
exposure context, not a separately verified theme-momentum strategy.

## Shared report structure

Each edition begins with a stage/date heading, a short executive summary and a
clear statement of the historical-selection limitation. The body covers study
scope and exact identities, data and accounting, baseline results and benchmark,
equity and drawdown evidence, four-cost sensitivity, capital-share diagnostics,
alpha/beta attribution, and stage-specific conclusions. Definitions and exports
accompany the narrative so rounded display values do not replace full-precision
records.

Development is a retrospective replay of the final selected portfolio set, not a
reconstruction of an untouched initial allocation decision. Validation preserves
weak and negative risk-adjusted findings. The historical OOS report distinguishes
the parent account-stage label from the later, OOS-informed portfolio selection.
All three use the same four allocations, six sleeve identities and cost grid.
No later-stage result is used to refit an earlier reported allocation.

## Signal and account conventions

The six active sleeves are GDX, FXI, QQQ, UNG, FDN and BND. Mean-reversion rules
use the exact saved z-score, Wilder RSI or EMA-distance thresholds. QQQ and FDN
use **price-versus-projected-EMA gates, not moving-average crossover systems**:

- QQQ entry requires provisional price strictly above both projected EMA50 and
  projected EMA200; its exit condition is price at or below projected EMA200.
- FDN entry requires provisional price strictly above both projected EMA50 and
  projected EMA100; its exit condition is price at or below projected EMA100.

Here price is the current provisional forward total-return index, not an
unadjusted dollar close mixed with an adjusted indicator. Each intraday preview
starts from the previous finalized daily state plus the current provisional
observation. It does not recursively treat successive half-hours as successive
daily observations. The z-score uses the preceding `n-1` finalized daily values
plus that observation and sample standard deviation (`ddof=1`). EMA smoothing is
`2/(n+1)`; Wilder RSI uses its original daily initialization and `1/14` smoothing.

Supported entry or exit conditions must persist for **seven consecutive eligible
half-hour checks spanning three trading hours**. Orders then execute at the next
eligible bar open, not the signal close. Session closures are not extra checks.
Preserved blackout, pending-order and terminal-execution conventions remain those
of the frozen parent account engine; this reporting layer does not reevaluate
signals or reconstruct fills.

Each stage begins flat with **$1,000**, no inherited orders or confirmation
streaks, and its own elapsed-time clock. Only feature history carries forward.
The account valuation grid is 17:00 America/New_York with exact UTC alignment
across DST; that valuation label is not a claim of a 17:00 exchange fill.
Initial-to-first returns and paid terminal liquidation are retained. Daily
maximum drawdown includes initial wealth and does not measure intraday losses.

Cash earns **3% nominal ACT/365, event compounded**. Its matched saved daily
return path is used, not a constant `3%/252` deduction or a 3% APY approximation.
Baseline costs are 1-bp commission plus 3-bp slippage per side; the other slippage
scenarios are 1, 10 and 25 bps. Costs, actions and cash are already embedded in
account paths and are not deducted or accrued a second time. The passive QQQ
control is a cost-matched buy-and-hold account, not the active QQQ sleeve.

## Wealth mixing and the historical cap

For each cost `c`, stage and observation `t`, normalize each saved sleeve account
by its own original $1,000, giving `E[c,t,i]`. The saved initial weights `w[i]`
are nonnegative and sum to one:

```text
V[c,t] = sum_i w[i] * E[c,t,i]           V[c,-1] = 1
r[c,t] = V[c,t] / V[c,t-1] - 1
share[c,t,i] = w[i] * E[c,t,i] / V[c,t]
```

This is an initial allocation with drifting sleeve capital shares, not the
constant-daily-weight formula `sum_i w[i] * sleeve_return[c,t,i]`. No free
cross-sleeve daily rebalancing is assumed. Scaling presumes fractional shares and
proportional basis-point fees, without fixed fees or capital-dependent impact.

“Daily-capped maximum Sharpe” names a best-found allocation fitted subject to
historical OOS daily capital-share constraints across four costs. It is not a
standing rebalancing rule, global-optimality certificate or future/intraday cap
guarantee. The same weights breach one-third in validation: the baseline maximum
is approximately **35.18%**, in the UNG sleeve, versus a 33.33% cap. That failure
is reported rather than repaired by a new fit. The cap concerns each strategy
account's capital, including idle cash, not direct ETF holdings or risk exposure.

## Statistics and attribution

Cash-excess Sharpe uses `sqrt(252) * mean(r - cash) / sample_std(r - cash)`.
Undefined/no-variance cases remain undefined, not zero. CAGR uses each stage's
actual ACT/365 investment interval, not its observation count divided by 252.
Raw-return and cash-excess volatility are separately identified. Correlation of
active net strategy returns is not the same analysis as correlation of passive
ETF returns or risk-factor exposure.

The QQQ-only regression and the joint model use the appropriate cost-matched
**passive ETF** returns, subtracting matched cash from both dependent and factor
series. The joint model includes an intercept and all six passive factors:

```text
portfolio_net_return - cash_return
    = alpha_daily + sum_j beta[j] * (passive_ETF_return[j] - cash_return)
      + residual
annualized_arithmetic_alpha = 252 * alpha_daily
```

Alpha is an arithmetic annualization, **not CAGR**, a compounded excess return or
proof of skill. Joint betas are conditional partial sensitivities, not allocation
weights or actual short positions. A higher in-sample R-squared after adding
factors does not validate forecasts. Rank and collinearity diagnostics are
retained; no unavailable confidence intervals, p-values, turnover, trade counts,
per-sleeve fee attribution or crypto-style significance tests are invented.

## Data vintage and reproducibility limits

Retained Alpha Vantage daily prices/actions and intraday captures underlie the
parent studies. Available native overlaps, same-provider 15-to-30-minute checks
and daily anchors support reconciliation; they are not independent-vendor
confirmation. Legacy adjusted intraday records may be restored only with their
matching historical adjustment vintage. Fresh factors must not be imposed on
older adjusted captures. ETF-specific approved revisions and frozen exceptions
remain distinct; QQQ exceptions do not transfer to other products.

Causal indicator construction does not make retrospectively captured provider
records a complete point-in-time database. No claim is made that every historical
revision was known on its economic date. The frozen parent account/source audits
and the independent saved-path arithmetic have different scopes; this report is
not a new raw-price reconciliation or independent intraday ledger reconstruction.
See [data sources](data_sources.md), [methods](methodology.md),
[three-period calculations](periods.md) and the [input schema](input_schema.md).

The public package contains portable code, exact parameter definitions, aggregate
tables and raster charts. It intentionally omits provider market observations,
numerical daily paths, credentials, private source maps, authorizations and study
freezes. Aggregate checks and synthetic tests can run without credentials; exact
numerical replay needs the privately held authenticated account bundles. Public
exports alone do not reproduce the underlying intraday backtests.

## Downloading and reading offline

1. From GitHub, download the repository ZIP or clone it, then open
   `final_reports/README.md` to identify the three editions. Alternatively, open
   one report's GitHub file page and use **Download raw file**.
2. Open a PDF in any PDF reader. Download the actual PDF bytes rather than saving
   a GitHub navigation page as a PDF.
3. For HTML, save the actual `.html` file with that extension and open the local
   file in a browser. GitHub's code preview is not the rendered report. Each HTML
   edition contains its own styles, aggregate tables and raster figures, so it
   does not require a server, API key, CDN or network connection to read.
4. Use the report's section links for navigation. Tables may scroll horizontally
   on narrow screens. A browser's Print command provides an alternative viewing
   mode; the supplied PDF is the inspected, paginated edition.

The selected configurations, removal of other ETFs and fitted weights used
examined 2024–2026 outcomes. Earlier-period portfolio comparisons are therefore
backward-looking diagnostics, and historical OOS is **not untouched portfolio
OOS**. None of the editions constitutes a deployment recommendation, live signal
or trading authorization. A genuinely new prospective test would require a new
explicit release and frozen inputs and decisions before examining that window.
