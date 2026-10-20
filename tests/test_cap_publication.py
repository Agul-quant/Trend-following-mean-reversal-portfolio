"""Synthetic mutations of saved public aggregates; no account or market access."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from trend_portfolio.cap_publication import (
    COMPLETED_SOURCE_SHA,
    COSTS,
    CONTROL_KEYS,
    CSV_KEYS,
    RETAINED_SHA,
    SOURCE_SCHEMA,
    SOURCE_SHA,
    STAGES,
    STAGE_LABELS,
    canonical_sha,
    csv_text,
    expected_config,
    markdown,
    public_json,
    publish_report,
    read_json,
    retained_payload,
    source_audit,
    stage_markdown,
    validate_config,
    validate_report,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def report():
    return read_json(ROOT / "reports/etf_portfolios/report.json")


def test_public_financial_pin_and_exact_scope(report):
    validate_report(report, read_json(ROOT / "configs/final_cap_rebalancing.json"))
    assert canonical_sha(retained_payload(report)) == RETAINED_SHA
    assert len(report["rows"]) == 36
    assert len(report["controls"]) == 15
    assert {r["frequency"] for r in report["rows"]} == {"none", "weekly", "monthly"}
    assert report["symbols"] == ["GDX", "FXI", "QQQ", "UNG", "FDN"]
    assert report["source_report_sha256"] == COMPLETED_SOURCE_SHA
    assert report["presentation_source_report_sha256"] == SOURCE_SHA


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r["rows"][0].__setitem__("cagr", r["rows"][0]["cagr"] + 1e-12),
        lambda r: r["rows"][0]["qqq_bh_regression"].__setitem__("alpha_daily", 0),
        lambda r: r["initial_weights"].__setitem__("QQQ", 0.1),
        lambda r: r["controls"][0].__setitem__("cash_excess_sharpe", 0),
        lambda r: r["periods"]["validation"].__setitem__(1, "2024-12-31"),
        lambda r: r["rows"][0].__setitem__("frequency", "other"),
        lambda r: r["rows"].append(copy.deepcopy(r["rows"][0])),
        lambda r: r["rows"].pop(),
        lambda r: r["controls"].pop(),
        lambda r: r["controls"].append(copy.deepcopy(r["controls"][0])),
        lambda r: r.__setitem__("optimized", True),
        lambda r: r.__setitem__("retrospective", False),
        lambda r: r.__setitem__("source_report_sha256", "0" * 64),
        lambda r: r.__setitem__("presentation_source_report_sha256", "0" * 64),
        lambda r: r.__setitem__("slippage_bps_each_way", [1, 3, 10, 20]),
        lambda r: r.__setitem__("retained_frequencies", ["none"]),
        lambda r: r.__setitem__("selection_method", "Refit for better results"),
        lambda r: r.__setitem__("symbols", ["GDX", "FXI", "QQQ", "UNG", "XYZ"]),
        lambda r: r.__setitem__("title", "Different universe"),
        lambda r: r.__setitem__("unbound_extra", "Another public result"),
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


def test_undefined_cash_sharpe_remains_undefined(report):
    next(r for r in report["controls"] if r["control"] == "cash")[
        "cash_excess_sharpe"
    ] = 0
    with pytest.raises(ValueError, match="undefined"):
        validate_report(report)


def test_config_requires_precise_initial_weights_and_no_extra_fields(report):
    config = expected_config(report)
    validate_config(config, report)
    config["initial_weights"]["FDN"] = round(config["initial_weights"]["FDN"], 6)
    with pytest.raises(ValueError, match="config mismatch"):
        validate_config(config, report)
    config = expected_config(report)
    config["unbound_extra"] = "Ignored extra configuration"
    with pytest.raises(ValueError, match="config mismatch"):
        validate_config(config, report)


def test_config_rejects_different_frequency(report):
    config = expected_config(report)
    config["frequencies"].append("other")
    with pytest.raises(ValueError, match="config mismatch"):
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


def test_presentation_copy_has_no_financial_changes_or_input_mutation(report):
    source = copy.deepcopy(retained_payload(report))
    source.update(schema=SOURCE_SCHEMA, source_report_sha256=COMPLETED_SOURCE_SHA)
    before = copy.deepcopy(source)
    selected = publish_report(source)
    assert selected == report
    assert source == before
    source["rows"].pop()
    with pytest.raises(ValueError, match="financial payload"):
        publish_report(source)


def test_markdown_discloses_execution_costs_and_retrospective_scope(report):
    text = markdown(report)
    for phrase in (
        "fee-free dividend-reinvestment",
        "not a reset to starting weights",
        "3% nominal ACT/365",
        "not at every market tick",
        "Retrospective",
        "1 bp commission",
        "next simultaneous eligible",
        "universe is **GDX, FXI, QQQ, UNG and FDN**",
    ):
        assert phrase in text
    assert text.count("| Weekly corrections |") == 15
    assert text.count("| Monthly corrections |") == 15
    assert "scripts/verify_etf_publication.py" in text


def test_standalone_verifier_reads_only_public_files(report, tmp_path):
    spec = importlib.util.spec_from_file_location(
        "verify_etf_publication", ROOT / "scripts/verify_etf_publication.py"
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


def test_released_equal_weight_comparison_in_all_periods_and_costs(report):
    comparison = read_json(ROOT / "reports/etf_portfolios/statistical_comparison.json")
    text = markdown(report, comparison)
    assert text.count("| Equal weight; no rebalancing |") == 12
    assert "48 portfolio/cost/period outcomes" in text
    assert "20% per sleeve" in text
    assert "four portfolios" in text
    assert text == (ROOT / "reports/etf_portfolios/report.md").read_text()
    readme = (ROOT / "README.md").read_text()
    cells = []
    for stage in ("development", "validation", "historical_OOS"):
        row = next(
            r
            for r in comparison["rows"]
            if r["stage"] == stage
            and r["series"] == "equal_initial"
            and r["slippage_bps_each_way"] == 3
        )
        cells.append(
            f"{row['cash_excess_sharpe']:.3f} / {row['cagr'] * 100:.2f}% / {row['max_drawdown'] * 100:.2f}%"
        )
    assert "| Equal weight; no rebalancing | " + " | ".join(cells) + " |" in readme


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: c.update(schema="unrecognized"),
        lambda c: c["rows"].pop(
            next(i for i, r in enumerate(c["rows"]) if r["series"] == "equal_initial")
        ),
        lambda c: c["rows"].append(
            copy.deepcopy(next(r for r in c["rows"] if r["series"] == "equal_initial"))
        ),
        lambda c: next(r for r in c["rows"] if r["series"] == "equal_initial").update(
            slippage_bps_each_way=2
        ),
        lambda c: next(r for r in c["rows"] if r["series"] == "equal_initial").update(
            commission_bps_each_way=2
        ),
        lambda c: next(r for r in c["rows"] if r["series"] == "equal_initial").update(
            observations=1
        ),
        lambda c: next(r for r in c["rows"] if r["series"] == "equal_initial").update(
            cagr=float("nan")
        ),
    ],
)
def test_equal_comparison_scope_cannot_silently_change(report, mutation):
    comparison = read_json(ROOT / "reports/etf_portfolios/statistical_comparison.json")
    mutation(comparison)
    with pytest.raises(ValueError):
        markdown(report, comparison)


def test_combined_report_pairs_each_stage_table_and_figures(report):
    comparison = read_json(ROOT / "reports/etf_portfolios/statistical_comparison.json")
    text = markdown(report, comparison)
    headings = [f"### {STAGE_LABELS[stage]} —" for stage in STAGES]
    previous_end = -1
    for index, stage in enumerate(STAGES):
        start = text.index(headings[index])
        end = (
            text.index(headings[index + 1])
            if index + 1 < len(headings)
            else text.index("## Baseline cap diagnostics")
        )
        section = text[start:end]
        table = section.index("| Portfolio / control |")
        cash = section.index("| Matched cash |")
        wealth = section.index(f"]({stage}_baseline.png)")
        daily = section.index(f"]({stage}_daily_net_returns_baseline.png)")
        assert previous_end <= start < end
        assert table < cash < wealth < daily
        assert section.count("](") == 3  # Focused report, wealth figure, daily figure.
        assert all(
            f"]({other}_baseline.png)" not in section
            and f"]({other}_daily_net_returns_baseline.png)" not in section
            for other in STAGES
            if other != stage
        )
        previous_end = end


@pytest.mark.parametrize("stage", STAGES)
def test_focused_stage_report_exact_table_scope_and_paired_figures(report, stage):
    comparison = read_json(ROOT / "reports/etf_portfolios/statistical_comparison.json")
    before = copy.deepcopy(report)
    combined = markdown(report, comparison)
    text = stage_markdown(report, stage, comparison)
    assert text == (ROOT / f"reports/etf_portfolios/{stage}_report.md").read_text()
    start, end, observations = STAGES[stage]
    assert f"{start}–{end}" in text
    assert f"{observations:,} daily observations" in text
    table_lines = [line for line in text.splitlines() if line.startswith("|")]
    assert len(table_lines) == 23  # Header + rule + 4 costs × 5 series + cash.
    for cost in COSTS:
        assert len([line for line in table_lines[2:] if line.split("|")[2].strip() == str(cost)]) == 5
    for name in (
        "Initial allocation; no rebalancing", "Equal weight; no rebalancing",
        "Weekly corrections", "Monthly corrections", "QQQ buy-and-hold",
    ):
        assert text.count(f"| {name} |") == 4
    assert text.count("| Matched cash |") == 1
    assert "\n".join(table_lines) in combined
    wealth = text.index(f"]({stage}_baseline.png)")
    daily = text.index(f"]({stage}_daily_net_returns_baseline.png)")
    assert text.index("| Matched cash |") < wealth < daily
    assert text.count("![") == 2
    assert f"../reproducibility/{stage}.csv" in text
    assert "not adjusted for portfolio selection" in text
    assert "configs/selected_etf_strategies.json" in text
    assert report == before


def test_focused_report_rejects_unknown_stage(report):
    with pytest.raises(ValueError, match="Unknown report stage"):
        stage_markdown(report, "not_a_stage")


def test_verifier_requires_complete_and_literal_focused_stage_set(report, tmp_path):
    spec = importlib.util.spec_from_file_location(
        "verify_etf_publication", ROOT / "scripts/verify_etf_publication.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    directory = tmp_path / "public"
    write_outputs(report, directory)
    config = tmp_path / "config.json"
    config.write_text(json.dumps(expected_config(report)))
    assert module.verify(directory, config)["focused_stage_reports"] == 0
    (directory / "development_report.md").write_text(stage_markdown(report, "development"))
    with pytest.raises(ValueError, match="all three periods"):
        module.verify(directory, config)
    for stage in STAGES:
        (directory / f"{stage}_report.md").write_text(stage_markdown(report, stage))
    assert module.verify(directory, config)["focused_stage_reports"] == 3
    (directory / "validation_report.md").write_text("changed")
    with pytest.raises(ValueError, match="presentation changed: validation_report.md"):
        module.verify(directory, config)
