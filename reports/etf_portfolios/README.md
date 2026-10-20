# ETF Strategy Portfolios

The portfolio uses **GDX, FXI, QQQ, UNG and FDN**, with **Weekly corrections**,
**Monthly corrections** and the **Initial allocation / no-rebalancing benchmark**.
Starting weights are identical across all periods, frequencies and costs.

- [All three periods and four costs](report.md).
- [Full-precision results, alpha and betas](report.json).
- [Portfolio performance](performance.csv) and [matched QQQ/cash controls](controls.csv).
- [Saved-aggregate identity receipt](source_subset_audit.json) and [figure manifest](figures_manifest.json).
- [Strategy definitions](../../configs/selected_etf_strategies.json), [portfolio policy](../../configs/final_cap_rebalancing.json), [methods](../../docs/etf_methods.md) and [research scope/data sources](../../docs/etf_data_sources.md).

The publication has **36 portfolio-cost-period rows** and **15 distinct controls**.
These are unchanged completed results, not a new fit, account replay or selection
exercise. The research scope and report terminology have been made consistent;
earlier snapshots are retained privately rather than mixed into this tree.

## Corrections and costs

At 17:00 New York on the last actual trading session of the ISO week or calendar
month, only an account-capital share above one-third queues a correction. It
executes at the next jointly eligible native bar open, after original actions,
dividend reinvestment and normal strategy fills. If the breach vanished, cancel.
Trim oversized accounts and redistribute proportionally to others' current
capital, respecting ETF/cash signals—not by restoring initial target weights.

A correction may move only cash and create no ETF order. Partial orders are not
extra completed strategy round trips. Direct cap costs mean cap-order fees and
slippage, not the total cost/return difference from no rebalancing. Paid normal,
cap and terminal ETF orders bear the stated costs; internal cash transfers and
the inherited fee-free dividend-reinvestment proxy do not. Cash earns 3% nominal
ACT/365 event-compounded; taxes and additional market impact are not modeled.

**The cap is not continuous or guaranteed at every daily close.** Between-check
drift and overnight gaps remain possible. It measures whole sleeve capital
including cash, not ETF exposure or risk contribution.

## Baseline equity and drawdown

Every panel starts from **$1,000** and uses **1-bp commission plus 3-bp slippage
each way**. The four curves are the Initial comparator, Weekly corrections,
Monthly corrections and QQQ buy-and-hold. Numerical daily paths remain private.

![Development: portfolio policies and QQQ](development_baseline.png)

![Validation: portfolio policies and QQQ](validation_baseline.png)

![Historical OOS: portfolio policies and QQQ](historical_OOS_baseline.png)

## Evidence boundary

This is **retrospective**, previously examined research—not untouched portfolio
OOS, an optimal-frequency claim or live trading instructions. The strategy and
portfolio accounts were independently audited before the publication cleanup.
Portable checks pin financial aggregates, configuration, rendered tables and
raster metadata; they do not reconstruct unavailable source data from a hash.
Exact financial reproduction requires the privately retained authenticated
input/event/account records. No underlying numerical daily series is published.
