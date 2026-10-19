"""Private-input-free integrity and cross-link checks for published aggregates."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import itertools
import json
import re
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ["GDX", "FXI", "QQQ", "UNG", "FDN", "BND"]
COSTS = [1.0, 3.0, 10.0, 25.0]
IDS = [
    "daily_capped_max_sharpe",
    "initial_capped_max_sharpe",
    "uncapped_max_sharpe",
    "equal_initial",
    "max_cagr_100pct_gdx",
]
CSV_COUNTS = {
    "portfolio_metrics_all_costs.csv": 20,
    "portfolio_capital_drift_all_costs.csv": 120,
    "strategy_metrics_all_costs.csv": 24,
    "own_ETF_buy_and_hold_metrics_all_costs.csv": 24,
    "strategy_correlation_matrices_all_costs.csv": 24,
    "strategy_correlation_pairs_all_costs.csv": 60,
    "QQQ_single_factor_portfolios_all_costs.csv": 20,
    "QQQ_single_factor_strategy_sleeves_all_costs.csv": 24,
    "six_factor_portfolios_all_costs.csv": 20,
    "six_factor_strategy_sleeves_all_costs.csv": 24,
    "pairwise_portfolio_betas_all_costs.csv": 120,
    "pairwise_strategy_sleeve_betas_all_costs.csv": 144,
}


def read_json(relative):
    return json.loads((ROOT / relative).read_text())


def rows(filename):
    with (ROOT / "results" / filename).open(newline="") as handle:
        return list(csv.DictReader(handle))


def portfolio_config():
    return read_json("configs/portfolios.json")


def import_export_helper():
    spec = importlib.util.spec_from_file_location(
        "public_export_helper", ROOT / "scripts" / "export_saved_results.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def markdown_tables(relative):
    tables, current = [], []
    for line in (ROOT / relative).read_text().splitlines() + [""]:
        if line.startswith("|"):
            cells = [
                cell.strip().replace("**", "").replace("−", "-")
                for cell in line.strip("|").split("|")
            ]
            if not all(set(cell) <= set(":- ") for cell in cells):
                current.append(cells)
        elif current:
            tables.append(current)
            current = []
    return tables


def test_exact_aggregate_manifest_hashes_are_stable_twice():
    manifest = read_json("results/export_manifest.json")
    expected = {f"results/{name}" for name in CSV_COUNTS}
    expected.update(
        {
            "configs/selected_strategies.json",
            "configs/portfolios.json",
            "configs/research_protocol.json",
            "results/six_factor_diagnostics.json",
            "results/provenance.json",
            "results/verification.json",
        }
    )
    assert len(expected) == 18 and set(manifest["files"]) == expected
    before = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in expected
    }
    after = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in expected
    }
    assert before == after == manifest["files"]
    assert len(expected | {"results/export_manifest.json"}) == 19
    assert manifest["public_aggregate_only"] is True


@pytest.mark.parametrize("filename,expected", CSV_COUNTS.items())
def test_complete_public_csv_dimensions(filename, expected):
    assert len(rows(filename)) == expected


def test_six_exact_configurations_and_protocol():
    config = read_json("configs/selected_strategies.json")
    assert config["symbols"] == SYMBOLS
    assert [row["symbol"] for row in config["strategies"]] == SYMBOLS
    assert len({row["candidate_id"] for row in config["strategies"]}) == 6
    for row in config["strategies"]:
        assert set(row) == {"symbol", "style", "candidate_id", "label", "definition"}
        assert "3" in row["candidate_id"]
    by_symbol = {row["symbol"]: row for row in config["strategies"]}
    assert by_symbol["GDX"]["definition"] == {
        "confirmation_hours": 3.0,
        "entry_threshold": -2.0,
        "exit_threshold": 0.0,
        "rule": {"family": "ZSCORE", "period": 20},
    }
    assert by_symbol["QQQ"]["definition"]["entry_rule"]["period"] == 50
    assert by_symbol["QQQ"]["definition"]["exit_rule"]["period"] == 200
    protocol = read_json("configs/research_protocol.json")
    assert protocol["historical_OOS"] == {
        "start": "2024-01-01",
        "first_session": "2024-01-02",
        "end": "2026-10-15",
        "sessions": 700,
    }
    assert protocol["costs"]["slippage_bps_each_way"] == COSTS
    assert (
        protocol["cash"]["nominal_annual_rate"] == 0.03
        and protocol["cash"]["day_count"] == "ACT/365"
    )
    assert (
        protocol["timing"]["consecutive_checks"] == 7
        and protocol["timing"]["shared_confirmation_hours"] == 3.0
    )


def test_five_fixed_weight_variants_current_choice_and_variant_specific_claims():
    config = portfolio_config()
    assert config["symbols"] == SYMBOLS
    assert [row["id"] for row in config["portfolios"]] == IDS
    assert sum(row["current_choice"] for row in config["portfolios"]) == 1
    for row in config["portfolios"]:
        w = np.array([row["initial_weights"][s] for s in SYMBOLS])
        assert np.isfinite(w).all() and w.min() >= 0.0 and abs(w.sum() - 1.0) < 1e-12
        assert row["current_choice"] == (row["id"] == IDS[0])
        assert row["global_optimum_certified"] == (row["id"] == "max_cagr_100pct_gdx")
        if row["cap_scope"] != "none":
            assert w.max() <= 1.0 / 3.0 + 1e-12
    current = config["portfolios"][0]
    assert current["cap_scope"] == "historical_daily_valuation_all_four_costs"
    assert config["portfolios"][1]["cap_scope"] == "initial_only"
    assert config["portfolios"][-1]["initial_weights"] == {
        s: float(s == "GDX") for s in SYMBOLS
    }


def test_portfolio_cost_identity_CAGR_clock_and_metric_finiteness():
    data = rows("portfolio_metrics_all_costs.csv")
    assert {
        (r["portfolio_id"], float(r["slippage_bps_each_way"])) for r in data
    } == set(itertools.product(IDS, COSTS))
    years = read_json("configs/research_protocol.json")["ACT365_elapsed_years"]
    for row in data:
        assert float(row["commission_bps_each_way"]) == 1.0
        for field, value in row.items():
            if field != "portfolio_id":
                assert np.isfinite(float(value))
        assert float(row["max_drawdown"]) <= 0.0
        calculated = (float(row["terminal_equity_from_1000"]) / 1000.0) ** (
            1.0 / years
        ) - 1.0
        assert float(row["cagr"]) == pytest.approx(calculated, abs=1e-13)


def test_drift_cap_and_static_initial_weights():
    config = {r["id"]: r for r in portfolio_config()["portfolios"]}
    data = rows("portfolio_capital_drift_all_costs.csv")
    for pid, cost in itertools.product(IDS, COSTS):
        selected = [
            r
            for r in data
            if r["portfolio_id"] == pid and float(r["slippage_bps_each_way"]) == cost
        ]
        assert {r["symbol"] for r in selected} == set(SYMBOLS)
        assert sum(
            float(r["terminal_sleeve_capital_share"]) for r in selected
        ) == pytest.approx(1.0, abs=1e-12)
        for row in selected:
            assert (
                float(row["initial_weight"])
                == config[pid]["initial_weights"][row["symbol"]]
            )
            assert float(
                row["max_observed_daily_sleeve_capital_share"]
            ) + 1e-12 >= float(row["terminal_sleeve_capital_share"])
            if pid == IDS[0]:
                assert (
                    float(row["max_observed_daily_sleeve_capital_share"])
                    <= 1.0 / 3.0 + 1e-12
                )
    a_gdx = next(
        r
        for r in data
        if r["portfolio_id"] == IDS[1]
        and r["symbol"] == "GDX"
        and float(r["slippage_bps_each_way"]) == 3.0
    )
    assert float(a_gdx["max_observed_daily_sleeve_capital_share"]) > 0.38


def test_strategy_and_passive_control_units_and_fills():
    definitions = {
        r["symbol"]: r
        for r in read_json("configs/selected_strategies.json")["strategies"]
    }
    for filename, is_passive in [
        ("strategy_metrics_all_costs.csv", False),
        ("own_ETF_buy_and_hold_metrics_all_costs.csv", True),
    ]:
        data = rows(filename)
        assert {(r["symbol"], float(r["slippage_bps_each_way"])) for r in data} == set(
            itertools.product(SYMBOLS, COSTS)
        )
        for row in data:
            assert row["candidate_id"] == (
                "benchmark_buy_and_hold"
                if is_passive
                else definitions[row["symbol"]]["candidate_id"]
            )
            assert int(row["fills"]) == 2 * int(row["completed_round_trips"])
            if is_passive:
                assert int(row["completed_round_trips"]) == 1
    assert (
        "no event ledger"
        in read_json("results/provenance.json")["QQQ_trade_count_caveat"]
    )


def test_correlations_symmetric_unit_diagonal_and_all_pair_links():
    matrices, pairs = (
        rows("strategy_correlation_matrices_all_costs.csv"),
        rows("strategy_correlation_pairs_all_costs.csv"),
    )
    for cost in COSTS:
        records = {
            r["symbol"]: r
            for r in matrices
            if float(r["slippage_bps_each_way"]) == cost
        }
        assert set(records) == set(SYMBOLS)
        matrix = np.array([[float(records[s][t]) for t in SYMBOLS] for s in SYMBOLS])
        np.testing.assert_allclose(matrix, matrix.T, atol=5e-15, rtol=0.0)
        np.testing.assert_allclose(np.diag(matrix), 1.0, atol=5e-15, rtol=0.0)
        assert np.linalg.eigvalsh(matrix).min() >= -1e-12
        selected = [r for r in pairs if float(r["slippage_bps_each_way"]) == cost]
        assert {(r["symbol_1"], r["symbol_2"]) for r in selected} == set(
            itertools.combinations(SYMBOLS, 2)
        )
        for row in selected:
            assert float(row["pearson_daily_net_strategy_returns"]) == float(
                records[row["symbol_1"]][row["symbol_2"]]
            )


def test_all_regression_cost_dimensions_and_alpha_units():
    files = [
        "QQQ_single_factor_portfolios_all_costs.csv",
        "QQQ_single_factor_strategy_sleeves_all_costs.csv",
        "six_factor_portfolios_all_costs.csv",
        "six_factor_strategy_sleeves_all_costs.csv",
        "pairwise_portfolio_betas_all_costs.csv",
        "pairwise_strategy_sleeve_betas_all_costs.csv",
    ]
    for filename in files:
        data = rows(filename)
        is_portfolio = "portfolio" in filename
        key = "portfolio_id" if is_portfolio else "symbol"
        universe = IDS if is_portfolio else SYMBOLS
        assert {(r[key], float(r["slippage_bps_each_way"])) for r in data} == set(
            itertools.product(universe, COSTS)
        )
        for row in data:
            assert (
                float(row["commission_bps_each_way"]) == 1.0
                and int(row["observations"]) == 700
            )
            assert float(row["alpha_annual_arithmetic"]) == pytest.approx(
                252.0 * float(row["alpha_daily"]), abs=1e-14
            )
            assert 0.0 <= float(row["R_squared"]) <= 1.0
            if filename.startswith("six_factor"):
                expected = 1.0 - (1.0 - float(row["R_squared"])) * 699.0 / 693.0
                assert float(row["adjusted_R_squared"]) == pytest.approx(
                    expected, abs=1e-14
                )


def test_pairwise_QQQ_matches_prior_single_factor_and_joint_R2_nesting():
    for kind, key in [("portfolios", "portfolio_id"), ("strategy_sleeves", "symbol")]:
        previous = rows(f"QQQ_single_factor_{kind}_all_costs.csv")
        pairs = rows(
            f"pairwise_{'portfolio' if kind == 'portfolios' else 'strategy_sleeve'}_betas_all_costs.csv"
        )
        joint = rows(f"six_factor_{kind}_all_costs.csv")
        for old in previous:
            same = [
                r
                for r in pairs
                if r[key] == old[key]
                and r["slippage_bps_each_way"] == old["slippage_bps_each_way"]
            ]
            assert {r["passive_ETF_factor"] for r in same} == set(SYMBOLS)
            qqq = next(r for r in same if r["passive_ETF_factor"] == "QQQ")
            assert float(qqq["beta"]) == pytest.approx(
                float(old["beta_to_QQQ_BH"]), abs=1e-13
            )
            for field in ["alpha_daily", "alpha_annual_arithmetic", "R_squared"]:
                assert float(qqq[field]) == pytest.approx(float(old[field]), abs=1e-13)
            joint_row = next(
                r
                for r in joint
                if r[key] == old[key]
                and r["slippage_bps_each_way"] == old["slippage_bps_each_way"]
            )
            assert float(joint_row["R_squared"]) + 1e-12 >= max(
                float(r["R_squared"]) for r in same
            )


def test_max_CAGR_portfolio_is_same_as_GDX_strategy():
    portfolios = rows("portfolio_metrics_all_costs.csv")
    strategies = rows("strategy_metrics_all_costs.csv")
    joint_p = rows("six_factor_portfolios_all_costs.csv")
    joint_s = rows("six_factor_strategy_sleeves_all_costs.csv")
    for cost in COSTS:
        p = next(
            r
            for r in portfolios
            if r["portfolio_id"] == "max_cagr_100pct_gdx"
            and float(r["slippage_bps_each_way"]) == cost
        )
        s = next(
            r
            for r in strategies
            if r["symbol"] == "GDX" and float(r["slippage_bps_each_way"]) == cost
        )
        for field in [
            "cash_excess_sharpe",
            "cagr",
            "max_drawdown",
            "terminal_equity_from_1000",
        ]:
            assert float(p[field]) == pytest.approx(float(s[field]), abs=1e-11)
        jp = next(
            r
            for r in joint_p
            if r["portfolio_id"] == "max_cagr_100pct_gdx"
            and float(r["slippage_bps_each_way"]) == cost
        )
        js = next(
            r
            for r in joint_s
            if r["symbol"] == "GDX" and float(r["slippage_bps_each_way"]) == cost
        )
        for field in [
            "alpha_annual_arithmetic",
            "R_squared",
            *[f"beta_{t}" for t in SYMBOLS],
        ]:
            assert float(jp[field]) == pytest.approx(float(js[field]), abs=1e-12)


def test_factor_diagnostics_names_full_rank_and_moderate_overlap():
    result = read_json("results/six_factor_diagnostics.json")
    assert result["factor_order"] == SYMBOLS
    assert [row["slippage_bps_each_way"] for row in result["diagnostics"]] == COSTS
    for row in result["diagnostics"]:
        assert row["rank_including_intercept"] == 7
        assert set(row["variance_inflation_factors"]) == set(SYMBOLS)
        assert all(v >= 1.0 for v in row["variance_inflation_factors"].values())
        assert row["standardized_factor_condition_number"] > 1.0


def test_public_provenance_contains_hashes_not_private_sources():
    manifest = read_json("results/export_manifest.json")
    provenance = read_json("results/provenance.json")
    assert (
        provenance["source_delivery_receipt_sha256"]
        == manifest["source_receipt_sha256"]
    )
    assert len(provenance["source_delivery_receipt_sha256"]) == 6
    for value in provenance["source_delivery_receipt_sha256"].values():
        assert len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)
    for name in manifest["files"]:
        text = (ROOT / name).read_text()
        assert (
            str(Path.home()) not in text
            and ".cache/" not in text
            and "file://" not in text
        )
        assert (
            "input_files_before_and_after" not in text and "human_request" not in text
        )
    verification = read_json("results/verification.json")
    assert verification["passed"] is True
    assert (
        verification[
            "full_daily_arrays_market_paths_source_maps_or_private_receipts_exported"
        ]
        is False
    )
    assert (
        verification[
            "byte_identical_reexport_with_same_verified_inputs_and_numeric_runtime"
        ]
        is True
    )


def test_export_module_import_and_serialization_need_no_private_inputs():
    module = import_export_helper()
    value = {"b": [0.1, -0.2], "a": "synthetic"}
    assert module.json_text(value) == module.json_text(value)
    fixture = [{"id": "synthetic", "value": 0.125}, {"id": "another", "value": -0.25}]
    assert module.csv_text(fixture) == module.csv_text(fixture)
    with pytest.raises(ValueError):
        module.json_text({"not_finite": float("nan")})


def test_export_rejects_result_not_bound_by_receipt_before_array_decode(
    tmp_path, monkeypatch
):
    module = import_export_helper()
    manifest, fake_pins = {}, {}
    for name in module.PINNED_RECEIPTS:
        folder = tmp_path / name
        folder.mkdir()
        filenames = {
            filename
            for receipt, filename in module.RECEIPT_BOUND_INPUTS.values()
            if receipt == name
        }
        files = {}
        for filename in filenames:
            path = folder / filename
            path.write_text('{"synthetic_fixture": true}\n')
            files[filename] = module.digest(path)
        receipt = folder / "receipt.json"
        receipt.write_text(json.dumps({"status": "complete", "files": files}))
        fake_pins[name] = module.digest(receipt)
        manifest[name] = {"path": str(receipt), "sha256": fake_pins[name]}
    forged = tmp_path / "unbound_result.json"
    forged.write_text('{"different_synthetic_fixture": true}\n')
    manifest["portfolio_result"] = {
        "path": str(forged),
        "sha256": module.digest(forged),
    }
    source_manifest = tmp_path / "external_manifest.json"
    source_manifest.write_text(json.dumps(manifest))
    monkeypatch.setattr(module, "PINNED_RECEIPTS", fake_pins)
    with pytest.raises(AssertionError, match="Receipt-bound input integrity failed"):
        module.export(source_manifest, tmp_path / "unused_output")
    assert not (tmp_path / "unused_output").exists()


def test_export_rejects_receipt_parent_traversal_before_read(tmp_path, monkeypatch):
    module = import_export_helper()
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps({"status": "complete", "files": {"../outside.json": "0" * 64}})
    )
    sha = module.digest(receipt)
    source_manifest = tmp_path / "external_manifest.json"
    source_manifest.write_text(
        json.dumps({"portfolio_receipt": {"path": str(receipt), "sha256": sha}})
    )
    monkeypatch.setattr(module, "PINNED_RECEIPTS", {"portfolio_receipt": sha})
    with pytest.raises(AssertionError):
        module.export(source_manifest, tmp_path / "unused_output")
    assert not (tmp_path / "unused_output").exists()


def test_archived_README_numeric_tables_match_full_precision_exports():
    tables = markdown_tables("docs/archived_five_portfolio_snapshot.md")
    assert [len(table) - 1 for table in tables] == [6, 4, 5, 1]
    config = portfolio_config()
    current = config["portfolios"][0]
    assert tables[0][1:] == [
        [s, f"{100.0 * current['initial_weights'][s]:.4f}%"] for s in SYMBOLS
    ]
    metrics = rows("portfolio_metrics_all_costs.csv")
    for row, cost in zip(tables[1][1:], COSTS, strict=True):
        assert float(re.search(r"\d+", row[0]).group()) == cost
        source = next(
            r
            for r in metrics
            if r["portfolio_id"] == IDS[0] and float(r["slippage_bps_each_way"]) == cost
        )
        assert row[1:] == [
            f"{float(source['cash_excess_sharpe']):.4f}",
            f"{100.0 * float(source['cagr']):.2f}%",
            f"{100.0 * float(source['max_drawdown']):.2f}%",
        ]
    for row, pid in zip(tables[2][1:], IDS, strict=True):
        source = next(
            r
            for r in metrics
            if r["portfolio_id"] == pid and float(r["slippage_bps_each_way"]) == 3.0
        )
        assert row[1:] == [
            f"{float(source['cash_excess_sharpe']):.4f}",
            f"{100.0 * float(source['cagr']):.2f}%",
            f"{100.0 * float(source['max_drawdown']):.2f}%",
        ]
    attribution = next(
        r
        for r in rows("six_factor_portfolios_all_costs.csv")
        if r["portfolio_id"] == IDS[0] and float(r["slippage_bps_each_way"]) == 3.0
    )
    assert tables[3][1] == [
        *[f"{float(attribution[f'beta_{s}']):.4f}" for s in SYMBOLS],
        f"{100.0 * float(attribution['alpha_annual_arithmetic']):.2f}%/year",
        f"{100.0 * float(attribution['R_squared']):.2f}%",
    ]


def test_results_README_all_numeric_tables_and_file_counts():
    tables = markdown_tables("results/README.md")
    assert [len(table) - 1 for table in tables] == [6, 6, 5, 12]
    strategies, passive = (
        rows("strategy_metrics_all_costs.csv"),
        rows("own_ETF_buy_and_hold_metrics_all_costs.csv"),
    )
    for cells, symbol in zip(tables[0][1:], SYMBOLS, strict=True):
        active = next(
            r
            for r in strategies
            if r["symbol"] == symbol and float(r["slippage_bps_each_way"]) == 3.0
        )
        bh = next(
            r
            for r in passive
            if r["symbol"] == symbol and float(r["slippage_bps_each_way"]) == 3.0
        )
        assert cells == [
            symbol,
            f"{float(active['cash_excess_sharpe']):.4f}",
            f"{100.0 * float(active['cagr']):.2f}%",
            f"{100.0 * float(active['max_drawdown']):.2f}%",
            active["completed_round_trips"],
            f"{float(bh['cash_excess_sharpe']):.4f}",
            f"{100.0 * float(bh['cagr']):.2f}%",
            f"{100.0 * float(bh['max_drawdown']):.2f}%",
        ]
    matrix = {
        r["symbol"]: r
        for r in rows("strategy_correlation_matrices_all_costs.csv")
        if float(r["slippage_bps_each_way"]) == 3.0
    }
    assert tables[1][1:] == [
        [s, *[f"{float(matrix[s][t]):.4f}" for t in SYMBOLS]] for s in SYMBOLS
    ]
    configs = {r["id"]: r for r in portfolio_config()["portfolios"]}
    attribution = [
        r
        for r in rows("six_factor_portfolios_all_costs.csv")
        if float(r["slippage_bps_each_way"]) == 3.0
    ]
    for cells, source in zip(tables[2][1:], attribution, strict=True):
        assert cells == [
            configs[source["portfolio_id"]]["label"],
            *[f"{float(source[f'beta_{s}']):.4f}" for s in SYMBOLS],
            f"{100.0 * float(source['alpha_annual_arithmetic']):.2f}%/year",
            f"{100.0 * float(source['R_squared']):.2f}%",
        ]
    for cells in tables[3][1:]:
        filename = re.search(r"\(([^)]+)\)", cells[0]).group(1)
        assert int(cells[1]) == CSV_COUNTS[filename] == len(rows(filename))
