"""Synthetic independent-oracle fixtures only; never historical input arrays."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("no_bond_oracle", ROOT / "scripts/verify_no_bond_portfolios.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def timestamps(dates):
    return [datetime.fromisoformat(day + "T17:00:00").replace(tzinfo=ZoneInfo("America/New_York")).isoformat()
            for day in dates]


def test_independent_week_month_calendar_iso_holidays_terminal():
    dates = ["2020-12-30", "2020-12-31", "2021-01-04", "2021-01-08", "2021-01-29", "2021-02-01"]
    times = timestamps(dates)
    assert AUDIT.independent_checkpoints(times, "weekly").tolist() == [1, 3, 4, 5]
    assert AUDIT.independent_checkpoints(times, "monthly").tolist() == [1, 4, 5]
    assert AUDIT.independent_checkpoints(times, "daily").tolist() == list(range(6))


def test_independent_calendar_uses_new_york_not_utc_month():
    times = ["2026-01-31T23:00:00-05:00", "2026-02-01T23:00:00-05:00"]
    assert AUDIT.independent_checkpoints(times, "monthly").tolist() == [0, 1]


@pytest.mark.parametrize("times", [["2026-01-01T17:00:00"],
                                   ["2026-01-01T22:00:00Z", "2026-01-01T22:00:00Z"],
                                   ["2026-01-02T22:00:00Z", "2026-01-01T22:00:00Z"],
                                   ["2026-01-01T21:00:00Z", "2026-01-01T22:00:00Z"]])
def test_calendar_rejects_naive_duplicate_unsorted_or_duplicate_local_day(times):
    with pytest.raises(ValueError):
        AUDIT.independent_checkpoints(times, "weekly")


def test_independent_wealth_is_not_frictionless_rebalancing():
    equity = np.ones((2, 5))
    equity[0, :2] = [2, 1]
    equity[1, :2] = [1, 2]
    wealth = AUDIT.independent_wealth(equity, [.5, .5, 0, 0, 0])
    np.testing.assert_array_equal(wealth, [1.5, 1.5])
    np.testing.assert_array_equal(AUDIT.independent_returns(wealth), [.5, 0])


def test_independent_metrics_exact_clock_dd_initial_and_cash_undefined():
    result = AUDIT.independent_metrics(np.array([.8, 1.21]), np.zeros(2), 2)
    assert result["cagr"] == pytest.approx(.1)
    assert result["max_drawdown"] == pytest.approx(-.2)
    assert result["terminal_equity_from_1000"] == 1210
    cash = np.array([.0001, .0002, .0003])
    result = AUDIT.independent_metrics(np.cumprod(1 + cash), cash, 1)
    assert result["cash_excess_sharpe"] is None
    assert result["annualized_cash_excess_volatility"] == 0


def test_between_checkpoint_breach_is_allowed_and_disclosed():
    equity = np.ones((3, 5))
    equity[1, 0] = 4
    result = AUDIT.independent_caps(equity, [.2] * 5, np.array([0, 2]))
    assert result["checkpoint_cap_pass_diagnostic"] is True
    assert result["daily_cap_pass_diagnostic"] is False
    assert result["checkpoint_breach_days"] == 0
    assert result["daily_breach_days"] == result["between_checkpoint_breach_days"] == 1


def test_initial_cap_independently_blocks_even_if_later_shares_pass():
    equity = np.ones((2, 5))
    equity[:, 0] = .1
    result = AUDIT.independent_caps(equity, [.6, .1, .1, .1, .1], np.array([1]))
    assert result["max_checkpoint_capital_share"] < 1 / 3
    assert result["initial_cap_pass_diagnostic"] is False
    assert result["checkpoint_cap_pass_diagnostic"] is False


def test_terminal_checkpoint_cannot_be_silently_omitted():
    with pytest.raises(ValueError, match="terminal"):
        AUDIT.independent_caps(np.ones((3, 5)), [.2] * 5, np.array([0, 1]))


def test_centered_regression_known_coefficients_and_self_control():
    random = np.random.default_rng(1984)
    factors = random.normal(0, .01, (60, 5))
    cash = np.full(60, .0001)
    beta = np.array([.1, -.2, .3, 0, .5])
    alpha = .0004
    returns = cash + alpha + (factors - cash[:, None]) @ beta
    result = AUDIT.independent_regression(returns, factors, cash)
    np.testing.assert_allclose(result["betas"], beta, atol=1e-14)
    assert result["alpha_daily"] == pytest.approx(alpha, abs=1e-14)
    assert result["alpha_annual_arithmetic"] == pytest.approx(252 * alpha)
    assert result["r_squared"] == pytest.approx(1)
    assert result["design_rank"] == 6
    self_control = AUDIT.independent_regression(factors[:, 2], factors[:, [2]], cash)
    assert self_control["betas"] == pytest.approx([1])
    assert self_control["alpha_daily"] == pytest.approx(0, abs=1e-14)


def test_rank_deficient_regression_rejected():
    with pytest.raises(ValueError, match="Rank"):
        AUDIT.independent_regression(np.arange(10) / 100, np.ones((10, 2)), np.zeros(10))


@pytest.mark.parametrize("value", [{"locator": "/" + "Users/person/private"}, list(range(129)),
                                    {"value": float("nan")}, {"key": "file" + "://private"}])
def test_public_report_rejects_private_paths_nonfinite_and_daily_arrays(value):
    with pytest.raises(ValueError):
        AUDIT.public_json(value)


def test_report_privacy_accepts_aggregate_rows_without_daily_paths():
    AUDIT.public_json({"metrics": [{"sharpe": .1}] * 216, "weight": 1e-18, "cash_sharpe": None})


def test_guard_fails_before_any_array_open_when_unauthorized(tmp_path, monkeypatch):
    payload = {"authorized_saved_path_evaluation": False}
    seal = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    release = tmp_path / "release.json"
    release.write_text(json.dumps({"payload": payload, "payload_sha256": seal}))
    monkeypatch.setattr(np, "load", lambda *args, **kwargs: pytest.fail("Unauthorized numerical read"))
    with pytest.raises(ValueError, match="No numerical-read release"):
        AUDIT.verify_release(release, tmp_path / "manifest.json")


def test_seal_tamper_rejected_before_any_array_open(tmp_path, monkeypatch):
    release = tmp_path / "release.json"
    release.write_text(json.dumps({"payload": {"authorized_saved_path_evaluation": True}, "payload_sha256": "0" * 64}))
    monkeypatch.setattr(np, "load", lambda *args, **kwargs: pytest.fail("Unauthorized numerical read"))
    with pytest.raises(ValueError, match="seal"):
        AUDIT.verify_release(release, tmp_path / "manifest.json")


@pytest.fixture(scope="module")
def synthetic_comparison():
    random = np.random.default_rng(56644)
    definitions = [{"id": identity, "initial_weights": dict.fromkeys(AUDIT.SYMBOLS, .2)} for identity in AUDIT.IDS]
    report = {"schema": "five_etf_six_portfolio_comparison_v1", "symbols": list(AUDIT.SYMBOLS),
              "portfolios": definitions, "slippage_bps_each_way": list(AUDIT.COSTS),
              "commission_bps_each_way": 1, "initial_capital_each_stage": 1000,
              "fit_stage": "historical_OOS", "fit_baseline_slippage_bps": 3,
              "method": "Static initial wealth; no rebalancing.",
              "limitations": ["Retrospective; not an untouched test; best-found, not globally certified."],
              "stage_summaries": [], "portfolio_rows": [], "control_rows": [], "checkpoint_rows": [],
              "QQQ_single_factor_rows": [], "five_passive_factor_rows": [],
              "strategy_correlations": [], "portfolio_correlations": [], "solver_summaries": []}
    bundles = {}
    for stage in AUDIT.STAGES:
        count = AUDIT.STAGES[stage][2]
        current = datetime.fromisoformat(AUDIT.STAGES[stage][0])
        dates = []
        while len(dates) < count:
            if current.weekday() < 5:
                dates.append(current.date().isoformat())
            current += timedelta(days=1)
        times = np.asarray(timestamps(dates))
        instants = AUDIT.utc_datetimes(times)
        years = (instants[-1] - instants[0]).total_seconds() / (365 * 86400) + .001
        report["stage_summaries"].append({"stage": stage, "elapsed_act365_years": years})
        factors = random.normal(.0002, .001, (4, count, 5))
        equity = np.cumprod(1 + random.normal(.0003, .001, (4, count, 5)), axis=1)
        cash = np.full(count, .0001)
        bundles[stage] = {"timestamps": times, "sleeve_normalized_equity": equity,
                          "buy_and_hold_returns": factors, "cash_returns": cash,
                          "elapsed_act365_years": years}
        for ci, cost in enumerate(AUDIT.COSTS):
            returns_for_correlations = []
            for record in definitions:
                identity, weights = record["id"], [.2] * 5
                wealth = AUDIT.independent_wealth(equity[ci], weights)
                base = {"stage": stage, "portfolio_id": identity, "slippage_bps_each_way": cost,
                        "commission_bps_each_way": 1}
                report["portfolio_rows"].append({**base, **AUDIT.independent_metrics(wealth, cash, years)})
                for frequency in AUDIT.FREQUENCIES:
                    points = AUDIT.independent_checkpoints(times, frequency)
                    report["checkpoint_rows"].append({**base, "checkpoint_frequency": frequency,
                                                       **AUDIT.independent_caps(equity[ci], weights, points)})
                returns = AUDIT.independent_returns(wealth)
                returns_for_correlations.append(returns)
                for field, columns in (("QQQ_single_factor_rows", [2]), ("five_passive_factor_rows", list(range(5)))):
                    result = AUDIT.independent_regression(returns, factors[ci][:, columns], cash)
                    coefficients = result.pop("betas")
                    result.update({f"beta_{AUDIT.SYMBOLS[c]}": value for c, value in zip(columns, coefficients)})
                    report[field].append({**base, **result})
            for identity, returns in (("QQQ_buy_and_hold", factors[ci, :, 2]), ("matched_cash", cash)):
                report["control_rows"].append({"stage": stage, "control_id": identity,
                                                "slippage_bps_each_way": cost, "commission_bps_each_way": 1,
                                                **AUDIT.independent_metrics(np.cumprod(1 + returns), cash, years)})
            strategies = np.column_stack([AUDIT.independent_returns(equity[ci, :, i]) for i in range(5)])
            portfolios = np.column_stack([*returns_for_correlations, factors[ci, :, 2]])
            common = {"stage": stage, "slippage_bps_each_way": cost, "commission_bps_each_way": 1}
            report["strategy_correlations"].append({**common, "symbols": list(AUDIT.SYMBOLS),
                                                     "matrix": np.corrcoef(strategies, rowvar=False).tolist()})
            report["portfolio_correlations"].append({**common, "portfolio_ids": list(AUDIT.IDS) + ["QQQ_buy_and_hold"],
                                                      "matrix": np.corrcoef(portfolios, rowvar=False).tolist()})
    portfolios = AUDIT.keyed(report["portfolio_rows"])
    for identity, mode in zip(AUDIT.IDS[:5], ("daily", "weekly", "monthly", "initial", "none")):
        report["solver_summaries"].append({"portfolio_id": identity, "cap_mode": mode,
                                           "baseline_cash_excess_sharpe": portfolios[("historical_OOS", identity, 3.0)]["cash_excess_sharpe"],
                                           "initial_weights": [.2] * 5, "certified_global_optimum": False,
                                           "seed": 1729, "lp_starts": 48, "ftol": 1e-12, "maxiter": 2000,
                                           "attempts": [{"success": True, "feasible": True}] * 48})
    original = {"control_rows": copy.deepcopy(report["control_rows"]),
                "stage_summaries": copy.deepcopy(report["stage_summaries"])}
    return report, bundles, original


def test_complete_independent_five_etf_saved_path_audit(synthetic_comparison):
    result = AUDIT.audit_report(*synthetic_comparison)
    assert result["passed"] is True
    assert result["rows_verified"] == {"portfolio_rows": 72, "control_rows": 24, "checkpoint_rows": 216,
                                       "QQQ_single_factor_rows": 72, "five_passive_factor_rows": 72,
                                       "strategy_correlations": 12, "portfolio_correlations": 12}


def test_independent_oracle_checks_separate_producer_synthetic_outputs(synthetic_comparison, monkeypatch):
    """Independent math also audits the real producer, without historical inputs."""
    report, bundles, original = synthetic_comparison
    spec = importlib.util.spec_from_file_location("no_bond_producer", ROOT / "scripts/report_no_bond_portfolios.py")
    producer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(producer)
    monkeypatch.setattr(np, "load", lambda *args, **kwargs: pytest.fail("Historical arrays are forbidden in this fixture"))
    stages = [{"id": stage, "equity": bundle["sleeve_normalized_equity"],
               "factors": bundle["buy_and_hold_returns"],
               "cash": np.broadcast_to(bundle["cash_returns"], (4, len(bundle["timestamps"]))),
               "times": bundle["timestamps"], "years": bundle["elapsed_act365_years"]}
              for stage, bundle in bundles.items()]
    results = {row["cap_mode"]: {key: value for key, value in row.items() if key != "portfolio_id"}
               for row in report["solver_summaries"]}
    produced = producer.make_report(stages, results, original, "0" * 64)
    result = AUDIT.audit_report(produced, bundles, original)
    assert result["passed"] is True


def test_public_aggregate_audit_does_not_open_private_arrays(synthetic_comparison, monkeypatch):
    report, _bundles, original = synthetic_comparison
    monkeypatch.setattr(np, "load", lambda *args, **kwargs: pytest.fail("Private numerical read in public mode"))
    result = AUDIT.audit_public_report(report, original)
    assert result["passed"] is True
    assert result["private_inputs_or_optimizer_required"] is False


@pytest.mark.parametrize("kind", ["missing", "duplicate", "bond_weight", "old_id", "cash", "checkpoint", "beta", "correlation", "solver"])
def test_malformed_or_unbonded_scope_publicly_rejected(synthetic_comparison, kind):
    report, _bundles, original = synthetic_comparison
    report = copy.deepcopy(report)
    if kind == "missing":
        report["portfolio_rows"].pop()
    elif kind == "duplicate":
        report["portfolio_rows"][-1] = report["portfolio_rows"][0]
    elif kind == "bond_weight":
        report["portfolios"][0]["initial_weights"]["BND"] = 0
    elif kind == "old_id":
        report["portfolios"][0]["id"] = "daily_capped_max_sharpe"
    elif kind == "cash":
        report["control_rows"][0]["terminal_equity_from_1000"] += 1
    elif kind == "checkpoint":
        report["checkpoint_rows"][0]["checkpoint_count"] -= 1
    elif kind == "beta":
        report["five_passive_factor_rows"][0]["beta_BND"] = 0
    elif kind == "correlation":
        report["strategy_correlations"][0]["symbols"].append("BND")
    else:
        report["solver_summaries"][0]["certified_global_optimum"] = True
    with pytest.raises(ValueError):
        AUDIT.audit_public_report(report, original)


@pytest.mark.parametrize("kind", ["sharpe", "beta", "correlation", "checkpoint"])
def test_independent_arithmetic_detects_resealed_metric_tamper(synthetic_comparison, kind):
    report, bundles, original = synthetic_comparison
    report = copy.deepcopy(report)
    if kind == "sharpe":
        report["portfolio_rows"][0]["cash_excess_sharpe"] += .01
    elif kind == "beta":
        report["five_passive_factor_rows"][0]["beta_GDX"] += .01
    elif kind == "correlation":
        row = report["strategy_correlations"][0]
        row["matrix"][0][1] = row["matrix"][1][0] = .5
    else:
        report["checkpoint_rows"][1]["max_checkpoint_capital_share"] += .001
    with pytest.raises(ValueError):
        AUDIT.audit_report(report, bundles, original)

