"""Plots use generated synthetic paths only; no historical daily rows in Git."""
import json

import numpy as np
import pytest

from trend_portfolio.analytics import cap_diagnostics
from trend_portfolio.plotting import main, prepare_plot_data, render_plots


def synthetic():
    # Distinct ACTIVE QQQ and PASSIVE QQQ paths catch benchmark substitution.
    times = np.array([f"2024-01-0{i}T22:00:00Z" for i in range(2, 9)])
    equity = np.array([[.99, .995, 1.0], [1.02, 1.005, .998], [1.01, .98, 1.001],
                       [1.05, 1.02, 1.002], [1.03, 1.04, .997], [1.06, 1.045, 1.004],
                       [1.059, 1.044, 1.003]])
    # First and final losses model already embedded entry/terminal costs.
    bh = np.array([-.001, .03, -.04, .02, .01, .01, -.002])
    factors = np.column_stack([np.zeros(7), bh, np.zeros(7)])
    bundle = {"timestamps": times, "symbols": np.array(["GDX", "QQQ", "BND"]),
              "slippage_bps": np.array([1, 3, 10, 25]),
              "sleeve_normalized_equity": np.stack([equity * 1.001, equity, equity * .999, equity * .997]),
              "buy_and_hold_returns": np.stack([factors * .9, factors, factors * 1.1, factors * 1.2]),
              "cash_returns": np.full(7, .0001)}
    portfolios = [{"id": f"mix_{i}", "initial_weights": weights} for i, weights in enumerate([
        [.4, .3, .3], [.3, .4, .3], [0, 0, 1], [1 / 3] * 3, [1, 0, 0]])]
    return bundle, portfolios


def prepared():
    bundle, portfolios = synthetic()
    return prepare_plot_data(bundle, portfolios, initial_timestamp="2024-01-02T14:30:00Z")


def test_five_fixed_portfolios_plus_passive_qqq_and_initial_point():
    bundle, portfolios = synthetic()
    original = {key: value.copy() for key, value in bundle.items()}
    caps = cap_diagnostics(bundle["sleeve_normalized_equity"], portfolios[3]["initial_weights"])
    result = prepared()
    assert result.equity.shape == (8, 6)  # Seven daily observations + fresh account.
    assert result.drawdown.shape == (8, 6)
    np.testing.assert_array_equal(result.equity[0], np.full(6, 1000))
    np.testing.assert_array_equal(result.drawdown[0], np.zeros(6))
    assert result.series_ids[-1] == "QQQ_buy_and_hold"
    assert len(result.timestamps) == 8
    expected = 1000 * (bundle["sleeve_normalized_equity"][1] @ np.array([.4, .3, .3]))
    np.testing.assert_allclose(result.equity[1:, 0], expected)
    passive = 1000 * np.cumprod(1 + bundle["buy_and_hold_returns"][1, :, 1])
    np.testing.assert_allclose(result.equity[1:, -1], passive)
    assert not np.allclose(result.equity[1:, -1], 1000 * bundle["sleeve_normalized_equity"][1, :, 1])
    for key in original:
        np.testing.assert_array_equal(bundle[key], original[key])
    assert cap_diagnostics(bundle["sleeve_normalized_equity"], portfolios[3]["initial_weights"]) == caps


def test_first_cost_and_paid_terminal_values_not_omitted_or_charged_twice():
    result = prepared()
    assert result.equity[1, -1] == pytest.approx(999)
    assert result.drawdown[1, -1] == pytest.approx(-.001)
    assert result.equity[-1, -1] / result.equity[-2, -1] - 1 == pytest.approx(-.002)
    assert result.equity[-1, 4] == pytest.approx(1059)
    assert result.drawdown[-1, 4] == pytest.approx(1059 / 1060 - 1)
    expected = result.equity / np.maximum.accumulate(result.equity, axis=0) - 1
    np.testing.assert_allclose(result.drawdown, expected)
    assert np.max(result.drawdown) <= 0


@pytest.mark.parametrize("initial", ["2024-01-02T22:00:00Z", "2024-01-03T00:00:00Z", "2024-01-02T14:30:00"])
def test_initial_timestamp_must_be_aware_and_strictly_before_first_daily(initial):
    bundle, portfolios = synthetic()
    with pytest.raises(ValueError):
        prepare_plot_data(bundle, portfolios, initial_timestamp=initial)


def test_baseline_must_exist_uniquely():
    bundle, portfolios = synthetic()
    for costs in ([1, 2, 10, 25], [1, 3, 3, 25]):
        bundle["slippage_bps"] = np.array(costs)
        with pytest.raises(ValueError, match="exactly one input cost"):
            prepare_plot_data(bundle, portfolios, initial_timestamp="2024-01-02T14:30:00Z")


def test_chronology_and_passive_basis_checks():
    bundle, portfolios = synthetic()
    bundle["timestamps"][2] = bundle["timestamps"][1]
    with pytest.raises(ValueError, match="strictly increasing"):
        prepare_plot_data(bundle, portfolios, initial_timestamp="2024-01-02T14:30:00Z")
    bundle, portfolios = synthetic()
    bundle["symbols"] = np.array(["GDX", "ACTIVE_QQQ", "BND"])
    with pytest.raises(ValueError, match="passive benchmark"):
        prepare_plot_data(bundle, portfolios, initial_timestamp="2024-01-02T14:30:00Z")
    bundle, portfolios = synthetic()
    bundle["buy_and_hold_returns"][1, 0, 1] = -1
    with pytest.raises(ValueError, match="passive benchmark returns"):
        prepare_plot_data(bundle, portfolios, initial_timestamp="2024-01-02T14:30:00Z")


def test_raster_only_deterministic_metadata_and_no_overwrite(tmp_path):
    pytest.importorskip("matplotlib")
    from PIL import Image
    data = prepared()
    first = render_plots(data, tmp_path / "attempt1")
    second = render_plots(data, tmp_path / "attempt2")
    assert {p.name for p in first.values()} == {"baseline_equity.png", "baseline_drawdown.png"}
    assert len(list((tmp_path / "attempt1").iterdir())) == 2
    for key in first:
        assert first[key].read_bytes() == second[key].read_bytes()
        with Image.open(first[key]) as image:
            assert image.format == "PNG" and image.width >= 1600
            assert image.info["Software"] == "Trend Following Study"
            assert set(image.info) <= {"Software", "dpi"}
            assert str(tmp_path) not in str(image.info)
    with pytest.raises(ValueError, match="already exist"):
        render_plots(data, tmp_path / "attempt1")


def test_cli_writes_exactly_two_pngs_with_no_private_arrays(tmp_path):
    pytest.importorskip("matplotlib")
    bundle, portfolios = synthetic()
    private = tmp_path / "private_inputs.npz"
    np.savez(private, **bundle)
    config = tmp_path / "p.json"
    config.write_text(json.dumps({"portfolios": [{"id": p["id"], "initial_weights": p["initial_weights"]} for p in portfolios]}))
    output = tmp_path / "new_attempt"
    assert main(["--input", str(private), "--portfolios", str(config), "--output-dir", str(output),
                 "--initial-timestamp", "2024-01-02T14:30:00Z"]) == 0
    assert sorted(path.suffix for path in output.iterdir()) == [".png", ".png"]
