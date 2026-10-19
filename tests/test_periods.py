"""Synthetic, independent saved-stage accounts; no historical daily input rows."""
import copy
from datetime import datetime
import json

import numpy as np
import pytest

from trend_portfolio.periods import (
    COSTS, STAGE_BOUNDS, SYMBOLS, analyze_periods, load_stage_manifest, main, write_report,
)


def fixtures():
    stages = []
    for index, (identifier, (start, end)) in enumerate(STAGE_BOUNDS.items()):
        year = int(start[:4])
        # Vary stage lengths and actual clocks; no n/252 or integer-year shortcuts.
        n = 3 + index
        dates = [f"{year}-01-02T22:00:00Z", f"{year}-06-03T21:00:00Z"]
        if n > 3:
            dates.append(f"{year + 1}-07-02T21:00:00Z")
        if n > 4:
            dates.append(f"{year + 2}-03-03T22:00:00Z")
        dates.append(f"{end}T21:00:00Z")
        cash = np.array([np.linspace(.0001 * (cost + 1), .0002 * (cost + 1), n) for cost in range(4)])
        equity = np.empty((4, n, 6))
        factors = np.zeros_like(equity)
        for cost in range(4):
            for sleeve in range(6):
                equity[cost, :, sleeve] = np.linspace(.995 - cost * .001, .9 + index * .15 + sleeve * .04, n)
            equity[cost, :, -1] = np.cumprod(1 + cash[cost])
            factors[cost, :, 2] = np.linspace(-.001 - cost * .0001, .002 - cost * .0001, n)
        stages.append({"id": identifier, "scored_start": start, "scored_end": end,
                       "initial_timestamp": f"{year}-01-02T14:30:00Z",
                       "bundle": {"timestamps": np.array(dates), "symbols": np.array(SYMBOLS),
                                  "slippage_bps": np.array(COSTS), "sleeve_normalized_equity": equity,
                                  "buy_and_hold_returns": factors, "cash_returns": cash}})
    portfolios = [{"id": "equal", "initial_weights": np.full(6, 1 / 6)},
                  {"id": "cash_sleeve", "initial_weights": np.array([0, 0, 0, 0, 0, 1.])},
                  {"id": "pair", "initial_weights": np.array([.5, .5, 0, 0, 0, 0])},
                  {"id": "fixed_fourth", "initial_weights": np.array([.25, .25, .25, .25, 0, 0])}]
    return stages, portfolios


def test_exact_counts_symbols_costs_stage_specific_actual_years_and_fresh_1000():
    stages, portfolios = fixtures()
    result = analyze_periods(stages, portfolios)
    assert len(result["portfolio_rows"]) == 48
    assert len(result["control_rows"]) == 24
    assert len(result["cap_rows"]) == 48
    assert len(result["stage_summaries"]) == 3
    assert result["symbols"] == list(SYMBOLS)
    assert result["initial_capital_each_stage"] == 1000
    years = []
    for stage, summary in zip(stages, result["stage_summaries"]):
        initial = datetime.fromisoformat(stage["initial_timestamp"].replace("Z", "+00:00"))
        final = datetime.fromisoformat(stage["bundle"]["timestamps"][-1].replace("Z", "+00:00"))
        exact = (final - initial).total_seconds() / (365 * 86400)
        assert summary["elapsed_act365_years"] == exact
        years.append(exact)
        assert summary["fresh_initial_capital"] == 1000
        row = next(r for r in result["portfolio_rows"] if r["stage"] == stage["id"] and r["portfolio_id"] == "pair")
        expected_terminal = float(stage["bundle"]["sleeve_normalized_equity"][0, -1, :2].mean())
        assert row["terminal_equity_from_1000"] == pytest.approx(expected_terminal * 1000)
        assert row["cagr"] == pytest.approx(expected_terminal ** (1 / exact) - 1)
    assert len(set(years)) == 3
    assert all(y != int(y) for y in years)
    # Portfolio definitions and stage account arrays are not updated in place.
    for stage in stages:
        assert stage["bundle"]["sleeve_normalized_equity"][0, 0, 0] == .995


def test_fresh_stages_not_stitched_and_no_daily_rebalancing():
    stages, portfolios = fixtures()
    for index, stage in enumerate(stages):
        stage["bundle"]["sleeve_normalized_equity"][:, :, :2] = np.array([2., 1.])
        stage["bundle"]["sleeve_normalized_equity"][:, -1, :2] = [1., 2.]
    result = analyze_periods(stages, portfolios)
    rows = [r for r in result["portfolio_rows"] if r["portfolio_id"] == "pair"]
    assert all(r["terminal_equity_from_1000"] == 1500 for r in rows)
    assert all(r["max_drawdown"] == 0 for r in rows)
    # Daily rebalancing would grow at the 2->1 / 1->2 reversal, unlike static wealth.


def test_first_loss_terminal_cost_and_initial_peak_are_retained():
    stages, portfolios = fixtures()
    for stage in stages:
        equity = stage["bundle"]["sleeve_normalized_equity"]
        equity[:, :, 0] = .999
        equity[:, :, 1] = .999
        equity[:, -1, :2] = .998
    result = analyze_periods(stages, portfolios)
    rows = [r for r in result["portfolio_rows"] if r["portfolio_id"] == "pair"]
    assert all(r["max_drawdown"] == pytest.approx(-.002) for r in rows)
    assert all(r["terminal_equity_from_1000"] == 998 for r in rows)
    assert all(r["observations"] >= 3 for r in rows)


def test_undefined_cash_sharpe_null_and_unequal_matched_cash_costs():
    stages, portfolios = fixtures()
    result = analyze_periods(stages, portfolios)
    rows = [r for r in result["portfolio_rows"] if r["portfolio_id"] == "cash_sleeve"]
    assert all(row["cash_excess_sharpe"] is None for row in rows)
    cash_controls = [row for row in result["control_rows"] if row["control_id"] == "matched_cash"]
    assert all(row["cash_excess_sharpe"] is None for row in cash_controls)
    terminals = [row["terminal_equity_from_1000"] for row in cash_controls if row["stage"] == "development"]
    assert len(set(terminals)) == 4
    for row in rows:
        matching = next(c for c in cash_controls if c["stage"] == row["stage"] and c["slippage_bps_each_way"] == row["slippage_bps_each_way"])
        assert row["terminal_equity_from_1000"] == matching["terminal_equity_from_1000"]
    assert "NaN" not in json.dumps(result, allow_nan=False)


def test_cap_breaches_are_reported_not_enforced_or_refitted():
    stages, portfolios = fixtures()
    weights_before = portfolios[0]["initial_weights"].copy()
    stages[0]["bundle"]["sleeve_normalized_equity"][:, -1, 0] = 10
    result = analyze_periods(stages, portfolios)
    caps = [r for r in result["cap_rows"] if r["stage"] == "development" and r["portfolio_id"] == "equal"]
    assert all(row["initial_cap_pass_diagnostic"] for row in caps)
    assert all(not row["daily_cap_pass_diagnostic"] for row in caps)
    assert all(row["max_daily_capital_share"] > 1 / 3 for row in caps)
    np.testing.assert_array_equal(portfolios[0]["initial_weights"], weights_before)


@pytest.mark.parametrize("mutation", ["stage_missing", "stage_duplicate", "cost_order", "cost_missing", "symbols", "bounds", "leakage", "initial", "time_duplicate", "cash_bad", "extra_portfolio", "excluded"])
def test_invalid_scope_or_arrays_are_rejected(mutation):
    stages, portfolios = fixtures()
    if mutation == "stage_missing":
        stages.pop()
    elif mutation == "stage_duplicate":
        stages[-1]["id"] = stages[0]["id"]
    elif mutation == "cost_order":
        stages[0]["bundle"]["slippage_bps"] = [3, 1, 10, 25]
    elif mutation == "cost_missing":
        stages[0]["bundle"]["slippage_bps"] = [1, 3, 10]
    elif mutation == "symbols":
        stages[0]["bundle"]["symbols"] = ["QQQ", "GDX", "FXI", "UNG", "FDN", "BND"]
    elif mutation == "bounds":
        stages[0]["scored_end"] = "2021-01-01"
    elif mutation == "leakage":
        stages[0]["bundle"]["timestamps"][-1] = "2021-01-01T21:00:00Z"
    elif mutation == "initial":
        stages[0]["initial_timestamp"] = stages[0]["bundle"]["timestamps"][0]
    elif mutation == "time_duplicate":
        stages[0]["bundle"]["timestamps"][1] = stages[0]["bundle"]["timestamps"][0]
    elif mutation == "cash_bad":
        stages[0]["bundle"]["cash_returns"][0, 0] = np.nan
    elif mutation == "extra_portfolio":
        portfolios.append({"id": "fifth", "initial_weights": portfolios[0]["initial_weights"]})
    elif mutation == "excluded":
        portfolios[-1]["id"] = "max_cagr_100pct_gdx"
    with pytest.raises(ValueError):
        analyze_periods(stages, portfolios)


def test_private_manifest_cli_aggregate_output_and_attempt_preservation(tmp_path):
    stages, portfolios = fixtures()
    manifest = {"stages": {}}
    for stage in stages:
        source = tmp_path / f"secret_{stage['id']}.npz"
        np.savez(source, **stage["bundle"])
        manifest["stages"][stage["id"]] = {"input": source.name, **{key: stage[key] for key in ("initial_timestamp", "scored_start", "scored_end")}}
    manifest_path = tmp_path / "private_manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    config = tmp_path / "four.json"
    config.write_text(json.dumps({"portfolios": [{"id": p["id"], "initial_weights": p["initial_weights"].tolist()} for p in portfolios]}))
    loaded = load_stage_manifest(manifest_path)
    assert len(loaded) == 3
    output = tmp_path / "new_aggregate_attempt"
    assert main(["--manifest", str(manifest_path), "--portfolios", str(config), "--output-dir", str(output)]) == 0
    assert len(list(output.iterdir())) == 5
    text = (output / "report.json").read_text()
    assert "secret_" not in text and str(tmp_path) not in text and "sleeve_normalized_equity" not in text
    assert "buy_and_hold_returns" not in text and "trade_count" not in text
    csv_text = (output / "portfolio_rows.csv").read_text()
    assert "nan" not in csv_text.lower()
    with pytest.raises(SystemExit):
        main(["--manifest", str(manifest_path), "--portfolios", str(config), "--output-dir", str(output)])
    with pytest.raises(FileExistsError):
        write_report(analyze_periods(stages, portfolios), output)
