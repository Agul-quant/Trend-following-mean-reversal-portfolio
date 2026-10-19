"""Temporary, generated synthetic inputs exercise the private input adapter."""
import json

import numpy as np
import pytest

from trend_portfolio.cli import _json_safe, load_bundle, load_portfolios, main


def make_bundle(path, **replacements):
    rng = np.random.default_rng(2026)
    c, t, s = 4, 70, 3
    cash = np.linspace(.00005, .00015, t)
    returns = rng.normal(.0005, .006, size=(c, t, s))
    arrays = dict(
        timestamps=np.array([f"2024-01-{i + 1:02d}T21:00:00Z" for i in range(28)] +
                            [f"2024-02-{i + 1:02d}T21:00:00Z" for i in range(29)] +
                            [f"2024-03-{i + 1:02d}T21:00:00Z" for i in range(13)]),
        symbols=np.array(["A", "B", "C"]), slippage_bps=np.array([1, 3, 10, 25]),
        cash_returns=cash, sleeve_normalized_equity=np.cumprod(1 + returns, axis=1),
        buy_and_hold_returns=rng.normal(.0004, .01, size=(c, t, s)),
    )
    arrays.update(replacements)
    np.savez(path, **arrays)
    return arrays


def test_cli_writes_aggregate_only_and_refuses_overwrite(tmp_path):
    source = tmp_path / "secret_input.npz"
    make_bundle(source)
    portfolios = tmp_path / "allocations.json"
    portfolios.write_text(json.dumps({"portfolios": [{"id": "equal", "initial_weights": {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}}]}))
    output = tmp_path / "aggregate.json"
    args = ["--input", str(source), "--portfolios", str(portfolios), "--years", "1", "--output", str(output)]
    assert main(args) == 0
    raw = output.read_text()
    result = json.loads(raw)
    assert len(result["portfolio_results"]) == 1
    assert len(result["portfolio_results"][0]["cost_results"]) == 4
    assert len(result["sleeve_results"]) == 12
    assert "timestamps" not in raw and "secret_input" not in raw and str(tmp_path) not in raw
    assert "sleeve_normalized_equity" not in raw
    with pytest.raises(SystemExit):
        main(args)


def test_cli_explicit_max_cagr_refit(tmp_path):
    source = tmp_path / "input.npz"
    make_bundle(source)
    portfolios = tmp_path / "p.json"
    portfolios.write_text(json.dumps({"equal": {"weights": [1 / 3] * 3}}))
    output = tmp_path / "out.json"
    assert main(["--input", str(source), "--portfolios", str(portfolios), "--years", "1",
                 "--output", str(output), "--optimize", "max-cagr"]) == 0
    result = json.loads(output.read_text())
    assert len(result["portfolio_results"]) == 2
    assert sorted(result["new_retrospective_fit"]["initial_weights"]) == [0, 0, 1]


def test_json_nonfinite_metrics_are_null():
    assert _json_safe({"x": [float("nan"), np.inf, -np.inf, np.float64(1)]}) == {"x": [None, None, None, 1.0]}
    assert json.dumps(_json_safe({"sharpe": np.nan}), allow_nan=False) == '{"sharpe": null}'


@pytest.mark.parametrize("field,value", [
    ("cash_returns", np.zeros(4)),
    ("slippage_bps", np.array([1, 3, 3, 25])),
    ("symbols", np.array(["A", "A", "C"])),
    ("symbols", np.array(["A", "B"])),
    ("buy_and_hold_returns", np.zeros((4, 70, 2))),
    ("sleeve_normalized_equity", np.zeros((4, 70, 3))),
    ("cash_returns", np.full(70, np.nan)),
    ("cash_returns", np.full(70, -1)),
])
def test_invalid_bundle_rejected(tmp_path, field, value):
    source = tmp_path / "input.npz"
    make_bundle(source, **{field: value})
    with pytest.raises(ValueError):
        load_bundle(source)


def test_duplicate_or_naive_timestamps_rejected(tmp_path):
    source = tmp_path / "input.npz"
    original = make_bundle(source)
    times = original["timestamps"].copy()
    times[1] = times[0]
    make_bundle(source, timestamps=times)
    with pytest.raises(ValueError, match="strictly increasing"):
        load_bundle(source)
    times = np.array([str(value).replace("Z", "") for value in original["timestamps"]])
    make_bundle(source, timestamps=times)
    with pytest.raises(ValueError, match="UTC offset"):
        load_bundle(source)


def test_missing_required_fields_rejected(tmp_path):
    source = tmp_path / "input.npz"
    np.savez(source, timestamps=["2024-01-01T21:00:00Z"])
    with pytest.raises(ValueError, match="missing fields"):
        load_bundle(source)


def test_weight_symbol_mapping_exactness_and_duplicate_ids(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"p": {"initial_weights": {"A": .5, "C": .5}}}))
    with pytest.raises(ValueError, match="exactly"):
        load_portfolios(path, ["A", "B"])
    path.write_text(json.dumps([{"id": "p", "weights": [.5, .5]}, {"id": "p", "weights": [.5, .5]}]))
    with pytest.raises(ValueError, match="unique"):
        load_portfolios(path, ["A", "B"])
