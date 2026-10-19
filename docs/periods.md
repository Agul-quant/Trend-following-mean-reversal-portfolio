# Four fixed portfolios across the three study periods

`report_periods.py` compares **four unchanged saved allocations**, excluding the
standalone maximum-CAGR / 100%-GDX portfolio. GDX remains one of the six strategy
sleeves. This interface does not alter the original five-portfolio snapshot,
optimize weights, rerun the execution engine, or select new strategies.

## Required private inputs

Supply three standard private NPZ bundles from the [input schema](input_schema.md).
They must use ordered symbols `GDX, FXI, QQQ, UNG, FDN, BND` and ordered one-way
slippage costs `1, 3, 10, 25` bps; the saved paths already include 1-bp commission
each way. Every stage has its **own independently initialized $1,000 account**.
No development holdings, confirmation streaks, orders or account wealth may be
carried into validation or historical OOS. The private adapter/source audit—not
this aggregate interface—must certify those execution-engine properties and the
normalization of every saved account by its own original $1,000.

Create a private manifest, preferably outside the checkout:

```json
{
  "stages": {
    "development": {
      "input": "development_inputs.npz",
      "initial_timestamp": "2017-01-03T14:30:00+00:00",
      "scored_start": "2017-01-01",
      "scored_end": "2020-12-31"
    },
    "validation": {
      "input": "validation_inputs.npz",
      "initial_timestamp": "2021-01-04T14:30:00+00:00",
      "scored_start": "2021-01-01",
      "scored_end": "2023-12-31"
    },
    "historical_OOS": {
      "input": "historical_oos_inputs.npz",
      "initial_timestamp": "2024-01-02T14:30:00+00:00",
      "scored_start": "2024-01-01",
      "scored_end": "2026-10-15"
    }
  }
}
```

Bundle paths are resolved relative to the private manifest, unless absolute.
The manifest and numerical daily bundles must remain private. The explicit
four-portfolio configuration is a subset of the old saved allocations; it must
not silently replace or rewrite those historical definitions.

```bash
python scripts/report_periods.py \
  --manifest /outside/checkout/private_periods_manifest.json \
  --portfolios configs/four_portfolios.json \
  --output-dir outputs/new_three_period_report
```

The output directory must not already exist. It contains only `report.json` and
four aggregate CSVs: `stage_summaries`, `portfolio_rows`, `control_rows`, and
`cap_rows`. No private source path, manifest locator, input filename, numerical
daily array or trading ledger is serialized.

## Calculations and interpretation

- Allocate initial capital once and mix normalized saved **wealth**, not daily
  returns at constant weights. Each stage resets the portfolio to $1,000.
- Compute ACT/365 years independently for each stage from its actual first
  account-open timestamp to its final daily valuation. Never reuse OOS years or
  approximate years by observation count divided by 252.
- Include the initial-to-first return and paid terminal liquidation. Daily maximum
  drawdown includes the initial normalized wealth of 1 in its peak calculation.
- Cash-excess Sharpe is `sqrt(252) * mean(r - cash) / sample_std(r - cash)`, using
  each cost's actual matched cash-return path. Undefined numerical-zero-variance
  Sharpe is JSON `null` / an empty CSV field, not zero.
- Report both annualized raw-return and cash-excess volatility with sample standard
  deviation and the `sqrt(252)` observation convention. CAGR uses elapsed ACT/365
  years instead. No trading counts are inferred from portfolio weights.
- Cost-matched passive QQQ wealth is `cumprod(1 + saved_QQQ_BH_returns)`, not the
  active QQQ strategy path. Matched cash is a separate control. Costs and cash are
  not charged again by the reporting layer.
- Initial and daily one-third capital-share tests are **diagnostics only**. The
  OOS-fitted daily-cap allocation may breach its cap in an earlier period. Such
  breaches remain in the report; they do not cause refitting, rebalancing or
  deletion. The cap concerns sleeve-account capital, including idle cash—not ETF
  holdings, intraday weights or risk contributions.

The portable validator rejects unexpected stage IDs/windows, nonmatching symbol
or cost axes, nonfinite/invalid paths, duplicate/unsorted timestamps, and scored
numerical dates outside a stage. It cannot certify full exchange-calendar
coverage, price units, corporate actions or engine causality from these arrays.
Those remain prerequisites of the separate private input audit.

The strategies and allocations were chosen after examining historical outcomes.
Comparing those unchanged allocations against development and validation history
is a **retrospective diagnostic**, not a newly untouched stage release or evidence
of forward investment performance.
