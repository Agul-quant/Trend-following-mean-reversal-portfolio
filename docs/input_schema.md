# Private saved-path input contract

The public repository contains aggregate historical results and synthetic tests,
not licensed market bars or full derived daily account paths. Reproducing the
historical numbers requires the exact private, reconciled saved-path bundle.
This interface analyzes saved paths; it does not reconstruct indicators, fills,
corporate actions, reinvestment or trading ledgers from market data.

Use an NPZ created without Python objects; loading uses `allow_pickle=False`.
Put private bundles outside this checkout, or under an ignored `private/` folder.

| Key | Shape | Meaning |
| --- | --- | --- |
| `timestamps` | `(T,)`, Unicode | Strictly increasing, unique ISO-8601 daily valuation timestamps with explicit UTC offsets; all arrays share this axis |
| `symbols` | `(S,)`, Unicode | Unique ordered sleeve symbols, also the passive BH factor order |
| `slippage_bps` | `(C,)` | Unique one-way slippage values; the saved paths already include all agreed commission/slippage each way |
| `sleeve_normalized_equity` | `(C,T,S)` | Net saved sleeve wealth divided by its original stage capital ($1,000 in the historical study), strictly positive |
| `buy_and_hold_returns` | `(C,T,S)` | Net **passive cost-matched buy-and-hold** simple returns, not active sleeve returns |
| `cash_returns` | `(T,)` or `(C,T)` | Actual matched event-compounded nominal ACT/365 cash return for every valuation interval |

The initial normalized wealth **before the first saved valuation is 1**, so
`E[0] - 1` is the first return. Include the paid terminal liquidation valuation.
Do not omit the first observation, align data by row count alone, substitute an
APY-based daily cash constant, splice account stages, or interpolate missing bars.
The portable adapter validates array shapes/finite values and timestamp order;
it cannot certify the private bundle's economic lineage, calendar completeness,
price units, matching costs or corporate-action treatment.

Supply the actual elapsed ACT/365 years separately. The published historical
window uses `2.787043378995434`, measured from 2024-01-02 14:30 UTC to
2026-10-15 21:00 UTC. Sharpe instead uses the study's 252-observation convention.

Portfolio definitions can be `{ "portfolios": [{"id": "example",
"initial_weights": {"GDX": 0.5, "QQQ": 0.5}}] }`, or an id-to-definition mapping.
Every mapping must contain exactly the input symbols, use nonnegative weights,
and sum to one. Positional lists are supported, but symbol mappings are safer.

```bash
python scripts/analyze_portfolios.py \
  --input /outside/checkout/private_bundle.npz \
  --portfolios configs/portfolios.json \
  --years 2.787043378995434 \
  --output private/recomputed_aggregate.json
```

The output contains only aggregate metrics, coefficients, correlations and
capital-share diagnostics. It never serializes private input paths or daily
arrays. Existing output files are not overwritten. Undefined zero-variance
Sharpe/correlations are JSON `null`, not zero. The metric function treats daily
excess-return standard deviation at or below 64 machine epsilons (about
1.42e-14 for ordinary return scales) as numerical zero, avoiding cash-path
roundoff masquerading as a finite Sharpe.

## Optional explicit retrospective refits

Add `--optimize uncapped`, `--optimize initial-cap`, `--optimize daily-cap`, or
`--optimize max-cagr`. The baseline defaults to 3-bp slippage. It is fitted once;
those same weights are evaluated at every other input cost. Default Sharpe
search: deterministic seed 1729, 12 LP starts plus feasible equal allocation,
multi-start SLSQP. This is a **best-found numerical search**, not the exact
historical audit's full search schedule, nor a globally certified optimum.

Daily-cap fitting constrains initial and every supplied historical daily sleeve
capital share, across **all input costs**, to one third by default. It does not
rebalance, enforce an intraday cap or guarantee a future cap. `max-cagr` is the
exact uncapped static-simplex terminal-wealth vertex; it does not impose the cap.
The caller must supply the intended full cost set. No refit is automatic.

Run synthetic tests with `python -m pytest -q`; they do not use private data and
are not evidence of out-of-sample investment performance.
