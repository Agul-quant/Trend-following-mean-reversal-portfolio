# Initial snapshot verification

These checks apply to the initial six-ETF portfolio publication. They verify
saved-account arithmetic and the sanitized snapshot, **not** a fresh strategy
backtest, raw-data certification, global Sharpe optimum or forward performance.

## Local runtime

| Component | Tested version |
|---|---|
| Python | 3.12.11 |
| NumPy | 2.4.6 |
| SciPy | 1.15.3 |
| pytest | 9.0.3 |

The package has an editable-install and CLI-help smoke check. CI is configured
for public-only tests on Python 3.10 and 3.12; this document records the local
run, not an assertion that a hosted CI run has already completed.

## Completed historical-account checks

- The aggregate exporter verified six fixed parent delivery receipts and
  rehashed **508** private source bindings unchanged. It independently checked
  metrics, correlations and regression coefficients against saved private paths.
  Maximum absolute saved-value/arithmetic difference: **4.53 × 10⁻¹³** (rounded
  upward). See [the machine summary](../results/verification.json).
- A separate portable-function roundtrip reproduced all **20 portfolio/cost
  performance rows**, **20 joint regressions** and **120 pairwise regressions**.
  Wealth, returns, primary metrics, betas and alpha matched exactly in the local
  runtime; the maximum R² difference was 2.23 × 10⁻¹⁶ (rounded upward).
- A full CLI roundtrip loaded the committed five allocations and a temporary
  private adapter bundle, aligned timestamps/symbols, and reproduced all
  **20 joint and 120 pairwise fits** within 10⁻¹² absolute tolerance. The temporary
  bundle was deleted. Its aggregate output contained no private input locator or
  daily array.
- All **16,800** historical daily capital-share inequalities for the chosen
  one-third-capped portfolio passed across all four costs. Initial weights also
  passed. This does not test intraday or future caps.
- All **72** original frozen production/configuration source hashes remained
  unchanged. No original study account was rerun or modified.

## Public-only checks

**69 tests passed locally:** 40 portable synthetic/CLI tests and 29 public
aggregate, export-guard and table-consistency tests. Two local re-export
verifications also produced byte-identical aggregate snapshots.

The synthetic suite tests initial-wealth mixing versus daily rebalancing, the
first return, initial-balance drawdown, actual-cash subtraction, sample standard
deviation, invalid inputs, undefined no-trade Sharpe, cap drift/all-cost
constraints, known joint and pairwise regressions, rank rejection, factor
conditioning, deterministic optimizer behavior and final-weight feasibility.

Public aggregate tests verify the export map, hashes, definitions/weights,
dimensions, cost/identity coverage, correlation matrices, attribution consistency
and arithmetic cross-links without opening private files or using the network.
An independent reviewer also matched **171** human-readable numerical/count
cells in the main and results READMEs to the committed aggregate candidates.

The publication boundary excludes market captures, daily account paths, private
source maps, receipt payloads, credentials and local absolute paths. Review the
exact staged files—not a broad copy of the original research directory—before
any future commit. Synthetic tests and public checks cannot establish the unseen
input data's lineage by themselves; see [reproducibility](reproducibility.md).

## Baseline chart follow-up

The README now includes net equity and daily-drawdown PNGs for all five fixed
portfolios and passive QQQ at 1-bp commission plus 3-bp slippage each way.
The renderer uses all 700 daily observations plus the initial $1,000 point
(701 plotted points per series); it performs no strategy run or refit.

**84 tests passed locally**, including nine new synthetic plot tests and six
private-input-free chart-asset tests. The six chart summaries match the original
baseline aggregates within **2.00 × 10⁻¹⁴** absolute difference. The original
18 aggregate payloads, portfolio weights and frozen research sources remain
unchanged. Source checks independently confirm that the QQQ curve is the matched
passive control rather than the active strategy.

Both 1920×1152 PNGs and 900-pixel-wide README previews were visually inspected.
PNG chunks/metadata were checked for private paths or hidden daily arrays;
only a generic software label and resolution information are present.
The new renderer used Matplotlib **3.10.8**. See the
[chart manifest](../assets/baseline_charts_manifest.json) for image, generator,
configuration and private-input hashes, and [charts.md](charts.md) for reproduction.
