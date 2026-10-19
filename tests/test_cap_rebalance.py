"""Synthetic account identities only; no historical prices or trading engine."""
from math import fsum

import numpy as np
import pytest

from trend_portfolio.cap_rebalance import capped_proportional_targets, rebalance_cap_at_open


def all_long(capital=(500, 200, 100, 100, 100), **kwargs):
    n = len(capital)
    return rebalance_cap_at_open(np.zeros(n), np.array(capital) / 100, np.full(n, 100),
                                 np.ones(n, dtype=bool), slippage_bps=kwargs.pop("slippage_bps", 3), **kwargs)


def assert_accounting(result):
    tolerance = result["accounting_tolerance"]
    assert fsum(result["cash_transfers"]) == pytest.approx(0, abs=tolerance)
    assert result["pre_wealth"] - result["post_wealth"] == pytest.approx(result["total_cost"], abs=tolerance)
    assert result["external_cash_added"] == 0
    assert result["post_max_capital_share"] <= result["cap"] + result["capital_share_tolerance"]
    assert np.all(result["cash"] >= 0) and np.all(result["shares"] >= 0)
    assert result["total_cost"] == pytest.approx(result["commission_paid"] + result["slippage_paid"])
    for row in result["order_ledger"]:
        assert (row["cash_before"] + row["transfer"] + row["trading_cash_change"]
                == pytest.approx(row["cash_after"], abs=tolerance))


def test_proportional_waterfill_preserves_uncapped_ratios_and_total():
    values = np.array([500, 200, 100, 100, 100])
    before = values.copy()
    result = capped_proportional_targets(values, 999, 1 / 3)
    np.testing.assert_allclose(result, [333, 266.4, 133.2, 133.2, 133.2])
    assert fsum(result) == pytest.approx(999)
    np.testing.assert_array_equal(values, before)


def test_multiple_oversized_sleeves_and_cascading_caps():
    result = capped_proportional_targets([400, 300, 100, 100, 100], 990, .25)
    np.testing.assert_allclose(result, [247.5, 247.5, 165, 165, 165])
    # With three positive sleeves and a one-third cap, all finish at one-third.
    result = capped_proportional_targets([900, 90, 10], 999)
    np.testing.assert_allclose(result, [333, 333, 333])


def test_zero_capital_is_not_implicitly_funded():
    np.testing.assert_allclose(capped_proportional_targets([6, 2, 1, 1, 0], 90), [30, 30, 15, 15, 0])
    with pytest.raises(ValueError, match="positive-capital"):
        capped_proportional_targets([9, 1, 0, 0, 0], 100)


def test_costs_apply_only_to_actual_partial_trades_and_post_cost_cap():
    result = all_long(symbols=["A", "B", "C", "D", "E"])
    assert result["executed"] and not result["cancelled"]
    assert_accounting(result)
    assert result["post_wealth"] < 1000
    assert result["post_capital"][0] == pytest.approx(result["post_wealth"] / 3)
    assert 160 < result["gross_raw_turnover"] < 400  # Not liquidation/rebuy of all $1,000.
    assert all(row["shares_after"] > 0 for row in result["order_ledger"])
    assert result["order_ledger"][0]["side"] == "SELL"
    assert all(row["side"] == "BUY" for row in result["order_ledger"][1:])
    for row in result["actual_orders"]:
        sign = 1 if row["side"] == "BUY" else -1
        assert row["fill_price"] == pytest.approx(row["raw_price"] * (1 + sign * .0003))
        assert row["commission"] == pytest.approx(abs(row["quantity_delta"]) * row["fill_price"] * .0001)
        assert row["slippage"] == pytest.approx(abs(row["quantity_delta"]) * row["raw_price"] * .0003)


def test_gap_cancellation_does_not_reinvest_long_cash_or_touch_inputs():
    cash = np.array([10., 0, 0, 0, 0])
    shares = np.array([1., 1.1, 1.2, 1.3, 1.4])
    quotes = np.full(5, 100.)
    long = np.ones(5, dtype=bool)
    copies = [value.copy() for value in (cash, shares, quotes, long)]
    result = rebalance_cap_at_open(cash, shares, quotes, long, slippage_bps=25)
    assert result["cancelled"] and not result["executed"]
    np.testing.assert_array_equal(result["cash"], cash)
    np.testing.assert_array_equal(result["shares"], shares)
    assert result["actual_orders"] == [] and result["total_cost"] == 0
    assert result["gross_raw_turnover"] == 0 and result["bisection_iterations"] == 0
    for original, before in zip((cash, shares, quotes, long), copies):
        np.testing.assert_array_equal(original, before)
    # Output arrays are independent, including a cancelled request.
    result["cash"][0] = 123
    assert cash[0] == 10


def test_logical_flat_sleeves_receive_cash_not_fabricated_stock_positions():
    cash = np.array([0., 200, 0, 100, 0])
    shares = np.array([5., 0, 1, 0, 1])
    long = np.array([True, False, True, False, True])
    result = rebalance_cap_at_open(cash, shares, np.full(5, 100), long, slippage_bps=10)
    assert_accounting(result)
    assert np.all(result["shares"][~long] == 0)
    assert np.all(result["cash"][long] == 0)
    assert np.all(result["cash"][~long] > cash[~long])
    assert all(not row["order_executed"] for row in result["order_ledger"] if not long[row["index"]])
    np.testing.assert_array_equal(long, [True, False, True, False, True])


def test_general_unearmarked_long_cash_uses_same_self_financing_equation():
    cash = np.array([40., 20, 10, 0, 0])
    shares = np.array([4.6, 1.8, .9, 1, 1])
    result = rebalance_cap_at_open(cash, shares, np.full(5, 100), np.ones(5, bool), slippage_bps=3)
    assert_accounting(result)
    np.testing.assert_array_equal(result["cash"], np.zeros(5))
    for row in result["order_ledger"]:
        a = (1 + .0003) * (1 + .0001) if row["quantity_delta"] >= 0 else (1 - .0003) * (1 - .0001)
        expected = row["raw_market_value_delta"] * a - row["cash_before"]
        assert row["transfer"] == pytest.approx(expected)


def test_all_cash_redistribution_has_no_exchange_trades_or_costs():
    cash = np.array([500., 200, 100, 100, 100])
    result = rebalance_cap_at_open(cash, np.zeros(5), np.full(5, 100), np.zeros(5, bool), slippage_bps=25)
    assert result["executed"] and result["actual_orders"] == []
    assert_accounting(result)
    assert result["post_wealth"] == pytest.approx(1000) and result["total_cost"] == 0
    assert result["gross_raw_turnover"] == 0


def test_frictionless_reallocation_has_no_wealth_loss():
    result = all_long(slippage_bps=0, commission_bps=0)
    assert_accounting(result)
    np.testing.assert_allclose(result["post_capital"], [1000 / 3, 800 / 3, 400 / 3, 400 / 3, 400 / 3])
    assert result["pre_wealth"] == pytest.approx(result["post_wealth"])
    assert result["total_cost"] == 0


def test_multioverweight_final_cap_uses_post_not_pre_cost_wealth():
    result = all_long((400, 300, 100, 100, 100), cap=.25, slippage_bps=25)
    assert_accounting(result)
    assert len([row for row in result["actual_orders"] if row["side"] == "SELL"]) == 2
    assert result["post_capital"][0] == pytest.approx(.25 * result["post_wealth"])
    assert result["post_capital"][1] == pytest.approx(.25 * result["post_wealth"])
    assert result["post_capital"][0] < 250  # A pre-cost $250 target would breach after paying fees.


@pytest.mark.parametrize("slippage", [0, 1, 3, 10, 25, 100])
def test_cost_scenarios_self_finance_and_charge_correct_increment(slippage):
    result = all_long(slippage_bps=slippage)
    assert_accounting(result)
    assert result["slippage_paid"] == pytest.approx(result["gross_raw_turnover"] * slippage / 10000)


def test_costs_reduce_post_wealth_monotonically_without_external_cash():
    results = [all_long(slippage_bps=cost) for cost in (1, 3, 10, 25)]
    assert all(left["post_wealth"] > right["post_wealth"] for left, right in zip(results, results[1:]))
    assert all(result["external_cash_added"] == 0 for result in results)


@pytest.mark.parametrize("mutation", ["zeroquote", "negativequote", "nanquote", "negativecash", "negativeshares",
    "flatshares", "badcap", "infeasiblecap", "badslip", "badfee", "badstate", "zeros", "badsymbols"])
def test_malformed_or_infeasible_accounts_rejected(mutation):
    cash, shares, prices, long = np.zeros(5), np.array([5., 2, 1, 1, 1]), np.full(5, 100.), np.ones(5, bool)
    kwargs = {"slippage_bps": 3}
    if mutation == "zeroquote":
        prices[0] = 0
    elif mutation == "negativequote":
        prices[0] = -1
    elif mutation == "nanquote":
        prices[0] = np.nan
    elif mutation == "negativecash":
        cash[1] = -.001
    elif mutation == "negativeshares":
        shares[1] = -.001
    elif mutation == "flatshares":
        long[1] = False
    elif mutation == "badcap":
        kwargs["cap"] = 0
    elif mutation == "infeasiblecap":
        kwargs["cap"] = .1
    elif mutation == "badslip":
        kwargs["slippage_bps"] = 10000
    elif mutation == "badfee":
        kwargs["commission_bps"] = np.nan
    elif mutation == "badstate":
        long = np.ones(5, int)
    elif mutation == "zeros":
        shares[:] = 0
    else:
        kwargs["symbols"] = ["A"] * 5
    with pytest.raises(ValueError):
        rebalance_cap_at_open(cash, shares, prices, long, **kwargs)


def test_executed_result_does_not_modify_input_arrays_or_logical_states():
    cash, shares, prices, long = np.zeros(5), np.array([5., 2, 1, 1, 1]), np.full(5, 100.), np.ones(5, bool)
    copies = [value.copy() for value in (cash, shares, prices, long)]
    result = rebalance_cap_at_open(cash, shares, prices, long, slippage_bps=3)
    for original, before in zip((cash, shares, prices, long), copies):
        np.testing.assert_array_equal(original, before)
    result["shares"][0] = 99
    result["pre_capital"][0] = 99
    assert shares[0] == 5 and cash[0] == 0


def test_seeded_random_accounts_conserve_every_sleeve_cash_and_wealth():
    rng = np.random.default_rng(1729)
    executed = 0
    for _ in range(100):
        capital = rng.uniform(10, 500, 5)
        long = rng.uniform(size=5) > .4
        prices = rng.uniform(10, 300, 5)
        cash = np.where(long, capital * rng.uniform(0, .05, 5), capital)
        shares = np.where(long, (capital - cash) / prices, 0)
        result = rebalance_cap_at_open(cash, shares, prices, long, slippage_bps=25)
        assert_accounting(result)
        executed += result["executed"]
    assert executed > 20
