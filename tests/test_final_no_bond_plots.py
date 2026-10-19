"""Synthetic-only fixtures for new fixed five-ETF portfolio raster views."""
import importlib.util
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/plot_final_no_bond.py"
SPEC = importlib.util.spec_from_file_location("final_no_bond_plot_script", SCRIPT)
plot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plot)


def fixture():
    rng = np.random.default_rng(733)
    n = 8
    returns = rng.normal(.002, .005, (n, 6))
    returns[0, 2] = -.001
    returns[-1, 2] = -.002
    base = np.cumprod(1 + returns, axis=0)
    factors = rng.normal(.001, .01, (n, 6))
    factors[0, 2], factors[-1, 2] = -.001, -.002
    source = {"timestamps": np.array([f"2024-01-{index + 2:02d}T22:00:00Z" for index in range(n)]),
              "symbols": np.array(plot.SOURCE_SYMBOLS), "slippage_bps": np.array([1, 3, 10, 25]),
              "sleeve_normalized_equity": np.stack([base * value for value in (1.001, 1, .999, .997)]),
              "buy_and_hold_returns": np.stack([factors * value for value in (.9, 1, 1.1, 1.2)]),
              "cash_returns": np.full((4, n), .0001)}
    vectors = ([.2] * 5, [.3, .2, .1, .2, .2], [.02, .02, .9, .02, .04], [.2] * 5)
    report = {"schema": "five_etf_four_portfolio_comparison_v1", "symbols": list(plot.SYMBOLS),
              "portfolios": [{"id": identifier, "initial_weights": dict(zip(plot.SYMBOLS, weights))}
                             for identifier, weights in zip(plot.IDS, vectors)],
              "portfolio_rows": [], "control_rows": [], "commission_bps_each_way": 1,
              "initial_capital_each_stage": 1000, "slippage_bps_each_way": [1, 3, 10, 25]}
    data = plot.prepare_no_bond_data(source, report, "2024-01-02T14:30:00Z")
    for column, identifier in enumerate(data.series_ids):
        record = {"stage": "historical_OOS", "slippage_bps_each_way": 3,
                  "commission_bps_each_way": 1, "observations": n,
                  "terminal_equity_from_1000": data.equity[-1, column],
                  "max_drawdown": data.drawdown[:, column].min()}
        if identifier == "QQQ_buy_and_hold":
            report["control_rows"].append({**record, "control_id": identifier})
        else:
            report["portfolio_rows"].append({**record, "portfolio_id": identifier})
    return source, report, data


def test_exact_bnd_slice_four_portfolios_and_passive_qqq_without_rebalancing():
    source, report, data = fixture()
    original = {key: value.copy() for key, value in source.items()}
    sliced = plot.without_bonds(source)
    assert sliced["symbols"].tolist() == list(plot.SYMBOLS)
    np.testing.assert_array_equal(sliced["sleeve_normalized_equity"], source["sleeve_normalized_equity"][:, :, :5])
    assert data.labels == plot.LABELS and data.series_ids == (*plot.IDS, "QQQ_buy_and_hold")
    assert data.equity.shape == data.drawdown.shape == (9, 5)
    np.testing.assert_array_equal(data.equity[0], np.full(5, 1000))
    np.testing.assert_array_equal(data.drawdown[0], np.zeros(5))
    for column, item in enumerate(report["portfolios"]):
        expected = 1000 * (source["sleeve_normalized_equity"][1, :, :5]
                           @ np.array([item["initial_weights"][symbol] for symbol in plot.SYMBOLS]))
        np.testing.assert_allclose(data.equity[1:, column], expected)
    passive = 1000 * np.cumprod(1 + source["buy_and_hold_returns"][1, :, 2])
    np.testing.assert_allclose(data.equity[1:, -1], passive)
    assert not np.allclose(passive, 1000 * source["sleeve_normalized_equity"][1, :, 2])
    for key, value in original.items():
        np.testing.assert_array_equal(source[key], value)
    evidence = plot.check_saved_metrics(data, report, "historical_OOS")
    assert evidence["series"] == 5 and evidence["points_per_series"] == 9


def test_initial_and_terminal_embedded_costs_remain_visible():
    _, _, data = fixture()
    assert data.equity[1, -1] == pytest.approx(999)
    assert data.drawdown[1, -1] == pytest.approx(-.001)
    assert data.equity[-1, -1] / data.equity[-2, -1] - 1 == pytest.approx(-.002)


@pytest.mark.parametrize("mutation", ["missing", "reordered", "old_id", "bnd_weights", "bad_schema"])
def test_report_requires_exact_new_four_allocations(mutation):
    source, report, _ = fixture()
    if mutation == "missing":
        report["portfolios"].pop()
    elif mutation == "reordered":
        report["portfolios"].reverse()
    elif mutation == "old_id":
        report["portfolios"][0]["id"] = "daily_capped_max_sharpe"
    elif mutation == "bnd_weights":
        report["portfolios"][0]["initial_weights"]["BND"] = 0
    else:
        report["schema"] = "old_report"
    with pytest.raises(ValueError):
        plot.prepare_no_bond_data(source, report, "2024-01-02T14:30:00Z")


@pytest.mark.parametrize("mutation", ["source_symbols", "source_costs", "cash"])
def test_source_axis_and_matched_cash_contract(mutation):
    source, _, _ = fixture()
    if mutation == "source_symbols":
        source["symbols"] = source["symbols"][::-1]
    elif mutation == "source_costs":
        source["slippage_bps"][1] = 2
    else:
        source["cash_returns"][3, -1] += .001
    with pytest.raises(ValueError):
        plot.without_bonds(source)


@pytest.mark.parametrize("field,value", [("terminal_equity_from_1000", 999), ("max_drawdown", -.9),
                                         ("observations", 100), ("commission_bps_each_way", 0)])
def test_saved_endpoint_drawdown_and_cost_oracle(field, value):
    _, report, data = fixture()
    report["portfolio_rows"][0][field] = value
    with pytest.raises(ValueError, match="disagrees with saved"):
        plot.check_saved_metrics(data, report, "historical_OOS")


def test_release_rehashes_all_413_guards_and_checksum(tmp_path):
    guards = {}
    for index in range(413):
        path = tmp_path / f"guard_{index}"
        path.write_text(f"synthetic guard {index}")
        guards[str(path)] = plot.digest(path)
    payload = {"authorized_saved_path_evaluation": True, "source_file_sha256": guards,
               "files": {**guards, str(SCRIPT): plot.digest(SCRIPT)}}
    released = {"payload": payload, "payload_sha256": hashlib.sha256(plot.canonical(payload)).hexdigest()}
    path = tmp_path / "release.json"
    path.write_text(json.dumps(released))
    assert len(plot.verify_release(path, [SCRIPT])) == 414
    (tmp_path / "guard_412").write_text("changed last guard")
    with pytest.raises(ValueError, match="changed before or during"):
        plot.verify_release(path, [SCRIPT])
    released["payload_sha256"] = "0" * 64
    path.write_text(json.dumps(released))
    with pytest.raises(ValueError, match="checksum"):
        plot.verify_release(path, [SCRIPT])


def test_insufficient_guard_or_missing_required_implementation_rejected(tmp_path):
    input_file = tmp_path / "input"
    input_file.write_bytes(b"synthetic")
    release = tmp_path / "release.json"
    release.write_text(json.dumps({"files": {str(input_file): plot.digest(input_file)},
                                  "source_file_sha256": {}, "authorized_saved_path_evaluation": True}))
    with pytest.raises(ValueError, match="413"):
        plot.verify_release(release, [SCRIPT])


def test_raster_only_five_curves_metadata_and_no_overwrite(tmp_path):
    pytest.importorskip("matplotlib")
    from PIL import Image
    _, _, data = fixture()
    first, second = tmp_path / "attempt1.png", tmp_path / "attempt2.png"
    plot.render_combined(data, "historical_OOS", first)
    plot.render_combined(data, "historical_OOS", second)
    assert first.read_bytes() == second.read_bytes()
    with Image.open(first) as picture:
        assert picture.format == "PNG" and picture.size == (1300, 1010)
        assert set(picture.info) <= {"Software", "dpi"}
        assert str(tmp_path) not in str(picture.info)
    with pytest.raises(ValueError, match="already exists"):
        plot.render_combined(data, "historical_OOS", first)
