"""Portable aggregate-only interface for a privately supplied saved-path bundle."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np

from .analytics import (
    cap_diagnostics, checked_weights, factor_diagnostics, joint_regression,
    max_cagr_weights, metrics, optimize_sharpe, pairwise_regressions,
    portfolio_equity, returns_from_equity,
)


def _json_safe(value: Any) -> Any:
    """Strict JSON: undefined metrics become null, not nonstandard NaN tokens."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def load_bundle(path: Path) -> dict[str, np.ndarray]:
    """Load non-pickled private arrays with a strict shape/alignment contract."""
    required = {"timestamps", "slippage_bps", "symbols", "sleeve_normalized_equity",
                "buy_and_hold_returns", "cash_returns"}
    with np.load(path, allow_pickle=False) as source:
        missing = required - set(source.files)
        if missing:
            raise ValueError(f"input bundle is missing fields: {', '.join(sorted(missing))}")
        data = {key: source[key].copy() for key in required}
    equity = np.asarray(data["sleeve_normalized_equity"], dtype=float)
    factors = np.asarray(data["buy_and_hold_returns"], dtype=float)
    if equity.ndim != 3 or min(equity.shape) < 1 or equity.shape[1] < 2:
        raise ValueError("sleeve_normalized_equity must have shape (cost,time,sleeve), time >= 2")
    if not np.isfinite(equity).all() or np.any(equity <= 0):
        raise ValueError("normalized equity must be finite and positive")
    if factors.shape != equity.shape or not np.isfinite(factors).all() or np.any(factors <= -1):
        raise ValueError("buy_and_hold_returns must match equity shape and contain valid simple returns")
    c, t, s = equity.shape
    cash = np.asarray(data["cash_returns"], dtype=float)
    if cash.shape == (t,):
        cash = np.broadcast_to(cash, (c, t)).copy()
    if cash.shape != (c, t) or not np.isfinite(cash).all() or np.any(cash <= -1):
        raise ValueError("cash_returns must have shape (time,) or (cost,time) and valid returns")
    for key, length in (("symbols", s), ("timestamps", t)):
        if data[key].shape != (length,) or data[key].dtype.kind not in "US":
            raise ValueError(f"{key} must be a one-dimensional string array matching its axis")
    symbols = [str(symbol) for symbol in data["symbols"].astype(str)]
    if len(set(symbols)) != len(symbols) or any(not value for value in symbols):
        raise ValueError("symbols must be unique and nonempty")
    times = []
    for value in data["timestamps"].astype(str):
        try:
            instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("timestamps must be ISO-8601 with an explicit UTC offset") from error
        if instant.tzinfo is None:
            raise ValueError("timestamps must include an explicit UTC offset")
        times.append(instant.astimezone(timezone.utc))
    if any(left >= right for left, right in zip(times, times[1:])):
        raise ValueError("timestamps must be unique and strictly increasing")
    costs = np.asarray(data["slippage_bps"], dtype=float)
    if costs.shape != (c,) or not np.isfinite(costs).all() or np.any(costs < 0) or len(set(costs)) != c:
        raise ValueError("slippage_bps must be a unique nonnegative finite cost-axis array")
    data.update(sleeve_normalized_equity=equity, buy_and_hold_returns=factors, cash_returns=cash,
                slippage_bps=costs, symbols=np.array(symbols))
    return data


def load_portfolios(path: Path, symbols: list[str]) -> list[dict[str, Any]]:
    """Read {portfolios:[{id,initial_weights}]} or an id->definition mapping."""
    document = json.loads(path.read_text())
    records = document.get("portfolios", document) if isinstance(document, dict) else document
    if isinstance(records, dict):
        records = [{"id": key, **(value if isinstance(value, dict) else {"initial_weights": value})}
                   for key, value in records.items()]
    if not isinstance(records, list) or not records:
        raise ValueError("portfolios must be a nonempty list or id->definition mapping")
    parsed = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
            raise ValueError("every portfolio needs a nonempty string id")
        raw = record.get("initial_weights", record.get("weights"))
        if isinstance(raw, dict):
            if set(raw) != set(symbols):
                raise ValueError("weight mappings must contain exactly the input symbols")
            raw = [raw[symbol] for symbol in symbols]
        weights = checked_weights(raw, len(symbols))
        parsed.append({"id": record["id"], "initial_weights": weights})
    if len({record["id"] for record in parsed}) != len(parsed):
        raise ValueError("portfolio ids must be unique")
    return parsed


def analyze(bundle: dict[str, np.ndarray], portfolios: list[dict[str, Any]], years: float,
            cap: float = 1 / 3) -> dict[str, Any]:
    """Aggregate analytics only: no saved input paths or numerical daily paths."""
    symbols = bundle["symbols"].tolist()
    equity = bundle["sleeve_normalized_equity"]
    cash = bundle["cash_returns"]
    factors = bundle["buy_and_hold_returns"]
    costs = bundle["slippage_bps"]
    report: dict[str, Any] = {
        "method": "static initial capital; no cross-sleeve rebalancing",
        "scope": "retrospective descriptive analysis; not untouched portfolio OOS or live trading",
        "symbols": symbols, "slippage_bps": costs.tolist(), "elapsed_act365_years": years,
        "observations": equity.shape[1], "portfolio_results": [], "factor_diagnostics": [],
        "sleeve_results": [], "strategy_return_correlations": [],
    }
    for record in portfolios:
        weights = checked_weights(record["initial_weights"], len(symbols))
        wealth = portfolio_equity(equity, weights)
        rows = []
        for index, cost in enumerate(costs):
            returns = returns_from_equity(wealth[index])
            rows.append({
                "slippage_bps": float(cost), "metrics": metrics(wealth[index], cash[index], years),
                "joint_passive_bh_regression": joint_regression(returns, factors[index], cash[index]),
                "pairwise_passive_bh_regressions": pairwise_regressions(returns, factors[index], cash[index]),
            })
        report["portfolio_results"].append({
            "id": record["id"], "initial_weights": dict(zip(symbols, weights.tolist())),
            "capital_share_diagnostics_all_costs": cap_diagnostics(equity, weights, cap), "cost_results": rows,
        })
    for index, cost in enumerate(costs):
        report["factor_diagnostics"].append({"slippage_bps": float(cost), **factor_diagnostics(factors[index], cash[index])})
        sleeve_returns = returns_from_equity(equity[index].T).T
        # Constant-return sleeve correlations are honestly undefined (JSON null).
        with np.errstate(invalid="ignore", divide="ignore"):
            correlation = np.corrcoef(sleeve_returns, rowvar=False)
        report["strategy_return_correlations"].append({"slippage_bps": float(cost), "matrix": correlation.tolist()})
        for sleeve, symbol in enumerate(symbols):
            report["sleeve_results"].append({
                "symbol": symbol, "slippage_bps": float(cost),
                "metrics": metrics(equity[index, :, sleeve], cash[index], years),
                "joint_passive_bh_regression": joint_regression(sleeve_returns[:, sleeve], factors[index], cash[index]),
            })
    return _json_safe(report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Private saved-path NPZ (never committed)")
    parser.add_argument("--portfolios", required=True, type=Path, help="Public initial-allocation JSON")
    parser.add_argument("--years", required=True, type=float, help="Actual elapsed ACT/365 years, not observations/252")
    parser.add_argument("--output", required=True, type=Path, help="New aggregate-only JSON; existing files are not overwritten")
    parser.add_argument("--baseline-slippage", type=float, default=3)
    parser.add_argument("--optimize", choices=["none", "uncapped", "initial-cap", "daily-cap", "max-cagr"], default="none")
    parser.add_argument("--cap", type=float, default=1 / 3)
    parser.add_argument("--starts", type=int, default=12)
    parser.add_argument("--seed", type=int, default=1729)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output already exists; choose a new path")
    try:
        bundle = load_bundle(args.input)
        portfolios = load_portfolios(args.portfolios, bundle["symbols"].tolist())
        optimization = None
        if args.optimize != "none":
            matches = np.flatnonzero(bundle["slippage_bps"] == args.baseline_slippage)
            if len(matches) != 1:
                raise ValueError("baseline slippage must identify exactly one input cost")
            baseline = int(matches[0])
            if args.optimize == "max-cagr":
                weights = max_cagr_weights(bundle["sleeve_normalized_equity"][baseline])
                optimization = {"initial_weights": weights.tolist(), "method": "exact uncapped static-simplex terminal-wealth vertex"}
            else:
                mode = {"uncapped": "none", "initial-cap": "initial", "daily-cap": "daily"}[args.optimize]
                optimization = optimize_sharpe(bundle["sleeve_normalized_equity"], bundle["cash_returns"][baseline],
                                               baseline_index=baseline, cap_mode=mode, cap=args.cap,
                                               starts=args.starts, seed=args.seed)
                weights = optimization["initial_weights"]
            identifier = f"new_fit_{args.optimize.replace('-', '_')}"
            if any(item["id"] == identifier for item in portfolios):
                raise ValueError("new-fit portfolio id conflicts with an existing definition")
            portfolios.append({"id": identifier, "initial_weights": weights})
        report = analyze(bundle, portfolios, args.years, args.cap)
        if optimization is not None:
            report["new_retrospective_fit"] = _json_safe(optimization)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write("\n")
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))
    return 0
