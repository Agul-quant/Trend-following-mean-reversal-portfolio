"""Saved public aggregate filtering only: never opens numerical account arrays."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "final_selector", ROOT / "scripts/select_final_no_bond_portfolios.py"
)
selector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selector)
SOURCE = ROOT / "reports/no_bond_portfolios/report.json"


def source():
    return json.loads(SOURCE.read_text())


def test_original_source_and_four_exact_definitions_unchanged():
    raw = SOURCE.read_bytes()
    original = source()
    before = copy.deepcopy(original)
    selected = selector.select(original)
    assert hashlib.sha256(raw).hexdigest() == selector.SOURCE_SHA
    assert original == before and SOURCE.read_bytes() == raw
    assert [p["id"] for p in selected["portfolios"]] == list(selector.IDS)
    for p in selected["portfolios"]:
        assert p == next(x for x in original["portfolios"] if x["id"] == p["id"])
    assert selected["control_rows"] == original["control_rows"]
    assert selected["strategy_correlations"] == original["strategy_correlations"]


@pytest.mark.parametrize(
    "field,count",
    [
        ("portfolio_rows", 48),
        ("QQQ_single_factor_rows", 48),
        ("five_passive_factor_rows", 48),
        ("solver_summaries", 3),
    ],
)
def test_retained_rows_are_literal_source_subsets(field, count):
    original = source()
    selected = selector.select(original)
    assert selected[field] == [
        r for r in original[field] if r["portfolio_id"] in selector.IDS
    ]
    assert len(selected[field]) == count


def test_only_daily_cap_diagnostics_and_five_by_five_portfolio_correlations():
    original = source()
    selected = selector.select(original)
    assert len(selected["checkpoint_rows"]) == 48
    assert all(
        r["checkpoint_frequency"] == "daily" for r in selected["checkpoint_rows"]
    )
    labels = list(selector.IDS) + ["QQQ_buy_and_hold"]
    for old, new in zip(
        original["portfolio_correlations"], selected["portfolio_correlations"]
    ):
        pos = [old["portfolio_ids"].index(x) for x in labels]
        assert new["portfolio_ids"] == labels
        assert new["matrix"] == [[old["matrix"][i][j] for j in pos] for i in pos]


def test_incomplete_source_rejected():
    original = source()
    original["portfolio_rows"].pop()
    with pytest.raises(ValueError, match="scope"):
        selector.select(original)


def test_cli_source_revision_rejected_without_output(tmp_path):
    file = tmp_path / "source.json"
    file.write_text(json.dumps(source()))
    with pytest.raises(SystemExit):
        selector.main(
            ["--source-report", str(file), "--output-dir", str(tmp_path / "new")]
        )
    assert not (tmp_path / "new").exists()


def test_new_aggregate_outputs_and_existing_attempt_never_replaced(tmp_path):
    target = tmp_path / "new"
    selected = selector.select(source())
    selector.write_outputs(selected, target)
    assert json.loads((target / "report.json").read_text()) == selected
    assert len((target / "portfolio_correlations.csv").read_text().splitlines()) == 301
    with pytest.raises(FileExistsError):
        selector.write_outputs(selected, target)
    text = (target / "report.json").read_text()
    for forbidden in ("/Users/", ".cache/", "sleeve_normalized_equity", "beta_BND"):
        assert forbidden not in text
