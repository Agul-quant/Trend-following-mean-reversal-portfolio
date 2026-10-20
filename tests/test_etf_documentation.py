"""Current publication scope; no historical market or saved account inputs."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_exact_scope_and_selected_definitions():
    universe = json.loads((ROOT / "configs/etf_universe.json").read_text())
    assert (
        universe["universe_size"]
        == len(universe["symbols"])
        == len(set(universe["symbols"]))
        == 47
    )
    assert sorted(map(len, universe["categories"].values())) == [5, 6, 10, 13, 13]
    assert set(universe["symbols"]) == {
        s for values in universe["categories"].values() for s in values
    }
    selected = json.loads((ROOT / "configs/selected_etf_strategies.json").read_text())
    assert selected["symbols"] == ["GDX", "FXI", "QQQ", "UNG", "FDN"]
    assert [s["symbol"] for s in selected["strategies"]] == selected["symbols"]
    assert set(selected["symbols"]) <= set(universe["symbols"])
    policy = json.loads((ROOT / "configs/final_cap_rebalancing.json").read_text())
    assert policy["symbols"] == selected["symbols"]


def test_scope_is_not_a_new_universe_screen_or_holdout():
    text = (ROOT / "docs/etf_data_sources.md").read_text()
    for phrase in (
        "47 ETFs",
        "not a newly",
        "same provider",
        "2017-01-01",
        "2020-12-31",
        "2021-01-01",
        "2023-12-31",
        "2024-01-01",
        "2026-10-15",
        "295",
    ):
        assert phrase in text
    methods = (ROOT / "docs/etf_methods.md").read_text()
    for phrase in (
        "379",
        "289",
        "90",
        "17:00",
        "one-third",
        "not a new universe-wide run",
        "cash",
    ):
        assert phrase in methods
    readme = (ROOT / "README.md").read_text()
    assert "Published 47-ETF universe" in readme
    assert "not a newly executed 47-ETF screening campaign" in readme


def test_every_published_symbol_is_documented():
    universe = json.loads((ROOT / "configs/etf_universe.json").read_text())
    readme = (ROOT / "README.md").read_text()
    detail = (ROOT / "docs/etf_data_sources.md").read_text()
    for symbol in universe["symbols"]:
        assert symbol in readme and symbol in detail


def test_comparison_figures_include_all_four_portfolios_and_qqq():
    manifest = json.loads(
        (ROOT / "reports/etf_portfolios/figures_manifest.json").read_text()
    )
    names = [
        "Initial allocation; no rebalancing",
        "Equal weight; no rebalancing",
        "Weekly corrections",
        "Monthly corrections",
        "QQQ buy-and-hold",
    ]
    assert manifest["curve_names"] == names
    for stage in ("development", "validation", "historical_OOS"):
        figure = manifest["figures"][stage]
        assert figure["curves"] == names
        assert "equal_initial_return" in figure["public_return_columns"]
    assert "20%" in (ROOT / "README.md").read_text()


def daily_plot_module():
    import importlib.util
    import pytest

    pytest.importorskip("matplotlib")
    spec = importlib.util.spec_from_file_location(
        "daily_return_plot_builder", ROOT / "scripts/build_daily_return_figures.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_daily_return_plots_use_every_unmodified_baseline_return():
    import csv
    import hashlib
    import numpy as np

    module = daily_plot_module()
    expected_counts = {"development": 1007, "validation": 753, "historical_OOS": 700}
    loaded = {}
    for stage, count in expected_counts.items():
        data = module.load_baseline(ROOT, stage)
        path = ROOT / f"reports/reproducibility/{stage}.csv"
        with path.open(newline="") as handle:
            rows = [
                r for r in csv.DictReader(handle) if r["slippage_bps_each_way"] == "3"
            ]
        assert data["observations"] == len(data["dates"]) == count
        assert data["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert data["date_strings"] == tuple(r["date"] for r in rows)
        assert len(data["returns"]) == 5
        for series, values in data["returns"].items():
            # Raw net simple returns: no cumprod, cash subtraction or initial zero.
            np.testing.assert_array_equal(
                values, [float(r[series + "_return"]) for r in rows]
            )
        loaded[stage] = data
    lower, upper = module.common_limits(loaded)
    for data in loaded.values():
        for values in data["returns"].values():
            assert lower <= min(values) * 100 <= max(values) * 100 <= upper


def test_daily_return_images_and_links_are_published_for_every_period():
    import hashlib

    manifest = json.loads(
        (ROOT / "reports/etf_portfolios/figures_manifest.json").read_text()
    )
    daily = manifest["daily_return_figures"]
    assert daily["commission_bps_each_way"] == 1
    assert daily["baseline_slippage_bps_each_way"] == 3
    assert daily["aggregation_smoothing_interpolation_clipping"] == "none"
    names = manifest["curve_names"]
    readme = (ROOT / "README.md").read_text()
    index = (ROOT / "reports/etf_portfolios/README.md").read_text()
    report = (ROOT / "reports/etf_portfolios/report.md").read_text()
    for stage, count in (
        ("development", 1007),
        ("validation", 753),
        ("historical_OOS", 700),
    ):
        figure = daily["figures"][stage]
        filename = f"{stage}_daily_returns_baseline.png"
        assert figure["filename"] == filename
        assert figure["daily_observations"] == count
        assert figure["curves"] == names
        assert figure["y_limits_percent"] == daily["shared_y_limits_percent"]
        assert (
            figure["sha256"]
            == hashlib.sha256(
                (ROOT / "reports/etf_portfolios" / filename).read_bytes()
            ).hexdigest()
        )
        assert filename in index and filename in report
        if stage == "historical_OOS":
            assert filename in readme
        else:
            assert filename not in readme
        period_report = ROOT / "reports/etf_portfolios" / f"{stage}_report.md"
        period_text = period_report.read_text()
        assert filename in period_text and f"{stage}_baseline.png" in period_text
        assert f"{stage}_report.md" in readme


def test_daily_plot_loader_rejects_revised_csv_without_release_receipt(tmp_path):
    import shutil
    import pytest

    module = daily_plot_module()
    folder = tmp_path / "reports/reproducibility"
    folder.mkdir(parents=True)
    shutil.copyfile(
        ROOT / "reports/reproducibility/manifest.json", folder / "manifest.json"
    )
    source = ROOT / "reports/reproducibility/development.csv"
    (folder / "development.csv").write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="SHA256|byte count"):
        module.load_baseline(tmp_path, "development")


def test_daily_plot_loader_rejects_nonfinite_values_even_with_refreshed_receipt(
    tmp_path,
):
    import csv
    import hashlib
    import pytest

    module = daily_plot_module()
    folder = tmp_path / "reports/reproducibility"
    folder.mkdir(parents=True)
    release = json.loads((ROOT / "reports/reproducibility/manifest.json").read_text())
    source = ROOT / "reports/reproducibility/development.csv"
    with source.open(newline="") as handle:
        reader = csv.DictReader(handle)
        names = reader.fieldnames
        rows = list(reader)
    rows[0]["initial_allocation_return"] = "nan"
    changed = folder / "development.csv"
    with changed.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)
    record = next(
        r
        for r in release["files"]
        if r["path"] == "reports/reproducibility/development.csv"
    )
    record.update(
        bytes=changed.stat().st_size,
        sha256=hashlib.sha256(changed.read_bytes()).hexdigest(),
    )
    (folder / "manifest.json").write_text(json.dumps(release))
    with pytest.raises(ValueError, match="Nonfinite|invalid simple"):
        module.load_baseline(tmp_path, "development")


def test_cash_clock_explanation_keeps_accrual_distinct_from_statistics():
    methods = (ROOT / "docs/etf_methods.md").read_text()
    section = methods.split("### Calendar-time cash versus trading-day statistics", 1)[
        1
    ].split("## Statistics and attribution", 1)[0]
    for phrase in (
        "elapsed_seconds",
        "365 * 86400",
        "252",
        "weekends",
        "same elapsed interval",
        "3.045%",
        "not an",
        "frozen forward model is changed",
    ):
        assert phrase in section
    readme = (ROOT / "README.md").read_text()
    assert readme.index("historical_OOS_baseline.png") < readme.index(
        "historical_OOS_daily_returns_baseline.png"
    )
    assert "development_daily_returns_baseline.png" not in readme
    assert "validation_daily_returns_baseline.png" not in readme
