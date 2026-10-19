"""Synthetic aggregate-only final-selection fixtures; no daily input arrays."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("final_no_bond_audit", ROOT / "scripts/verify_final_no_bond.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


@pytest.fixture
def comparison():
    source = {"schema": "five_etf_six_portfolio_comparison_v1", "symbols": list(AUDIT.SYMBOLS),
              "portfolios": [{"id": identity, "initial_weights": dict.fromkeys(AUDIT.SYMBOLS, .2)}
                             for identity in AUDIT.SOURCE_IDS],
              "slippage_bps_each_way": list(AUDIT.COSTS), "commission_bps_each_way": 1,
              "initial_capital_each_stage": 1000, "fit_stage": "historical_OOS",
              "fit_baseline_slippage_bps": 3, "source_hashes": {"original_stage_report": "a" * 64},
              "stage_summaries": [], "portfolio_rows": [], "control_rows": [], "checkpoint_rows": [],
              "QQQ_single_factor_rows": [], "five_passive_factor_rows": [],
              "strategy_correlations": [], "portfolio_correlations": [], "solver_summaries": [],
              "method": "Static initial sleeve wealth; no rebalancing.",
              "limitations": ["Retrospective; not an untouched portfolio test. Numerically best-found, not globally certified."]}
    for stage, (start, end, observations) in AUDIT.STAGES.items():
        source["stage_summaries"].append({"stage": stage, "scored_start": start, "scored_end": end,
                                          "observations": observations, "fresh_initial_capital": 1000,
                                          "elapsed_act365_years": 3.0})
        for cost in AUDIT.COSTS:
            common = {"stage": stage, "slippage_bps_each_way": cost, "commission_bps_each_way": 1}
            for identity in AUDIT.SOURCE_IDS:
                base = {**common, "portfolio_id": identity}
                source["portfolio_rows"].append({**base, "observations": observations,
                                                  "cash_excess_sharpe": 1.23456789, "cagr": .1})
                for frequency in ("daily", "weekly", "monthly"):
                    source["checkpoint_rows"].append({**base, "checkpoint_frequency": frequency,
                                                       "checkpoint_count": observations, "max_daily_capital_share": .25})
                source["QQQ_single_factor_rows"].append({**base, "observations": observations,
                                                          "beta_QQQ": .25, "alpha_daily": .0001})
                source["five_passive_factor_rows"].append({**base, "observations": observations,
                                                            **{"beta_" + symbol: .1 for symbol in AUDIT.SYMBOLS}})
            for identity in ("QQQ_buy_and_hold", "matched_cash"):
                source["control_rows"].append({**common, "control_id": identity, "observations": observations,
                                                "cash_excess_sharpe": None if identity == "matched_cash" else 1})
            source["strategy_correlations"].append({**common, "symbols": list(AUDIT.SYMBOLS),
                                                     "matrix": [[1 if i == j else (i + j + 1) / 100 for j in range(5)] for i in range(5)]})
            source["portfolio_correlations"].append({**common, "portfolio_ids": list(AUDIT.SOURCE_IDS) + ["QQQ_buy_and_hold"],
                                                      "matrix": [[1 if i == j else (i + j + 1) / 100 for j in range(7)] for i in range(7)]})
    for identity, mode in zip(AUDIT.SOURCE_IDS[:5], ("daily", "weekly", "monthly", "initial", "none")):
        source["solver_summaries"].append({"portfolio_id": identity, "cap_mode": mode,
                                           "certified_global_optimum": False, "baseline_cash_excess_sharpe": 1.23456789})
    active = copy.deepcopy(source)
    active.update(schema="five_etf_four_portfolio_comparison_v1", source_report_sha256=AUDIT.SOURCE_SHA256,
                  dropped_portfolio_ids=list(AUDIT.REMOVED_IDS),
                  selection_method="Exact saved-result subset; no refit or account run")
    active["source_hashes"]["archived_six_portfolio_report"] = AUDIT.SOURCE_SHA256
    active["portfolios"] = [r for r in active["portfolios"] if r["id"] in AUDIT.IDS]
    for field in ("portfolio_rows", "QQQ_single_factor_rows", "five_passive_factor_rows", "solver_summaries"):
        active[field] = [r for r in active[field] if r["portfolio_id"] in AUDIT.IDS]
    active["checkpoint_rows"] = [r for r in active["checkpoint_rows"]
                                  if r["portfolio_id"] in AUDIT.IDS and r["checkpoint_frequency"] == "daily"]
    active["portfolio_correlations"] = AUDIT.sliced_correlations(source["portfolio_correlations"])
    return active, source


def test_exact_four_portfolio_saved_subset_passes(comparison):
    result = AUDIT.verify_subset(*comparison)
    assert result["passed"] is True
    assert result["rows_verified"] == {"portfolio_rows": 48, "control_rows": 24, "checkpoint_rows": 48,
                                       "QQQ_single_factor_rows": 48, "five_passive_factor_rows": 48,
                                       "strategy_correlations": 12, "portfolio_correlations": 12}
    assert result["financial_metrics_recomputed_or_weights_refitted"] is False
    assert result["private_numerical_arrays_read"] is False


def test_correlation_slices_actual_nonadjacent_portfolio_positions(comparison):
    active, source = comparison
    original = source["portfolio_correlations"][0]["matrix"]
    selected = active["portfolio_correlations"][0]["matrix"]
    positions = [0, 3, 4, 5, 6]
    assert selected == [[original[i][j] for j in positions] for i in positions]


@pytest.mark.parametrize("kind", ["weekly_weight", "monthly_metric", "refit_weight", "round_metric", "duplicate",
                                 "wrong_stage", "wrong_cost", "wrong_fee", "weekly_cap", "changed_control",
                                 "beta_bond", "correlation_slice", "correlation_labels", "solver_weekly",
                                 "source_hash", "source_top_hash", "dropped_metadata", "changed_clock", "source_definition"])
def test_changed_or_removed_output_rejected(comparison, kind):
    active, source = comparison
    if kind == "weekly_weight":
        active["portfolios"].append(copy.deepcopy(source["portfolios"][1]))
    elif kind == "monthly_metric":
        active["portfolio_rows"].append(copy.deepcopy(source["portfolio_rows"][2]))
    elif kind == "refit_weight":
        active["portfolios"][0]["initial_weights"]["GDX"] += .001
    elif kind == "round_metric":
        active["portfolio_rows"][0]["cash_excess_sharpe"] = 1.235
    elif kind == "duplicate":
        active["portfolio_rows"][-1] = active["portfolio_rows"][0]
    elif kind == "wrong_stage":
        active["portfolio_rows"][0]["stage"] = "future_OOS"
    elif kind == "wrong_cost":
        active["portfolio_rows"][0]["slippage_bps_each_way"] = 7
    elif kind == "wrong_fee":
        active["portfolio_rows"][0]["commission_bps_each_way"] = 0
    elif kind == "weekly_cap":
        active["checkpoint_rows"][0]["checkpoint_frequency"] = "weekly"
    elif kind == "changed_control":
        active["control_rows"][0]["cash_excess_sharpe"] += .01
    elif kind == "beta_bond":
        active["five_passive_factor_rows"][0]["beta_BND"] = 0
    elif kind == "correlation_slice":
        active["portfolio_correlations"][0]["matrix"][0][1] = .9
    elif kind == "correlation_labels":
        active["portfolio_correlations"][0]["portfolio_ids"].reverse()
    elif kind == "solver_weekly":
        active["solver_summaries"][0] = copy.deepcopy(source["solver_summaries"][1])
    elif kind == "source_hash":
        active["source_hashes"]["archived_six_portfolio_report"] = "0" * 64
    elif kind == "source_top_hash":
        active["source_report_sha256"] = "0" * 64
    elif kind == "dropped_metadata":
        active["dropped_portfolio_ids"].pop()
    elif kind == "changed_clock":
        active["stage_summaries"][0]["observations"] = 999
    else:
        source["portfolios"][0]["id"] = "untrusted_source"
    with pytest.raises(ValueError):
        AUDIT.verify_subset(active, source)


@pytest.mark.parametrize("value", [{"private": "/" + "Users/person/input"}, list(range(129)),
                                    {"invalid": float("nan")}, {"private": "file" + "://input"}])
def test_private_arrays_locators_and_nonfinite_rejected(value):
    with pytest.raises(ValueError):
        AUDIT.public_json(value)


def test_cli_rejects_unpinned_source_before_reading_active_report(tmp_path):
    source = tmp_path / "source.json"
    source.write_text("{}")
    with pytest.raises(ValueError, match="SHA256"):
        AUDIT.main(["--source-report", str(source), "--report", str(tmp_path / "does_not_exist.json")])


def test_cli_writes_new_audit_and_preserves_existing_output(comparison, tmp_path, monkeypatch):
    active, source = comparison
    source_path, report_path, output = (tmp_path / name for name in ("source.json", "active.json", "audit.json"))
    source_path.write_text(json.dumps(source))
    synthetic_hash = AUDIT.digest(source_path)
    monkeypatch.setattr(AUDIT, "SOURCE_SHA256", synthetic_hash)
    active["source_report_sha256"] = synthetic_hash
    active["source_hashes"]["archived_six_portfolio_report"] = synthetic_hash
    report_path.write_text(json.dumps(active))
    assert AUDIT.main(["--report", str(report_path), "--source-report", str(source_path), "--output", str(output)]) == 0
    assert json.loads(output.read_text())["passed"] is True
    with pytest.raises(ValueError, match="Preserve"):
        AUDIT.main(["--report", str(report_path), "--source-report", str(source_path), "--output", str(output)])
