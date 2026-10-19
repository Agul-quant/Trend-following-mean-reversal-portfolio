# Final four portfolios across five non-bond ETFs

The active strategies are **GDX, FXI, QQQ, UNG and FDN**. Retain **Daily cap fit,
Initial cap fit, Uncapped fit and Equal initial**; remove the other two cap fits
from active tables, rankings, correlations and chart legends. The standalone
Maximum CAGR allocation remains excluded. Strategy definitions, full-precision
weights, costs, clocks and saved outcomes are unchanged.

The [current report index](../reports/final_no_bond_portfolios/README.md) covers
2017–2020 development, 2021–2023 validation and historical OOS from 2024 through
October 15, 2026. All four one-way slippages—1, 3, 10 and 25 bps—add 1-bp commission
each way. Each period starts independently at $1,000. Cash remains 3% nominal
ACT/365 event-compounded, not 3% APY. No numerical daily arrays are public.

## Exact saved-result subset

The complete [six-allocation source](../reports/no_bond_portfolios/report.json)
is an immutable historical archive. Its full SHA256 is
`55010e543ec1af7210b24b4b2d2794d0b40c85e67541241ba058e97f85ae9239`.
The final [four-portfolio JSON](../reports/final_no_bond_portfolios/report.json)
retains exactly the corresponding source rows and weight dictionaries. It
contains 48 portfolio, 24 control, 48 daily-cap diagnostic, 48 QQQ-only regression
and 48 joint-five-passive-factor regression outcomes. The 12 strategy correlation
matrices remain unchanged. Each of the 12 portfolio/QQQ correlation matrices is
the literal five-series submatrix for the four retained portfolios plus QQQ.
Three original solver summaries remain unchanged, not rerun.

No optimizer, market-data download, account evaluation, dividend reconciliation,
new model selection or future-stage extension was performed. The
[independent audit](../reports/final_no_bond_portfolios/independent_audit.json)
checks exact subsets, scopes, coefficients, matrix slicing and source hashes.
The earlier complete saved-path audit still supports all retained outcomes.
New raster figures remove inactive series and preserve initial $1,000, every
baseline daily observation and terminal values/drawdowns. PNGs contain no arrays.

## Capital and metrics

Capital is assigned once. Portfolio wealth is `sum(initial_weight * sleeve_wealth)`;
there is **no cross-sleeve rebalancing or free cash redistribution**. Sleeve shares
include idle cash. Daily cap fit constrained initial weights and all fitted
historical OOS daily shares to one-third across all costs. Initial cap applies
only at allocation; later drift is allowed. Uncapped and Equal initial have no
ongoing limit. Earlier-period breaches remain visible. None is a guarantee of
future or intraday concentration compliance.

Daily cash-excess Sharpe uses square-root-252 annualization and sample standard
deviation. CAGR uses exact first-open-to-terminal ACT/365 years. Maximum drawdown
includes initial capital and daily valuations, not intraday extremes. Cash Sharpe
is undefined. QQQ-only and joint-five-factor OLS use matched passive buy-and-hold
excess returns; alpha is 252 times the daily intercept, not CAGR or proof of skill.
BND is absent from active weights and factors; ordinary modeled idle cash remains.

These portfolios were fitted on already examined historical OOS. Backward replay
into development/validation is hindsight-conditioned, **not untouched portfolio
validation**. Fits remain best-found rather than globally certified, and no model
is authorized for live allocation or trading.

```bash
python scripts/verify_final_no_bond.py --report reports/final_no_bond_portfolios/report.json \
  --source-report reports/no_bond_portfolios/report.json
python scripts/build_final_no_bond_reports.py --report reports/final_no_bond_portfolios/report.json \
  --source-report reports/no_bond_portfolios/report.json \
  --figures-dir reports/final_no_bond_portfolios --output-dir outputs/final_no_bond_reports
```

The verifier checks saved aggregates without private inputs; the builder changes
presentation only. Do not rerun completed fits to regenerate these reports.
