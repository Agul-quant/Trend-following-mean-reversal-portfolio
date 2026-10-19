# Baseline equity and drawdown charts

The README figures compare the five **unchanged saved portfolio allocations**
with **passive QQQ buy-and-hold**, all at baseline 1-bp commission plus 3-bp
slippage each way. They are a visualization of the existing historical results,
not new optimizations, new strategy runs or an extension beyond October 15, 2026.

## Accounting

- All six curves start with $1,000 at the fresh account's January 2, 2024 open,
  before the first daily return. The figures then show all 700 saved daily
  valuations through October 15, 2026, including paid terminal liquidation.
- A portfolio's net equity is `$1,000 × sum(initial_weight × normalized_sleeve_equity)`.
  The selected weights stay fixed as **initial capital allocations**, not daily
  rebalance weights. Each underlying sleeve's cash accrual and trading costs
  are already embedded; neither cash nor costs are applied a second time.
- QQQ's curve is `$1,000 × cumulative_product(1 + matched_passive_QQQ_return)`.
  It uses the passive, cost-matched control, **not the active QQQ strategy** and
  not a newly downloaded market-price or gross index series.
- Drawdown is `equity / running_max_equity - 1`, including the initial $1,000
  in the running maximum. Each series has its own peak. The percent axis is
  signed, with zero at the top. This is daily, not intraday, drawdown.
- Linear dollar equity and signed-percentage drawdown use the same chronology.
  Initial entry costs, distributions, flat/cash intervals and final liquidation
  remain in the saved paths. There is no resampling, smoothing or new model fit.

The strategies, pruning and allocations were chosen after examining this
historical sample. The plots do not restore untouched OOS evidence or imply
future cap enforcement, forward profitability or significance.

## Reproduce with private saved inputs

Install the optional renderer and use the existing [private input contract](input_schema.md):

```bash
python -m pip install -e '.[plots]'
python scripts/plot_portfolios.py \
  --input private/portfolio_inputs.npz \
  --portfolios configs/portfolios.json \
  --initial-timestamp 2024-01-02T14:30:00+00:00 \
  --initial-capital 1000 \
  --baseline-slippage 3 \
  --commission-bps 1 \
  --output-dir outputs/baseline_charts
```

The source holder must supply the same privately retained input bundle; the
aggregate CSVs alone cannot reconstruct these curves. The renderer uses saved
net paths and cannot certify their raw-price lineage or that a caller's fee
labels match its inputs. It refuses to overwrite existing chart files.
Different renderer/font versions can change PNG bytes without changing the
underlying account calculations; the manifest records the generating runtime.

## Published boundary and verification

Only the two raster PNGs and [aggregate chart provenance](../assets/baseline_charts_manifest.json)
are published. There are no public numerical daily arrays, path CSVs, raw market
captures, SVG/vector point data, private source maps or input locators. PNG
metadata contains only a generic software marker and resolution information.
The images necessarily reveal the requested visual path shapes, but do not
bundle the private source accounts.

The chart manifest binds the PNG bytes, plotting code, public configuration and
private saved input hashes by logical role. It reports only aggregate checks and
six-series summary statistics. The original 19-file aggregate export and all
historical weights/results remain unchanged. Synthetic tests exercise chart
math and input rejection; local checks compare the historical terminal wealth,
CAGR, Sharpe and daily drawdown with the previously published aggregate rows.
Both full-size charts and their README-width renderings are visually inspected
before publication.
