# Four fixed portfolios — three historical periods, four slippages

The standalone **maximum-CAGR / 100% GDX strategy portfolio is excluded**.
GDX remains inside the six underlying strategy sleeves; the other four
full-precision initial allocations and six strategy definitions are unchanged.
There is no reoptimization, stage concatenation, new market data or account rerun.

**Important:** these strategies and weights were selected/fitted after examining
historical OOS. “Development”, “validation” and “historical OOS” below name the
parent accounts' original periods—not a new chronological portfolio experiment.
The earlier-period applications are backward retrospective diagnostics. Inputs
retain each original stage's frozen data vintage and corporate-action decisions;
this is not a newly refreshed common-vintage strategy study.

Every period starts independently with **$1,000**, feature history but no inherited
positions/orders/confirmation streaks. Portfolio equity mixes fixed initial
sleeve **wealth**, not daily returns at rebalanced weights. Cash, distributions,
transaction costs and paid terminal liquidation are already embedded in the
completed saved accounts. Scaling uses the original fractional-share and
proportional-fee convention.

## All-cost performance

**Each cell: cash-excess Sharpe / CAGR / maximum daily drawdown.** Sharpe is
computed as sqrt(252) × mean daily cash-excess return / sample standard deviation,
and subtracts the matched actual cash path
(3% nominal ACT/365 event-compounded, not 3% APY). CAGR uses each stage's exact
first-open-to-terminal ACT/365 clock. Drawdown includes the initial balance and
is daily, not intraday. Costs are **1-bp commission plus the column's one-way
slippage, each way**; the same weights are used at every cost and stage.

### Development: 2017–2020

| Portfolio | 1 bp | 3 bps — baseline | 10 bps | 25 bps |
|---|---:|---:|---:|---:|
| Daily-cap weights† | 1.330 / 14.86% / -7.52% | 1.321 / 14.77% / -7.52% | 1.293 / 14.47% / -7.53% | 1.230 / 13.82% / -7.54% |
| Initial-only cap | 1.303 / 16.24% / -8.48% | 1.295 / 16.14% / -8.48% | 1.267 / 15.80% / -8.49% | 1.205 / 15.08% / -8.51% |
| Uncapped max-Sharpe | 1.331 / 6.24% / -2.31% | 1.320 / 6.21% / -2.32% | 1.279 / 6.12% / -2.37% | 1.193 / 5.93% / -2.48% |
| Equal initial weights | 1.513 / 17.51% / -6.53% | 1.506 / 17.43% / -6.56% | 1.481 / 17.16% / -6.65% | 1.427 / 16.58% / -6.85% |
| QQQ buy-and-hold | 1.063 / 28.40% / -28.56% | 1.063 / 28.39% / -28.56% | 1.061 / 28.35% / -28.56% | 1.058 / 28.25% / -28.56% |

### Validation: 2021–2023

| Portfolio | 1 bp | 3 bps — baseline | 10 bps | 25 bps |
|---|---:|---:|---:|---:|
| Daily-cap weights† | 0.391 / 7.02% / -17.50% | 0.381 / 6.90% / -17.52% | 0.346 / 6.48% / -17.59% | 0.272 / 5.59% / -17.73% |
| Initial-only cap | 0.429 / 7.90% / -19.22% | 0.419 / 7.77% / -19.24% | 0.385 / 7.30% / -19.33% | 0.311 / 6.32% / -19.52% |
| Uncapped max-Sharpe | -0.231 / 1.88% / -9.66% | -0.243 / 1.82% / -9.70% | -0.285 / 1.63% / -9.85% | -0.375 / 1.23% / -10.16% |
| Equal initial weights | 0.485 / 7.42% / -13.45% | 0.473 / 7.30% / -13.48% | 0.432 / 6.89% / -13.56% | 0.346 / 6.01% / -13.75% |
| QQQ buy-and-hold | 0.388 / 9.86% / -35.12% | 0.387 / 9.84% / -35.12% | 0.385 / 9.79% / -35.12% | 0.381 / 9.68% / -35.12% |

### Historical OOS: 2024–2026-10-15

| Portfolio | 1 bp | 3 bps — baseline | 10 bps | 25 bps |
|---|---:|---:|---:|---:|
| Daily-cap weights† | 2.492 / 21.98% / -4.23% | 2.481 / 21.85% / -4.24% | 2.440 / 21.42% / -4.25% | 2.351 / 20.50% / -4.29% |
| Initial-only cap | 2.499 / 24.71% / -4.66% | 2.487 / 24.57% / -4.67% | 2.447 / 24.08% / -4.69% | 2.358 / 23.04% / -4.74% |
| Uncapped max-Sharpe | 2.508 / 6.89% / -0.82% | 2.497 / 6.86% / -0.82% | 2.455 / 6.73% / -0.82% | 2.351 / 6.46% / -0.82% |
| Equal initial weights | 2.216 / 20.58% / -4.27% | 2.204 / 20.46% / -4.27% | 2.164 / 20.07% / -4.29% | 2.077 / 19.25% / -4.31% |
| QQQ buy-and-hold | 0.997 / 23.95% / -22.77% | 0.996 / 23.93% / -22.77% | 0.993 / 23.87% / -22.77% | 0.988 / 23.73% / -22.77% |

QQQ is the stage-specific, cost-matched **passive** buy-and-hold account, not
the active QQQ strategy sleeve. The matched cash control remains in the complete
machine-readable report with undefined/null cash-excess Sharpe; it is not
silently assigned zero Sharpe or removed from the record.

## † The original daily-cap fit does not guarantee a cap in earlier periods

These are the **OOS-fitted daily-capped weights**, not a daily rebalancing rule.
When replayed unchanged in validation they exceed one-third in the UNG strategy
sleeve: **35.18% at baseline, on 41 daily valuations**. Every validation cost
scenario has41 breach days. No weights or paths were changed to repair this.

| Period | Max sleeve share: 1 bp | 3 bps | 10 bps | 25 bps | Daily one-third cap |
|---|---:|---:|---:|---:|---|
| Development | 26.80% | 26.80% | 26.80% | 26.80% | Pass at all four costs |
| Validation | 35.16% | 35.18% | 35.28% | 35.48% | **Breached at all four costs** |
| Historical OOS | 33.33% | 33.27% | 33.05% | 32.57% | Pass at all four costs |

The initial-only allocation has no post-initial cap promise; the uncapped and
equal-initial comparators are not newly constrained either. All48 capital-share
diagnostic rows remain available; breach flags are descriptive, not a reason to
change allocations, discard a result or introduce free rebalance trades.

## Reading the results

At baseline, equal initial weights have higher cash-excess Sharpe than the other
three portfolio variants in development and validation. Validation is the weak
period: the uncapped max-Sharpe allocation has **negative cash-excess Sharpe at
all four costs**, despite positive CAGR, because returns are below the matched
cash reference on this statistic. Stronger fitted-period OOS results do not
establish forward robustness or undo the hindsight-conditioned choices.

## Stage clocks

| Period | First open (UTC) | Last valuation (UTC) | Daily observations | ACT/365 years |
|---|---|---|---:|---:|
| development | 2017-01-03T14:30:00+00:00 | 2020-12-31T22:00:00+00:00 | 1007 | 3.995376712328767 |
| validation | 2021-01-04T14:30:00+00:00 | 2023-12-29T22:00:00+00:00 | 753 | 2.984417808219178 |
| historical_OOS | 2024-01-02T14:30:00+00:00 | 2026-10-15T21:00:00+00:00 | 700 | 2.787043378995434 |

The first actual sessions are January3,2017; January4,2021; and January2,2024.
There is no capital/holding carry between these periods and no return rebasing
by the first end-of-day equity (which would erase the first return/cost).

## Files and audit scope

- [portfolio_rows.csv](portfolio_rows.csv):48 portfolio × stage × cost outcomes.
- [control_rows.csv](control_rows.csv):12 QQQ buy-and-hold and12 matched-cash outcomes.
- [cap_rows.csv](cap_rows.csv):48 daily capital-share diagnostics, not cap enforcement.
- [stage_summaries.csv](stage_summaries.csv):3 exact independent account clocks.
- [report.json](report.json):all aggregate rows and exact unchanged four allocations.
- [provenance.json](provenance.json):sanitized source/implementation hashes and verification summary.
- [Four-portfolio definitions](../../configs/four_portfolios.json) and
  [portable report reproduction](../../docs/periods.md).

A separately implemented oracle recomputes the saved-stage arithmetic and
checks selected account metrics, cash, chronology and cap diagnostics. Original
source72 hashes,403 bound inputs and the18 previously published aggregate payloads
are unchanged. This does not independently rebuild intraday trades or the QQQ
legacy ledger, and no new raw-price reconciliation or financial account run is
claimed. Private arrays, local input paths, source maps and authorization payloads
are not bundled. The historical five-portfolio snapshot is retained unchanged;
the standalone GDX maximum-CAGR case is excluded from this new report.

This follow-up is saved locally; no new commit, push or publication was requested
or performed for this report.
