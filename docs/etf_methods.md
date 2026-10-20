# ETF Strategy and Portfolio Methods

The current portfolio comparison uses **GDX, FXI, QQQ, UNG and FDN**, with
**Initial allocation; no rebalancing**, **Equal weight; no rebalancing**,
**Weekly corrections** and **Monthly corrections** comparisons. All are unlevered and long/cash. There is no
shorting, standalone maximum-CAGR allocation or newly optimized starting vector.

This is a scope-restricted publication of completed, previously examined
research. The [47-ETF scope](etf_data_sources.md) is not a new universe-wide run.
Published portfolio outcomes and strategy definitions are unchanged; no
unreported development or validation survivor counts are inferred from it.

## Underlying staged strategy research

The original definition registry contains **379 configurations**: 289
trend-following definitions and 90 persistent-oversold/recovery mean-reversion
definitions. Mean reversion is long/cash: enter after persistent oversold
conditions and exit on recovery, not a short strategy.

| Stage | Scored dates | Account reset |
|---|---|---|
| Development | 2017-01-01–2020-12-31 | Fresh $1,000, flat account |
| Validation | 2021-01-01–2023-12-31 | Fresh $1,000, flat account |
| Retrospective portfolio-selection sample (**in-sample**; internal historical_OOS) | 2024-01-01–2026-10-15 | Fresh $1,000, flat account |

Daily causal indicators use native half-hour observations and the shared
**three-trading-hour / seven-consecutive-check** entry and exit confirmation.
Confirmed normal orders execute at the next eligible observed bar open, not
the signal close. Daily recursive state is finalized once per session rather
than reinitialized or advanced as if every half-hour were a new daily close.
Features initialize from verified available 2015 history with at least 295
completed pre-development daily observations. Actual inception and strict
coverage checks apply; historical observations are not fabricated.

Only feature history crosses a stage boundary. Holdings, pending orders,
confirmation streaks and earned capital do not. ETF-specific buy-and-hold and
cash controls use the same stage, action treatment and relevant trading costs.

The staged screen was ETF-specific at **25-bp one-way slippage**: net
cash-excess Sharpe must strictly exceed the ETF's cost-matched buy-and-hold
Sharpe. The amended growth condition requires CAGR strictly greater than
two-thirds of buy-and-hold CAGR when buy-and-hold CAGR is nonnegative; if
buy-and-hold CAGR is negative, candidate CAGR must instead be **positive**.
The subsequent ETF advancement filter required more than five survivors.
These are historical selection rules, not counts or a claim that every ETF
in the published scope advanced. Nonfinite candidate metrics cannot pass;
a nonfinite required control makes selection non-evaluable, not an automatic
pass. Validation comparison results did not replace already sealed membership.

## Five unchanged strategy sleeves

Exact identifiers, rule parameters and definitions are in
[the selected-strategy config](../configs/selected_etf_strategies.json).

| ETF | Strategy |
|---|---|
| GDX | Mean reversion: Z-score(20), entry ≤ −2, recovery exit ≥ 0 |
| FXI | Mean reversion: Z-score(50), entry ≤ −2, recovery exit ≥ 0.5 |
| QQQ | Trend following: EMA50 entry / EMA200 exit |
| UNG | Mean reversion: Wilder RSI(14), entry ≤ 30, recovery exit ≥ 50 |
| FDN | Trend following: EMA50 entry / EMA100 exit |

Each portfolio starts each stage independently with **$1,000 total**, initially
flat and allocated to the five cash sleeves below. The full-precision saved
fitted vector is identical across stages, costs and correction frequencies; it
was not refitted. The equal-weight comparison instead allocates 20% to each
sleeve once per stage, with no later rebalancing.

| Sleeve | Initial weight |
|---|---:|
| GDX | 0.2905130826010515 |
| FXI | 0.2799197437112525 |
| QQQ | 0.06304492619579012 |
| UNG | 0.26729328450466966 |
| FDN | 0.0992289629872361 |

The [portfolio policy config](../configs/final_cap_rebalancing.json) is the
machine-readable authority for this vector, periods and costs.

## Initial allocation comparator

For saved normalized sleeve wealth `E[c,t,i]` and initial weights `w[i]`, the
no-rebalancing comparator is:

```text
V[c,t] = sum_i w[i] * E[c,t,i]
r[c,t] = V[c,t] / V[c,t-1] - 1, with V[c,-1] = 1
sleeve_capital_share[c,t,i] = w[i] * E[c,t,i] / V[c,t]
```

Capital is allocated once and then drifts. This is not the constant-weight
return average `sum_i w[i] * r[c,t,i]`, which would silently introduce free
rebalancing. Cash remains inside its strategy account. Fractional shares and
proportional basis-point costs are assumed; fixed ticket fees, taxes and
capital-dependent market impact are not modeled.

## Weekly and monthly cap-triggered corrections

1. At **17:00 America/New_York** on the last actual XNYS trading session of
   each ISO week or calendar month, inspect each sleeve's whole account capital:
   ETF market value **plus its cash**. Queue a portfolio correction only if a
   share exceeds one-third, subject to the numerical tolerance. Do not create
   an artificial checkpoint at the fixed cutoff's incomplete week or month.
2. Wait until the next simultaneously eligible observed raw half-hour **bar
   open for all five ETFs**, strictly after that decision. Corporate actions,
   the original dividend-reinvestment proxy and all confirmed normal strategy
   fills occur first. Reassess the cap; cancel the correction if the breach
   disappeared. Do not place portfolio trades inside a per-ETF processing loop.
3. Trim oversized accounts and redistribute excess proportionally to the
   other sleeves' **current account capital**, recursively capping recipients.
   It is not a reset to the initial vector. Solve post-cost total wealth and
   capped allocations self-consistently; internal cash transfers sum to zero
   and no external capital is added.
4. Respect each strategy's current signal. Long recipients buy additional
   ETF shares; flat recipients keep the received cash. Partial cap orders do
   not change the logical long/cash state, reset confirmation streaks or count
   as completed strategy round trips. There is no cross-sleeve or signal/cap
   order netting.

A cap execution can consist solely of cash transfers. Thus execution counts,
paid ETF-order counts and completed strategy trips measure different things.
The source ledger separately records them. A correction that is not triggered
is a true no-op, not a forced investment of residual cash.

**The one-third cap is post-correction, not continuous.** Between-check drift,
overnight gaps and daily closing breaches remain possible. It is a limit on
whole sleeve capital, not on ETF exposure, volatility or risk contribution.
Observed daily/opening diagnostics do not certify every intraday tick.

## Cash, actions, costs and terminal valuation

- Cash earns **3% nominal ACT/365, compounded once at account-event times**;
  it is not 3% APY or a fixed 3%/252 daily subtraction. Dividend cash earmarks
  are subsets of cash, not additional wealth.
- Each paid normal, correction or terminal ETF order pays **1-bp commission
  plus 1/3/10/25-bp one-way slippage, each way**. Baseline slippage is **3 bps**.
  Costs apply to actual incremental trade quantities. Internal cash transfers
  have no trading fee. The original fee-free dividend-reinvestment proxy is
  retained and is not confused with a paid correction purchase.
- Original split, distribution, reinvestment and provider-daily-close marking
  conventions remain intact. Normal orders are next-open; forced terminal
  liquidation is the original **paid sale at the final safe observed regular-
  session bar close**. Pending intents that cannot execute by the cutoff are
  cancelled; no market data or fills beyond 2026-10-15 are introduced.
- Additional correction costs are direct correction-order commissions and
  slippage, not the entire cost/return difference against the comparator.
  Later normal strategy trades may have different sizes after capital moves.

### Calendar-time cash versus trading-day statistics

The model's cash balance grows at each unique event as:

```text
cash_next = cash_now * (1 + 0.03 * elapsed_seconds / (365 * 86400))
```

**ACT/365 and 252 are not competing annualization denominators.** ACT/365
converts real elapsed calendar time into an interest accrual fraction; 252
annualizes statistics of the observed trading-session return series. Cash
accrues over weekends and holidays even though no extra ETF return rows are
inserted. A Friday-to-Monday portfolio return and its matched cash return
cover the same elapsed interval. Sharpe subtracts that matched interval's cash
return—not a constant `0.03/252` or `0.03/365` from every observation. CAGR
uses actual elapsed ACT/365 years, not `n/252`, for both portfolios and controls.

Calendar-day weighting is normal in cash-rate conventions; for example, the
[New York Fed's SOFR methodology](https://www.newyorkfed.org/markets/reference-rates/additional-information-about-reference-rates)
assigns weekend/holiday calendar-day weights to the preceding business-day
rate. SOFR itself uses ACT/360: this study's fixed ACT/365 model is **not** a
claim to reproduce SOFR or any particular deposit instrument. For the separate
statistical convention, see [Sharpe's discussion of measurement periods and
annualization](https://www-leland.stanford.edu/~wfsharpe/art/sr/SR.htm).

The economic assumption remains material. **A fixed 3% is modeled, not an
observed or guaranteed historical/future cash yield.** Reinvesting interest at
every event also makes effective growth slightly event-frequency-dependent;
fine intervals approach `exp(0.03)-1`, approximately **3.045% per 365 elapsed
days**, rather than 3% APY. ACT/365 retains a 365-day denominator in leap years.
Given the portfolio's substantial cash allocation, realism of the earned cash
rate matters separately from clock consistency. Any alternative cash rate,
actual-yield series or compounding convention requires a separately labeled
experiment; neither saved performance nor the frozen forward model is changed
by this explanation.

## Statistics and attribution

Use aligned net daily simple returns `r[t]` and the matched cash path `cash[t]`:

```text
x[t] = r[t] - cash[t]
cash_excess_Sharpe = sqrt(252) * mean(x) / sample_std(x, ddof=1)
CAGR = (terminal_wealth / initial_wealth) ** (1 / elapsed_ACT365_years) - 1
max_drawdown = min_t (wealth[t] / running_peak_including_initial_wealth[t] - 1)
```

Cash-excess does **not** mean excess over buy-and-hold. CAGR uses actual
initial-to-terminal elapsed time, not the calendar stage label or `n/252`.
Drawdown is measured on daily marked wealth including initial capital, not
intraday extrema. Undefined/no-trade metrics remain explicitly undefined;
independent stage accounts are not spliced into one investment history.

Where attribution is reported, regress net portfolio cash-excess returns on
cost-matched passive ETF cash-excess returns with an intercept. Annual alpha is
**252 times the daily arithmetic intercept**, not CAGR. Joint five-ETF betas are
conditional partial sensitivities, not allocations or causal effects; pairwise
betas are separate specifications and must not be added. Strategy correlations
and passive-factor correlations refer to different return series and must be
labeled accordingly.

## Evidence, limitations and reproduction

Before the completed cap calculations, disabled-correction replay matched the
five original frozen sleeve wealth paths and cash across all three periods and
four costs. Independent scalar checks examined chronological cash, actions,
dividend reinvestment, fills, transfers, paid costs, post-cost caps and saved
statistics. The original aggregate retains **36 fitted-portfolio/cost/period rows and
15 distinct matched controls**. The public return release supplies the 12
equal-weight comparison rows, for 48 portfolio outcomes; this publication
does not rerun any account or change the frozen forward portfolio.

Public manifests bind aggregate bytes, policy and scope, and synthetic tests
exercise accounting without market data. They do not replace the unpublished
input provenance or independently recreate source financial outcomes from a
hash. Exact financial reproduction requires authenticated private inputs,
event primitives, ledgers and sleeve paths; these are not published.
Derived aggregate daily portfolio/benchmark/cash returns are now released with
a portable summary-statistic verifier; this does not expose raw ETF prices.

**Retrospective selection is material.** Strategy identities, pruning and the
starting vector used already examined historical OOS. The historical stage name
does not make this untouched portfolio OOS. This is not an optimal-frequency
claim, forward alpha guarantee or live trading instruction.

[Current aggregate report](../reports/etf_portfolios/report.md) ·
[Data sources and scope](etf_data_sources.md)

## Statistical comparison and inference

The equal-initial comparator allocates 20% once to each of the same five
strategies and allows capital to drift. It is extracted from existing saved
wealth paths, not a new optimizer or free daily rebalanced return average.
The [public returns release](../reports/reproducibility/README.md) includes all
three periods and costs, plus the current fitted static, weekly and monthly
accounts and matched controls. Historical retained aggregates are unchanged.

For `x = net_portfolio_return - matched_cash_return`, the IID mean-excess
t-statistic is `mean(x)/(sample_std(x)/sqrt(n))`. HAC/Newey–West inference
uses an intercept-only regression, Bartlett weights, a predeclared automatic
lag `floor(4*(n/100)^(2/9))`, HC1 finite-sample correction, and explicit
0/5/10/20-lag sensitivity. These are tests of the daily mean excess return,
not regression-alpha t-statistics. See the public verifier for exact arithmetic.
Serial dependence matters ([Lo, 2002](https://rpc.cfainstitute.org/research/financial-analysts-journal/2002/the-statistics-of-sharpe-ratios)); HAC does not correct
for the historical search, chosen universe, pruning, optimized weights or
multiple testing. Do not interpret either statistic as a selection-adjusted
p-value or evidence of untouched portfolio OOS.

## Prospective paper tracking

Only **Initial allocation; no rebalancing** is the primary forward portfolio,
explicitly chosen by the user. The timestamped [public protocol seal](../configs/paper_portfolio_freeze.json)
and [operating protocol](paper_tracking.md) define the future-only start, fresh
flat accounts, fixed strategies/weights/costs/cash and fail-closed data checks.
No historical 2024–2026 observation is counted as forward. The running account
is marked, not forcibly liquidated at each report date. Paper outcomes are
simulated hypothetical fills, never actual broker executions.
