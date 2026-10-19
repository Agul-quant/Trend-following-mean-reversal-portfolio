# Trend Following Study — portfolio research

- This repository is the separate public portfolio-analysis snapshot requested
  for `Agul-quant/Trend-following-mean-reversal-portfolio`. Do not redirect its
  commits into the original strategy-study repository or import unrelated studies.
- Preserve the published strategy IDs, exact saved portfolio weights and historical
  aggregate outcomes. A new calculation or correction must be labeled explicitly;
  do not silently replace a historical result with a new optimizer solution.
- Public project name: **Trend Following Study**, without a version label.
- No raw market data, full daily account paths, credentials, private source maps,
  authorization records, caches or study freezes belong in Git. Use explicit file
  allowlists when staging. Public exports must be aggregate-only and portable.
  User-requested raster charts may visualize saved paths, but must not embed
  numerical daily series or private input locators in metadata or vector files.
- The selected six-ETF portfolio is retrospective: configurations, pruning and
  weights used the examined 2024–2026 history. It is not untouched portfolio OOS,
  a live allocation or trading authorization.
- Mix normalized sleeve **wealth**, not returns at constant daily weights. The
  current historical cap is on daily sleeve capital shares across four cost
  scenarios, without rebalancing; it is not a future or intraday guarantee.
- Run tests before committing. Keep saved results auditable; generic optimizer
  reruns are best-found research experiments, not replacements for saved weights.
- Verify the origin push URL before every push. Never force-push without explicit
  authorization. Local Python: `~/.venvs/myenv/bin/python` when available.
