"""Synthetic mutations of public aggregates; no market/account input access."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from trend_portfolio.cap_subset import (
    CONTROL_KEYS,
    CSV_KEYS,
    RETAINED_SHA,
    SOURCE_SHA,
    canonical_sha,
    csv_text,
    expected_config,
    markdown,
    public_json,
    read_json,
    retained_payload,
    select_report,
    source_audit,
    validate_config,
    validate_report,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def report():
    return read_json(ROOT / "reports/final_cap_rebalancing/report.json")


def test_saved_subset_portable_pin_and_exact_scope(report):
    validate_report(report, read_json(ROOT / "configs/final_cap_rebalancing.json"))
    assert canonical_sha(retained_payload(report)) == RETAINED_SHA
    assert len(report["rows"]) == 36
    assert len(report["controls"]) == 15
    assert {r["frequency"] for r in report["rows"]} == {"none", "weekly", "monthly"}
    assert report["source_report_sha256"] == SOURCE_SHA


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r["rows"][0].__setitem__("cagr", r["rows"][0]["cagr"] + 1e-12),
        lambda r: r["rows"][0]["qqq_bh_regression"].__setitem__("alpha_daily", 0),
        lambda r: r["initial_weights"].__setitem__("QQQ", 0.1),
        lambda r: r["controls"][0].__setitem__("cash_excess_sharpe", 0),
        lambda r: r["periods"]["validation"].__setitem__(1, "2024-12-31"),
        lambda r: r["rows"][0].__setitem__("frequency", "daily"),
        lambda r: r["rows"].append(copy.deepcopy(r["rows"][0])),
        lambda r: r["rows"].pop(),
        lambda r: r["controls"].pop(),
        lambda r: r["controls"].append(copy.deepcopy(r["controls"][0])),
        lambda r: r.__setitem__("optimized", True),
        lambda r: r.__setitem__("retrospective", False),
        lambda r: r.__setitem__("source_report_sha256", "0" * 64),
        lambda r: r.__setitem__("slippage_bps_each_way", [1, 3, 10, 20]),
        lambda r: r.__setitem__("removed_frequencies", []),
        lambda r: r.__setitem__("selection_method", "Refit for better results"),
    ],
)
def test_mutation_rejected_even_with_recomputed_self_declared_digest(report, mutation):
    mutation(report)
    report["retained_source_payload_sha256"] = canonical_sha(retained_payload(report))
    with pytest.raises(ValueError):
        validate_report(report)


def test_duplicate_identity_cannot_replace_missing_result(report):
    report["rows"][-1] = copy.deepcopy(report["rows"][0])
    with pytest.raises(ValueError, match="scope"):
        validate_report(report)


def test_undefined_cash_sharpe_is_not_zero(report):
    next(r for r in report["controls"] if r["control"] == "cash")[
        "cash_excess_sharpe"
    ] = 0
    with pytest.raises(ValueError, match="undefined"):
        validate_report(report)


def test_config_requires_same_precise_initial_weights(report):
    config = expected_config(report)
    validate_config(config, report)
    config["initial_weights"]["FDN"] = round(config["initial_weights"]["FDN"], 6)
    with pytest.raises(ValueError, match="initial_weights"):
        validate_config(config, report)


def test_config_rejects_daily_or_different_stage(report):
    config = expected_config(report)
    config["frequencies"].append("daily")
    with pytest.raises(ValueError, match="frequencies"):
        validate_config(config, report)


@pytest.mark.parametrize(
    "bad",
    [
        {"path": "/Users/private/data.csv"},
        {"path": "file://private"},
        {"path": "/home/user/data.csv"},
        {"token": "api_key=abcdefghij"},
        {"x": float("nan")},
        {"x": float("inf")},
        {"x": list(range(700))},
    ],
)
def test_public_safety_rejects_private_or_nonfinite(bad):
    with pytest.raises(ValueError):
        public_json(bad)


def test_json_parser_rejects_nonfinite(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"metric": NaN}')
    with pytest.raises(ValueError, match="Nonfinite"):
        read_json(path)


def test_writer_is_exclusive_and_literal(report, tmp_path):
    directory = tmp_path / "new"
    write_outputs(report, directory)
    assert read_json(directory / "report.json") == report
    assert (directory / "performance.csv").read_bytes() == csv_text(
        report["rows"], CSV_KEYS
    ).encode()
    assert (directory / "controls.csv").read_bytes() == csv_text(
        report["controls"], CONTROL_KEYS
    ).encode()
    assert read_json(directory / "source_subset_audit.json") == source_audit(report)
    assert (directory / "report.md").read_text() == markdown(report)
    with pytest.raises(FileExistsError):
        write_outputs(report, directory)


def test_source_selection_is_additive_and_no_retained_value_changes(report):
    source = copy.deepcopy(retained_payload(report))
    source["schema"] = "actual_cap_rebalance_aggregate_report_v1"
    source["title"] = "Actual Cap-Triggered Rebalancing"
    # The unretained synthetic rows test only identity filtering, not financial values.
    source["rows"] += [
        dict(copy.deepcopy(r), frequency="daily")
        for r in report["rows"]
        if r["frequency"] == "none"
    ]
    before = copy.deepcopy(source)
    selected = select_report(source)
    assert selected == report
    assert source == before
    source["rows"].pop()
    with pytest.raises(ValueError, match="source scope"):
        select_report(source)


def test_markdown_discloses_execution_costs_and_retrospective_scope(report):
    text = markdown(report)
    for phrase in (
        "fee-free dividend-reinvestment",
        "not a reset to starting weights",
        "3% nominal ACT/365",
        "not at every market tick",
        "Retrospective",
        "Daily corrections have been removed",
        "1 bp commission",
        "next simultaneous eligible",
    ):
        assert phrase in text
    assert "| Daily corrections |" not in text
    assert text.count("| Weekly corrections |") == 15  # 12 performance + 3 diagnostics
    assert text.count("| Monthly corrections |") == 15


def test_standalone_portable_verifier_reads_only_public_files(report, tmp_path):
    spec = importlib.util.spec_from_file_location(
        "verify_final_cap", ROOT / "scripts/verify_final_cap.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    directory = tmp_path / "public"
    write_outputs(report, directory)
    config = tmp_path / "config.json"
    config.write_text(json.dumps(expected_config(report)))
    result = module.verify(directory, config)
    assert result["passed"]
    assert result["private_market_or_account_inputs_read"] is False
    assert result["financial_audit_reproduced"] is False
    (directory / "performance.csv").write_text("changed")
    with pytest.raises(ValueError, match="presentation changed"):
        module.verify(directory, config)
