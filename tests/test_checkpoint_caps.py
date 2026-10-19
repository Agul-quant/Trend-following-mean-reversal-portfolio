"""Synthetic-only checkpoint calendar, gradient, constraint and solver fixtures."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from trend_portfolio.analytics import metrics, portfolio_equity
from trend_portfolio.checkpoint_caps import (
    checkpoint_cap_diagnostics, checkpoint_indices, checkpoint_sharpe_objective,
    optimize_checkpoint_sharpe,
)


def times(n):
    start = datetime(2024, 1, 2, 22, tzinfo=timezone.utc)
    return [(start + timedelta(days=index)).isoformat() for index in range(n)]


def fixture(n=35, sleeves=4):
    rng = np.random.default_rng(173)
    returns = rng.normal(.0008, .003, (n, sleeves))
    base = np.cumprod(1 + returns, axis=0)
    equity = np.stack([base * np.linspace(1, final, n)[:, None] for final in (1, .999, .997, .993)])
    return equity, np.full(n, .0001), times(n)


def test_weekly_holiday_and_terminal_partial_period():
    dates = ["2024-03-27T21:00:00Z", "2024-03-28T21:00:00Z",  # Good Friday closed.
             "2024-04-01T21:00:00Z", "2024-04-02T21:00:00Z"]
    np.testing.assert_array_equal(checkpoint_indices(dates, "weekly"), [1, 3])
    np.testing.assert_array_equal(checkpoint_indices(dates, "monthly"), [1, 3])
    np.testing.assert_array_equal(checkpoint_indices(dates, "daily"), [0, 1, 2, 3])


def test_iso_year_is_used_and_ny_date_not_utc_date():
    # Dec 30 2020 and Jan 1 2021 are ISO 2020 week 53. Jan 4 begins week 1.
    dates = ["2020-12-30T22:00:00Z", "2021-01-01T22:00:00Z", "2021-01-04T22:00:00Z"]
    np.testing.assert_array_equal(checkpoint_indices(dates, "weekly"), [1, 2])
    # These UTC month/year/week boundaries still belong to the previous NY date.
    dates = ["2023-12-31T23:00:00Z", "2024-01-01T01:00:00Z"]
    with pytest.raises(ValueError, match="one daily valuation"):
        checkpoint_indices(dates, "monthly")
    dates = ["2024-03-30T22:00:00Z", "2024-04-01T00:30:00Z", "2024-04-01T21:00:00Z"]
    np.testing.assert_array_equal(checkpoint_indices(dates, "monthly"), [1, 2])
    np.testing.assert_array_equal(checkpoint_indices(dates, "weekly"), [1, 2])


def test_dst_offset_changes_preserve_ny_daily_grouping():
    dates = ["2024-03-08T22:00:00Z", "2024-03-11T21:00:00Z", "2024-03-15T21:00:00Z",
             "2024-11-01T21:00:00Z", "2024-11-04T22:00:00Z"]
    np.testing.assert_array_equal(checkpoint_indices(dates, "weekly"), [0, 2, 3, 4])
    np.testing.assert_array_equal(checkpoint_indices(dates, "monthly"), [2, 4])


@pytest.mark.parametrize("dates,frequency", [([], "weekly"), (["2024-01-01"], "weekly"),
    (["2024-01-01T22:00Z", "2024-01-01T22:00Z"], "weekly"),
    (["2024-01-02T22:00Z", "2024-01-01T22:00Z"], "monthly"),
    (["2024-01-01T22:00Z"], "quarterly"), (["not a date"], "weekly")])
def test_invalid_calendar_inputs_rejected(dates, frequency):
    with pytest.raises(ValueError):
        checkpoint_indices(dates, frequency)


def test_diagnostics_discloses_between_checkpoint_breach_without_rebalancing():
    # Monday exceeds 1/3, but Friday and terminal Tuesday have recovered.
    dates = ["2024-01-08T22:00Z", "2024-01-12T22:00Z", "2024-01-16T22:00Z"]
    base = np.array([[3, 1, 1, 1], [1, 1, 1, 1], [1.1, 1, 1, 1]])
    equity = np.stack([base.copy() for _ in range(4)])
    result = checkpoint_cap_diagnostics(equity, [.25] * 4, dates, "weekly")
    assert result["initial_cap_satisfied"] and result["all_costs_checkpoint_cap_satisfied"]
    for row in result["per_cost"]:
        assert row["checkpoint_count"] == 2
        assert row["checkpoint_breach_days"] == 0
        assert row["daily_breach_days"] == row["between_checkpoint_breach_days"] == 1
        assert row["daily_max_capital_share"] == .5
        assert not row["all_daily_cap_satisfied"]
        assert row["checkpoint_max_capital_share"] == pytest.approx(1.1 / 4.1)
    np.testing.assert_allclose(portfolio_equity(equity, [.25] * 4)[0], [1.5, 1, 1.025])


def test_diagnostics_checks_initial_cap_and_all_four_costs():
    equity = np.ones((4, 3, 4))
    equity[3, -1, 0] = 3
    result = checkpoint_cap_diagnostics(equity, [.25] * 4, times(3), "monthly")
    assert not result["all_costs_checkpoint_cap_satisfied"]
    assert [row["checkpoint_breach_days"] for row in result["per_cost"]] == [0, 0, 0, 1]
    initial = checkpoint_cap_diagnostics(np.ones((4, 3, 4)), [.4, .2, .2, .2], times(3), "weekly")
    assert not initial["initial_cap_satisfied"] and not initial["all_costs_checkpoint_cap_satisfied"]


def test_single_cost_daily_diagnostic_and_no_new_daily_optimizer():
    equity, cash, dates = fixture()
    diagnostic = checkpoint_cap_diagnostics(equity[:1], [.25] * 4, dates, "daily")
    assert diagnostic["checkpoint_count"] == len(dates)
    assert len(diagnostic["per_cost"]) == 1
    row = diagnostic["per_cost"][0]
    assert row["checkpoint_breach_days"] == row["daily_breach_days"]
    assert row["between_checkpoint_breach_days"] == 0
    assert row["checkpoint_max_capital_share"] == row["daily_max_capital_share"]
    with pytest.raises(ValueError, match="new optimizer frequency"):
        optimize_checkpoint_sharpe(equity, cash, dates, "daily", starts=1)


def test_analytic_gradient_matches_central_difference_and_full_daily_objective():
    equity, cash, _ = fixture()
    weights = np.array([.2, .25, .25, .3])
    objective, gradient = checkpoint_sharpe_objective(equity[1], cash, weights)
    numerical = []
    for index in range(4):
        change = np.zeros(4)
        change[index] = 1e-7
        right = checkpoint_sharpe_objective(equity[1], cash, weights + change)[0]
        left = checkpoint_sharpe_objective(equity[1], cash, weights - change)[0]
        numerical.append((right - left) / 2e-7)
    np.testing.assert_allclose(gradient, numerical, rtol=2e-6, atol=1e-6)
    daily = metrics(equity[1] @ weights, cash, 1)["cash_excess_sharpe"]
    assert -objective == pytest.approx(daily)


@pytest.mark.parametrize("frequency", ["weekly", "monthly"])
def test_optimizer_deterministic_all_costs_feasible_and_daily_not_resampled(frequency):
    equity, cash, dates = fixture()
    options = dict(starts=3, seed=1729, known_weights=[.25] * 4)
    first = optimize_checkpoint_sharpe(equity, cash, dates, frequency, **options)
    second = optimize_checkpoint_sharpe(equity, cash, dates, frequency, **options)
    np.testing.assert_array_equal(first["initial_weights"], second["initial_weights"])
    assert first["objective_frequency"] == "daily" and first["objective_observations"] == len(cash)
    assert first["constraint_costs"] == 4 and first["initial_cap_enforced"]
    assert first["no_rebalancing"] and not first["certified_global_optimum"]
    diagnostics = checkpoint_cap_diagnostics(equity, first["initial_weights"], dates, frequency)
    assert diagnostics["initial_cap_satisfied"] and diagnostics["all_costs_checkpoint_cap_satisfied"]
    daily = metrics(equity[1] @ first["initial_weights"], cash, 1)["cash_excess_sharpe"]
    assert first["baseline_cash_excess_sharpe"] == pytest.approx(daily)
    assert first["baseline_cash_excess_sharpe"] >= first["known_incumbent_cash_excess_sharpe"] - 1e-10
    indices = checkpoint_indices(dates, frequency)
    # Sampling wealth at checkpoint dates would incorrectly change the objective.
    wrong = metrics((equity[1] @ first["initial_weights"])[indices], cash[indices], 1)["cash_excess_sharpe"]
    assert daily != pytest.approx(wrong)


def test_known_seed_retained_even_when_every_local_solver_fails():
    equity, cash, dates = fixture()
    known = np.array([.2, .3, .2, .3])
    def failed_solver(fun, start, **kwargs):
        return SimpleNamespace(x=np.full(4, np.nan), success=False, nit=1, status=9)
    # Fault injection is local to this new module; old analytics remains untouched.
    with patch("trend_portfolio.checkpoint_caps.minimize", failed_solver):
        result = optimize_checkpoint_sharpe(equity, cash, dates, "weekly", starts=2, known_weights=known)
    assert all(not row["success"] and not row["feasible"] for row in result["attempts"])
    value = -checkpoint_sharpe_objective(equity[1], cash, known)[0]
    assert result["baseline_cash_excess_sharpe"] >= value - 1e-10
    assert result["known_incumbent_cash_excess_sharpe"] == pytest.approx(value)


def test_fourth_cost_checkpoint_constraints_restrict_optimizer():
    equity, cash, dates = fixture()
    equity[3, -1, 0] = 20
    result = optimize_checkpoint_sharpe(equity, cash, dates, "monthly", starts=2)
    weights = np.array(result["initial_weights"])
    shares = equity[3, -1] * weights / (equity[3, -1] @ weights)
    assert shares.max() <= 1 / 3 + 1e-10
    assert weights[0] < .04  # No ignoring the nonbaseline fourth cost.


def test_infeasible_initial_and_checkpoint_constraints_rejected():
    with pytest.raises(ValueError, match="initial cap is infeasible"):
        optimize_checkpoint_sharpe(np.ones((4, 3, 2)), np.zeros(3), times(3), "weekly", starts=1)
    dates = [f"2024-0{index + 1}-31T22:00Z" for index in (0, 2, 4, 6)]
    base = np.ones((4, 4))
    np.fill_diagonal(base, 1000)
    equity = np.stack([base] * 4)
    with pytest.raises(ValueError, match="constraints are infeasible"):
        optimize_checkpoint_sharpe(equity, np.zeros(4), dates, "monthly", starts=1)


@pytest.mark.parametrize("change", ["badcash", "unequalcash", "badindex", "badstarts", "badcap", "badknown", "costcount"])
def test_input_contract_failures(change):
    equity, cash, dates = fixture()
    kwargs = {"starts": 1}
    if change == "badcash":
        cash = cash[:-1]
    elif change == "unequalcash":
        cash = np.stack([cash] * 4)
        cash[3, -1] += .001
    elif change == "badindex":
        kwargs["baseline_index"] = 4
    elif change == "badstarts":
        kwargs["starts"] = True
    elif change == "badcap":
        kwargs["cap"] = np.nan
    elif change == "badknown":
        kwargs["known_weights"] = [.4, .2, .2, .2]
    else:
        equity = equity[:3]
    with pytest.raises(ValueError):
        optimize_checkpoint_sharpe(equity, cash, dates, "monthly", **kwargs)
