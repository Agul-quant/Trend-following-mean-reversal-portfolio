# Trend Following and Mean Reversion ETF Portfolios

- This repository is the separate public portfolio-analysis snapshot requested
  for `Agul-quant/Trend-following-mean-reversal-portfolio`. Do not redirect its
  commits into the original strategy-study repository or import unrelated studies.
- Preserve the published strategy IDs, exact saved portfolio weights and historical
  aggregate outcomes. A new calculation or correction must be labeled explicitly;
  do not silently replace a historical result with a new optimizer solution.
- Public project name: **Trend Following and Mean Reversion ETF Portfolios**, without a version label.
- Raw ETF data, sleeve-level account/position paths, credentials, private source
  maps, authorization receipts, caches and historical private freezes stay out
  of Git. The user explicitly authorized publication of derived aggregate daily
  portfolio, QQQ benchmark and modeled cash RETURNS, plus portable verification.
  This narrow exception does not authorize raw OHLCV, fills or private locators.
  Use explicit staging allowlists. The separately authorized public forward
  portfolio protocol/hash seal contains rules and public source hashes only.
- The selected ETF portfolio is retrospective: configurations, pruning and
  weights used the examined 2024–2026 history. It is not untouched portfolio OOS,
  a live allocation or trading authorization.
- Preserve the distinct accounting models: the static benchmark mixes normalized
  sleeve wealth once; actual cap corrections use the costed canonical-event
  ledger. Never approximate rebalancing by free constant-weight return mixing.
- Run tests before committing. Keep saved results auditable; generic optimizer
  reruns are research experiments, not replacements for saved weights.
- Verify the origin push URL before every push. Never force-push without explicit
  authorization. Local Python: `~/.venvs/myenv/bin/python` when available.

- Active final basket: GDX, FXI, QQQ, UNG and FDN. Current models
  are Weekly corrections, Monthly corrections and the Initial allocation /
  no-rebalancing comparator. Daily corrections are excluded from active results,
  tables and charts. Generic engine support for other frequencies is not an
  active portfolio definition.
- Use configs/final_cap_rebalancing.json and reports/etf_portfolios.
  Starting weights are the exact saved Initial cap vector, unchanged across
  costs, frequencies and all three periods. Do not refit or rerun completed
  accounts when filtering/reporting. Next-eligible-open corrections enforce a
  post-cost sleeve-capital cap, not a continuous or daily-closing guarantee.
- Development 2017–2020, validation 2021–2023 and historical OOS
  2024-01-01–2026-10-15 remain unchanged, all four costs. No date extension,
  live trading, leverage or shorting is implied. Results remain retrospective.
- The published research scope is the exact 47-product list in
  configs/etf_universe.json. Exact five selected definitions are in
  configs/selected_etf_strategies.json. Use neutral ETF labels throughout.
- Earlier snapshots, source identifiers, definitions, account paths and aggregate
  results remain byte-preserved privately; do not rewrite them or turn scope
  cleanup into a new screening/optimization run. They are not current public
  dependencies. Do not reintroduce withdrawn snapshots into the public tree.
- Current report/metadata scope is 36 portfolio-cost-period results and 15
  distinct controls, across unchanged three periods and four costs. Validate
  with scripts/verify_etf_publication.py and scripts/verify_publication.py.
- Maximum CAGR stays excluded; corrected-split work stays inactive. The
  unpublished broader correction source remains private and is not committed.

- **Forward paper portfolio, explicitly chosen by the user:** Initial allocation,
  no rebalancing; exact existing five definitions and starting weights. Weekly
  and Monthly corrections remain historical comparisons, not candidate forward
  winners. Follow configs/paper_portfolio_freeze.json and docs/paper_tracking.md.
  Never backdate the actual freeze, change the frozen model, refit, splice
  historical holdings or terminally liquidate at every monitoring update.
  Fresh flat $1,000 paper accounts per cost start only at the sealed future open.
  Missing/unreconciled inputs block tracking; never fabricate paper returns.
  Revised consumed evidence requires quarantine and a disclosed correction, not
  silent history replacement. Paper tracking never authorizes broker orders.
- The internal historical_OOS ID is preserved for compatibility, but every
  reader-facing 2024–2026 portfolio result must be labeled retrospective
  portfolio-selection / in-sample. Earlier portfolio backcasts also inherit
  hindsight selection. Daily-return verification reproduces summary statistics,
  not the private market-data-to-signal audit or selection-adjusted inference.
