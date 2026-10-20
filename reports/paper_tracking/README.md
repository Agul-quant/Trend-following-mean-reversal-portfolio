# Forward paper-tracking record

**Primary portfolio: Initial allocation; no rebalancing.**
Five fixed strategy sleeves: GDX, FXI, QQQ, UNG and FDN, at the exact saved
starting weights. No future refitting or switching to a historical cap-policy
winner is allowed. Four independent $1,000 accounts use the four fixed costs.

- [Public timestamped model freeze](../../configs/paper_portfolio_freeze.json).
- [Current machine-readable status](status.json).
- [Derived forward daily returns](daily_returns.csv)—header only until a
  complete, verified future session is accepted.
- [Protocol, data requirements and limitations](../../docs/paper_tracking.md).

The planned inception is **October 21, 2026, 09:30 America/New_York**. There are
**no accepted forward observations at publication**. Historical 2024–2026 results
are in-sample and do not enter this record. The inception is after the actual
October 20 freeze, not backdated to the historical research cutoff.

## Operational status

The standalone no-rebalancing engine and fail-closed update command are
implemented. **An automatic market-data collector / certified-packet producer
is not configured.** Scheduled checks consume an existing private packet if
one is available; otherwise they report a data wait, not fabricated returns.
Weekday checks are scheduled for **18:15 America/New_York**; the local computer
and app must remain running. A scheduled check is not proof that the paper
account has received usable data.

The tracker accepts only full native 30-minute sessions with reconciled raw
price units, corporate actions and the full verified daily feature seed. Its
QA attestation is a trusted upstream input contract, not independent proof of
source reconciliation. No credentials, raw ETF data, per-sleeve positions or
trade ledgers are published.

Once observations exist, returns are **completed-day, fixed-rule modeled paper
accounting**, with actual observation/processing times retained. Late inputs
are disclosed as delayed reconstructions, not contemporaneously submitted
orders. Positions remain open at each update; there is no reporting-date
terminal liquidation and no broker connection.

## Local commands

From the repository root:

```bash
python -m pip install -e '.[paper]'
python scripts/run_paper_tracker.py --status-only
python scripts/run_paper_tracker.py
```

The default input and state locations are ignored local cache directories;
see the command's `--help` for overrides. Never put source packets in Git.
Missing data do not advance inception or count as successful paper days.
Revised consumed history or changed frozen sources is refused and quarantined.
Interrupted publication transactions fail closed and require review/recovery;
do not delete locks/journals or overwrite prior receipts merely to make a run
pass. No automatic commits, pushes or live orders are part of scheduled checks.
