"""Aggregate-only, three-stage evaluation of four UNCHANGED saved allocations.

This reports already saved, independently initialized sleeve accounts. It never
runs the strategy engine, stitches accounts, selects candidates or refits weights.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np

from .analytics import cap_diagnostics, checked_weights, metrics, portfolio_equity, returns_from_equity
from .cli import _json_safe, load_bundle, load_portfolios


STAGE_BOUNDS = {
    "development": ("2017-01-01", "2020-12-31"),
    "validation": ("2021-01-01", "2023-12-31"),
    "historical_OOS": ("2024-01-01", "2026-10-15"),
}
SYMBOLS = ("GDX", "FXI", "QQQ", "UNG", "FDN", "BND")
COSTS = (1.0, 3.0, 10.0, 25.0)


def _instant(value: Any) -> datetime:
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("stage timestamps must be ISO-8601 instants") from error
    if result.tzinfo is None:
        raise ValueError("stage timestamps must have explicit UTC offsets")
    return result.astimezone(timezone.utc)


def load_stage_manifest(path: Path) -> list[dict[str, Any]]:
    """Load a PRIVATE manifest. Locators are never copied into public reports.

    Format: {"stages": {"development": {"input": "...npz", ...}, ...}}.
    Paths may be absolute or relative to the private manifest's parent.
    """
    document = json.loads(Path(path).read_text())
    records = document.get("stages", document) if isinstance(document, dict) else None
    if not isinstance(records, dict) or set(records) != set(STAGE_BOUNDS):
        raise ValueError("manifest must contain exactly development, validation, historical_OOS")
    stages = []
    for identifier in STAGE_BOUNDS:
        record = records[identifier]
        if not isinstance(record, dict) or not isinstance(record.get("input"), str):
            raise ValueError("every stage needs a private input bundle path")
        source = Path(record["input"])
        if not source.is_absolute():
            source = Path(path).parent / source
        bundle = load_bundle(source)
        stages.append({"id": identifier, "bundle": bundle,
                       "initial_timestamp": record.get("initial_timestamp"),
                       "scored_start": record.get("scored_start"),
                       "scored_end": record.get("scored_end")})
    return stages


def _validated_stage(stage: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[datetime, ...], datetime, float]:
    identifier = stage.get("id")
    if identifier not in STAGE_BOUNDS:
        raise ValueError("unexpected stage id")
    expected_start, expected_end = STAGE_BOUNDS[identifier]
    if (stage.get("scored_start"), stage.get("scored_end")) != (expected_start, expected_end):
        raise ValueError("scored bounds must match the fixed authorized stage window")
    bundle = stage["bundle"]
    if tuple(np.asarray(bundle["symbols"]).astype(str)) != SYMBOLS:
        raise ValueError("every stage must use the identical ordered six-symbol universe")
    if tuple(np.asarray(bundle["slippage_bps"], dtype=float)) != COSTS:
        raise ValueError("every stage must use ordered slippage costs 1,3,10,25 bps")
    equity = np.asarray(bundle["sleeve_normalized_equity"], dtype=float)
    factors = np.asarray(bundle["buy_and_hold_returns"], dtype=float)
    if equity.ndim != 3 or equity.shape[0] != 4 or equity.shape[2] != 6 or equity.shape[1] < 2:
        raise ValueError("stage sleeve equity must have shape (4,time>=2,6)")
    if not np.isfinite(equity).all() or np.any(equity <= 0):
        raise ValueError("saved normalized equity must be finite and positive")
    if factors.shape != equity.shape or not np.isfinite(factors).all() or np.any(factors <= -1):
        raise ValueError("matched passive returns must share equity axes and be valid simple returns")
    cash = np.asarray(bundle["cash_returns"], dtype=float)
    if cash.shape == (equity.shape[1],):
        cash = np.broadcast_to(cash, equity.shape[:2])
    if cash.shape != equity.shape[:2] or not np.isfinite(cash).all() or np.any(cash <= -1):
        raise ValueError("cash paths must match every stage cost and daily valuation")
    timestamps = np.asarray(bundle["timestamps"])
    if timestamps.shape != (equity.shape[1],):
        raise ValueError("timestamps must match the daily valuation axis")
    times = tuple(_instant(value) for value in timestamps)
    initial = _instant(stage["initial_timestamp"])
    if initial >= times[0] or any(a >= b for a, b in zip(times, times[1:])):
        raise ValueError("independent stage initial must precede unique increasing daily valuations")
    lower, upper = date.fromisoformat(expected_start), date.fromisoformat(expected_end)
    if any(not lower <= value.date() <= upper for value in (initial, *times)):
        raise ValueError("stage contains out-of-bound numerical date leakage")
    years = (times[-1] - initial).total_seconds() / (365 * 86400)
    if not np.isfinite(years) or years <= 0:
        raise ValueError("stage ACT/365 elapsed years must be positive")
    return equity, factors, cash, times, initial, years


def _row_metrics(wealth: np.ndarray, cash: np.ndarray, years: float) -> dict[str, Any]:
    row = metrics(wealth, cash, years)
    returns = returns_from_equity(wealth)
    row.update({"annualized_return_volatility": float(np.std(returns, ddof=1) * np.sqrt(252)),
                "annualized_cash_excess_volatility": float(np.std(returns - cash, ddof=1) * np.sqrt(252)),
                "terminal_equity_from_1000": float(1000 * wealth[-1])})
    return row


def analyze_periods(stages: list[dict[str, Any]], portfolios: list[dict[str, Any]]) -> dict[str, Any]:
    """Return 48 portfolio rows, 24 control rows and 48 cap-diagnostic rows.

    All four saved allocations are evaluated unchanged, including cap breaches.
    Exactly zero-weight sleeves contribute no wealth. Tiny positive weights
    remain positive, matching the frozen allocations. No trade counts are inferred.
    """
    if len(stages) != 3 or {stage.get("id") for stage in stages} != set(STAGE_BOUNDS):
        raise ValueError("exactly the three fixed stages are required")
    if len(portfolios) != 4 or len({p.get("id") for p in portfolios}) != 4:
        raise ValueError("supply exactly four distinct fixed portfolio definitions")
    for portfolio in portfolios:
        if not isinstance(portfolio.get("id"), str) or not portfolio["id"]:
            raise ValueError("portfolio ids must be nonempty strings")
        if portfolio["id"] == "max_cagr_100pct_gdx":
            raise ValueError("the excluded standalone maximum-CAGR portfolio is not in this report")
        checked_weights(portfolio["initial_weights"], 6)
    by_stage = {stage["id"]: stage for stage in stages}
    report: dict[str, Any] = {
        "schema": "four_fixed_portfolios_three_periods_aggregate_v1",
        "method": "static initial sleeve capital; independent fresh $1000 per stage; no rebalancing or weight refit",
        "limitations": ["Retrospective selected strategies and OOS-fitted weights; not untouched portfolio OOS.",
                        "Daily cap is diagnostic only in these periods and may be breached; no cap enforcement or refitting.",
                        "Numerical input lineage and full trading calendar require separate private source audits."],
        "symbols": list(SYMBOLS), "slippage_bps_each_way": list(COSTS),
        "commission_bps_each_way": 1.0,
        "initial_capital_each_stage": 1000,
        "portfolios": [{"id": p["id"], "initial_weights": dict(zip(SYMBOLS, np.asarray(p["initial_weights"]).tolist()))}
                       for p in portfolios],
        "stage_summaries": [], "portfolio_rows": [], "control_rows": [], "cap_rows": [],
    }
    for identifier in STAGE_BOUNDS:
        stage = by_stage[identifier]
        equity, factors, cash, times, initial, years = _validated_stage(stage)
        summary = {"stage": identifier, "scored_start": stage["scored_start"], "scored_end": stage["scored_end"],
                   "initial_timestamp": initial.isoformat(), "first_daily_valuation": times[0].isoformat(),
                   "last_daily_valuation": times[-1].isoformat(), "elapsed_act365_years": years,
                   "observations": len(times), "fresh_initial_capital": 1000}
        report["stage_summaries"].append(summary)
        for portfolio in portfolios:
            weights = checked_weights(portfolio["initial_weights"], 6)
            wealth = portfolio_equity(equity, weights)
            for index, cost in enumerate(COSTS):
                identity = {"stage": identifier, "portfolio_id": portfolio["id"],
                            "slippage_bps_each_way": cost, "commission_bps_each_way": 1.0}
                report["portfolio_rows"].append({**identity, "elapsed_act365_years": years,
                                                 **_row_metrics(wealth[index], cash[index], years)})
                cap = cap_diagnostics(equity[index], weights)
                report["cap_rows"].append({**identity, "cap_fraction": cap["cap"],
                    "initial_cap_pass_diagnostic": cap["initial_cap_satisfied"],
                    "daily_cap_pass_diagnostic": cap["all_daily_cap_satisfied"],
                    "max_daily_capital_share": cap["max_daily_capital_share"],
                    "max_capital_share_including_initial": max(float(weights.max()), cap["max_daily_capital_share"]),
                    **{f"max_daily_share_{symbol}": value for symbol, value in zip(SYMBOLS, cap["max_daily_capital_share_by_sleeve"])}})
        for index, cost in enumerate(COSTS):
            for control, returns in (("QQQ_buy_and_hold", factors[index, :, SYMBOLS.index("QQQ")]),
                                     ("matched_cash", cash[index])):
                wealth = np.cumprod(1 + returns)
                report["control_rows"].append({"stage": identifier, "control_id": control,
                    "slippage_bps_each_way": cost, "commission_bps_each_way": 1.0,
                    "elapsed_act365_years": years, **_row_metrics(wealth, cash[index], years)})
    return _json_safe(report)


def write_report(report: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    """Create a new aggregate-only report directory; never overwrite attempts."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    targets = {}
    for key in ("stage_summaries", "portfolio_rows", "control_rows", "cap_rows"):
        target = output_dir / f"{key}.csv"
        rows = report[key]
        fields = list(dict.fromkeys(field for row in rows for field in row))
        with target.open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        targets[key] = target
    target = output_dir / "report.json"
    with target.open("x") as stream:
        json.dump(_json_safe(report), stream, indent=2, allow_nan=False)
        stream.write("\n")
    targets["report"] = target
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="PRIVATE three-stage saved-path manifest")
    parser.add_argument("--portfolios", type=Path, required=True, help="Explicit unchanged four-allocation JSON")
    parser.add_argument("--output-dir", type=Path, required=True, help="New aggregate-only attempt directory")
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        parser.error("output directory already exists; choose a new attempt")
    try:
        stages = load_stage_manifest(args.manifest)
        portfolios = load_portfolios(args.portfolios, list(SYMBOLS))
        write_report(analyze_periods(stages, portfolios), args.output_dir)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))
    return 0
