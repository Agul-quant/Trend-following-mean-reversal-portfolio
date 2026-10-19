"""Synthetic saved-account recomputation; no real account input is opened."""

import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from trend_portfolio.periods import COSTS, STAGE_BOUNDS, SYMBOLS, analyze_periods

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "no_bond_runner", ROOT / "scripts/report_no_bond_portfolios.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def fixture():
    rng = np.random.default_rng(1729)
    original = json.loads((ROOT / "configs/four_portfolios.json").read_text())
    old = [
        {"id": p["id"], "initial_weights": [p["initial_weights"][s] for s in SYMBOLS]}
        for p in original["portfolios"]
    ]
    stages = []
    for identifier, (start, end) in STAGE_BOUNDS.items():
        year = int(start[:4])
        n = 18
        returns = rng.normal(0.0005, 0.003, (4, n, 6))
        stages.append(
            {
                "id": identifier,
                "scored_start": start,
                "scored_end": end,
                "initial_timestamp": f"{year}-01-02T14:30:00Z",
                "bundle": {
                    "symbols": np.array(SYMBOLS),
                    "slippage_bps": np.array(COSTS),
                    "timestamps": np.array(
                        [f"{year}-01-{d:02d}T22:00:00Z" for d in range(2, 2 + n)]
                    ),
                    "cash_returns": np.full((4, n), 0.00008),
                    "sleeve_normalized_equity": np.cumprod(1 + returns, axis=1),
                    "buy_and_hold_returns": rng.normal(0.0002, 0.01, (4, n, 6)),
                },
            }
        )
    saved = analyze_periods(stages, old)
    fits = {
        mode: {
            "initial_weights": [0.2] * 5,
            "baseline_cash_excess_sharpe": 1.0,
            "cap_mode": mode,
            "certified_global_optimum": False,
            "solver": "synthetic only",
            "seed": 1729,
            "lp_starts": 48,
            "ftol": 1e-12,
            "maxiter": 2000,
            "attempts": [],
        }
        for mode in runner.MODES
    }
    return stages, original, saved, fits


def test_five_symbols_six_new_portfolios_all_periods_costs_and_no_bond_factors():
    stages, _, saved, fits = fixture()
    report = runner.make_report(runner.prepare_stages(stages), fits, saved, "a" * 64)
    assert report["symbols"] == ["GDX", "FXI", "QQQ", "UNG", "FDN"]
    assert report["excluded_etfs"] == ["BND"]
    assert [p["id"] for p in report["portfolios"]] == list(runner.IDS)
    for p in report["portfolios"]:
        assert set(p["initial_weights"]) == set(runner.SYMBOLS)
    assert report["portfolios"][-1]["initial_weights"] == dict.fromkeys(
        runner.SYMBOLS, 0.2
    )
    assert report["control_rows"] == saved["control_rows"]
    for key, n in (
        ("portfolio_rows", 72),
        ("control_rows", 24),
        ("checkpoint_rows", 216),
        ("QQQ_single_factor_rows", 72),
        ("five_passive_factor_rows", 72),
        ("strategy_correlations", 12),
        ("portfolio_correlations", 12),
    ):
        assert len(report[key]) == n
    assert all("beta_BND" not in row for row in report["five_passive_factor_rows"])
    assert all(
        np.array(row["matrix"]).shape == (5, 5)
        for row in report["strategy_correlations"]
    )
    assert all(
        np.array(row["matrix"]).shape == (7, 7)
        for row in report["portfolio_correlations"]
    )


def test_bnd_saved_column_cannot_influence_new_paths_or_factors():
    stages, _, saved, fits = fixture()
    first = runner.make_report(runner.prepare_stages(stages), fits, saved, "a" * 64)
    for stage in stages:
        stage["bundle"]["sleeve_normalized_equity"][:, :, 5] *= 100000
        stage["bundle"]["buy_and_hold_returns"][:, :, 5] = 0.5
    second = runner.make_report(runner.prepare_stages(stages), fits, saved, "a" * 64)
    assert first == second


def test_cash_must_not_differ_by_cost():
    stages, _, _, _ = fixture()
    stages[0]["bundle"]["cash_returns"][1, 0] += 0.001
    with pytest.raises(ValueError, match="cash reference"):
        runner.prepare_stages(stages)


@pytest.mark.parametrize("key", ["symbols", "slippage_bps", "timestamps"])
def test_original_saved_input_must_pass_before_column_removal(key):
    stages, _, _, _ = fixture()
    if key == "symbols":
        stages[0]["bundle"][key][0] = "BND"
    elif key == "slippage_bps":
        stages[0]["bundle"][key][0] = 2
    else:
        stages[0]["bundle"][key][0] = "2026-11-01T22:00:00Z"
    with pytest.raises(ValueError):
        runner.prepare_stages(stages)


def test_control_revision_not_silently_accepted():
    _, _, saved, _ = fixture()
    changed = copy.deepcopy(saved["control_rows"])
    changed[0]["cagr"] += 0.001
    with pytest.raises(ValueError, match="statistic changed"):
        runner.compare_controls(changed, saved["control_rows"])


def test_export_aggregate_only_and_no_attempt_overwrite(tmp_path):
    stages, _, saved, fits = fixture()
    report = runner.make_report(runner.prepare_stages(stages), fits, saved, "a" * 64)
    runner.write_outputs(report, tmp_path)
    text = (tmp_path / "report.json").read_text()
    for forbidden in (
        "/Users/",
        ".cache/",
        "sleeve_normalized_equity",
        "beta_BND",
        "buy_and_hold_returns",
        '"timestamps"',
    ):
        assert forbidden not in text
    assert len((tmp_path / "strategy_correlations.csv").read_text().splitlines()) == 301
    assert (
        len((tmp_path / "portfolio_correlations.csv").read_text().splitlines()) == 589
    )
    with pytest.raises(FileExistsError):
        runner.write_outputs(report, tmp_path)


def test_unsealed_scope_rejected_before_any_account_loader(tmp_path, monkeypatch):
    release = tmp_path / "release.json"
    release.write_text('{"payload":{},"payload_sha256":"invalid"}')
    monkeypatch.setattr(
        runner, "load_stage_manifest", lambda *a: pytest.fail("Unsealed loader access")
    )
    with pytest.raises(ValueError, match="checksum"):
        runner.main(
            [
                "--manifest",
                str(tmp_path / "none.json"),
                "--input-release",
                str(release),
                "--output-dir",
                str(tmp_path / "new"),
            ]
        )
    assert not (tmp_path / "new").exists()
