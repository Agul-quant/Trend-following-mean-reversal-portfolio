"""Saved-public-aggregate tests; no market, daily account or optimizer inputs."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
from pathlib import Path
import re
import shutil
import struct
import zlib

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "final_report_builder", ROOT / "scripts/build_final_reports.py"
)
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


@pytest.fixture
def inputs():
    return BUILDER.load_inputs(ROOT)


def validate(data):
    return BUILDER.validate_data(
        data["report"],
        data["config"],
        data["single"],
        data["joint"],
        data["provenance"],
    )


def test_exact_saved_input_contract_and_no_private_dependencies(inputs):
    assert len(inputs["report"]["portfolio_rows"]) == 48
    assert len(inputs["report"]["control_rows"]) == 24
    assert (
        len(inputs["report"]["cap_rows"])
        == len(inputs["single"])
        == len(inputs["joint"])
        == 48
    )
    assert len(inputs["factor_diagnostics"]) == 12
    assert all(
        not path.startswith(".") and ".cache" not in path
        for path in inputs["source_hashes"]
    )
    code = (ROOT / "scripts/build_final_reports.py").read_text()
    for forbidden in (
        "import numpy",
        "load_bundle",
        "import scipy",
        "import analytics",
        "import periods",
    ):
        assert forbidden not in code


@pytest.mark.parametrize("field", ["portfolio_rows", "control_rows", "cap_rows"])
def test_missing_row_rejected(inputs, field):
    inputs["report"][field].pop()
    with pytest.raises(ValueError, match="incomplete"):
        validate(inputs)


@pytest.mark.parametrize("field", ["portfolio_rows", "control_rows", "cap_rows"])
def test_duplicate_identity_rejected(inputs, field):
    inputs["report"][field][1] = copy.deepcopy(inputs["report"][field][0])
    with pytest.raises(ValueError, match="duplicated"):
        validate(inputs)


@pytest.mark.parametrize(
    "mutation",
    [
        "stage",
        "cost",
        "commission",
        "observations",
        "cagr",
        "terminal",
        "nonfinite",
        "cash_sharpe",
        "weight",
        "tiny_zero",
        "clock",
        "bounds",
        "cap_note",
    ],
)
def test_bad_numerical_or_scope_contract_rejected(inputs, mutation):
    row = inputs["report"]["portfolio_rows"][0]
    if mutation == "stage":
        row["stage"] = "future"
    elif mutation == "cost":
        row["slippage_bps_each_way"] = 2
    elif mutation == "commission":
        row["commission_bps_each_way"] = 3
    elif mutation == "observations":
        row["observations"] = 700
    elif mutation == "cagr":
        row["cagr"] += 0.01
    elif mutation == "terminal":
        row["terminal_equity_from_1000"] += 1
    elif mutation == "nonfinite":
        row["cash_excess_sharpe"] = float("nan")
    elif mutation == "cash_sharpe":
        inputs["report"]["control_rows"][1]["cash_excess_sharpe"] = 0
    elif mutation == "weight":
        inputs["config"]["portfolios"][0]["initial_weights"]["GDX"] += 0.001
    elif mutation == "tiny_zero":
        inputs["config"]["portfolios"][1]["initial_weights"]["BND"] = 0
        inputs["report"]["portfolios"][1]["initial_weights"]["BND"] = 0
    elif mutation == "clock":
        inputs["report"]["stage_summaries"][0]["elapsed_act365_years"] = 4
    elif mutation == "bounds":
        inputs["report"]["stage_summaries"][1]["scored_end"] = "2024-12-31"
    elif mutation == "cap_note":
        inputs["provenance"]["validation_current_daily_cap"][
            "days_above_one_third_each_cost"
        ] = 40
    with pytest.raises(ValueError):
        validate(inputs)


@pytest.mark.parametrize("field", ["single", "joint"])
@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "wrong_stage",
        "wrong_cost",
        "alpha_scale",
        "observations",
        "r2",
        "adjusted_r2",
    ],
)
def test_bad_attribution_cross_join_or_metric_rejected(inputs, field, mutation):
    row = inputs[field][0]
    if mutation == "missing":
        inputs[field].pop()
    elif mutation == "duplicate":
        inputs[field][1] = copy.deepcopy(row)
    elif mutation == "wrong_stage":
        row["stage"] = "future"
    elif mutation == "wrong_cost":
        row["slippage_bps_each_way"] = "5"
    elif mutation == "alpha_scale":
        row["alpha_annual_arithmetic"] = str(float(row["alpha_daily"]) * 365)
    elif mutation == "observations":
        row["observations"] = "99"
    elif mutation == "r2":
        row["r_squared"] = "1.2"
    elif mutation == "adjusted_r2":
        row["adjusted_r_squared"] = "-.9"
    with pytest.raises(ValueError):
        validate(inputs)


def test_all_stages_are_isolated_complete_typed_and_static(inputs):
    for sid in BUILDER.STAGES:
        report = BUILDER.stage_data(inputs, sid)
        assert report["stage"] == sid
        assert report["initial_allocations"] == inputs["report"]["portfolios"]
        for field, count in [
            ("portfolio_rows", 16),
            ("control_rows", 8),
            ("cap_rows", 16),
            ("QQQ_single_factor_rows", 16),
            ("six_passive_factor_rows", 16),
            ("factor_diagnostic_rows", 4),
        ]:
            assert len(report[field]) == count
            assert all(row["stage"] == sid for row in report[field])
        assert all(
            isinstance(row["alpha_daily"], float)
            for row in report["QQQ_single_factor_rows"]
        )
        assert all(
            isinstance(row["observations"], int)
            for row in report["six_passive_factor_rows"]
        )
        assert (
            sum(row["cash_excess_sharpe"] is None for row in report["control_rows"])
            == 4
        )
        assert ("audited_cap_warning" in report) == (sid == "validation")
        assert set(report["strategy_definitions"][0]) == {
            "symbol",
            "style",
            "candidate_id",
            "label",
            "definition",
        }
        assert "source_hashes" not in report and "root" not in report


def test_html_is_offline_complete_and_honest_about_cap_and_selection(inputs):
    for sid in BUILDER.STAGES:
        result = BUILDER.stage_data(inputs, sid)
        png = (ROOT / BUILDER.FIGURES / f"{sid}_baseline.png").read_bytes()
        correlation_png = (
            (ROOT / BUILDER.FIGURES / "oos_strategy_correlations.png").read_bytes()
            if sid == "historical_OOS"
            else None
        )
        text = BUILDER.render_html(result, png, correlation_png)
        assert text.startswith("<!doctype html>")
        assert text.count("data:image/png;base64,") == (
            2 if sid == "historical_OOS" else 1
        )
        assert '<div class="table-scroll"><table>' in text
        assert "overflow-x: auto" in text and "overflow: visible" in text
        assert not re.search(
            r"<script\b|(?:src|href)=[\"\'](?:https?:|//|file:)", text, re.I
        )
        assert "/Users/" not in text and ".cache/" not in text
        assert "size: A4" in text and "@bottom-right" not in text
        for section in range(1, 8):
            assert f'id="section{section}"' in text
        for cost in BUILDER.COSTS:
            assert f"{int(cost)} bp slippage each way" in text
        assert "not an untouched portfolio test" in text
        assert "Undefined" in text and "9.720788330706766" in text
        assert "Total return" in text and "Period interpretation" in text
        assert "V<sub>c,0</sub> = 1" in text and "V<sub>c,t−1</sub>" in text
        assert "not independent-vendor confirmation" in text
        for reference in ("[1]", "[2]", "[3]", "[4]"):
            assert reference in text
        assert "no cross-sleeve cash funding or rebalance trades" in text
        assert "no p-values or significance claims" in text.lower()
        if sid == "validation":
            assert "41 daily valuations" in text and "35.1826%" in text
        if sid == "historical_OOS":
            assert "Active strategy return correlations" in text
            assert "0.649855" in text and "-0.063184" in text
            assert len(result["baseline_active_strategy_correlation_rows"]) == 6
        else:
            assert "Active strategy return correlations" not in text
            assert "baseline_active_strategy_correlation_rows" not in result


def test_manifest_hashes_deterministic_build_and_verify(inputs, tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    a = BUILDER.build(ROOT, first)
    b = BUILDER.build(ROOT, second)
    assert a == b
    assert a["files"] and len(a["stages"]) == 3
    assert (first / "manifest.json").read_bytes() == (
        second / "manifest.json"
    ).read_bytes()
    for name, digest in a["files"].items():
        assert (first / name).read_bytes() == (second / name).read_bytes()
        assert hashlib.sha256((first / name).read_bytes()).hexdigest() == digest
    assert BUILDER.verify(ROOT, first) == a
    with pytest.raises(ValueError, match="not empty"):
        BUILDER.build(ROOT, first)
    target = first / a["stages"][0]["html"]
    target.write_text(target.read_text() + "\nchanged")
    with pytest.raises(ValueError, match="output file hash"):
        BUILDER.verify(ROOT, first)


def test_source_hash_tampering_rejected_before_any_output(inputs, tmp_path):
    source = tmp_path / "public_only_root"
    for relative in inputs["source_hashes"]:
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    path = source / "configs/four_portfolios.json"
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="hash changed"):
        BUILDER.build(source, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_csv_json_counterpart_mismatch_rejected():
    with pytest.raises(ValueError, match="CSV JSON mismatch"):
        BUILDER.csv_matches([{"n": 1.2}], [{"n": "1.3"}], "fixture")
    BUILDER.csv_matches(
        [{"n": None, "b": False, "t": "literal"}],
        [{"n": "", "b": "False", "t": "literal"}],
        "fixture",
    )


def test_unsafe_png_text_rejected(tmp_path):
    def chunk(kind, value):
        return (
            struct.pack(">I", len(value))
            + kind
            + value
            + struct.pack(">I", zlib.crc32(kind + value) & 0xFFFFFFFF)
        )

    raw = b"\x89PNG\r\n\x1a\n" + chunk(
        b"IHDR", struct.pack(">II5B", 1, 1, 8, 6, 0, 0, 0)
    )
    raw += chunk(b"tEXt", b"PrivateSource\0/Users/example/.cache/secret.npz") + chunk(
        b"IEND", b""
    )
    path = tmp_path / "unsafe.png"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="unsafe PNG"):
        BUILDER.png_check(path)


def test_png_hash_and_aggregate_endpoints_are_checked(inputs):
    verification = BUILDER.read_json(
        ROOT / BUILDER.FIGURES / "figure_verification.json"
    )
    verification["stage_figures"][0]["terminal_equity_by_series"]["equal_initial"] += 1
    with pytest.raises(ValueError, match="endpoint"):
        BUILDER.validate_figures(inputs, verification, ROOT)
    verification = BUILDER.read_json(
        ROOT / BUILDER.FIGURES / "figure_verification.json"
    )
    verification["stage_figures"][1]["series"] = 6
    with pytest.raises(ValueError, match="identity"):
        BUILDER.validate_figures(inputs, verification, ROOT)


@pytest.mark.parametrize(
    "name",
    [
        "/Users/private.txt",
        "../secret.json",
        ".cache/private.json",
        "good/../secret.json",
    ],
)
def test_public_manifest_path_safety(name):
    assert not BUILDER.safe_relative(name)
