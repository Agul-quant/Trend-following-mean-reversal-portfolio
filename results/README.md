# Saved aggregate results

Historical window **2024-01-01–2026-10-15**; 700 common daily observations from
January 2, 2024. Baseline means 1-bp commission + 3-bp slippage **each way**.
Rates in CSVs are decimals (0.20 = 20%), drawdowns are signed negative values,
and trades are completed round trips including paid terminal liquidation.

**All of these comparisons are hindsight-conditioned.** The six configurations
and portfolio weights were selected after examining this history. These are
saved descriptive results, not newly untouched portfolio OOS or forward advice.

## Selected active strategies versus their own passive ETF — baseline

| ETF | Strategy Sharpe | Strategy CAGR | Strategy daily max DD | Strategy round trips | BH Sharpe | BH CAGR | BH daily max DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| GDX | 1.8186 | 35.33% | -6.59% | 12 | 1.0583 | 45.63% | -38.93% |
| FXI | 1.3778 | 20.62% | -6.79% | 7 | 0.5927 | 16.62% | -23.24% |
| QQQ | 1.1154 | 23.09% | -13.56% | 3 | 0.9959 | 23.93% | -22.77% |
| UNG | 1.0795 | 18.34% | -13.79% | 3 | -0.1450 | -20.42% | -64.70% |
| FDN | 0.9382 | 18.08% | -12.94% | 9 | 0.7351 | 18.09% | -24.98% |
| BND | 0.8433 | 3.44% | -0.30% | 1 | -0.0756 | 2.56% | -4.74% |

BH is ETF-specific cost-matched buy-and-hold. Both Sharpe columns subtract the
matched study cash return; neither is a Sharpe of active returns versus BH.
QQQ's saved legacy trade count is domain-checked, not independently rebuilt from
an event ledger. The EMA50→EMA200 QQQ representative is retained unchanged;
SMA50→EMA200 was an exact baseline Sharpe/CAGR tie, not a proven inferior choice.
The BND sleeve is mostly cash, not continuous passive bond exposure.

## Active-strategy daily net-return correlations — baseline

| ETF | GDX | FXI | QQQ | UNG | FDN | BND |
|---|---:|---:|---:|---:|---:|---:|
| GDX | 1.0000 | 0.1390 | 0.1427 | -0.0632 | 0.0870 | 0.0974 |
| FXI | 0.1390 | 1.0000 | 0.1256 | 0.0070 | 0.0705 | 0.0245 |
| QQQ | 0.1427 | 0.1256 | 1.0000 | 0.0067 | 0.6499 | -0.0278 |
| UNG | -0.0632 | 0.0070 | 0.0067 | 1.0000 | -0.0509 | 0.0061 |
| FDN | 0.0870 | 0.0705 | 0.6499 | -0.0509 | 1.0000 | 0.0172 |
| BND | 0.0974 | 0.0245 | -0.0278 | 0.0061 | 0.0172 | 1.0000 |

These correlations use all aligned active-account returns, including flat/cash
intervals. They are not intraday holding correlations or the passive-factor
matrix used in the regressions. All four costs appear in the machine tables.

## Joint passive-ETF attribution — baseline

Each joint beta controls for the other five passive ETF factors. Alpha is the
arithmetic annualization `252 × daily intercept`, **not CAGR**. Coefficients
are not allocation weights; a negative beta is not a short holding.

| Portfolio | GDX beta | FXI beta | QQQ beta | UNG beta | FDN beta | BND beta | Annual alpha | R² |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Daily-capped max-Sharpe mix — current choice | 0.0366 | 0.0369 | 0.0746 | 0.0090 | 0.0516 | -0.0169 | 12.59%/year | 31.37% |
| Initial-only capped max-Sharpe mix — comparison | 0.0432 | 0.0401 | 0.0818 | 0.0097 | 0.0572 | -0.0172 | 14.31%/year | 30.72% |
| Uncapped max-Sharpe mix | 0.0074 | 0.0076 | 0.0146 | 0.0018 | 0.0102 | 0.0027 | 2.77%/year | 27.94% |
| Equal initial allocation, six strategies | 0.0276 | 0.0183 | 0.1421 | 0.0043 | 0.0924 | 0.0151 | 10.08%/year | 56.43% |
| Uncapped maximum-CAGR: 100% GDX strategy | 0.1366 | -0.0077 | 0.0325 | -0.0105 | 0.0061 | 0.1226 | 22.00%/year | 14.62% |

At baseline the factor design has rank 7 including the intercept. Passive QQQ/FDN
cash-excess correlation is 0.829; their VIFs are 3.438 and 3.218. Attribution
is conditional on this non-exhaustive ETF factor set, not a causal risk model or
proof of skill. Adding factors can increase in-sample R² without predictive gain.

## Machine-readable tables

All scenario weights remain the same baseline-selected values. Each slippage
scenario also has its own cost-matched passive factors.

| File | Rows | Contents |
|---|---:|---|
| [portfolio_metrics_all_costs.csv](portfolio_metrics_all_costs.csv) | 20 | Five portfolios × four costs; net Sharpe/CAGR/DD, volatility, terminal value, max sleeve share |
| [portfolio_capital_drift_all_costs.csv](portfolio_capital_drift_all_costs.csv) | 120 | Initial/terminal/max daily sleeve-capital shares |
| [strategy_metrics_all_costs.csv](strategy_metrics_all_costs.csv) | 24 | Six selected active strategies × four costs, including trades/fills |
| [own_ETF_buy_and_hold_metrics_all_costs.csv](own_ETF_buy_and_hold_metrics_all_costs.csv) | 24 | Matched own-ETF passive controls |
| [strategy_correlation_matrices_all_costs.csv](strategy_correlation_matrices_all_costs.csv) | 24 | Four 6×6 daily active net-return correlation matrices |
| [strategy_correlation_pairs_all_costs.csv](strategy_correlation_pairs_all_costs.csv) | 60 | Fifteen unique ETF pairs × four costs |
| [QQQ_single_factor_portfolios_all_costs.csv](QQQ_single_factor_portfolios_all_costs.csv) | 20 | Portfolio alpha/beta versus passive QQQ only |
| [QQQ_single_factor_strategy_sleeves_all_costs.csv](QQQ_single_factor_strategy_sleeves_all_costs.csv) | 24 | Active-strategy alpha/beta versus passive QQQ only |
| [six_factor_portfolios_all_costs.csv](six_factor_portfolios_all_costs.csv) | 20 | Joint six-passive-ETF portfolio attribution |
| [six_factor_strategy_sleeves_all_costs.csv](six_factor_strategy_sleeves_all_costs.csv) | 24 | Supplementary active-strategy joint attribution |
| [pairwise_portfolio_betas_all_costs.csv](pairwise_portfolio_betas_all_costs.csv) | 120 | Separate one-passive-ETF-at-a-time portfolio fits |
| [pairwise_strategy_sleeve_betas_all_costs.csv](pairwise_strategy_sleeve_betas_all_costs.csv) | 144 | Separate active-strategy versus passive-ETF fits |

[Factor diagnostics](six_factor_diagnostics.json) report all-cost conditioning,
VIF and passive-factor correlations. [Provenance](provenance.json) contains only
logical parent receipt hashes, not private source maps.
[Verification](verification.json) records completed saved-path cross-checks;
[export_manifest.json](export_manifest.json) hashes the 18 payload files emitted
by the aggregate exporter (the manifest itself is its nineteenth output).
Documentation and portable source files are outside that export-only map.

See [methodology](../docs/methodology.md) for portfolio accounting and limitations,
and [reproducibility](../docs/reproducibility.md) for the boundary between public
synthetic/aggregate checks and private historical-account recomputation.
