# Trend Following and Mean Reversion ETF Portfolios

- This repository is the separate public portfolio-analysis snapshot requested
  for `Agul-quant/Trend-following-mean-reversal-portfolio`. Do not redirect its
  commits into the original strategy-study repository or import unrelated studies.
- Preserve the published strategy IDs, exact saved portfolio weights and historical
  aggregate outcomes. A new calculation or correction must be labeled explicitly;
  do not silently replace a historical result with a new optimizer solution.
- Public project name: **Trend Following and Mean Reversion ETF Portfolios**, without a version label.
- No raw market data, full daily account paths, credentials, private source maps,
  authorization records, caches or study freezes belong in Git. Use explicit file
  allowlists when staging. Public exports must be aggregate-only and portable.
  User-requested raster charts may visualize saved paths, but must not embed
  numerical daily series or private input locators in metadata or vector files.
- The selected ETF portfolio is retrospective: configurations, pruning and
  weights used the examined 2024–2026 history. It is not untouched portfolio OOS,
  a live allocation or trading authorization.
- Mix normalized sleeve **wealth**, not returns at constant daily weights. The
  current historical cap is on daily sleeve capital shares across four cost
  scenarios, without rebalancing; it is not a future or intraday guarantee.
- Run tests before committing. Keep saved results auditable; generic optimizer
  reruns are best-found research experiments, not replacements for saved weights.
- Verify the origin push URL before every push. Never force-push without explicit
  authorization. Local Python: `~/.venvs/myenv/bin/python` when available.

- Active final basket: GDX, FXI, QQQ, UNG and FDN; no bond ETFs. The final
  FOUR portfolios are Daily cap, Initial cap, Uncapped and Equal initial,
  defined in configs/final_no_bond_portfolios.json. Weekly/Monthly cap fits
  are excluded from the active publication and retained only in the archive.
  Keep the same saved full-precision weights; this is a result subset, not a refit.
  Development 2017–2020, validation 2021–2023 and historical OOS
  2024-01-01–2026-10-15 remain unchanged, all four costs, no rebalancing.
  All prior financial sources, six-model no-bond results and original class
  reports remain unchanged archives. Maximum CAGR stays excluded; corrected-split
  work stays inactive. Completed fits are verification/report-only.
