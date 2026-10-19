# Reproducibility and publication boundary

## Two different levels of reproduction

1. **Public, no market data needed:** install the package, run synthetic unit
   tests and inspect the committed full-precision configuration, aggregate metric,
   correlation and regression tables. The synthetic data test the formulas and
   input rejection behavior; they are explicitly not market performance evidence.
2. **Private historical-account recomputation:** supply the saved normalized
   daily strategy equity, cost-matched passive buy-and-hold returns, actual cash
   returns and aligned timestamps described in [input_schema.md](input_schema.md).
   Evaluate the committed full-precision weights. This recomputes the portfolio
   layer; it does not rerun the underlying intraday strategies or raw-data QA.

Raw market captures, daily account paths, private reconciliation evidence,
authorization receipts and frozen studies are intentionally absent from Git.
Aggregate outputs alone cannot regenerate those inputs or reconstruct trades.
The public calculation code is a new portable implementation of the disclosed
math, not a copied private account engine.

## Snapshot lineage

The public provenance file in `results/` identifies private parent artifacts by
logical role and SHA-256 only. Those hashes permit the source holder to match an
unchanged saved calculation; they are not a public link to the underlying files,
independent proof that data are correct, or permission to use an unseen dataset.
The export utility accepts an explicitly supplied private source manifest and
emits only allowlisted definitions and aggregate fields. It does not serialize
that manifest's local paths, full private source maps, authorization records or
daily observations.

Publication is a separate, explicitly requested snapshot. Historical flags saying
“no publication performed” in older private results describe their creation-time
scope; they are not rewritten or exported as current authorization.

## Verification required for this initial snapshot

- Match selected6 definitions and five full-precision weight vectors to their
  immutable saved results; retain all four fixed cost scenarios.
- Check the saved result/receipt hashes before exporting. Keep private filenames,
  paths and receipt payloads out of the public export.
- Independently recompute saved-weight wealth, returns, Sharpe, ACT/365 CAGR,
  daily drawdown and regressions from private saved arrays locally; compare them
  with committed aggregates within numerical tolerance.
- Validate all public table dimensions and numerical consistency in tests.
- Run portable synthetic tests without private files, network, credentials or a
  market downloader. No automatic strategy evaluation or trading occurs in CI.
- Scan the exact staged file list for private absolute paths, secrets, price
  captures and daily account paths. Verify the new repository's push destination.

The resulting verification summary records checks actually completed, not merely
expected counts. Independent original audits and portable recomputation validate
arithmetic on saved paths; they do not undo hindsight selection, certify a
future cap, establish a global Sharpe optimum or demonstrate forward profitability.

## Updating later

Keep this snapshot's identities and results identifiable. New dates, revised
market inputs, changed strategies or new weight searches require a separately
labeled research release and fresh provenance; do not overwrite this history
silently. No scheduled downloads, queue changes, live orders or new-stage
evaluation are authorized by this repository's existence.
