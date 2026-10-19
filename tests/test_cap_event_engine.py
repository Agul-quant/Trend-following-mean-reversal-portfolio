"""Pure generated canonical clocks; no saved source events or market prices."""
from datetime import datetime, timedelta
from math import fsum
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from trend_portfolio.cap_event_engine import simulate_cap_events


NY = ZoneInfo("America/New_York")


def fixture(days=3, start="2024-01-02", first_entries=True):
    first = datetime.fromisoformat(start)
    instants = []
    for day in range(days):
        date = first + timedelta(days=day)
        for hour, minute in ((9, 30), (10, 0), (16, 0), (17, 0)):
            instant = datetime(date.year, date.month, date.day, hour, minute, tzinfo=NY)
            instants.append(instant.isoformat())
    n = len(instants)
    events = {"timestamps": np.array(instants), "symbols": np.array(["GDX", "FXI", "QQQ", "UNG", "FDN"]),
              "cash_returns": np.zeros(n), "open_prices": np.full((n, 5), np.nan),
              "open_eligible": np.zeros((n, 5), bool), "close_prices": np.full((n, 5), np.nan),
              "split": np.ones((n, 5)), "dividend": np.zeros((n, 5)), "fill_side": np.zeros((n, 5), int),
              "terminal_price": np.full((n, 5), np.nan), "valuation_prices": np.full((n, 5), np.nan),
              "schedule_flags": np.zeros((n, 3), bool)}
    for day in range(days):
        for position in (0, 1):
            index = day * 4 + position
            events["open_prices"][index] = 100
            events["open_eligible"][index] = True
        events["close_prices"][day * 4 + 1] = 100  # Completed bar and next open share a clock tick.
        events["close_prices"][day * 4 + 2] = 100
        events["valuation_prices"][day * 4 + 3] = 100
        events["schedule_flags"][day * 4 + 3, 0] = True
    events["terminal_price"][-2] = 100
    if first_entries:
        events["fill_side"][0] = 1
    return events


def trace(events):
    long = np.zeros(5, bool)
    expected = []
    for row in range(len(events["timestamps"])):
        long[np.isfinite(events["terminal_price"][row])] = False
        long[events["fill_side"][row] > 0] = True
        long[events["fill_side"][row] < 0] = False
        expected.append(long.copy())
    events["signal_long_after_open"] = np.array(expected)
    return events


def overweight(events, start_row=2, price=300):
    for field in ("open_prices", "close_prices", "valuation_prices", "terminal_price"):
        mask = np.isfinite(events[field][start_row:, 0])
        events[field][start_row:, 0][mask] = price
    return events


def run(events, frequency="none", **kwargs):
    return simulate_cap_events(events, [.2] * 5, frequency=frequency,
                               slippage_bps=kwargs.pop("slippage_bps", 3), **kwargs)


def test_fresh_stage_all_in_entries_and_paid_terminal_once_without_rebalancing():
    events = trace(fixture())
    result = run(events)
    a_buy, a_sell = 1.0003 * 1.0001, .9997 * .9999
    np.testing.assert_allclose(result["portfolio_equity"], [1000 / a_buy, 1000 / a_buy, 1000 / a_buy * a_sell])
    assert result["counters"]["paid_strategy_entries"] == 5
    assert result["counters"]["paid_terminal_exits"] == 5
    assert result["counters"]["paid_rebalance_orders"] == 0
    assert len(result["ledger"]) == 10
    assert len([row for row in result["ledger"] if row["reason"] == "terminal_liquidation"]) == 5
    assert not result["final_logical_long"].any() and np.all(result["final_shares"] == 0)
    assert result["portfolio_equity"][-1] == pytest.approx(fsum(result["final_cash"]))
    assert result["counters"]["checks"] == 0


def test_cash_accrues_once_on_shared_bar_close_and_open_event_clock():
    events = trace(fixture(first_entries=False))
    events["cash_returns"] = np.arange(len(events["timestamps"])) / 100000
    result = run(events)
    full = 1000 * np.cumprod(1 + events["cash_returns"])
    np.testing.assert_allclose(result["cash_reference"], full[[3, 7, 11]])
    np.testing.assert_allclose(result["portfolio_equity"], result["cash_reference"])
    assert result["ledger"] == []


def test_scheduled_daily_close_queues_but_executes_only_at_following_safe_open():
    events = trace(overweight(fixture()))
    result = run(events, "daily")
    executions = [row for row in result["rebal_event_list"] if row["decision"] == "execute"]
    assert len(executions) == 1
    assert executions[0]["event_index"] == 4 and executions[0]["queued_at"] == "2024-01-02T22:00:00+00:00"
    assert executions[0]["timestamp"] == "2024-01-03T14:30:00+00:00"
    assert result["event_pending_intent"][3] and not result["event_pending_intent"][4]
    assert result["event_open_capital_shares"][4].max() > 1 / 3
    assert result["event_post_open_capital_shares"][4].max() <= 1 / 3 + 1e-10
    assert np.isnan(result["event_open_capital_shares"][3]).all()  # Provider mark is not an execution.
    assert all(row["event_index"] != 3 for row in result["ledger"])
    np.testing.assert_array_equal(result["event_long"], events["signal_long_after_open"])


def test_fresh_open_gap_cancels_preceding_close_breach_without_fees():
    events = overweight(fixture(), start_row=2)
    for field in ("open_prices", "close_prices", "valuation_prices", "terminal_price"):
        mask = np.isfinite(events[field][4:, 0])
        events[field][4:, 0][mask] = 100
    result = run(trace(events), "daily")
    assert result["counters"]["gapcancel"] == 1 and result["counters"]["actualexec"] == 0
    assert len(result["ledger"]) == 10
    first = result["rebal_event_list"][0]
    assert first["decision"] == "gap_cancel" and first["allocator"]["total_cost"] == 0


def test_pending_intent_defers_until_all_five_same_open_quotes_are_safe():
    events = overweight(fixture())
    events["open_eligible"][4, 4] = False
    events["open_prices"][4, 4] = np.nan
    result = run(trace(events), "daily")
    assert result["event_pending_intent"][4]
    assert np.isnan(result["event_open_capital_shares"][4]).all()
    assert result["rebal_event_list"][0]["event_index"] == 5


def test_normal_strategy_fills_finish_before_separate_paid_cap_orders_no_netting():
    events = overweight(fixture(first_entries=False))
    events["fill_side"][0, 0] = 1
    events["fill_side"][4, 1] = 1
    result = run(trace(events), "daily")
    orders = [row for row in result["ledger"] if row["event_index"] == 4]
    assert orders[0]["reason"] == "strategy_entry" and orders[0]["symbol"] == "FXI"
    fxi = [row for row in orders if row["symbol"] == "FXI"]
    assert len(fxi) == 2 and fxi[1]["reason"] == "cap_rebalance"
    assert all(row["commission"] > 0 for row in fxi)
    assert not result["event_long"][4, 2:].any()  # Flat recipients receive cash, never forced ETF entries.
    assert np.all(result["event_shares"][4, 2:] == 0)


def test_split_dividend_drip_precedes_normal_exit_and_is_not_double_counted():
    events = fixture()
    events["split"][4, 0] = 2
    events["dividend"][4, 0] = 1
    events["fill_side"][4, 0] = -1
    for field in ("open_prices", "close_prices", "valuation_prices", "terminal_price"):
        mask = np.isfinite(events[field][4:, 0])
        events[field][4:, 0][mask] = 50
    result = run(trace(events))
    initial_quantity = 200 / (100 * 1.0003 * 1.0001)
    dividend = 2 * initial_quantity
    drip_quantity = dividend / 50
    drip = result["dividend_reinvestment_ledger"][0]
    assert drip["cash_reinvested"] == pytest.approx(dividend)
    assert drip["quantity"] == pytest.approx(drip_quantity)
    exit_order = next(row for row in result["ledger"] if row["reason"] == "strategy_exit")
    assert exit_order["quantity"] == pytest.approx(2 * initial_quantity + drip_quantity)
    expected_cash = (2 * initial_quantity + drip_quantity) * 50 * .9997 * .9999
    assert result["event_cash"][4, 0] == pytest.approx(expected_cash)
    assert result["event_dividend"][4, 0] == 0
    assert result["counters"]["paid_terminal_exits"] == 4
    assert result["counters"]["strategy_round_trips"] == 1


def test_dividend_earmark_accrues_with_cash_but_remains_part_of_cash_until_safe_drip():
    events = fixture()
    events["dividend"][4, 0] = 1
    events["open_eligible"][4, 0] = False
    events["open_prices"][4, 0] = np.nan
    events["cash_returns"][5] = .01
    result = run(trace(events))
    quantity = 200 / (100 * 1.0003 * 1.0001)
    assert result["event_cash"][4, 0] == pytest.approx(quantity)
    assert result["event_dividend"][4, 0] == pytest.approx(quantity)
    assert result["dividend_reinvestment_ledger"][0]["cash_reinvested"] == pytest.approx(quantity * 1.01)
    assert result["event_dividend"][5, 0] == 0 and result["event_cash"][5, 0] == pytest.approx(0)


@pytest.mark.parametrize("frequency,column", [("weekly", 1), ("monthly", 2)])
def test_only_supplied_true_calendar_flags_trigger_no_invented_partial_period(frequency, column):
    events = trace(overweight(fixture()))
    result = run(events, frequency)
    assert result["counters"]["checks"] == 0 and result["rebal_event_list"] == []
    events["schedule_flags"][3, column] = True
    result = run(events, frequency)
    assert result["counters"]["checks"] == 1 and result["counters"]["actualexec"] == 1


def test_october_fourteen_pending_can_execute_october_fifteen_before_terminal_close():
    events = trace(overweight(fixture(start="2026-10-13"), start_row=6))
    result = run(events, "daily")
    row = next(row for row in result["rebal_event_list"] if row["decision"] == "execute")
    assert row["queued_at"] == "2026-10-14T21:00:00+00:00"
    assert row["timestamp"] == "2026-10-15T13:30:00+00:00"
    assert row["event_index"] == 8
    assert all(order["event_index"] == 10 for order in result["ledger"] if order["reason"] == "terminal_liquidation")


def test_terminal_cancels_unfilled_portfolio_intent_but_does_not_duplicate_liquidation():
    events = overweight(fixture())
    events["open_eligible"][4:, 4] = False
    events["open_prices"][4:, 4] = np.nan
    result = run(trace(events), "daily")
    assert result["counters"]["actualexec"] == 0
    assert result["counters"]["terminalcancel"] == 1
    assert result["counters"]["pending_checks_preserved"] >= 1
    assert result["rebal_event_list"][-1]["decision"] == "terminal_cancel"
    assert result["counters"]["paid_terminal_exits"] == 5
    assert result["event_pending_intent"][-1]  # Snapshot precedes explicit stage-end cleanup.
    assert result["final_pending_intent"] is False
    assert "before stage-end" in result["event_state_timing"]


def test_all_cash_cap_transfers_have_zero_exchange_trades_or_fees():
    events = trace(fixture(first_entries=False))
    result = simulate_cap_events(events, [.5, .2, .1, .1, .1], frequency="daily", slippage_bps=25)
    assert result["counters"]["actualexec"] == 1 and result["ledger"] == []
    assert result["total_cost"] == 0 and not result["daily_long"].any()
    np.testing.assert_allclose(result["portfolio_equity"], 1000)
    assert result["event_post_open_capital_shares"][4].max() <= 1 / 3 + 1e-10


def test_none_mode_does_not_rebalance_overweight_accounts():
    events = trace(overweight(fixture()))
    result = run(events)
    assert result["counters"]["checks"] == 0 and result["rebal_event_list"] == []
    assert (result["sleeve_equity"][0] / result["portfolio_equity"][0]).max() > 1 / 3


def test_inputs_unmodified_and_optional_full_event_state_can_be_disabled():
    events = trace(overweight(fixture()))
    before = {key: value.copy() for key, value in events.items()}
    result = run(events, "daily", record_event_state=False)
    assert "event_cash" not in result and "event_shares" not in result
    assert result["event_open_capital_shares"].shape == (12, 5)
    for key in events:
        np.testing.assert_array_equal(events[key], before[key])


@pytest.mark.parametrize("mutation", ["missing", "duplicate_clock", "naive_clock", "zero_open", "unsafe_fill",
    "valuation_execution", "partial_mark", "wrong_mark_time", "missing_terminal", "duplicate_terminal",
    "wrong_terminal_price", "cash_factor", "bad_state_trace", "flag_not_mark", "negative_dividend", "wrong_action_time"])
def test_malformed_events_rejected(mutation):
    events = trace(fixture())
    if mutation == "missing":
        del events["close_prices"]
    elif mutation == "duplicate_clock":
        events["timestamps"][1] = events["timestamps"][0]
    elif mutation == "naive_clock":
        events["timestamps"][0] = "2024-01-02T09:30:00"
    elif mutation == "zero_open":
        events["open_prices"][0, 0] = 0
    elif mutation == "unsafe_fill":
        events["open_eligible"][0, 0] = False
    elif mutation == "valuation_execution":
        events["open_eligible"][3] = True
        events["open_prices"][3] = 100
    elif mutation == "partial_mark":
        events["valuation_prices"][3, 0] = np.nan
    elif mutation == "wrong_mark_time":
        events["timestamps"][3] = "2024-01-02T16:59:00-05:00"
    elif mutation == "missing_terminal":
        events["terminal_price"][-2, 0] = np.nan
    elif mutation == "duplicate_terminal":
        events["terminal_price"][1, 0] = 100
    elif mutation == "wrong_terminal_price":
        events["terminal_price"][-2, 0] = 99
    elif mutation == "cash_factor":
        events["cash_returns"][1] = -1
    elif mutation == "bad_state_trace":
        events["signal_long_after_open"][1, 0] = False
    elif mutation == "flag_not_mark":
        events["schedule_flags"][1, 1] = True
    elif mutation == "negative_dividend":
        events["dividend"][4, 0] = -1
    else:
        events["dividend"][1, 0] = 1
    with pytest.raises(ValueError):
        run(events)


@pytest.mark.parametrize("kwargs", [{"frequency": "hourly"}, {"initial_cash": 0}, {"cap": .1},
    {"slippage_bps": 10000}, {"commission_bps": -1}, {"record_event_state": 1}])
def test_invalid_account_options_rejected(kwargs):
    defaults = {"frequency": "none", "slippage_bps": 3}
    defaults.update(kwargs)
    with pytest.raises(ValueError):
        simulate_cap_events(trace(fixture()), [.2] * 5, **defaults)


def test_paid_cost_and_turnover_totals_are_exact_ledger_sums():
    result = run(trace(overweight(fixture())), "daily", slippage_bps=25)
    assert result["commission_paid"] == fsum(row["commission"] for row in result["ledger"])
    assert result["slippage_paid"] == fsum(row["slippage"] for row in result["ledger"])
    assert result["gross_raw_turnover"] == fsum(abs(row["raw_market_value_delta"]) for row in result["ledger"])
    assert result["counters"]["strategy_round_trips"] == 0
    assert result["counters"]["terminal_round_trips"] == 5
    assert all(row["strategy_entries"] == 1 and row["terminal_exits"] == 1
               for row in result["trade_counts_by_symbol"].values())
