"""Seeded synthetic fixtures only. No historical daily paths are embedded."""
import numpy as np
import pytest

from trend_portfolio.analytics import (
    _daily_cap_matrix, _finalized_weights, cap_diagnostics, checked_weights, factor_diagnostics,
    joint_regression, max_cagr_weights, metrics, optimize_sharpe,
    pairwise_regressions, portfolio_equity, returns_from_equity,
)


def test_static_initial_wealth_is_not_daily_rebalancing():
    sleeves = np.array([[2.0, 1.0], [1.0, 2.0]])
    wealth = portfolio_equity(sleeves, [0.5, 0.5])
    np.testing.assert_allclose(wealth, [1.5, 1.5])
    np.testing.assert_allclose(returns_from_equity(wealth), [0.5, 0.0])
    daily_rebalanced = (returns_from_equity(sleeves.T).T @ np.array([0.5, 0.5]))
    assert daily_rebalanced[1] == 0.25  # Wrong model: reuses winners' capital.


def test_first_return_and_initial_drawdown_are_included():
    result = metrics([0.9, 0.99], [0.0, 0.0], 1.0)
    np.testing.assert_allclose(returns_from_equity([0.9, 0.99]), [-0.1, 0.1])
    assert result["max_drawdown"] == pytest.approx(-0.1)
    assert result["cagr"] == pytest.approx(-0.01)
    assert result["observations"] == 2


def test_metrics_above_actual_cash_and_sample_standard_deviation():
    r = np.array([0.01, -0.02, 0.03, 0.005])
    cash = np.array([0.0001, 0.0003, 0.0002, 0.0001])
    wealth = np.cumprod(1 + r)
    result = metrics(wealth, cash, 0.75)
    expected = np.sqrt(252) * np.mean(r - cash) / np.std(r - cash, ddof=1)
    assert result["cash_excess_sharpe"] == pytest.approx(expected)
    assert result["cagr"] == pytest.approx(wealth[-1] ** (1 / 0.75) - 1)


def test_exact_cash_no_trade_sharpe_is_undefined():
    cash = np.array([0.0002, 0.0001, 0.0003, 0.0001])
    result = metrics(np.cumprod(1 + cash), cash, 1.0)
    assert np.isnan(result["cash_excess_sharpe"])


@pytest.mark.parametrize("weights", [[0.6, 0.6], [-0.1, 1.1], [1.0], [np.nan, 0]])
def test_reject_invalid_weights(weights):
    with pytest.raises(ValueError):
        checked_weights(weights, 2)


@pytest.mark.parametrize("equity", [[[0.0, 1], [1, 1]], [[1, np.inf], [1, 1]], [1, 2]])
def test_reject_invalid_sleeve_equity(equity):
    with pytest.raises(ValueError):
        portfolio_equity(equity, [0.5, 0.5])


@pytest.mark.parametrize("years", [0, -1, np.nan, np.inf])
def test_reject_invalid_elapsed_years(years):
    with pytest.raises(ValueError):
        metrics([1.0, 1.1], [0, 0], years)


def test_cost_and_time_axes_preserved():
    equity = np.array([[[1, 1], [1.2, 1.1]], [[0.99, 1], [1.1, 1.05]]])
    result = portfolio_equity(equity, [0.25, 0.75])
    assert result.shape == (2, 2)
    np.testing.assert_allclose(result, [[1, 1.125], [0.9975, 1.0625]])
    assert returns_from_equity(result).shape == (2, 2)


def test_daily_cap_is_not_initial_cap():
    equity = np.array([[1, 1, 1, 1], [3, 1, 1, 1]])
    result = cap_diagnostics(equity, [0.25] * 4)
    assert result["initial_cap_satisfied"]
    assert not result["all_daily_cap_satisfied"]
    assert result["max_daily_capital_share"] == 0.5
    np.testing.assert_allclose(result["terminal_capital_shares"], [.5, 1 / 6, 1 / 6, 1 / 6])


def test_daily_cap_checks_all_costs_and_linear_inequalities():
    equity = np.array([[[1, 1, 1, 1]], [[3, 1, 1, 1]]])
    weights = np.full(4, 0.25)
    result = cap_diagnostics(equity, weights)
    assert not result["all_daily_cap_satisfied"]
    constraints = _daily_cap_matrix(equity, 1 / 3)
    assert constraints.shape == (8, 4)
    assert (constraints @ weights).min() < 0
    equity = equity[:1]
    assert ( _daily_cap_matrix(equity, 1 / 3) @ weights).min() > 0


def test_known_joint_alpha_beta_and_pairwise_difference():
    rng = np.random.default_rng(77)
    n = 500
    independent = rng.normal(0, .01, size=(n, 3))
    factors = independent @ np.array([[1, .7, 0], [0, .7, 0], [0, 0, 1]])
    cash = rng.uniform(.00001, .0001, size=n)
    factors += cash[:, None]
    beta = np.array([.2, .4, -.1])
    alpha = .00012
    portfolio = cash + alpha + (factors - cash[:, None]) @ beta
    fit = joint_regression(portfolio, factors, cash)
    np.testing.assert_allclose(fit["betas"], beta, atol=1e-12)
    assert fit["alpha_daily"] == pytest.approx(alpha)
    assert fit["alpha_annual_arithmetic"] == pytest.approx(alpha * 252)
    assert fit["r_squared"] == pytest.approx(1)
    assert fit["adjusted_r_squared"] == pytest.approx(1)
    assert fit["design_rank"] == 4
    separate = pairwise_regressions(portfolio, factors, cash)
    assert separate[0]["betas"][0] != pytest.approx(beta[0])
    assert len(separate) == 3


def test_factor_self_regression():
    rng = np.random.default_rng(8)
    cash = np.full(80, .0001)
    returns = rng.normal(.001, .01, 80)
    result = joint_regression(returns, returns[:, None], cash)
    assert result["betas"][0] == pytest.approx(1)
    assert result["alpha_daily"] == pytest.approx(0, abs=1e-15)
    assert result["r_squared"] == pytest.approx(1)


def test_rank_deficiency_rejected_not_silently_factor_dropped():
    returns = np.linspace(-.01, .01, 80)
    factors = np.column_stack([returns, returns])
    with pytest.raises(ValueError, match="rank deficient"):
        joint_regression(returns, factors, np.zeros(80))
    with pytest.raises(ValueError, match="rank deficient"):
        factor_diagnostics(factors, np.zeros(80))


def test_factor_diagnostics():
    rng = np.random.default_rng(18)
    f = rng.normal(0, .01, size=(500, 3))
    diag = factor_diagnostics(f, np.zeros(500))
    np.testing.assert_allclose(np.diag(diag["correlation"]), 1)
    assert np.min(diag["variance_inflation_factors"]) >= 1 - 1e-10
    assert diag["standardized_condition_number"] < 1.3


def test_max_cagr_static_simplex_vertex_and_first_tie():
    equity = np.array([[1, .99, 1], [1.2, 1.3, 1.3]])
    np.testing.assert_array_equal(max_cagr_weights(equity), [0, 1, 0])
    rng = np.random.default_rng(4)
    mixtures = rng.dirichlet(np.ones(3), size=500)
    assert (equity[-1] @ mixtures.T).max() <= 1.3 + 1e-12


def test_optimizer_deterministic_and_daily_feasible():
    rng = np.random.default_rng(17)
    n, s = 70, 4
    returns = rng.normal(.001, .004, size=(n, s))
    equity = np.cumprod(1 + returns, axis=0)
    costs = np.stack([equity, equity * np.linspace(.999, .998, n)[:, None]])
    options = dict(baseline_index=0, cap_mode="daily", starts=3, seed=54)
    result = optimize_sharpe(costs, np.full(n, .0001), **options)
    repeated = optimize_sharpe(costs, np.full(n, .0001), **options)
    np.testing.assert_allclose(result["initial_weights"], repeated["initial_weights"], atol=1e-12)
    assert not result["certified_global_optimum"]
    diagnostics = cap_diagnostics(costs, result["initial_weights"])
    assert diagnostics["initial_cap_satisfied"]
    assert diagnostics["all_daily_cap_satisfied"]
    assert sum(result["initial_weights"]) == pytest.approx(1)
    wealth = portfolio_equity(costs, result["initial_weights"])[0]
    actual = metrics(wealth, np.full(n, .0001), 1)["cash_excess_sharpe"]
    assert result["baseline_cash_excess_sharpe"] == pytest.approx(actual, abs=1e-8)


def test_optimizer_infeasible_initial_cap():
    with pytest.raises(ValueError, match="infeasible"):
        optimize_sharpe(np.ones((1, 5, 2)), np.zeros(5), cap_mode="initial")


def test_optimizer_postprocessing_rechecks_boundary_cap():
    # An otherwise tolerated equality residual can violate the cap when
    # normalized; it must not be advertised as feasible after cleanup.
    weights = np.array([1 / 3, 1 / 3, .2, 1 / 3 - .2 - 8e-9])
    with pytest.raises(ValueError, match="postprocessed"):
        _finalized_weights(weights, 1 / 3, None)
    rows = np.array([[1., -1., 0., 0.]])
    with pytest.raises(ValueError, match="postprocessed"):
        _finalized_weights(np.array([.2, .3, .25, .25]), 1., rows)
