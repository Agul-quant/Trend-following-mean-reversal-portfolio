"""Analytics for saved net sleeve paths; never reruns the strategy engine.

All equity arrays are normalized by the original stage capital. Mixing is static
INITIAL allocation, not free daily rebalancing. Prices, actions, fills and costs
must already be correctly embedded in the saved input equity/return paths.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from scipy.optimize import LinearConstraint, linprog, minimize


ANNUAL_OBSERVATIONS = 252


def _finite(value: Any, name: str, ndim: int | None = None) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if ndim is not None and array.ndim != ndim:
        raise ValueError(f"{name} must have {ndim} dimensions")
    if not array.size or not np.isfinite(array).all():
        raise ValueError(f"{name} must be nonempty and finite")
    return array


def checked_weights(weights: Any, sleeves: int) -> np.ndarray:
    weights = _finite(weights, "weights", 1)
    if len(weights) != sleeves or np.any(weights < 0):
        raise ValueError("weights must be nonnegative and match the sleeve count")
    if not np.isclose(weights.sum(), 1.0, rtol=0, atol=1e-10):
        raise ValueError("initial weights must sum to one")
    return weights


def _equity(value: Any, ndim: int | None = None) -> np.ndarray:
    equity = _finite(value, "normalized equity", ndim)
    if np.any(equity <= 0):
        raise ValueError("normalized equity must be strictly positive")
    return equity


def portfolio_equity(sleeve_equity: Any, weights: Any) -> np.ndarray:
    """Return sum(w_i E_i,t), for (..., time, sleeve) saved normalized paths."""
    equity = _equity(sleeve_equity)
    if equity.ndim < 2:
        raise ValueError("sleeve equity must have time and sleeve dimensions")
    return equity @ checked_weights(weights, equity.shape[-1])


def returns_from_equity(normalized_equity: Any) -> np.ndarray:
    """Simple returns along final axis; include first return from initial wealth 1."""
    equity = _equity(normalized_equity)
    if equity.ndim < 1:
        raise ValueError("equity must have a time dimension")
    previous = np.concatenate([np.ones(equity.shape[:-1] + (1,)), equity[..., :-1]], axis=-1)
    return equity / previous - 1.0


def metrics(normalized_equity: Any, cash_returns: Any, years: float) -> dict[str, float]:
    """Net metrics. Annual alpha is not CAGR; Sharpe is above actual matched cash.

    Undefined (zero-variance) Sharpe is NaN, including exact all-cash returns.
    The caller should represent nonfinite values as JSON null, never zero.
    """
    equity = _equity(normalized_equity, 1)
    cash = _finite(cash_returns, "cash returns", 1)
    if len(cash) != len(equity) or len(equity) < 2 or np.any(cash <= -1):
        raise ValueError("cash/equity must align with at least two valid returns")
    if not np.isfinite(years) or years <= 0:
        raise ValueError("elapsed ACT/365 years must be finite and positive")
    returns = returns_from_equity(equity)
    excess = returns - cash
    sigma = float(np.std(excess, ddof=1))
    # Multiplicative cash paths can introduce roundoff at ~machine epsilon.
    zero_variance = sigma <= 64 * np.finfo(float).eps * max(1.0, float(np.max(np.abs(excess))))
    sharpe = float("nan") if zero_variance else float(np.sqrt(ANNUAL_OBSERVATIONS) * excess.mean() / sigma)
    path_with_initial = np.concatenate([[1.0], equity])
    drawdown = path_with_initial / np.maximum.accumulate(path_with_initial) - 1
    return {
        "cash_excess_sharpe": sharpe,
        "cagr": float(equity[-1] ** (1.0 / years) - 1.0),
        "max_drawdown": float(drawdown.min()),
        "terminal_normalized_equity": float(equity[-1]),
        "observations": int(len(equity)),
    }


def cap_diagnostics(sleeve_equity: Any, weights: Any, cap: float = 1 / 3) -> dict[str, Any]:
    """Daily CAPITAL-share diagnostics, not ETF holdings/exposure/risk weights.

    Validates historical saved valuations only. Does not imply rebalancing,
    intraday cap enforcement, executable orders, or future-cap guarantees.
    """
    equity = _equity(sleeve_equity)
    if equity.ndim not in (2, 3):
        raise ValueError("sleeve equity must have shape (time,sleeve) or (cost,time,sleeve)")
    weights = checked_weights(weights, equity.shape[-1])
    if not np.isfinite(cap) or not 0 < cap <= 1:
        raise ValueError("cap must be in (0,1]")
    capital = equity * weights
    shares = capital / capital.sum(axis=-1, keepdims=True)
    axes = tuple(range(shares.ndim - 1))
    maxima = shares.max(axis=axes)
    return {
        "cap": float(cap),
        "initial_cap_satisfied": bool(weights.max() <= cap + 1e-10),
        "all_daily_cap_satisfied": bool(shares.max() <= cap + 1e-10),
        "max_daily_capital_share": float(shares.max()),
        "max_daily_capital_share_by_sleeve": maxima.tolist(),
        "terminal_capital_shares": shares[..., -1, :].tolist(),
    }


def joint_regression(portfolio_returns: Any, factor_returns: Any, cash_returns: Any) -> dict[str, Any]:
    """OLS: net portfolio excess ~ intercept + cost-matched PASSIVE BH excess.

    A factor column is not a traded portfolio sleeve weight. Negative partial
    beta is permitted for a long-only portfolio. Full-rank design is required.
    The annual alpha is 252 * daily intercept, arithmetic rather than compounded.
    """
    returns = _finite(portfolio_returns, "portfolio returns", 1)
    factors = _finite(factor_returns, "factor returns", 2)
    cash = _finite(cash_returns, "cash returns", 1)
    n, k = factors.shape
    if len(returns) != n or len(cash) != n or n <= k + 1:
        raise ValueError("regression arrays must align and leave residual degrees of freedom")
    if np.any(returns <= -1) or np.any(factors <= -1) or np.any(cash <= -1):
        raise ValueError("simple returns must exceed -1")
    x = np.column_stack([np.ones(n), factors - cash[:, None]])
    y = returns - cash
    coefficient, _, rank, singular = np.linalg.lstsq(x, y, rcond=None)
    if rank != k + 1:
        raise ValueError("regression design is rank deficient")
    residual = y - x @ coefficient
    sst = float(np.square(y - y.mean()).sum())
    sse = float(residual @ residual)
    r2 = float("nan") if sst == 0 else float(1 - sse / sst)
    adjusted = float("nan") if not np.isfinite(r2) else float(1 - (1 - r2) * (n - 1) / (n - k - 1))
    return {
        "alpha_daily": float(coefficient[0]),
        "alpha_annual_arithmetic": float(ANNUAL_OBSERVATIONS * coefficient[0]),
        "betas": coefficient[1:].tolist(),
        "r_squared": r2,
        "adjusted_r_squared": adjusted,
        "observations": n,
        "design_rank": int(rank),
        "design_condition_number": float(singular[0] / singular[-1]),
    }


def pairwise_regressions(portfolio_returns: Any, factor_returns: Any, cash_returns: Any) -> list[dict[str, Any]]:
    """Separate one-factor fits; not partial beta from a joint regression."""
    factors = _finite(factor_returns, "factor returns", 2)
    return [joint_regression(portfolio_returns, factors[:, [i]], cash_returns) for i in range(factors.shape[1])]


def factor_diagnostics(factor_returns: Any, cash_returns: Any) -> dict[str, Any]:
    """Centered/standardized factor conditioning and variance-inflation factors."""
    factors = _finite(factor_returns, "factor returns", 2)
    cash = _finite(cash_returns, "cash returns", 1)
    if factors.shape[0] != len(cash) or len(cash) < 3:
        raise ValueError("cash/factors must align")
    excess = factors - cash[:, None]
    scale = excess.std(axis=0, ddof=1)
    if np.any(scale == 0):
        raise ValueError("constant factors cannot be standardized")
    z = (excess - excess.mean(axis=0)) / scale
    if np.linalg.matrix_rank(z) != z.shape[1]:
        raise ValueError("factor design is rank deficient")
    corr = z.T @ z / (len(z) - 1)
    return {
        "correlation": corr.tolist(),
        "standardized_condition_number": float(np.linalg.cond(z)),
        "variance_inflation_factors": np.diag(np.linalg.inv(corr)).tolist(),
    }


def max_cagr_weights(sleeve_equity: Any) -> np.ndarray:
    """Exact uncapped static-simplex terminal-wealth optimum (first tied vertex).

    Not an optimizer for dynamically rebalanced portfolios or daily share caps.
    """
    equity = _equity(sleeve_equity, 2)
    weights = np.zeros(equity.shape[1])
    weights[int(np.argmax(equity[-1]))] = 1.0
    return weights


def _daily_cap_matrix(equity: np.ndarray, cap: float) -> np.ndarray:
    # cap * sum_j(E_j,t w_j) - E_i,t w_i >= 0, across ALL costs/days.
    flat = equity.reshape(-1, equity.shape[-1])
    rows = np.repeat(cap * flat, flat.shape[1], axis=0)
    sleeves = np.tile(np.arange(flat.shape[1]), len(flat))
    rows[np.arange(len(rows)), sleeves] -= flat.ravel()
    return rows


def _finalized_weights(weights: np.ndarray, bound: float, rows: np.ndarray | None) -> np.ndarray:
    """Normalize floating-point output, then independently recheck every cap."""
    weights = np.maximum(weights, 0)
    weights /= weights.sum()
    if (not np.isfinite(weights).all() or abs(weights.sum() - 1) > 1e-10
            or weights.min() < 0 or weights.max() > bound + 1e-10
            or (rows is not None and (rows @ weights).min() < -1e-10)):
        raise ValueError("postprocessed optimizer weights violate allocation constraints")
    return weights


def optimize_sharpe(
    sleeve_equity: Any,
    cash_returns: Any,
    *,
    baseline_index: int = 0,
    cap_mode: str = "none",
    cap: float = 1 / 3,
    starts: int = 12,
    seed: int = 1729,
) -> dict[str, Any]:
    """Deterministic multi-start SLSQP best-found cash-excess Sharpe.

    The objective uses the baseline cost only; ``daily`` constrains every input
    cost's saved daily capital shares AND initial shares. Baseline-fit weights
    are not refitted for other costs. No claim of globally certified optimality.
    """
    equity = _equity(sleeve_equity, 3)
    costs, n, sleeves = equity.shape
    cash = _finite(cash_returns, "cash returns", 1)
    if len(cash) != n or n < 2 or np.any(cash <= -1):
        raise ValueError("cash/equity must align with at least two returns")
    if not 0 <= baseline_index < costs or cap_mode not in {"none", "initial", "daily"}:
        raise ValueError("invalid baseline index or cap mode")
    if starts < 1 or not isinstance(starts, int):
        raise ValueError("starts must be a positive integer")
    if not np.isfinite(cap) or not 0 < cap <= 1:
        raise ValueError("cap must be in (0,1]")
    bound = 1.0 if cap_mode == "none" else cap
    if bound * sleeves < 1 - 1e-12:
        raise ValueError("initial cap is infeasible for this sleeve count")
    rows = _daily_cap_matrix(equity, cap) if cap_mode == "daily" else None
    bounds = [(0.0, bound)] * sleeves
    rng = np.random.default_rng(seed)
    seeds = []
    # LP starts certify feasibility and explore deterministic simplex vertices.
    for i in range(starts):
        objective = np.zeros(sleeves) if i == 0 else rng.standard_normal(sleeves)
        linear = linprog(objective, A_ub=None if rows is None else -rows,
                         b_ub=None if rows is None else np.zeros(len(rows)),
                         A_eq=np.ones((1, sleeves)), b_eq=[1.0], bounds=bounds, method="highs")
        if not linear.success:
            raise ValueError("historical capital-share constraints are infeasible")
        seeds.append(linear.x)
    equal = np.full(sleeves, 1 / sleeves)
    if equal.max() <= bound and (rows is None or (rows @ equal).min() >= -1e-12):
        seeds.append(equal)
    constraints = [LinearConstraint(np.ones((1, sleeves)), 1.0, 1.0)]
    if rows is not None:
        constraints.append(LinearConstraint(rows, 0.0, np.inf))
    baseline = equity[baseline_index]
    previous = np.concatenate([np.ones((1, sleeves)), baseline[:-1]], axis=0)

    def objective_and_gradient(weights: np.ndarray) -> tuple[float, np.ndarray]:
        wealth = baseline @ weights
        prev_wealth = previous @ weights
        # The independent stage starts with wealth 1, not with arbitrary sum(w).
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
        gradient = np.sqrt(252) * (derivative.mean(axis=0) / sigma - mean * dsigma / sigma ** 2)
        return float(-np.sqrt(252) * mean / sigma), -gradient

    candidates: list[tuple[float, np.ndarray]] = []
    attempts = []
    for start in seeds:
        result = minimize(objective_and_gradient, start, jac=True, method="SLSQP", bounds=bounds,
                          constraints=constraints, options={"ftol": 1e-12, "maxiter": 2000})
        weights = result.x
        feasible = (abs(weights.sum() - 1) <= 1e-8 and weights.min() >= -1e-10
                    and weights.max() <= bound + 1e-10
                    and (rows is None or (rows @ weights).min() >= -1e-10))
        objective, _ = objective_and_gradient(weights)
        attempts.append({"success": bool(result.success), "feasible": bool(feasible), "objective": float(objective)})
        # Compare feasible starts too: a failed local solver must not worsen them.
        for candidate in (start, weights) if feasible else (start,):
            value, _ = objective_and_gradient(candidate)
            if np.isfinite(value) and value < 1e11:
                candidates.append((value, candidate.copy()))
    if not candidates:
        raise ValueError("no finite-Sharpe feasible portfolio was found")
    value, weights = min(candidates, key=lambda pair: pair[0])
    weights = _finalized_weights(weights, bound, rows)
    value, _ = objective_and_gradient(weights)
    if not np.isfinite(value) or value >= 1e11:
        raise ValueError("postprocessed optimizer weights have undefined Sharpe")
    return {"initial_weights": weights.tolist(), "baseline_cash_excess_sharpe": float(-value),
            "cap_mode": cap_mode, "certified_global_optimum": False, "solver": "multi-start SLSQP",
            "seed": seed, "attempts": attempts}
