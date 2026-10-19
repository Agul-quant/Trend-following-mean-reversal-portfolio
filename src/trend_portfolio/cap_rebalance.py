"""Costed cap-only redistribution at a caller-authorized safe bar open.

This module knows no dates, signals, orders, confirmation streaks or schedules.
The caller processes signal trades/corporate actions first and supplies the
current raw-open account state. It must separately authorize this new account
calculation. Nothing here changes any saved static-allocation research result.
"""
from __future__ import annotations

from math import fsum
from typing import Any

import numpy as np


def _vector(value: Any, name: str, size: int | None = None) -> np.ndarray:
    result = np.asarray(value, dtype=float)
    if result.ndim != 1 or not len(result) or (size is not None and len(result) != size):
        raise ValueError(f"{name} must be a nonempty matching one-dimensional array")
    if not np.isfinite(result).all():
        raise ValueError(f"{name} must be finite")
    return result.copy()


def _cap(value: float, sleeves: int) -> float:
    if isinstance(value, bool) or not np.isfinite(value) or not 0 < value <= 1:
        raise ValueError("cap must be finite and in (0,1]")
    if value * sleeves < 1:
        raise ValueError("cap is infeasible for the sleeve count")
    return float(value)


def capped_proportional_targets(capital: Any, post_cost_wealth: float,
                                cap: float = 1 / 3) -> np.ndarray:
    """Return y_i=min(cap*S, lambda*C_i), with sum(y)=S.

    Preserve the relative CURRENT capital of uncapped sleeves, not original
    target weights. Zero-capital sleeves receive zero under this proportional
    rule; enough positive-capital sleeves must remain to make the cap feasible.
    """
    current = _vector(capital, "capital")
    cap = _cap(cap, len(current))
    if np.any(current < 0) or fsum(current) <= 0:
        raise ValueError("capital must be nonnegative with positive total wealth")
    if isinstance(post_cost_wealth, bool) or not np.isfinite(post_cost_wealth) or post_cost_wealth <= 0:
        raise ValueError("post-cost wealth must be finite and positive")
    positive = current > 0
    if cap * int(positive.sum()) < 1:
        raise ValueError("cap is infeasible for proportional positive-capital sleeves")
    fractions = np.zeros(len(current))
    active = positive.copy()
    remaining = 1.0
    for _ in range(len(current) + 1):
        if not active.any():
            break
        proposal = remaining * (current[active] / fsum(current[active]))
        exceeds = proposal > cap
        positions = np.flatnonzero(active)
        if not exceeds.any():
            fractions[positions] = proposal
            break
        capped = positions[exceeds]
        fractions[capped] = cap
        active[capped] = False
        remaining = 1 - fsum(fractions)
    if abs(fsum(fractions) - 1) > 64 * np.finfo(float).eps:
        raise ArithmeticError("capped proportional waterfill failed wealth conservation")
    targets = fractions * float(post_cost_wealth)
    if (not np.isfinite(targets).all() or np.any(targets < 0)
            or np.any(targets > cap * post_cost_wealth + 64 * np.finfo(float).eps * post_cost_wealth)):
        raise ArithmeticError("capped proportional waterfill violated its target cap")
    return targets


def _post_cost_root(capital: np.ndarray, stock_value: np.ndarray, cash: np.ndarray,
                    logical_long: np.ndarray, fractions: np.ndarray,
                    buy_multiplier: float, sell_multiplier: float) -> tuple[float, int]:
    """Solve the self-financing sum(K_i)=0 root inside [0, pre-cost wealth]."""
    wealth = fsum(capital)
    money_tolerance = max(128 * np.finfo(float).eps * wealth, 1e-12)

    def residual(total: float) -> float:
        targets = fractions * total
        delta = targets - stock_value
        multipliers = np.where(delta >= 0, buy_multiplier, sell_multiplier)
        transfers = np.where(logical_long, delta * multipliers - cash, targets - cash)
        return fsum(transfers)

    low, high = 0.0, wealth
    lower, upper = residual(low), residual(high)
    if lower > money_tolerance or upper < -money_tolerance:
        raise ArithmeticError("self-financing rebalance root is not bracketed")
    if abs(upper) <= money_tolerance:
        answer, iterations = high, 0
    else:
        answer = (low + high) / 2
        iterations = 0
        for iterations in range(1, 257):
            answer = (low + high) / 2
            value = residual(answer)
            if abs(value) <= money_tolerance or high - low <= money_tolerance:
                break
            if value > 0:
                high = answer
            else:
                low = answer
        else:
            raise ArithmeticError("self-financing rebalance bisection did not converge")
    # The bracketed residual is continuous and piecewise linear. Polish only
    # within the same economic [0,W] bracket to remove cash-roundoff residuals.
    for _ in range(8):
        delta = fractions * answer - stock_value
        multipliers = np.where(delta >= 0, buy_multiplier, sell_multiplier)
        slopes = np.where(logical_long, fractions * multipliers, fractions)
        constants = np.where(logical_long, stock_value * multipliers + cash, cash)
        candidate = fsum(constants) / fsum(slopes)
        if not np.isfinite(candidate) or not 0 < candidate <= wealth + money_tolerance:
            raise ArithmeticError("self-financing root polish left the wealth bracket")
        answer = min(candidate, wealth)
        if abs(residual(answer)) <= money_tolerance:
            break
    if answer <= 0 or abs(residual(answer)) > money_tolerance:
        raise ArithmeticError("self-financing rebalance root has an unresolved cash residual")
    return float(answer), iterations


def rebalance_cap_at_open(
    cash: Any, shares: Any, raw_open: Any, logical_long: Any, *,
    slippage_bps: float, commission_bps: float = 1, cap: float = 1 / 3,
    symbols: Any = None, tolerance: float = 1e-10,
) -> dict[str, Any]:
    """Trim an OPEN-time cap breach and fund capped proportional recipients.

    A queued request is cancelled if the freshly marked raw-open capital shares
    no longer breach cap+tolerance. A cancellation changes no cash or shares,
    including unearmarked long-sleeve cash. On execution, long sleeves finish
    invested and flat sleeves finish in cash; their logical states are untouched.

    Positive ``cash_transfers`` mean internal cash RECEIVED by a sleeve. Their
    sum is zero within explicit floating-point accounting tolerance. Broker fees
    apply only to actual incremental ETF quantities, never internal cash moves.
    ``turnover_fraction`` is gross raw traded notional / pre-rebalance wealth,
    counting both buys and sells; it is not divided by two.
    """
    old_cash = _vector(cash, "cash")
    n = len(old_cash)
    old_shares = _vector(shares, "shares", n)
    prices = _vector(raw_open, "raw open", n)
    cap = _cap(cap, n)
    if np.any(old_cash < 0) or np.any(old_shares < 0) or np.any(prices <= 0):
        raise ValueError("cash/shares must be nonnegative and every raw open strictly positive")
    long = np.asarray(logical_long)
    if long.shape != (n,) or long.dtype.kind != "b":
        raise ValueError("logical long states must be a matching boolean array")
    long = long.copy()
    if np.any(old_shares[~long] != 0):
        raise ValueError("a logically flat sleeve must have exactly zero shares")
    for value, name in ((slippage_bps, "slippage"), (commission_bps, "commission")):
        if isinstance(value, bool) or not np.isfinite(value) or not 0 <= value < 10000:
            raise ValueError(f"{name} bps must be finite and in [0,10000)")
    if isinstance(tolerance, bool) or not np.isfinite(tolerance) or not 0 <= tolerance < 1:
        raise ValueError("capital-share tolerance must be finite and in [0,1)")
    if symbols is None:
        names = tuple(str(index) for index in range(n))
    else:
        names = tuple(symbols)
        if len(names) != n or len(set(names)) != n or any(not isinstance(name, str) or not name for name in names):
            raise ValueError("symbols must be unique nonempty strings matching the sleeves")
    with np.errstate(over="ignore", invalid="ignore"):
        stock = old_shares * prices
        capital = old_cash + stock
    if not np.isfinite(capital).all():
        raise ValueError("raw-open capital must remain finite")
    pre_wealth = fsum(capital)
    if not np.isfinite(pre_wealth) or pre_wealth <= 0:
        raise ValueError("raw-open portfolio wealth must be finite and positive")
    pre_fraction = capital / pre_wealth
    executed = bool(pre_fraction.max() > cap + tolerance)
    slip, fee_rate = float(slippage_bps) / 10000, float(commission_bps) / 10000
    buy_multiplier, sell_multiplier = (1 + slip) * (1 + fee_rate), (1 - slip) * (1 - fee_rate)
    if executed:
        fractions = capped_proportional_targets(capital, 1.0, cap)
        solved_wealth, iterations = _post_cost_root(capital, stock, old_cash, long, fractions,
                                                   buy_multiplier, sell_multiplier)
        targets = fractions * solved_wealth
        new_cash = np.where(long, 0.0, targets)
        new_shares = np.where(long, targets / prices, 0.0)
    else:
        solved_wealth, iterations = pre_wealth, 0
        targets = capital.copy()
        new_cash, new_shares = old_cash.copy(), old_shares.copy()
    transfers = np.zeros(n)
    ledger = []
    total_fees, total_slippage, raw_turnover = [], [], []
    for index in range(n):
        quantity_delta = float(new_shares[index] - old_shares[index])
        raw_delta = float(quantity_delta * prices[index])
        side = "BUY" if quantity_delta > 0 else ("SELL" if quantity_delta < 0 else "NONE")
        fill_price = None
        commission, slippage, trading_cash = 0.0, 0.0, 0.0
        if side != "NONE":
            fill_price = float(prices[index] * (1 + slip if side == "BUY" else 1 - slip))
            commission = float(abs(quantity_delta) * fill_price * fee_rate)
            slippage = float(abs(quantity_delta) * prices[index] * slip)
            trading_cash = float(-quantity_delta * fill_price - commission)
        if executed:
            transfers[index] = (-trading_cash - old_cash[index] if long[index]
                                else new_cash[index] - old_cash[index])
        ledger.append({"symbol": names[index], "index": index, "side": side,
                       "order_executed": side != "NONE", "quantity_delta": quantity_delta,
                       "quantity": abs(quantity_delta), "raw_price": float(prices[index]),
                       "fill_price": fill_price, "raw_market_value_delta": raw_delta,
                       "commission": commission, "fee": commission, "slippage": slippage,
                       "trading_cash_change": trading_cash, "transfer": float(transfers[index]),
                       "cash_before": float(old_cash[index]), "cash_after": float(new_cash[index]),
                       "shares_before": float(old_shares[index]), "shares_after": float(new_shares[index]),
                       "capital_before": float(capital[index]), "target_capital": float(targets[index])})
        total_fees.append(commission)
        total_slippage.append(slippage)
        raw_turnover.append(abs(raw_delta))
    post_capital = new_cash + new_shares * prices
    post_wealth = fsum(post_capital)
    fees, slippage_loss, gross_raw = fsum(total_fees), fsum(total_slippage), fsum(raw_turnover)
    total_cost = fees + slippage_loss
    cash_residual = fsum(transfers)
    wealth_residual = pre_wealth - post_wealth - total_cost
    money_tolerance = max(128 * np.finfo(float).eps * pre_wealth, 1e-12)
    if (abs(cash_residual) > money_tolerance or abs(wealth_residual) > money_tolerance
            or abs(post_wealth - solved_wealth) > money_tolerance):
        raise ArithmeticError("rebalance violates self-financing cash or post-cost wealth conservation")
    post_fractions = post_capital / post_wealth
    if (np.any(new_cash < 0) or np.any(new_shares < 0)
            or (executed and post_fractions.max() > cap + tolerance)):
        raise ArithmeticError("rebalance violates nonnegative accounts or its post-cost cap")
    for index, row in enumerate(ledger):
        row["capital_after"] = float(post_capital[index])
        row["capital_share_after"] = float(post_fractions[index])
        balance = row["cash_before"] + row["transfer"] + row["trading_cash_change"] - row["cash_after"]
        if abs(balance) > money_tolerance:
            raise ArithmeticError("a rebalance sleeve cash account does not balance")
    return {"executed": executed, "cancelled": not executed,
            "reason": "raw_open_cap_breach" if executed else "raw_open_cap_no_longer_breached",
            "cash": new_cash.copy(), "shares": new_shares.copy(),
            "pre_capital": capital.copy(), "post_capital": post_capital.copy(),
            "target_capital": targets.copy(), "pre_wealth": float(pre_wealth), "post_wealth": float(post_wealth),
            "pre_capital_shares": pre_fraction.copy(), "post_capital_shares": post_fractions.copy(),
            "pre_max_capital_share": float(pre_fraction.max()),
            "post_max_capital_share": float(post_fractions.max()),
            "cap": cap, "capital_share_tolerance": float(tolerance),
            "post_cost_cap_satisfied": bool(post_fractions.max() <= cap + tolerance),
            "cash_transfers": transfers.copy(), "order_ledger": ledger,
            "actual_orders": [dict(row) for row in ledger if row["order_executed"]],
            "commission_paid": float(fees), "slippage_paid": float(slippage_loss), "total_cost": float(total_cost),
            "gross_raw_turnover": float(gross_raw), "turnover_fraction": float(gross_raw / pre_wealth),
            "cash_conservation_residual": float(cash_residual),
            "wealth_conservation_residual": float(wealth_residual), "accounting_tolerance": float(money_tolerance),
            "bisection_iterations": iterations, "slippage_bps": float(slippage_bps),
            "commission_bps": float(commission_bps), "external_cash_added": 0.0}
