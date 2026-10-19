> **Historical four-portfolio class reports.** These retain the original six-sleeve results unchanged. The active final set excludes all bond ETFs; see the [new five-ETF reports](../reports/final_no_bond_portfolios/README.md).

# Class project reports

The earlier study is restored as the active report basis. All three reports use
**the same four saved allocations and six fixed strategy definitions**, not the
inactive corrected-split experiment. The standalone maximum-CAGR 100%-GDX strategy
portfolio is excluded; GDX remains a sleeve in the retained mixtures.

| Report | Scored period | Daily observations | PDF | Offline HTML |
|---|---|---:|---|---|
| Development and robustness | 2017-01-01 to 2020-12-31 | 1,007 | [10 pages](01_development/01_development_and_robustness.pdf) | [Open or download](01_development/01_development_and_robustness.html) |
| Validation and frozen selection | 2021-01-01 to 2023-12-31 | 753 | [10 pages](02_validation/02_validation_and_frozen_selection.pdf) | [Open or download](02_validation/02_validation_and_frozen_selection.html) |
| Historical OOS and conclusions | 2024-01-01 to 2026-10-15 | 700 | [11 pages](03_historical_oos/03_historical_oos_and_conclusions.pdf) | [Open or download](03_historical_oos/03_historical_oos_and_conclusions.html) |

The seven-part course structure covers the project goal, research outline, data,
backtesting, execution and slippage, weighting and performance evaluation. The
presentation follows the [cryptocurrency class-project reports](https://github.com/Agul-quant/Cryptocurrency-statistical-arbitrage/tree/5d4fb259b0ca3d448bb6a55d09445063d1f48add/final_reports),
not their trading rules, cost assumptions, data or numerical outcomes.

Every period includes 16 portfolio-cost outcomes, eight matched QQQ/cash controls,
16 capital-share diagnostics, 16 QQQ-only and 16 joint-six-passive-ETF regressions,
and four factor-overlap diagnostic rows. The historical OOS report also includes
the saved six-strategy baseline correlation heatmap. Full-precision CSV and JSON
are beside each PDF/HTML; stage manifests bind them to the saved public sources.
All use 1-bp commission plus 1/3/10/25-bp one-way slippage, charged each way.

## How to read these results

Configurations, pruning and portfolio weights used already examined historical
OOS. The earlier-period applications are retrospective diagnostics; these are
**not untouched portfolio development, validation or OOS tests**. Stage accounts
start independently at $1,000 with the matched cash path. The allocation called
“daily cap fit” is not a rebalancing rule or a future guarantee: it breaches
one-third in validation, peaking at 35.18% in UNG on a path with 41 breach days at
every cost. Unsuccessful results and undefined cash Sharpe are retained.

## Complete project and code supplement

- [Word class project](class_project/Trend_Following_Study_Class_Project.docx): the previously verified 19-page combined project.
- [Reproducibility supplement](class_project/Trend_Following_Study_Reproducibility.zip): portable code, exact definitions/weights, aggregate tables, figures and synthetic tests; no raw data or full numerical daily paths.
- [Course coverage and method mapping](../docs/class_project_reports.md).
- [Dataset specification and private-data boundary](../docs/data_sources.md).

Download an HTML file using GitHub's raw/download action and open it in a browser.
It runs offline, uses no JavaScript or CDN, and embeds the approved PNG figures.
The PDF is printed from that exact same HTML source. On small screens, wide
tables scroll inside their own container rather than widening the page.

## Verification and reproduction

```bash
python scripts/verify_project.py
python scripts/build_final_reports.py --output-dir outputs/new_report_attempt
npm install
npx playwright install chromium
node scripts/render_final_reports.cjs --reports outputs/new_report_attempt
```

Run these commands from the repository root. PDF rendering can instead use an
existing compatible Chromium by setting `CHROMIUM_EXECUTABLE_PATH`; the render
receipt records the actual browser and Playwright versions. The delivered PDFs
were rendered with Chromium 145 and Playwright 1.62.1, with all network requests
blocked. PDF metadata can vary by renderer/platform; the saved HTML and aggregate
source hashes are the canonical content bindings.

The public verification and report build need no market data or API key. They do
not rerun the original indicators/trades, refit portfolios, refresh prices or
reproduce historical accounts from aggregates. Private saved account inputs are
required for numerical path/statistic recomputation. The [root publication manifest](../metadata/project_manifest.json),
[HTML/data manifest](manifest.json) and [same-HTML PDF receipt](render_manifest.json)
provide the shipped file checksums.
