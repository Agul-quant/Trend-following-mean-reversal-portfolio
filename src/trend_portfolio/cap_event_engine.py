"""Generic canonical-event replay for separately authorized costed cap accounts.

No input files, market access, indicators, confirmation logic or optimization live
here. Confirmed normal fills and true-calendar schedule flags are external,
frozen inputs. Portfolio transfers never change the supplied signal-state trace.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import fsum
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from .cap_rebalance import rebalance_cap_at_open


NEW_YORK = ZoneInfo("America/New_York")
FREQUENCIES = ("daily", "weekly", "monthly")


def _validated(events: dict) -> dict:
    required = {"timestamps", "symbols", "cash_returns", "open_prices", "open_eligible", "close_prices",
                "split", "dividend", "fill_side", "terminal_price", "valuation_prices", "schedule_flags"}
    if not isinstance(events, dict) or required - set(events):
        raise ValueError("canonical event input is missing required fields")
    symbols = np.asarray(events["symbols"])
    times = np.asarray(events["timestamps"])
    if symbols.shape != (5,) or symbols.dtype.kind not in "US" or len(set(symbols.tolist())) != 5:
        raise ValueError("exactly five unique symbol strings are required")
    if any(not str(value) for value in symbols):
        raise ValueError("symbol names must not be empty")
    if times.ndim != 1 or len(times) < 2 or times.dtype.kind not in "US":
        raise ValueError("timestamps must be a one-dimensional string clock with at least two events")
    instants = []
    for value in times:
        try:
            instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("timestamps must be ISO-8601 instants") from error
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("timestamps must have an explicit UTC offset")
        instants.append(instant.astimezone(timezone.utc))
    if any(left >= right for left, right in zip(instants, instants[1:])):
        raise ValueError("canonical clock must be unique and strictly increasing")
    t, n = len(times), len(symbols)
    result = {"symbols": symbols.astype(str).copy(), "times": tuple(instants),
              "timestamps": np.array([instant.isoformat() for instant in instants])}
    for name in ("open_prices", "close_prices", "terminal_price", "valuation_prices"):
        values = np.asarray(events[name], dtype=float)
        if values.shape != (t, n) or np.isinf(values).any() or np.any(values[np.isfinite(values)] <= 0):
            raise ValueError(f"{name} must be positive finite quotes or NaN on the event/symbol axes")
        result[name] = values.copy()
    for name, shape in (("open_eligible", (t, n)), ("schedule_flags", (t, 3))):
        values = np.asarray(events[name])
        if values.shape != shape or values.dtype.kind != "b":
            raise ValueError(f"{name} must be a matching boolean array")
        result[name] = values.copy()
    for name in ("split", "dividend", "fill_side"):
        values = np.asarray(events[name], dtype=float)
        if values.shape != (t, n) or not np.isfinite(values).all():
            raise ValueError(f"{name} must be a finite matching event/symbol array")
        result[name] = values.copy()
    if np.any(result["split"] <= 0) or np.any(result["dividend"] < 0):
        raise ValueError("splits must be positive and cash dividends nonnegative")
    action_rows = np.any((result["split"] != 1) | (result["dividend"] != 0), axis=1)
    for index in np.flatnonzero(action_rows):
        local = instants[index].astimezone(NEW_YORK)
        if (local.hour, local.minute, local.second, local.microsecond) != (9, 30, 0, 0):
            raise ValueError("split and distribution actions require the 09:30 New York action event")
    if not np.isin(result["fill_side"], (-1, 0, 1)).all():
        raise ValueError("confirmed fill sides must be -1, 0 or +1")
    cash = np.asarray(events["cash_returns"], dtype=float)
    if cash.shape != (t,) or not np.isfinite(cash).all() or np.any(cash <= -1):
        raise ValueError("one valid matched cash return is required per unique event timestamp")
    result["cash_returns"] = cash.copy()
    eligible = result["open_eligible"]
    if np.any(eligible & ~np.isfinite(result["open_prices"])):
        raise ValueError("an eligible open must have a positive raw quote")
    if np.any((result["fill_side"] != 0) & ~eligible):
        raise ValueError("confirmed ETF fills cannot use an unsafe or missing open")
    valuations = np.isfinite(result["valuation_prices"])
    if np.any(valuations.any(axis=1) != valuations.all(axis=1)) or not valuations.any():
        raise ValueError("each daily valuation requires all five provider close marks")
    daily = valuations.all(axis=1)
    for index in np.flatnonzero(daily):
        local = instants[index].astimezone(NEW_YORK)
        if (local.hour, local.minute, local.second, local.microsecond) != (17, 0, 0, 0):
            raise ValueError("daily provider marks must occur at 17 New York, never as execution quotes")
    if np.any(eligible[daily]):
        raise ValueError("17 New York provider marks cannot be eligible execution opens")
    if (not np.array_equal(result["schedule_flags"][:, 0], daily)
            or np.any(result["schedule_flags"].any(axis=1) & ~daily)):
        raise ValueError("calendar schedule flags must identify provider valuation events only")
    terminal = np.isfinite(result["terminal_price"])
    if not np.all(terminal.sum(axis=0) == 1):
        raise ValueError("each ETF requires exactly one explicitly supplied terminal close")
    if np.any(terminal & ~np.isfinite(result["close_prices"])) or not np.allclose(
        result["terminal_price"][terminal], result["close_prices"][terminal], rtol=1e-12, atol=1e-12
    ):
        raise ValueError("terminal execution prices must match native observed close quotes")
    for sleeve in range(n):
        end = int(np.flatnonzero(terminal[:, sleeve])[0])
        if (np.any(eligible[end:, sleeve]) or np.any(result["fill_side"][end:, sleeve] != 0)
                or np.isfinite(result["close_prices"][end + 1:, sleeve]).any()):
            raise ValueError("native opens, fills or closes cannot follow that ETF's terminal close")
        if int(np.flatnonzero(daily)[-1]) < end:
            raise ValueError("the final daily valuation cannot precede terminal liquidation")
    if "signal_long_after_open" in events:
        expected = np.asarray(events["signal_long_after_open"])
        if expected.shape != (t, n) or expected.dtype.kind != "b":
            raise ValueError("optional signal trace must be a matching boolean array")
        result["signal_long_after_open"] = expected.copy()
    return result


def simulate_cap_events(
    events: dict, initial_weights: Any, *, frequency: str = "none", slippage_bps: float,
    commission_bps: float = 1, initial_cash: float = 1000, cap: float = 1 / 3,
    record_event_state: bool = True,
) -> dict[str, Any]:
    """Replay fresh independent accounts using synchronized event phases.

    Cash compounds once per unique timestamp. A preceding scheduled 17 NY breach
    queues at most one portfolio intent. It can execute only at a later jointly
    eligible raw open AFTER all ordinary ETF fills; it is reassessed then. No
    close mark, final partial calendar period, or assumed intraday cap is invented.
    """
    source = _validated(events)
    if frequency not in {"none", *FREQUENCIES}:
        raise ValueError("frequency must be none, daily, weekly or monthly")
    weights = np.asarray(initial_weights, dtype=float)
    if (weights.shape != (5,) or not np.isfinite(weights).all() or np.any(weights < 0)
            or not np.isclose(fsum(weights), 1, rtol=0, atol=1e-10)):
        raise ValueError("initial weights must be five nonnegative finite fractions summing to one")
    if isinstance(initial_cash, bool) or not np.isfinite(initial_cash) or initial_cash <= 0:
        raise ValueError("fresh initial capital must be finite and positive")
    if isinstance(cap, bool) or not np.isfinite(cap) or not 0 < cap <= 1 or 5 * cap < 1:
        raise ValueError("capital cap must be feasible for five sleeves")
    for value in (slippage_bps, commission_bps):
        if isinstance(value, bool) or not np.isfinite(value) or not 0 <= value < 10000:
            raise ValueError("one-way slippage and commission bps must be in [0,10000)")
    if not isinstance(record_event_state, bool):
        raise ValueError("record_event_state must be boolean")
    cash = weights.copy() * initial_cash
    shares, dividend_cash = np.zeros(5), np.zeros(5)
    logical_long, terminated = np.zeros(5, bool), np.zeros(5, bool)
    slip, fee = float(slippage_bps) / 10000, float(commission_bps) / 10000
    symbols = source["symbols"].tolist()
    pending = None
    cash_reference = float(initial_cash)
    observed_max_share = None
    daily_times, daily_equity, daily_sleeves, daily_cash = [], [], [], []
    daily_long, daily_market_value, daily_exposure = [], [], []
    ledger, drips, rebals = [], [], []
    counters = {key: 0 for key in (
        "checks", "triggers", "intents_queued", "pending_checks_preserved", "actualexec", "gapcancel",
        "terminalcancel", "paid_strategy_entries", "paid_strategy_exits", "paid_terminal_exits",
        "paid_rebalance_orders", "strategy_round_trips", "terminal_round_trips", "dividend_reinvestments")}
    trade_counts = {symbol: {key: 0 for key in ("strategy_entries", "strategy_exits", "terminal_exits",
                                               "rebalance_partial_orders", "strategy_round_trips", "terminal_round_trips")}
                    for symbol in symbols}
    event_cash, event_shares, event_dividends, event_long, event_pending = [], [], [], [], []
    open_capital_shares = np.full((len(source["times"]), 5), np.nan)
    post_open_capital_shares = np.full_like(open_capital_shares, np.nan)

    def observe_common_open(event_index: int, prices: np.ndarray, *, after: bool):
        nonlocal observed_max_share
        capital = cash + shares * prices
        fractions = capital / fsum(capital)
        (post_open_capital_shares if after else open_capital_shares)[event_index] = fractions
        share = float(fractions.max())
        observed_max_share = share if observed_max_share is None else max(observed_max_share, share)

    def order(index: int, quantity_delta: float, raw_price: float, reason: str, event_index: int):
        if quantity_delta == 0:
            return
        side = "BUY" if quantity_delta > 0 else "SELL"
        fill = raw_price * (1 + slip if quantity_delta > 0 else 1 - slip)
        commission = abs(quantity_delta) * fill * fee
        ledger.append({"timestamp": str(source["timestamps"][event_index]), "event_index": event_index,
                       "symbol": symbols[index], "index": index, "reason": reason, "side": side,
                       "quantity_delta": float(quantity_delta), "quantity": float(abs(quantity_delta)),
                       "raw_price": float(raw_price), "fill_price": float(fill),
                       "commission": float(commission), "fee": float(commission),
                       "slippage": float(abs(quantity_delta) * raw_price * slip),
                       "raw_market_value_delta": float(quantity_delta * raw_price)})

    for event_index, instant in enumerate(source["times"]):
        timestamp = str(source["timestamps"][event_index])
        # One clock tick, including the earmark tracker which is already PART of cash.
        growth = 1 + source["cash_returns"][event_index]
        cash *= growth
        dividend_cash *= growth
        cash_reference *= growth
        # Phase 0: completed native close quotes and paid terminal liquidation.
        for index in np.flatnonzero(np.isfinite(source["terminal_price"][event_index])):
            raw = source["terminal_price"][event_index, index]
            if terminated[index]:
                raise ValueError("an ETF cannot be terminally liquidated twice")
            if shares[index] > 0:
                order(index, -shares[index], raw, "terminal_liquidation", event_index)
                cash[index] += shares[index] * raw * (1 - slip) * (1 - fee)
                counters["paid_terminal_exits"] += 1
                trade_counts[symbols[index]]["terminal_exits"] += 1
            if logical_long[index]:
                counters["terminal_round_trips"] += 1
                trade_counts[symbols[index]]["terminal_round_trips"] += 1
            shares[index], dividend_cash[index], logical_long[index], terminated[index] = 0, 0, False, True
        # Phase 3: source actions on post-split raw shares; earmark is not extra wealth.
        shares *= source["split"][event_index]
        distributions = shares * source["dividend"][event_index]
        cash += distributions
        dividend_cash += distributions
        # Phase 4a: fee-free original DRIP proxy, only at the sleeve's eligible open.
        eligible = source["open_eligible"][event_index] & ~terminated
        opens = source["open_prices"][event_index]
        for index in np.flatnonzero(eligible & logical_long & (dividend_cash > 0)):
            amount = min(float(dividend_cash[index]), float(cash[index]))
            shares[index] += amount / opens[index]
            cash[index] -= amount
            dividend_cash[index] = 0
            drips.append({"timestamp": timestamp, "event_index": event_index, "symbol": symbols[index],
                          "raw_price": float(opens[index]), "cash_reinvested": amount,
                          "quantity": float(amount / opens[index]), "commission": 0.0, "slippage": 0.0})
            counters["dividend_reinvestments"] += 1
        # Phase 4b: finish ALL independent ordinary fills before portfolio transfers.
        for index in np.flatnonzero(source["fill_side"][event_index] != 0):
            side = source["fill_side"][event_index, index]
            if not eligible[index]:
                raise ValueError("normal strategy fill is not eligible at this open")
            raw = opens[index]
            if side > 0:
                if logical_long[index] or shares[index] != 0:
                    raise ValueError("confirmed entry requires a logically flat sleeve")
                quantity = cash[index] / (raw * (1 + slip) * (1 + fee))
                order(index, quantity, raw, "strategy_entry", event_index)
                shares[index] = quantity
                cash[index], dividend_cash[index], logical_long[index] = 0, 0, True
                if quantity > 0:
                    counters["paid_strategy_entries"] += 1
                    trade_counts[symbols[index]]["strategy_entries"] += 1
            else:
                if not logical_long[index]:
                    raise ValueError("confirmed exit requires a logically long sleeve")
                quantity = shares[index]
                order(index, -quantity, raw, "strategy_exit", event_index)
                cash[index] += quantity * raw * (1 - slip) * (1 - fee)
                shares[index], dividend_cash[index], logical_long[index] = 0, 0, False
                counters["strategy_round_trips"] += 1
                trade_counts[symbols[index]]["strategy_round_trips"] += 1
                if quantity > 0:
                    counters["paid_strategy_exits"] += 1
                    trade_counts[symbols[index]]["strategy_exits"] += 1
        if ("signal_long_after_open" in source
                and not np.array_equal(logical_long, source["signal_long_after_open"][event_index])):
            raise ValueError("costed account departed from the original independent logical signal trace")
        if eligible.all():
            observe_common_open(event_index, opens, after=False)
        # Phase 4c: only a PRECEDING scheduled check may authorize a common safe open.
        if pending is not None and eligible.all():
            if instant <= pending["instant"]:
                raise ValueError("portfolio intent must precede its eligible execution open")
            result = rebalance_cap_at_open(cash, shares, opens, logical_long, slippage_bps=slippage_bps,
                                           commission_bps=commission_bps, cap=cap, symbols=symbols)
            cash, shares = result["cash"].copy(), result["shares"].copy()
            dividend_cash[:] = 0
            decision = "execute" if result["executed"] else "gap_cancel"
            rebals.append({"timestamp": timestamp, "event_index": event_index,
                           "queued_at": pending["timestamp"], "decision": decision, "allocator": result})
            counters["actualexec" if result["executed"] else "gapcancel"] += 1
            for raw_order in result["actual_orders"]:
                index = raw_order["index"]
                order(index, raw_order["quantity_delta"], raw_order["raw_price"], "cap_rebalance", event_index)
                counters["paid_rebalance_orders"] += 1
                trade_counts[symbols[index]]["rebalance_partial_orders"] += 1
            pending = None
        if eligible.all():
            observe_common_open(event_index, opens, after=True)
        # Phase 5: provider marks value accounts; they never act as execution quotes.
        valuation = source["valuation_prices"][event_index]
        if np.isfinite(valuation).all():
            capital = cash + shares * valuation
            wealth = fsum(capital)
            daily_times.append(timestamp)
            daily_equity.append(wealth)
            daily_sleeves.append(capital.copy())
            daily_cash.append(cash_reference)
            daily_long.append(logical_long.copy())
            market = shares * valuation
            daily_market_value.append(market.copy())
            daily_exposure.append(market / wealth)
            if frequency != "none" and source["schedule_flags"][event_index, FREQUENCIES.index(frequency)]:
                counters["checks"] += 1
                if float(capital.max() / wealth) > cap + 1e-10:
                    counters["triggers"] += 1
                    if pending is None:
                        pending = {"instant": instant, "timestamp": timestamp}
                        counters["intents_queued"] += 1
                    else:
                        counters["pending_checks_preserved"] += 1
        if (not np.isfinite(cash).all() or not np.isfinite(shares).all()
                or np.any(cash < 0) or np.any(shares < 0) or np.any(shares[~logical_long] != 0)
                or np.any(dividend_cash < 0) or np.any(dividend_cash > cash + 1e-9)):
            raise ArithmeticError("event account violated finite nonnegative cash, shares or earmark accounting")
        if record_event_state:
            event_cash.append(cash.copy())
            event_shares.append(shares.copy())
            event_dividends.append(dividend_cash.copy())
            event_long.append(logical_long.copy())
            event_pending.append(pending is not None)
    if not terminated.all() or np.any(shares != 0) or logical_long.any():
        raise ValueError("all five stage accounts must finish with paid terminal conventions and flat state")
    if pending is not None:
        counters["terminalcancel"] += 1
        rebals.append({"timestamp": str(source["timestamps"][-1]), "event_index": len(source["times"]) - 1,
                       "queued_at": pending["timestamp"], "decision": "terminal_cancel"})
    commissions = fsum(row["commission"] for row in ledger)
    slippages = fsum(row["slippage"] for row in ledger)
    turnover = fsum(abs(row["raw_market_value_delta"]) for row in ledger)
    output = {"timestamps": np.array(daily_times), "portfolio_equity": np.array(daily_equity),
              "sleeve_equity": np.array(daily_sleeves), "cash_reference": np.array(daily_cash),
              "daily_long": np.array(daily_long), "daily_etf_exposure": np.array(daily_exposure),
              "daily_etf_market_value": np.array(daily_market_value), "ledger": ledger,
              "dividend_reinvestment_ledger": drips, "rebal_event_list": rebals, "counters": counters,
              "trade_counts_by_symbol": trade_counts, "commission_paid": commissions,
              "slippage_paid": slippages, "total_cost": commissions + slippages,
              "gross_raw_turnover": turnover, "turnover_fraction_of_initial": turnover / initial_cash,
              "final_cash": cash.copy(), "final_shares": shares.copy(), "final_logical_long": logical_long.copy(),
              "final_pending_intent": False,
              "event_state_timing": "after phase5 before stage-end terminal-intent cleanup",
              "initial_cash": float(initial_cash), "initial_weights": weights.copy(), "symbols": source["symbols"].copy(),
              "frequency": frequency, "cap": float(cap), "slippage_bps": float(slippage_bps),
              "commission_bps": float(commission_bps), "observed_quote_max_capital_share": observed_max_share,
              "round_trip_count_basis": "logical normal exits; terminal closes separate; cap partial orders excluded",
              "observed_quote_scope": "joint safe opens after ordinary fills, before and after portfolio reassessment",
              "event_open_capital_shares": open_capital_shares,
              "event_post_open_capital_shares": post_open_capital_shares,
              "continuous_cap_guarantee": False}
    if record_event_state:
        output.update({"event_cash": np.array(event_cash), "event_shares": np.array(event_shares),
                       "event_dividend": np.array(event_dividends), "event_long": np.array(event_long),
                       "event_pending_intent": np.array(event_pending, dtype=bool)})
    return output
