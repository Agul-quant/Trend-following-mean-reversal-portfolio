"""Synthetic aggregate-only no-bond presentation QA, without account data."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import zlib

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "no_bond_report_builder", ROOT / "scripts/build_no_bond_reports.py"
)
assert SPEC and SPEC.loader
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def fake_png():
    """One synthetic pixel; it is not a financial chart or source account."""

    def chunk(kind, payload):
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">II5B", 1, 1, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff\xff"))
        + chunk(b"IEND", b"")
    )


@pytest.fixture
def aggregate():
    report = {
        "schema": BUILDER.SCHEMA,
        "symbols": list(BUILDER.SYMBOLS),
        "portfolios": [
            {"id": p, "initial_weights": {s: 0.2 for s in BUILDER.SYMBOLS}}
            for p in BUILDER.IDS
        ],
        "stage_summaries": [],
        "portfolio_rows": [],
        "control_rows": [],
        "checkpoint_rows": [],
        "QQQ_single_factor_rows": [],
        "five_passive_factor_rows": [],
        "strategy_correlations": [],
        "portfolio_correlations": [],
        "solver_summaries": [
            {
                "portfolio_id": p,
                "cap_mode": mode,
                "seed": 1729,
                "baseline_cash_excess_sharpe": 1.25,
                "certified_global_optimum": False,
                "solver": "multi-start SLSQP",
                "lp_starts": 48,
                "attempts": [],
            }
            for p, mode in zip(BUILDER.IDS[:5], BUILDER.MODES)
        ],
        "source_hashes": {"synthetic_fixture": "1" * 64},
    }
    for stage, (start, end, observations) in BUILDER.STAGES.items():
        report["stage_summaries"].append(
            {
                "stage": stage,
                "scored_start": start,
                "scored_end": end,
                "observations": observations,
                "fresh_initial_capital": 1000,
                "elapsed_act365_years": 3.0,
            }
        )
        for cost in BUILDER.COSTS:
            common = {
                "stage": stage,
                "commission_bps_each_way": 1.0,
                "slippage_bps_each_way": cost,
            }
            metric = {
                **common,
                "observations": observations,
                "elapsed_act365_years": 3.0,
                "cash_excess_sharpe": 1.25,
                "cagr": 0.1,
                "terminal_equity_from_1000": 1331,
                "terminal_normalized_equity": 1.331,
                "max_drawdown": -0.1,
                "annualized_return_volatility": 0.1,
                "annualized_cash_excess_volatility": 0.1,
            }
            for pid in BUILDER.IDS:
                report["portfolio_rows"].append({**metric, "portfolio_id": pid})
                for frequency in BUILDER.FREQUENCIES:
                    report["checkpoint_rows"].append(
                        {
                            **common,
                            "portfolio_id": pid,
                            "checkpoint_frequency": frequency,
                            "checkpoint_count": observations
                            if frequency == "daily"
                            else 100,
                            "initial_cap_pass_diagnostic": True,
                            "checkpoint_cap_pass_diagnostic": True,
                            "max_checkpoint_capital_share": 0.3,
                            "checkpoint_breach_days": 0,
                            "max_daily_capital_share": 0.3,
                            "daily_breach_days": 0,
                            "between_checkpoint_breach_days": 0,
                            "cap_fraction": 1 / 3,
                        }
                    )
                for field, factors in (
                    ("QQQ_single_factor_rows", ("QQQ",)),
                    ("five_passive_factor_rows", BUILDER.SYMBOLS),
                ):
                    report[field].append(
                        {
                            **common,
                            "portfolio_id": pid,
                            "observations": observations,
                            "alpha_daily": 0.0001,
                            "alpha_annual_arithmetic": 0.0252,
                            "r_squared": 0.4,
                            **{f"beta_{s}": 0.1 for s in factors},
                        }
                    )
            for cid in BUILDER.CONTROL_IDS:
                report["control_rows"].append(
                    {
                        **metric,
                        "control_id": cid,
                        "cash_excess_sharpe": None if cid == "matched_cash" else 1.25,
                    }
                )
            for field, label, names in (
                ("strategy_correlations", "symbols", BUILDER.SYMBOLS),
                (
                    "portfolio_correlations",
                    "portfolio_ids",
                    BUILDER.IDS + (BUILDER.CONTROL_IDS[0],),
                ),
            ):
                report[field].append(
                    {
                        **common,
                        label: list(names),
                        "matrix": [
                            [1.0 if i == j else 0.1 for j in range(len(names))]
                            for i in range(len(names))
                        ],
                    }
                )
    return report


def save_fixture(report, tmp_path):
    source = tmp_path / "synthetic.json"
    source.write_text(json.dumps(report))
    directory = tmp_path / "figures"
    directory.mkdir()
    receipt = {
        "schema": "five_etf_six_portfolio_raster_verification_v1",
        "baseline_commission_bps_each_way": 1,
        "baseline_slippage_bps_each_way": 3,
        "raster_only": True,
        "daily_input_arrays_exported": False,
        "private_input_locators_exported": False,
        "series_ids": list(BUILDER.IDS) + [BUILDER.CONTROL_IDS[0]],
        "symbols": list(BUILDER.SYMBOLS),
        "initial_capital": 1000,
        "no_rebalancing": True,
        "all_released_guards_unchanged": True,
        "guard_count": 413,
        "saved_report_sha256": BUILDER.sha(source),
        "stage_figures": [],
    }
    for stage, (_, _, observations) in BUILDER.STAGES.items():
        png = directory / f"{stage}_baseline.png"
        png.write_bytes(fake_png())
        receipt["stage_figures"].append(
            {
                "stage": stage,
                "file": png.name,
                "sha256": BUILDER.sha(png),
                "series": 7,
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
    receipt_path = directory / "figures_verification.json"
    receipt_path.write_text(json.dumps(receipt))
    return source, directory, receipt


def test_exact_complete_five_etf_six_new_portfolio_contract(aggregate):
    assert BUILDER.validate(aggregate) is aggregate
    assert (
        len(aggregate["portfolio_rows"])
        == len(aggregate["QQQ_single_factor_rows"])
        == len(aggregate["five_passive_factor_rows"])
        == 72
    )
    assert len(aggregate["control_rows"]) == 24
    assert len(aggregate["checkpoint_rows"]) == 216
    assert (
        len(aggregate["strategy_correlations"])
        == len(aggregate["portfolio_correlations"])
        == 12
    )


@pytest.mark.parametrize(
    "field",
    [
        "portfolio_rows",
        "control_rows",
        "checkpoint_rows",
        "QQQ_single_factor_rows",
        "five_passive_factor_rows",
        "strategy_correlations",
        "portfolio_correlations",
    ],
)
@pytest.mark.parametrize("mutation", ["missing", "duplicate", "future", "cost"])
def test_scope_identity_rejections(aggregate, field, mutation):
    if mutation == "missing":
        aggregate[field].pop()
    elif mutation == "duplicate":
        aggregate[field][1] = copy.deepcopy(aggregate[field][0])
    elif mutation == "future":
        aggregate[field][0]["stage"] = "future"
    else:
        aggregate[field][0]["slippage_bps_each_way"] = 5
    with pytest.raises(ValueError):
        BUILDER.validate(aggregate)


@pytest.mark.parametrize(
    "mutation",
    [
        "old_identity",
        "bond_weight",
        "equal_weight",
        "negative_weight",
        "new_cap",
        "nonfinite",
        "cash_sharpe",
        "cagr",
        "bounds",
        "clock",
        "checkpoint_count",
        "between",
        "flag",
        "global",
        "seed",
        "mode",
        "old_bond_beta",
        "alpha",
        "corr_order",
        "corr_range",
        "corr_symmetry",
        "corr_diagonal",
        "corr_size",
        "private_locator",
    ],
)
def test_financial_or_definition_guard_rejections(aggregate, mutation):
    if mutation == "old_identity":
        aggregate["portfolios"][0]["id"] = "daily_capped_max_sharpe"
    elif mutation == "bond_weight":
        aggregate["portfolios"][0]["initial_weights"]["BND"] = 0
    elif mutation == "equal_weight":
        aggregate["portfolios"][-1]["initial_weights"] = {
            s: (0.19 if i == 0 else 0.21 if i == 1 else 0.2)
            for i, s in enumerate(BUILDER.SYMBOLS)
        }
    elif mutation == "negative_weight":
        aggregate["portfolios"][0]["initial_weights"]["GDX"] = -0.1
    elif mutation == "new_cap":
        aggregate["portfolios"][0]["initial_weights"] = {
            s: int(i == 0) for i, s in enumerate(BUILDER.SYMBOLS)
        }
    elif mutation == "nonfinite":
        aggregate["portfolio_rows"][0]["cash_excess_sharpe"] = float("nan")
    elif mutation == "cash_sharpe":
        aggregate["control_rows"][1]["cash_excess_sharpe"] = 0
    elif mutation == "cagr":
        aggregate["portfolio_rows"][0]["cagr"] = 0.2
    elif mutation == "bounds":
        aggregate["stage_summaries"][1]["scored_end"] = "2024-12-31"
    elif mutation == "clock":
        aggregate["portfolio_rows"][0]["elapsed_act365_years"] = 4
    elif mutation == "checkpoint_count":
        aggregate["checkpoint_rows"][0]["checkpoint_count"] -= 1
    elif mutation == "between":
        aggregate["checkpoint_rows"][1]["between_checkpoint_breach_days"] = 1
    elif mutation == "flag":
        aggregate["checkpoint_rows"][0]["checkpoint_cap_pass_diagnostic"] = False
    elif mutation == "global":
        aggregate["solver_summaries"][0]["certified_global_optimum"] = True
    elif mutation == "seed":
        aggregate["solver_summaries"][0]["seed"] = 5
    elif mutation == "mode":
        aggregate["solver_summaries"][0]["cap_mode"] = "monthly"
    elif mutation == "old_bond_beta":
        aggregate["five_passive_factor_rows"][0]["beta_BND"] = 0
    elif mutation == "alpha":
        aggregate["QQQ_single_factor_rows"][0]["alpha_annual_arithmetic"] = 0.2
    elif mutation == "corr_order":
        aggregate["strategy_correlations"][0]["symbols"].reverse()
    elif mutation == "corr_range":
        aggregate["strategy_correlations"][0]["matrix"][0][1] = 1.2
    elif mutation == "corr_symmetry":
        aggregate["strategy_correlations"][0]["matrix"][0][1] = 0.8
    elif mutation == "corr_diagonal":
        aggregate["strategy_correlations"][0]["matrix"][0][0] = 0.1
    elif mutation == "corr_size":
        aggregate["strategy_correlations"][0]["matrix"].pop()
    else:
        aggregate["source_hashes"] = {"/Users/private/source.npz": "1" * 64}
    with pytest.raises(ValueError):
        BUILDER.validate(aggregate)


def test_null_correlations_stay_undefined(aggregate):
    matrix = aggregate["strategy_correlations"][0]["matrix"]
    matrix[0][1] = matrix[1][0] = None
    BUILDER.validate(aggregate)
    markdown, standalone = BUILDER.render_stage(aggregate, "development", fake_png())
    assert "Undefined" in markdown and "Undefined" in standalone


def test_all_stage_reports_full_costs_attribution_and_correlations(aggregate):
    for stage in BUILDER.STAGES:
        markdown, standalone = BUILDER.render_stage(aggregate, stage, fake_png())
        assert standalone.startswith("<!doctype html>")
        assert standalone.count("data:image/png;base64,") == 1
        assert not re.search(
            r"<script\b|(?:src|href)=[\"'](?:https?:|//|file:)", standalone
        )
        assert "overflow-x: auto" in standalone and "@media print" in standalone
        for text in (markdown, standalone):
            assert "GDX, FXI, QQQ, UNG and FDN" in text
            assert "20%" in text
            assert "no later cap enforcement" in text
            assert "not generally nested" in text
            assert "retrospective" in text.lower()
            assert "best-found" in text
            assert "same exact full-precision weights" in text
            assert "Joint five passive ETF factor attribution" in text
            assert "Active strategy and portfolio correlations" in text
            assert "/Users/" not in text and ".cache/" not in text
            assert "BND beta" not in text
            assert "no_bond_" not in text  # readable aliases, no stale six-sleeve IDs
            assert "Maximum CAGR" in text and "excluded" in text
            for cost in BUILDER.COSTS:
                assert f"{int(cost)} bp slippage" in text
            for alias in BUILDER.ALIASES.values():
                assert alias in text
        assert (
            standalone.count("<table>") == 23
        )  # baseline, weights,4metrics,1QQQ,4joint,4cap,8corr


@pytest.mark.parametrize(
    "mutation", ["hash", "series", "symbol", "report", "endpoint", "private", "points"]
)
def test_figure_scope_and_endpoint_rejections(aggregate, tmp_path, mutation):
    source, figures, receipt = save_fixture(aggregate, tmp_path)
    if mutation == "hash":
        receipt["stage_figures"][0]["sha256"] = "0" * 64
    elif mutation == "series":
        receipt["stage_figures"][0]["series"] = 6
    elif mutation == "symbol":
        receipt["symbols"].append("BND")
    elif mutation == "report":
        receipt["saved_report_sha256"] = "0" * 64
    elif mutation == "endpoint":
        receipt["stage_figures"][0]["saved_aggregate_checks"][0][
            "terminal_equity_from_1000"
        ] += 1
    elif mutation == "private":
        receipt["private_input_locators_exported"] = True
    else:
        receipt["stage_figures"][0]["points_per_series"] -= 1
    (figures / "figures_verification.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        BUILDER.build(source, figures, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_manifest_determinism_and_new_outputs_only(aggregate, tmp_path):
    source, figures, _ = save_fixture(aggregate, tmp_path)
    first = BUILDER.build(source, figures, tmp_path / "first")
    second = BUILDER.build(source, figures, tmp_path / "second")
    assert first == second
    assert set(first["files"]) == {
        "README.md",
        "combined_report.md",
        *(f"{s}.html" for s in BUILDER.STAGES),
        *(f"{s}_baseline.png" for s in BUILDER.STAGES),
    }
    assert first["source_report_sha256"] == BUILDER.sha(source)
    for name, digest in first["files"].items():
        assert (
            hashlib.sha256((tmp_path / "first" / name).read_bytes()).hexdigest()
            == digest
        )
    with pytest.raises(ValueError, match="not empty"):
        BUILDER.build(source, figures, tmp_path / "first")
    overview = (tmp_path / "first" / "README.md").read_text()
    for stage in BUILDER.STAGES:
        assert f"]({stage}.html)" in overview


def test_report_builder_has_no_financial_array_or_fit_dependencies():
    source = (ROOT / "scripts/build_no_bond_reports.py").read_text()
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
        assert forbidden not in source


@pytest.mark.parametrize("legacy_key", ["mode", "frequency"])
def test_producer_cap_mode_is_required_without_legacy_key_fallback(
    aggregate, legacy_key
):
    """Mirror the producer schema; generic aliases must not mask a missing key."""
    assert [r["cap_mode"] for r in aggregate["solver_summaries"]] == list(BUILDER.MODES)
    aggregate["solver_summaries"][0][legacy_key] = aggregate["solver_summaries"][0].pop(
        "cap_mode"
    )
    with pytest.raises(ValueError, match="solver mode"):
        BUILDER.validate(aggregate)
