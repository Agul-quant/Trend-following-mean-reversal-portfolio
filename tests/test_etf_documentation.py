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
