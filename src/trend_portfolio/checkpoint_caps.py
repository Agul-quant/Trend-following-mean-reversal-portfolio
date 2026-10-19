"""Static initial-wealth fits capped only at observed week or month ends.

These are retrospective capital-share constraints, not rebalancing instructions,
ETF holding weights, intraday guarantees, or new untouched OOS evidence. Every
objective return remains daily; only the constraint observation dates change.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

import numpy as np
from scipy.optimize import LinearConstraint, linprog, minimize

from .analytics import ANNUAL_OBSERVATIONS, checked_weights


CAP_TOLERANCE = 1e-10
NEW_YORK = ZoneInfo("America/New_York")


def _daily_instants(timestamps: Any) -> tuple[datetime, ...]:
    values = np.asarray(timestamps, dtype=object)
    if values.ndim != 1 or not len(values):
        raise ValueError("timestamps must be a nonempty one-dimensional daily sequence")
    times = []
    for value in values:
        try:
            instant = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError) as error:
            raise ValueError("timestamps must be ISO-8601 instants") from error
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("timestamps must have an explicit UTC offset")
        times.append(instant.astimezone(timezone.utc))
    if any(left >= right for left, right in zip(times, times[1:])):
        raise ValueError("timestamps must be unique and strictly increasing")
    dates = [instant.astimezone(NEW_YORK).date() for instant in times]
    if len(set(dates)) != len(dates):
        raise ValueError("only one daily valuation per New York date is allowed")
    return tuple(times)


def checkpoint_indices(timestamps: Any, frequency: str) -> np.ndarray:
    """Last OBSERVED daily valuation per NY ISO week or calendar month.

    Holidays do not create or fill observations. ISO year is part of the weekly
    grouping, and the final incomplete week or month is always included.
    """
    if frequency not in {"daily", "weekly", "monthly"}:
        raise ValueError("frequency must be daily, weekly or monthly")
    times = _daily_instants(timestamps)
    if frequency == "daily":
        return np.arange(len(times), dtype=int)
    dates = [instant.astimezone(NEW_YORK).date() for instant in times]
    periods = [(day.isocalendar().year, day.isocalendar().week) if frequency == "weekly"
               else (day.year, day.month) for day in dates]
    return np.array([index for index in range(len(periods))
                     if index == len(periods) - 1 or periods[index] != periods[index + 1]], dtype=int)


def _validated_equity(sleeve_equity: Any, *, require_four: bool = True) -> np.ndarray:
    equity = np.asarray(sleeve_equity, dtype=float)
    if (equity.ndim != 3 or equity.shape[0] < 1 or (require_four and equity.shape[0] != 4)
            or equity.shape[1] < 2 or equity.shape[2] < 1
            or not np.isfinite(equity).all() or np.any(equity <= 0)):
        raise ValueError("equity must be positive finite (four costs,time>=2,sleeve) saved wealth")
    return equity


def _cap_value(cap: float) -> float:
    if isinstance(cap, bool) or not np.isfinite(cap) or not 0 < cap <= 1:
        raise ValueError("cap must be finite and in (0,1]")
    return float(cap)


def _matched_cash(cash_returns: Any, costs: int, n: int) -> np.ndarray:
    cash = np.asarray(cash_returns, dtype=float)
    if cash.shape == (costs, n):
        if not np.array_equal(cash, np.broadcast_to(cash[0], cash.shape)):
            raise ValueError("all four costs must use the identical matched cash path")
        cash = cash[0]
    if cash.shape != (n,) or not np.isfinite(cash).all() or np.any(cash <= -1):
        raise ValueError("cash must be valid daily simple returns aligned with every saved day")
    return cash


def _objective_factory(baseline: np.ndarray, cash: np.ndarray) -> Callable:
    """Same daily static-wealth objective and analytic gradient as analytics.py."""
    n, sleeves = baseline.shape
    previous = np.concatenate([np.ones((1, sleeves)), baseline[:-1]], axis=0)

    def objective_and_gradient(weights: np.ndarray) -> tuple[float, np.ndarray]:
        wealth = baseline @ weights
        prev_wealth = previous @ weights
        # Fresh account starts at 1, independently of an optimizer trial's sum(w).
        prev_wealth[0] = 1.0
        if np.any(wealth <= 0) or np.any(prev_wealth <= 0):
            return 1e12, np.zeros(sleeves)
        excess = wealth / prev_wealth - 1.0 - cash
        derivative = baseline / prev_wealth[:, None] - wealth[:, None] * previous / prev_wealth[:, None] ** 2
        derivative[0] = baseline[0]
        sigma = excess.std(ddof=1)
        if sigma < 1e-14:
            return 1e12, np.zeros(sleeves)
        mean = excess.mean()
        dsigma = ((excess - mean)[:, None] * derivative).sum(axis=0) / ((n - 1) * sigma)
        gradient = np.sqrt(ANNUAL_OBSERVATIONS) * (derivative.mean(axis=0) / sigma - mean * dsigma / sigma ** 2)
        return float(-np.sqrt(ANNUAL_OBSERVATIONS) * mean / sigma), -gradient

    return objective_and_gradient


def checkpoint_sharpe_objective(baseline_equity: Any, cash_returns: Any, weights: Any) -> tuple[float, np.ndarray]:
    """Negative daily cash-excess Sharpe and its unconstrained trial gradient.

    Exposed for independent synthetic gradient checks; no return resampling.
    """
    baseline = np.asarray(baseline_equity, dtype=float)
    if (baseline.ndim != 2 or baseline.shape[0] < 2 or baseline.shape[1] < 1
            or not np.isfinite(baseline).all() or np.any(baseline <= 0)):
        raise ValueError("baseline wealth must be a positive finite daily time by sleeve array")
    cash = _matched_cash(cash_returns, 1, len(baseline))
    trial = np.asarray(weights, dtype=float)
    if trial.shape != (baseline.shape[1],) or not np.isfinite(trial).all():
        raise ValueError("trial weights must be finite and match the sleeve axis")
    return _objective_factory(baseline, cash)(trial)


def _constraint_matrix(equity: np.ndarray, indices: np.ndarray, cap: float) -> np.ndarray:
    flat = equity[:, indices, :].reshape(-1, equity.shape[-1])
    rows = np.repeat(cap * flat, flat.shape[1], axis=0)
    sleeves = np.tile(np.arange(flat.shape[1]), len(flat))
    rows[np.arange(len(rows)), sleeves] -= flat.ravel()
    return rows


def checkpoint_cap_diagnostics(sleeve_equity: Any, weights: Any, timestamps: Any,
                               frequency: str, cap: float = 1 / 3) -> dict[str, Any]:
    """Per-cost capital-share maxima and counts, with daily breaches disclosed.

    A breach day means at least one sleeve exceeds cap + 1e-10 on that daily
    valuation. Counts exclude initial capital, whose status is separate.
    """
    equity = _validated_equity(sleeve_equity, require_four=False)
    cap = _cap_value(cap)
    weights = checked_weights(weights, equity.shape[-1])
    indices = checkpoint_indices(timestamps, frequency)
    if len(timestamps) != equity.shape[1]:
        raise ValueError("timestamps must align with every saved daily valuation")
    capital = equity * weights
    shares = capital / capital.sum(axis=-1, keepdims=True)
    initial_ok = bool(weights.max() <= cap + CAP_TOLERANCE)
    checkpoint_mask = np.zeros(equity.shape[1], dtype=bool)
    checkpoint_mask[indices] = True
    per_cost = []
    for cost_index, cost_shares in enumerate(shares):
        selected = cost_shares[indices]
        breaches = np.any(cost_shares > cap + CAP_TOLERANCE, axis=1)
        checkpoint_breaches = breaches[indices]
        per_cost.append({
            "cost_index": cost_index,
            "checkpoint_count": int(len(indices)),
            "checkpoint_max_capital_share": float(selected.max()),
            "checkpoint_max_capital_share_by_sleeve": selected.max(axis=0).tolist(),
            "checkpoint_breach_days": int(checkpoint_breaches.sum()),
            "checkpoint_cap_satisfied": bool(initial_ok and not checkpoint_breaches.any()),
            "daily_max_capital_share": float(cost_shares.max()),
            "daily_max_capital_share_by_sleeve": cost_shares.max(axis=0).tolist(),
            "daily_breach_days": int(breaches.sum()),
            "between_checkpoint_breach_days": int(breaches[~checkpoint_mask].sum()),
            "all_daily_cap_satisfied": bool(initial_ok and not breaches.any()),
            "terminal_capital_shares": cost_shares[-1].tolist(),
        })
    return {"frequency": frequency, "cap": cap, "cap_tolerance": CAP_TOLERANCE,
            "initial_max_capital_share": float(weights.max()), "initial_cap_satisfied": initial_ok,
            "checkpoint_count": int(len(indices)), "daily_observations": int(equity.shape[1]),
            "final_partial_period_included": True, "no_rebalancing": True,
            "all_costs_checkpoint_cap_satisfied": bool(all(row["checkpoint_cap_satisfied"] for row in per_cost)),
            "per_cost": per_cost}


def optimize_checkpoint_sharpe(
    sleeve_equity: Any, cash_returns: Any, timestamps: Any, frequency: str, *,
    baseline_index: int = 1, cap: float = 1 / 3, starts: int = 48, seed: int = 1729,
    known_weights: Any = None,
) -> dict[str, Any]:
    """Deterministic LP-start/SLSQP best-found static allocation, never global proof.

    Constrain initial shares and every cost's observed period-end shares. The
    baseline objective uses ALL daily returns. A feasible, finite known seed is
    an incumbent independently of local-solver success and cannot be worsened.
    """
    equity = _validated_equity(sleeve_equity)
    if frequency not in {"weekly", "monthly"}:
        raise ValueError("new optimizer frequency must be weekly or monthly")
    costs, n, sleeves = equity.shape
    cash = _matched_cash(cash_returns, costs, n)
    cap = _cap_value(cap)
    if (not isinstance(baseline_index, (int, np.integer)) or isinstance(baseline_index, bool)
            or not 0 <= baseline_index < costs):
        raise ValueError("baseline index must identify an input cost")
    if not isinstance(starts, int) or isinstance(starts, bool) or starts < 1:
        raise ValueError("starts must be a positive integer")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if cap * sleeves < 1 - 1e-12:
        raise ValueError("initial cap is infeasible for this sleeve count")
    indices = checkpoint_indices(timestamps, frequency)
    if len(timestamps) != n:
        raise ValueError("timestamps must align with every saved daily valuation")
    rows = _constraint_matrix(equity, indices, cap)
    objective_and_gradient = _objective_factory(equity[baseline_index], cash)
    bounds = [(0.0, cap)] * sleeves

    def finalized(candidate: np.ndarray) -> np.ndarray:
        weights = np.asarray(candidate, dtype=float).copy()
        if (weights.shape != (sleeves,) or not np.isfinite(weights).all()
                or abs(weights.sum() - 1) > 1e-8 or weights.min() < -CAP_TOLERANCE
                or weights.max() > cap + CAP_TOLERANCE):
            raise ValueError("optimizer trial is infeasible")
        weights = np.maximum(weights, 0)
        weights /= weights.sum()
        capital = equity[:, indices, :] * weights
        shares = capital / capital.sum(axis=-1, keepdims=True)
        if weights.max() > cap + CAP_TOLERANCE or shares.max() > cap + CAP_TOLERANCE:
            raise ValueError("postprocessed optimizer weights violate checkpoint constraints")
        return weights

    seeds: list[tuple[str, np.ndarray]] = []
    candidates: list[tuple[float, np.ndarray, str]] = []
    known_sharpe = None
    if known_weights is not None:
        known = checked_weights(known_weights, sleeves)
        try:
            known = finalized(known)
        except ValueError as error:
            raise ValueError("known incumbent violates initial or checkpoint cap") from error
        value, _ = objective_and_gradient(known)
        if not np.isfinite(value) or value >= 1e11:
            raise ValueError("known incumbent has undefined daily cash-excess Sharpe")
        known_sharpe = float(-value)
        candidates.append((value, known.copy(), "known_incumbent"))
        seeds.append(("known_incumbent", known))
    rng = np.random.default_rng(seed)
    for index in range(starts):
        objective = np.zeros(sleeves) if index == 0 else rng.standard_normal(sleeves)
        linear = linprog(objective, A_ub=-rows, b_ub=np.zeros(len(rows)),
                         A_eq=np.ones((1, sleeves)), b_eq=[1.0], bounds=bounds, method="highs")
        if not linear.success:
            raise ValueError("historical checkpoint capital-share constraints are infeasible or LP failed")
        try:
            start = finalized(linear.x)
        except ValueError as error:
            raise ValueError("LP start fails independent checkpoint feasibility recheck") from error
        seeds.append((f"lp_{index}", start))
    equal = np.full(sleeves, 1 / sleeves)
    try:
        equal = finalized(equal)
    except ValueError:
        pass
    else:
        seeds.append(("equal_initial", equal))
    constraints = [LinearConstraint(np.ones((1, sleeves)), 1.0, 1.0),
                   LinearConstraint(rows, 0.0, np.inf)]
    attempts = []
    for source, start in seeds:
        # Evaluate all feasible starts independently of the solver's terminal flag.
        start_value, _ = objective_and_gradient(start)
        if np.isfinite(start_value) and start_value < 1e11:
            candidates.append((start_value, start.copy(), source))
        result = minimize(objective_and_gradient, start, jac=True, method="SLSQP", bounds=bounds,
                          constraints=constraints, options={"ftol": 1e-12, "maxiter": 2000})
        feasible = False
        value = 1e12
        try:
            weights = finalized(result.x)
            feasible = True
        except ValueError:
            pass
        else:
            value, _ = objective_and_gradient(weights)
            if np.isfinite(value) and value < 1e11:
                candidates.append((value, weights, f"{source}_solver"))
        attempts.append({"start_source": source, "success": bool(result.success),
                         "feasible": feasible, "objective": float(value),
                         "iterations": int(result.nit), "status": int(result.status)})
    if not candidates:
        raise ValueError("no finite-Sharpe feasible portfolio was found")
    value, weights, source = min(candidates, key=lambda record: record[0])
    weights = finalized(weights)
    value, _ = objective_and_gradient(weights)
    if not np.isfinite(value) or value >= 1e11:
        raise ValueError("postprocessed optimizer weights have undefined Sharpe")
    if known_sharpe is not None and -value < known_sharpe - 1e-10:
        raise ValueError("optimizer unexpectedly worsened the known feasible incumbent")
    diagnostics = checkpoint_cap_diagnostics(equity, weights, timestamps, frequency, cap)
    if not diagnostics["all_costs_checkpoint_cap_satisfied"]:
        raise ValueError("final optimizer result fails independent checkpoint diagnostics")
    return {"initial_weights": weights.tolist(), "baseline_cash_excess_sharpe": float(-value),
            "baseline_index": int(baseline_index), "objective_frequency": "daily",
            "objective_observations": n, "cap_mode": frequency, "cap": cap,
            "checkpoint_count": int(len(indices)), "constraint_costs": costs,
            "initial_cap_enforced": True, "no_rebalancing": True,
            "certified_global_optimum": False, "solver": "analytic-gradient multi-start SLSQP",
            "seed": seed, "lp_starts": starts, "ftol": 1e-12, "maxiter": 2000,
            "known_incumbent_cash_excess_sharpe": known_sharpe,
            "selected_candidate_source": source, "attempts": attempts,
            "checkpoint_diagnostics": diagnostics}
