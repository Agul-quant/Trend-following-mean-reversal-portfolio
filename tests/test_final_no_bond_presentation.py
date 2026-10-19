"""Synthetic exact-subset presentation tests; no numerical account input reads."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "final_no_bond_builder", ROOT / "scripts/build_final_no_bond_reports.py"
)
assert SPEC and SPEC.loader
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)
FIXTURE_SPEC = importlib.util.spec_from_file_location(
    "saved_no_bond_synthetic_fixtures", ROOT / "tests/test_no_bond_presentation.py"
)
assert FIXTURE_SPEC and FIXTURE_SPEC.loader
SYNTHETIC = importlib.util.module_from_spec(FIXTURE_SPEC)
FIXTURE_SPEC.loader.exec_module(SYNTHETIC)


@pytest.fixture
def reports():
    source = SYNTHETIC.aggregate.__wrapped__()
    digest = "1" * 64
    result = {
        "schema": BUILDER.SCHEMA,
        "source_report_sha256": digest,
        "selection_method": BUILDER.SELECTION,
        "symbols": list(BUILDER.SYMBOLS),
        "portfolios": [r for r in source["portfolios"] if r["id"] in BUILDER.IDS],
        "stage_summaries": source["stage_summaries"],
        "control_rows": source["control_rows"],
        "strategy_correlations": source["strategy_correlations"],
        "portfolio_rows": [
            r for r in source["portfolio_rows"] if r["portfolio_id"] in BUILDER.IDS
        ],
        "checkpoint_rows": [
            r
            for r in source["checkpoint_rows"]
            if r["portfolio_id"] in BUILDER.IDS and r["checkpoint_frequency"] == "daily"
        ],
        "QQQ_single_factor_rows": [
            r
            for r in source["QQQ_single_factor_rows"]
            if r["portfolio_id"] in BUILDER.IDS
        ],
        "five_passive_factor_rows": [
            r
            for r in source["five_passive_factor_rows"]
            if r["portfolio_id"] in BUILDER.IDS
        ],
        "solver_summaries": [
            r for r in source["solver_summaries"] if r["portfolio_id"] in BUILDER.IDS
        ],
        "portfolio_correlations": [
            BUILDER.correlation_subset(row) for row in source["portfolio_correlations"]
        ],
        "source_hashes": {"synthetic_source": digest},
    }
    return copy.deepcopy(result), source, digest


def fixture_files(reports, tmp_path, monkeypatch):
    active, source, _ = reports
    source_path = tmp_path / "synthetic_six.json"
    source_path.write_text(json.dumps(source))
    digest = BUILDER.P.sha(source_path)
    monkeypatch.setattr(BUILDER, "SOURCE_REPORT_SHA", digest)
    active["source_report_sha256"] = digest
    report_path = tmp_path / "synthetic_four.json"
    report_path.write_text(json.dumps(active))
    figures = tmp_path / "figures"
    figures.mkdir()
    receipt = {
        "schema": "five_etf_four_portfolio_raster_verification_v1",
        "symbols": list(BUILDER.SYMBOLS),
        "series_ids": list(BUILDER.IDS) + [BUILDER.CONTROL_IDS[0]],
        "initial_capital": 1000,
        "baseline_commission_bps_each_way": 1,
        "baseline_slippage_bps_each_way": 3,
        "no_rebalancing": True,
        "raster_only": True,
        "daily_input_arrays_exported": False,
        "private_input_locators_exported": False,
        "all_released_guards_unchanged": True,
        "guard_count": 413,
        "saved_report_sha256": BUILDER.P.sha(report_path),
        "stage_figures": [],
    }
    for stage, (_, _, observations) in BUILDER.STAGES.items():
        path = figures / f"{stage}_baseline.png"
        path.write_bytes(SYNTHETIC.fake_png())
        receipt["stage_figures"].append(
            {
                "stage": stage,
                "file": path.name,
                "sha256": BUILDER.P.sha(path),
                "series": 5,
                "points_per_series": observations + 1,
                "initial_value": 1000,
                "all_daily_points_rendered": True,
                "saved_aggregate_checks": [
                    {
                        "series_id": p,
                        "terminal_equity_from_1000": 1331,
                        "max_drawdown": -0.1,
                    }
                    for p in BUILDER.IDS + (BUILDER.CONTROL_IDS[0],)
                ],
            }
        )
    (figures / "figures_verification.json").write_text(json.dumps(receipt))
    return report_path, source_path, figures, receipt


def test_complete_exact_saved_four_subset(reports):
    active, source, digest = reports
    assert BUILDER.validate(active, source, digest) is active
    assert [r["id"] for r in active["portfolios"]] == list(BUILDER.IDS)
    assert (
        len(active["portfolio_rows"])
        == len(active["checkpoint_rows"])
        == len(active["QQQ_single_factor_rows"])
        == len(active["five_passive_factor_rows"])
        == 48
    )
    assert len(active["control_rows"]) == 24
    assert len(active["solver_summaries"]) == 3
    assert {r["cap_mode"] for r in active["solver_summaries"]} == {
        "daily",
        "initial",
        "none",
    }
    assert (
        len(active["portfolio_correlations"])
        == len(active["strategy_correlations"])
        == 12
    )
    assert all(len(r["matrix"]) == 5 for r in active["portfolio_correlations"])


@pytest.mark.parametrize(
    "field",
    [
        "portfolios",
        "stage_summaries",
        "control_rows",
        "strategy_correlations",
        "portfolio_rows",
        "checkpoint_rows",
        "QQQ_single_factor_rows",
        "five_passive_factor_rows",
        "solver_summaries",
        "portfolio_correlations",
    ],
)
@pytest.mark.parametrize("mutation", ["missing", "reordered", "changed"])
def test_every_active_field_must_be_exact_saved_subset(reports, field, mutation):
    active, source, digest = reports
    if mutation == "missing":
        active[field].pop()
    elif mutation == "reordered":
        active[field].reverse()
    else:
        active[field][0]["injected"] = True
    with pytest.raises(ValueError, match="exact saved-result subset"):
        BUILDER.validate(active, source, digest)


@pytest.mark.parametrize(
    "mutation",
    [
        "weekly_weight",
        "monthly_metric",
        "weekly_checkpoint",
        "weekly_solver",
        "correlation_cell",
        "submatrix_order",
        "weight_change",
        "clock",
        "source_bind",
        "selection",
        "private_path",
    ],
)
def test_removed_or_modified_comparison_rejected(reports, mutation):
    active, source, digest = reports
    if mutation == "weekly_weight":
        active["portfolios"][1] = copy.deepcopy(source["portfolios"][1])
    elif mutation == "monthly_metric":
        active["portfolio_rows"][0]["portfolio_id"] = BUILDER.SOURCE_IDS[2]
    elif mutation == "weekly_checkpoint":
        active["checkpoint_rows"][0]["checkpoint_frequency"] = "weekly"
    elif mutation == "weekly_solver":
        active["solver_summaries"][0] = copy.deepcopy(source["solver_summaries"][1])
    elif mutation == "correlation_cell":
        active["portfolio_correlations"][0]["matrix"][0][1] += 0.1
    elif mutation == "submatrix_order":
        active["portfolio_correlations"][0]["portfolio_ids"].reverse()
    elif mutation == "weight_change":
        active["portfolios"][0]["initial_weights"]["GDX"] += 0.01
    elif mutation == "clock":
        active["stage_summaries"][0]["elapsed_act365_years"] += 0.1
    elif mutation == "source_bind":
        active["source_report_sha256"] = "2" * 64
    elif mutation == "selection":
        active["selection_method"] = "refit to better weights"
    else:
        active["source_hashes"] = {"/Users/private.npz": "1" * 64}
    with pytest.raises(ValueError):
        BUILDER.validate(active, source, digest)


def test_immutable_source_itself_is_validated(reports):
    active, source, digest = reports
    source["solver_summaries"][0]["certified_global_optimum"] = True
    with pytest.raises(ValueError):
        BUILDER.validate(active, source, digest)


def test_stage_html_is_offline_active_only_and_complete(reports):
    active, _, _ = reports
    for stage in BUILDER.STAGES:
        markdown, standalone = BUILDER.render_stage(active, stage, SYNTHETIC.fake_png())
        assert standalone.startswith("<!doctype html>")
        assert standalone.count("data:image/png;base64,") == 1
        assert not re.search(
            r"<script\b|(?:src|href)=[\"'](?:https?:|//|file:)", standalone
        )
        assert (
            standalone.count("<table>") == 20
        )  # baseline1,weights1,metrics4,QQQ1,joint4,daily1,corr8
        assert "@media print" in standalone and "overflow-x: auto" in standalone
        for text in (markdown, standalone):
            assert "/Users/" not in text and ".cache/" not in text
            assert "Weekly cap fit" not in text and "Monthly cap fit" not in text
            assert (
                "weekly" not in text.lower()
                or "removed from the active comparison" in text
            )
            assert "there is no later enforcement" in text
            assert "retrospective" in text.lower()
            assert "four retained" in text.lower()
            assert "five-series portfolio matrix" in text
            assert "BND beta" not in text
            assert (
                "No bond ETF or standalone Maximum CAGR portfolio is included" in text
            )
            for alias in BUILDER.ALIASES.values():
                assert alias in text
            for cost in BUILDER.COSTS:
                assert f"{int(cost)} bp slippage" in text


@pytest.mark.parametrize(
    "mutation",
    ["series", "receipt_schema", "endpoint", "weekly_id", "png_hash", "report_hash"],
)
def test_active_five_series_figure_rejections(reports, tmp_path, monkeypatch, mutation):
    report_path, source_path, figures, receipt = fixture_files(
        reports, tmp_path, monkeypatch
    )
    if mutation == "series":
        receipt["stage_figures"][0]["series"] = 7
    elif mutation == "receipt_schema":
        receipt["schema"] = "five_etf_six_portfolio_raster_verification_v1"
    elif mutation == "endpoint":
        receipt["stage_figures"][0]["saved_aggregate_checks"][0]["max_drawdown"] -= 0.01
    elif mutation == "weekly_id":
        receipt["series_ids"][1] = BUILDER.SOURCE_IDS[1]
    elif mutation == "png_hash":
        receipt["stage_figures"][0]["sha256"] = "0" * 64
    else:
        receipt["saved_report_sha256"] = "0" * 64
    (figures / "figures_verification.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        BUILDER.build(report_path, figures, tmp_path / "output", source_path)
    assert not (tmp_path / "output").exists()


def test_deterministic_build_preserves_outputs_and_source(
    reports, tmp_path, monkeypatch
):
    report_path, source_path, figures, _ = fixture_files(reports, tmp_path, monkeypatch)
    before = BUILDER.P.sha(source_path)
    first = BUILDER.build(report_path, figures, tmp_path / "first", source_path)
    second = BUILDER.build(report_path, figures, tmp_path / "second", source_path)
    assert first == second
    assert first["archived_six_report_sha256"] == before == BUILDER.P.sha(source_path)
    assert first["portfolio_ids"] == list(BUILDER.IDS)
    assert len(first["files"]) == 8
    for name, digest in first["files"].items():
        assert BUILDER.P.sha(tmp_path / "first" / name) == digest
    with pytest.raises(ValueError, match="not empty"):
        BUILDER.build(report_path, figures, tmp_path / "first", source_path)
    source_path.write_text(source_path.read_text() + "\n")
    with pytest.raises(ValueError, match="source hash changed"):
        BUILDER.build(report_path, figures, tmp_path / "third", source_path)


def test_no_account_array_or_optimizer_dependency():
    code = (ROOT / "scripts/build_final_no_bond_reports.py").read_text()
    for forbidden in (
        "import numpy",
        "import scipy",
        "np.load",
        "load_bundle",
        "optimize_sharpe(",
        "import analytics",
        "import periods",
        ".npz",
    ):
        assert forbidden not in code
