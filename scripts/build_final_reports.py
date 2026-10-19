#!/usr/bin/env python3
"""Build offline, aggregate-only class-project reports from saved public tables.

No trading account, market-data array, regression, selection or optimizer is run.
The same standalone HTML is the sole source for any separately rendered PDF.
"""

from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime
import hashlib
import html
import io
import itertools
import json
import math
from pathlib import Path
import re
import struct
import zlib

STAGES = {
    "development": (
        "2017-01-01",
        "2020-12-31",
        1007,
        "2017-01-03T14:30:00+00:00",
        "2017-01-03T22:00:00+00:00",
        "2020-12-31T22:00:00+00:00",
    ),
    "validation": (
        "2021-01-01",
        "2023-12-31",
        753,
        "2021-01-04T14:30:00+00:00",
        "2021-01-04T22:00:00+00:00",
        "2023-12-29T22:00:00+00:00",
    ),
    "historical_OOS": (
        "2024-01-01",
        "2026-10-15",
        700,
        "2024-01-02T14:30:00+00:00",
        "2024-01-02T22:00:00+00:00",
        "2026-10-15T21:00:00+00:00",
    ),
}
IDS = (
    "daily_capped_max_sharpe",
    "initial_capped_max_sharpe",
    "uncapped_max_sharpe",
    "equal_initial",
)
SYMBOLS = ("GDX", "FXI", "QQQ", "UNG", "FDN", "BND")
COSTS = (1.0, 3.0, 10.0, 25.0)
ALIASES = dict(
    zip(IDS, ("Daily cap fit", "Initial cap fit", "Uncapped fit", "Equal initial"))
)
DIRECTORIES = {
    "development": ("01_development", "01_development_and_robustness"),
    "validation": ("02_validation", "02_validation_and_frozen_selection"),
    "historical_OOS": ("03_historical_oos", "03_historical_oos_and_conclusions"),
}
TITLES = {
    "development": "Development and robustness",
    "validation": "Validation and frozen selection",
    "historical_OOS": "Historical OOS and conclusions",
}
REPORT = "reports/four_portfolios_three_periods"
ATTRIBUTION = "results/four_portfolio_attribution"
FIGURES = "assets/periods"
REPORT_SHA = "2213a49db6c339841a06457a8dd762b2431a9d232ae512ff29541d9c90edd3b0"
WEIGHTS_SHA = "79badfecbb5e260523582301bcd3aecda746323bab08142aa365c8df1642cc3e"
ATTRIBUTION_HASHES = {
    "QQQ_single_factor_all_periods_all_costs.csv": "14b2449aead11ef1ea65df568797b84fb15d4376f6e4b374dde117b2bc245dee",
    "six_passive_factor_all_periods_all_costs.csv": "c43c0ea072a99cb9f8e72148ddcf057b4085b100c6ec097549a78a4401f0548b",
    "factor_diagnostics_all_periods_all_costs.csv": "88df418f91fa1cc2aa87199036783b71b57cf5d281bb9eedfa1a59131d643fc1",
    "passive_factor_self_controls.csv": "0b12b293bfcc44c3c4efcd1fea4c045668079dd08a72db4945ad286828a922bf",
    "attribution.json": "f2f066ae9d32d759f202791bf95a315db9c7dfa4d5369bbdd2480620cdbdac84",
}
SCHEMA = "four_fixed_portfolios_offline_class_reports_v1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"nonfinite JSON {value}")
        ),
    )


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(
            reader.fieldnames
        ):
            raise ValueError("CSV has missing or duplicated columns")
        return list(reader)


def number(value, name: str = "number") -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} cannot be boolean")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def close(a, b, name: str, tolerance: float = 1e-11):
    if not math.isclose(
        number(a, name), number(b, name), rel_tol=tolerance, abs_tol=tolerance
    ):
        raise ValueError(f"{name} mismatch")


def identity(row: dict, key: str = "portfolio_id") -> tuple:
    return row["stage"], row[key], number(row["slippage_bps_each_way"])


def indexed(rows: list[dict], key: str = "portfolio_id") -> dict:
    result = {}
    for row in rows:
        item = identity(row, key)
        if item in result:
            raise ValueError("duplicated stage entity cost identity")
        result[item] = row
    return result


def _coerced_equal(value, text):
    if value is None:
        return text == ""
    if isinstance(value, bool):
        return text == str(value)
    if isinstance(value, (int, float)):
        return math.isfinite(float(text)) and float(text) == float(value)
    return value == text


def csv_matches(rows: list[dict], parsed: list[dict], name: str):
    if len(rows) != len(parsed):
        raise ValueError(f"{name} CSV row count mismatch")
    for left, right in zip(rows, parsed):
        if set(left) != set(right) or not all(
            _coerced_equal(value, right[key]) for key, value in left.items()
        ):
            raise ValueError(f"{name} CSV JSON mismatch")


def validate_data(
    report: dict,
    config: dict,
    singles: list[dict],
    joints: list[dict],
    provenance: dict,
):
    """Check complete, stage-specific aggregate identities without account paths."""
    if report.get("schema") != "four_fixed_portfolios_three_periods_aggregate_v1":
        raise ValueError("unexpected aggregate report schema")
    if (
        tuple(report.get("symbols", ())) != SYMBOLS
        or tuple(config.get("symbols", ())) != SYMBOLS
    ):
        raise ValueError("six-symbol order mismatch")
    if (
        tuple(report.get("slippage_bps_each_way", ())) != COSTS
        or report.get("commission_bps_each_way") != 1
        or report.get("initial_capital_each_stage") != 1000
    ):
        raise ValueError("fixed cost or initial capital mismatch")
    definitions = config.get("portfolios", [])
    saved = report.get("portfolios", [])
    if [r.get("id") for r in definitions] != list(IDS) or [
        r.get("id") for r in saved
    ] != list(IDS):
        raise ValueError("four fixed portfolio identity/order mismatch")
    for left, right in zip(definitions, saved):
        weights = left["initial_weights"]
        if set(weights) != set(SYMBOLS) or weights != right["initial_weights"]:
            raise ValueError("exact saved weights differ")
        values = [number(weights[s], "weight") for s in SYMBOLS]
        if min(values) < 0 or not math.isclose(sum(values), 1, abs_tol=1e-14):
            raise ValueError("invalid initial allocation")
    if definitions[1]["initial_weights"]["BND"] != 9.720788330706766e-18:
        raise ValueError("tiny positive BND weight must not be zeroed")
    summaries = report.get("stage_summaries", [])
    if [row.get("stage") for row in summaries] != list(STAGES):
        raise ValueError("three stage summary order mismatch")
    years = {}
    for row in summaries:
        stage = row["stage"]
        start, end, count, initial, first, last = STAGES[stage]
        if (
            row["scored_start"],
            row["scored_end"],
            row["observations"],
            row["initial_timestamp"],
            row["first_daily_valuation"],
            row["last_daily_valuation"],
            row["fresh_initial_capital"],
        ) != (start, end, count, initial, first, last, 1000):
            raise ValueError("stage bounds clock or observation count mismatch")
        years[stage] = (
            datetime.fromisoformat(last) - datetime.fromisoformat(initial)
        ).total_seconds() / (365 * 86400)
        close(row["elapsed_act365_years"], years[stage], "ACT365 clock", 1e-14)
    expected = set(itertools.product(STAGES, IDS, COSTS))
    controls_expected = set(
        itertools.product(STAGES, ("QQQ_buy_and_hold", "matched_cash"), COSTS)
    )
    for name, entity, expected_keys in (
        ("portfolio_rows", "portfolio_id", expected),
        ("control_rows", "control_id", controls_expected),
        ("cap_rows", "portfolio_id", expected),
    ):
        rows = report.get(name, [])
        actual = indexed(rows, entity)
        if set(actual) != expected_keys:
            raise ValueError(f"{name} incomplete or unknown stage entity cost")
        for (stage, item, _), row in actual.items():
            if number(row["commission_bps_each_way"]) != 1:
                raise ValueError("wrong commission")
            if name == "cap_rows":
                close(row["cap_fraction"], 1 / 3, "cap")
                maximum = max(number(row[f"max_daily_share_{s}"]) for s in SYMBOLS)
                close(maximum, row["max_daily_capital_share"], "maximum daily share")
                if not 0 < maximum <= 1 or not isinstance(
                    row["daily_cap_pass_diagnostic"], bool
                ):
                    raise ValueError("invalid cap diagnostic")
                if row["daily_cap_pass_diagnostic"] != (maximum <= 1 / 3 + 1e-12):
                    raise ValueError("cap pass flag mismatch")
                continue
            if row["observations"] != STAGES[stage][2]:
                raise ValueError("row observation count mismatch")
            close(row["elapsed_act365_years"], years[stage], "row ACT365")
            terminal = number(row["terminal_normalized_equity"])
            if terminal <= 0:
                raise ValueError("invalid terminal equity")
            close(
                row["terminal_equity_from_1000"],
                1000 * terminal,
                "terminal dollar units",
            )
            close(row["cagr"], terminal ** (1 / years[stage]) - 1, "CAGR clock")
            if (
                not -1 < number(row["max_drawdown"]) <= 0
                or number(row["annualized_return_volatility"]) < 0
                or number(row["annualized_cash_excess_volatility"]) < 0
            ):
                raise ValueError("invalid drawdown or volatility")
            if item == "matched_cash":
                if (
                    row["cash_excess_sharpe"] is not None
                    or row["annualized_cash_excess_volatility"] != 0
                ):
                    raise ValueError("cash Sharpe must remain undefined")
            else:
                number(row["cash_excess_sharpe"], "Sharpe")
    cash_rows = indexed(report["control_rows"], "control_id")
    for stage in STAGES:
        reference = {
            k: v
            for k, v in cash_rows[(stage, "matched_cash", 1.0)].items()
            if k != "slippage_bps_each_way"
        }
        if any(
            {
                k: v
                for k, v in cash_rows[(stage, "matched_cash", c)].items()
                if k != "slippage_bps_each_way"
            }
            != reference
            for c in COSTS
        ):
            raise ValueError("matched cash differs by nominal cost label")
    for rows, beta_names, count in ((singles, ("QQQ",), 1), (joints, SYMBOLS, 6)):
        if set(indexed(rows)) != expected:
            raise ValueError("attribution stage cost portfolio join mismatch")
        for row in rows:
            stage = row["stage"]
            if (
                number(row["commission_bps_each_way"]) != 1
                or number(row["observations"]) != STAGES[stage][2]
            ):
                raise ValueError("attribution cost or observation mismatch")
            close(
                row["alpha_annual_arithmetic"],
                252 * number(row["alpha_daily"]),
                "arithmetic alpha scaling",
            )
            for name in beta_names:
                number(row[f"beta_{name}"])
            r2 = number(row["r_squared"])
            if not 0 <= r2 <= 1 or number(row["residual_annualized_volatility"]) < 0:
                raise ValueError("invalid regression diagnostics")
            adjusted = 1 - (1 - r2) * (STAGES[stage][2] - 1) / (
                STAGES[stage][2] - count - 1
            )
            close(row["adjusted_r_squared"], adjusted, "adjusted R squared")
    cap_note = provenance.get("validation_current_daily_cap", {})
    if (
        cap_note.get("days_above_one_third_each_cost") != 41
        or cap_note.get("sleeve") != "UNG"
        or cap_note.get("weights_not_refitted_or_rebalanced") is not True
    ):
        raise ValueError("audited validation cap warning missing")
    current = indexed(report["cap_rows"])[("validation", IDS[0], 3.0)]
    close(
        cap_note["baseline_peak_sleeve_share"],
        current["max_daily_capital_share"],
        "validation cap warning peak",
    )
    return {
        "report": report,
        "config": config,
        "single": singles,
        "joint": joints,
        "provenance": provenance,
    }


def png_check(path: Path):
    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("figure is not a PNG")
    offset = 8
    dimensions = None
    while offset < len(raw):
        length = struct.unpack(">I", raw[offset : offset + 4])[0]
        kind = raw[offset + 4 : offset + 8]
        payload = raw[offset + 8 : offset + 8 + length]
        if len(payload) != length or offset + 12 + length > len(raw):
            raise ValueError("truncated PNG")
        crc = struct.unpack(">I", raw[offset + 8 + length : offset + 12 + length])[0]
        if crc != zlib.crc32(kind + payload) & 0xFFFFFFFF:
            raise ValueError("PNG CRC mismatch")
        if kind not in {b"IHDR", b"tEXt", b"pHYs", b"IDAT", b"IEND"}:
            raise ValueError("unexpected PNG metadata")
        if kind == b"tEXt" and (
            not payload.startswith(b"Software\0")
            or b"/Users/" in payload
            or b".cache" in payload
        ):
            raise ValueError("unsafe PNG text metadata")
        if kind == b"IHDR":
            dimensions = struct.unpack(">II", payload[:8])
        offset += length + 12
        if kind == b"IEND":
            break
    if offset != len(raw) or dimensions is None or min(dimensions) <= 0:
        raise ValueError("invalid PNG framing")
    return dimensions


def validate_figures(data: dict, verification: dict, root: Path):
    if (
        verification.get("baseline_commission_bps_each_way") != 1
        or verification.get("baseline_slippage_bps_each_way") != 3
        or verification.get("raster_only") is not True
        or verification.get("daily_input_arrays_exported") is not False
        or verification.get("private_input_locators_exported") is not False
    ):
        raise ValueError("figure scope mismatch")
    rows = verification.get("stage_figures", [])
    if [r.get("stage") for r in rows] != list(STAGES):
        raise ValueError("figure stage mapping mismatch")
    portfolios = indexed(data["report"]["portfolio_rows"])
    controls = indexed(data["report"]["control_rows"], "control_id")
    for row in rows:
        stage = row["stage"]
        expected = f"{stage}_baseline.png"
        if (
            row["file"] != expected
            or row["series"] != 5
            or row["points_per_series"] != STAGES[stage][2] + 1
            or row["initial_value"] != 1000
            or row.get("all_daily_points_rendered") is not True
        ):
            raise ValueError("baseline chart identity mismatch")
        path = root / FIGURES / expected
        if sha(path) != row["sha256"]:
            raise ValueError("figure hash mismatch")
        png_check(path)
        for field, metric in (
            ("terminal_equity_by_series", "terminal_equity_from_1000"),
            ("max_daily_drawdown_by_series", "max_drawdown"),
        ):
            if set(row[field]) != set(IDS) | {"QQQ_buy_and_hold"}:
                raise ValueError("chart series identity mismatch")
            for entity, value in row[field].items():
                source = (
                    controls[(stage, entity, 3.0)]
                    if entity == "QQQ_buy_and_hold"
                    else portfolios[(stage, entity, 3.0)]
                )
                close(value, source[metric], "chart aggregate endpoint")


def load_inputs(root: Path) -> dict:
    required = [
        f"{REPORT}/manifest.json",
        f"{REPORT}/report.json",
        "configs/four_portfolios.json",
        "configs/selected_strategies.json",
        "configs/research_protocol.json",
        f"{ATTRIBUTION}/QQQ_single_factor_all_periods_all_costs.csv",
        f"{ATTRIBUTION}/six_passive_factor_all_periods_all_costs.csv",
        f"{FIGURES}/figure_verification.json",
    ]
    manifest = read_json(root / REPORT / "manifest.json")
    files = manifest.get("files", {})
    if (
        set(files)
        != {
            "cap_rows.csv",
            "control_rows.csv",
            "portfolio_rows.csv",
            "provenance.json",
            "report.json",
            "report.md",
            "stage_summaries.csv",
        }
        or manifest.get("aggregate_only") is not True
    ):
        raise ValueError("aggregate input manifest mismatch")
    for name, digest in files.items():
        relative = f"{REPORT}/{name}"
        if sha(root / relative) != digest:
            raise ValueError("aggregate source hash mismatch")
        required.append(relative)
    if (
        sha(root / REPORT / "report.json") != REPORT_SHA
        or sha(root / "configs/four_portfolios.json") != WEIGHTS_SHA
    ):
        raise ValueError("frozen aggregate or four allocation hash changed")
    historical_manifest = read_json(root / "results/export_manifest.json")
    required.append("results/export_manifest.json")
    for relative in (
        "configs/selected_strategies.json",
        "configs/research_protocol.json",
    ):
        if sha(root / relative) != historical_manifest["files"][relative]:
            raise ValueError("frozen signal or protocol hash changed")
    presentation = read_json(root / "configs/study_presentation.json")
    if presentation.get(
        "active_study"
    ) != "earlier_four_fixed_portfolio_study" or presentation.get(
        "portfolio_ids"
    ) != list(IDS):
        raise ValueError("active study presentation mismatch")
    for stage, (start, end, *_) in STAGES.items():
        if presentation.get(stage) != {"start": start, "end": end}:
            raise ValueError("active presentation stage bounds mismatch")
    required.append("configs/study_presentation.json")
    for name, digest in ATTRIBUTION_HASHES.items():
        relative = f"{ATTRIBUTION}/{name}"
        if sha(root / relative) != digest:
            raise ValueError("verified attribution source hash changed")
        required.append(relative)
    report = read_json(root / REPORT / "report.json")
    for field in ("portfolio_rows", "control_rows", "cap_rows", "stage_summaries"):
        csv_matches(report[field], read_csv(root / REPORT / f"{field}.csv"), field)
    config = read_json(root / "configs/four_portfolios.json")
    single = read_csv(
        root / ATTRIBUTION / "QQQ_single_factor_all_periods_all_costs.csv"
    )
    joint = read_csv(
        root / ATTRIBUTION / "six_passive_factor_all_periods_all_costs.csv"
    )
    provenance = read_json(root / REPORT / "provenance.json")
    data = validate_data(report, config, single, joint, provenance)
    attribution = read_json(root / ATTRIBUTION / "attribution.json")
    if (
        attribution.get("four_fixed_portfolio_config_sha256") != WEIGHTS_SHA
        or attribution.get("joint_factors") != list(SYMBOLS)
        or attribution.get("independent_models_verified") != 96
    ):
        raise ValueError("attribution definition binding mismatch")
    csv_matches(attribution["QQQ_single_factor_rows"], single, "QQQ attribution")
    csv_matches(attribution["six_passive_factor_rows"], joint, "joint attribution")
    diagnostics = attribution["factor_diagnostic_rows"]
    csv_matches(
        diagnostics,
        read_csv(root / ATTRIBUTION / "factor_diagnostics_all_periods_all_costs.csv"),
        "factor diagnostics",
    )
    if {(r["stage"], r["slippage_bps_each_way"]) for r in diagnostics} != set(
        itertools.product(STAGES, COSTS)
    ) or len(diagnostics) != 12:
        raise ValueError("factor diagnostic stage cost mapping mismatch")
    for row in diagnostics:
        if (
            row["observations"] != STAGES[row["stage"]][2]
            or row["commission_bps_each_way"] != 1
            or row["regression_design_rank_including_intercept"] != 7
        ):
            raise ValueError("factor diagnostic rank or clock mismatch")
        if (
            number(row["standardized_factor_condition_number"]) < 1
            or min(number(row[f"VIF_{s}"]) for s in SYMBOLS) < 1 - 1e-12
        ):
            raise ValueError("invalid factor overlap diagnostics")
    data["factor_diagnostics"] = diagnostics
    data["strategies"] = read_json(root / "configs/selected_strategies.json")
    if data["strategies"].get("symbols") != list(SYMBOLS) or [
        r.get("symbol") for r in data["strategies"].get("strategies", [])
    ] != list(SYMBOLS):
        raise ValueError("selected strategy mapping mismatch")
    protocol = read_json(root / "configs/research_protocol.json")
    if (
        protocol["timing"]["consecutive_checks"] != 7
        or protocol["cash"]["nominal_annual_rate"] != 0.03
    ):
        raise ValueError("fixed strategy protocol mismatch")
    verification = read_json(root / FIGURES / "figure_verification.json")
    validate_figures(data, verification, root)
    required += [f"{FIGURES}/{stage}_baseline.png" for stage in STAGES]
    correlation_name = "results/strategy_correlation_matrices_all_costs.csv"
    if sha(root / correlation_name) != historical_manifest["files"][correlation_name]:
        raise ValueError("saved strategy correlation source hash changed")
    correlation = read_csv(root / correlation_name)
    if len(correlation) != 24 or {
        (number(r["slippage_bps_each_way"]), r["symbol"]) for r in correlation
    } != set(itertools.product(COSTS, SYMBOLS)):
        raise ValueError("strategy correlation cost symbol mapping mismatch")
    baseline = {
        r["symbol"]: r for r in correlation if number(r["slippage_bps_each_way"]) == 3
    }
    for symbol in SYMBOLS:
        close(baseline[symbol][symbol], 1, "correlation diagonal")
        for other in SYMBOLS:
            if abs(number(baseline[symbol][other])) > 1 + 1e-12:
                raise ValueError("invalid saved strategy correlation")
            close(
                baseline[symbol][other], baseline[other][symbol], "correlation symmetry"
            )
    data["baseline_strategy_correlations"] = [
        {
            "symbol": symbol,
            **{other: number(baseline[symbol][other]) for other in SYMBOLS},
        }
        for symbol in SYMBOLS
    ]
    correlation_figure = verification.get("correlation_figure", {})
    if correlation_figure.get("file") != "oos_strategy_correlations.png" or sha(
        root / FIGURES / correlation_figure["file"]
    ) != correlation_figure.get("sha256"):
        raise ValueError("OOS correlation raster hash mismatch")
    png_check(root / FIGURES / correlation_figure["file"])
    required += [correlation_name, f"{FIGURES}/{correlation_figure['file']}"]
    data["source_hashes"] = {name: sha(root / name) for name in sorted(set(required))}
    data["root"] = root
    return data


def safe_json(value) -> str:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    )


def stage_data(data: dict, stage: str) -> dict:
    """Copy only explicit aggregate fields; never serialize an input source map."""
    if stage not in STAGES:
        raise ValueError("unknown stage")
    report = data["report"]
    common = ("stage", "slippage_bps_each_way", "commission_bps_each_way")
    metrics = (
        "elapsed_act365_years",
        "cash_excess_sharpe",
        "cagr",
        "max_drawdown",
        "terminal_normalized_equity",
        "observations",
        "annualized_return_volatility",
        "annualized_cash_excess_volatility",
        "terminal_equity_from_1000",
    )
    caps = (
        "cap_fraction",
        "initial_cap_pass_diagnostic",
        "daily_cap_pass_diagnostic",
        "max_daily_capital_share",
        "max_capital_share_including_initial",
        *(f"max_daily_share_{s}" for s in SYMBOLS),
    )
    attribution = (
        "alpha_daily",
        "alpha_annual_arithmetic",
        "r_squared",
        "adjusted_r_squared",
        "observations",
        "residual_annualized_volatility",
    )
    result = {
        "schema": SCHEMA,
        "stage": stage,
        "title": TITLES[stage],
        "summary": next(r for r in report["stage_summaries"] if r["stage"] == stage),
        "initial_allocations": report["portfolios"],
        "strategy_definitions": data["strategies"]["strategies"],
        "limitations": [
            "Retrospective OOS-examined configurations, pruning and weights; not untouched portfolio validation or OOS.",
            "Static initial sleeve wealth; no cross-sleeve rebalancing or refit by stage or cost.",
            "The historical daily cap can fail backward validation and does not promise future or intraday enforcement.",
        ],
    }
    groups = (
        (
            "portfolio_rows",
            report["portfolio_rows"],
            (*common, "portfolio_id", *metrics),
        ),
        ("control_rows", report["control_rows"], (*common, "control_id", *metrics)),
        ("cap_rows", report["cap_rows"], (*common, "portfolio_id", *caps)),
        (
            "QQQ_single_factor_rows",
            data["single"],
            (*common, "portfolio_id", *attribution, "beta_QQQ"),
        ),
        (
            "six_passive_factor_rows",
            data["joint"],
            (*common, "portfolio_id", *attribution, *(f"beta_{s}" for s in SYMBOLS)),
        ),
    )
    for key, rows, fields in groups:
        result[key] = []
        for row in rows:
            if row["stage"] != stage:
                continue
            copied = {field: row[field] for field in fields}
            if key in ("QQQ_single_factor_rows", "six_passive_factor_rows"):
                copied = {
                    field: (
                        value
                        if field in ("stage", "portfolio_id")
                        else int(number(value))
                        if field == "observations"
                        else number(value)
                    )
                    for field, value in copied.items()
                }
            result[key].append(copied)
    result["factor_diagnostic_rows"] = [
        r for r in data.get("factor_diagnostics", []) if r["stage"] == stage
    ]
    if stage == "validation":
        result["audited_cap_warning"] = data["provenance"][
            "validation_current_daily_cap"
        ]
    if stage == "historical_OOS":
        result["baseline_active_strategy_correlation_rows"] = data[
            "baseline_strategy_correlations"
        ]
    return result


def e(value) -> str:
    return html.escape(str(value), quote=True)


def fmt(value, percent=False, digits=3) -> str:
    if value is None or value == "":
        return "Undefined"
    return f"{number(value) * (100 if percent else 1):,.{digits}f}" + (
        "%" if percent else ""
    )


def table(headers: list[str], rows: list[list[str]], numeric_from=1) -> str:
    def cell(tag, value, index):
        return (
            f"<{tag}"
            + (
                ' class="num"'
                if index >= numeric_from or (index == 0 and headers[0] == "Slippage bp")
                else ""
            )
            + f">{e(value)}</{tag}>"
        )

    return (
        '<div class="table-scroll"><table><thead><tr>'
        + "".join(cell("th", h, i) for i, h in enumerate(headers))
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join(cell("td", c, i) for i, c in enumerate(row)) + "</tr>"
            for row in rows
        )
        + "</tbody></table></div>"
    )


CSS = """
@page { size: A4; margin: 18mm 17mm 19mm; }
* { box-sizing: border-box; }
body { margin: 0 auto; max-width: 1050px; padding: 34px; color: #171717; background: white; font: 15px/1.48 Arial,Helvetica,sans-serif; }
h1,h2,h3,h4 { color: #111; line-height: 1.15; font-weight: 700; break-after: avoid; }
h1 { font-size: 47px; margin: 15px 0 24px; letter-spacing: -1.3px; }
h2 { font-size: 31px; margin: 35px 0 19px; letter-spacing: -.6px; }
h3 { font-size: 21px; margin: 25px 0 13px; }
h4 { font-size: 16px; margin: 19px 0 10px; }
p { margin: 10px 0; } .eyebrow,.date,.caption,.muted { color: #666; }
.eyebrow { font-size: 13px; text-transform: uppercase; letter-spacing: 1.4px; }
.date { margin: 10px 0 35px; } .lead { font-size: 19px; line-height: 1.5; }
.warning { border-left: 3px solid #777; padding-left: 15px; margin: 20px 0; }
nav { margin: 25px 0; } nav ol { columns: 2; padding-left: 20px; } nav li { margin: 6px 0; }
a { color: #222; } .chapter { margin-top: 38px; }
.table-scroll { width: 100%; max-width: 100%; overflow-x: auto; }
table { min-width: 600px; border-collapse: collapse; width: 100%; font-size: 12px; margin: 13px 0 18px; font-variant-numeric: tabular-nums; }
th,td { padding: 7px 6px; text-align: left; vertical-align: top; border-bottom: 1px solid #ddd; }
th { font-weight: 700; background: #f4f4f4; border-top: 1px solid #ccc; } .num { text-align: right; }
tr { break-inside: avoid; } thead { display: table-header-group; }
img { width: 100%; height: auto; display: block; margin: 12px 0 0; } figure { margin: 18px 0; break-inside: avoid; } figcaption { font-size: 12px; color: #666; margin: 8px 0; }
.formula { font-family: Georgia,serif; font-size: 17px; padding: 10px 0; }
.small { font-size: 12px; } .definitions td:last-child { overflow-wrap: anywhere; } .definitions { font-size: 11px; }
.small { overflow-wrap: anywhere; } footer { margin-top: 30px; color: #666; font-size: 11px; border-top: 1px solid #ddd; padding-top: 12px; }
@media (max-width: 600px) { body { padding: 20px 16px; font-size: 14px; } h1 { font-size: 34px; letter-spacing: -.7px; } h2 { font-size: 27px; } nav ol { columns: 1; } }
@media print { body { padding: 0; max-width: none; font-size: 10pt; line-height: 1.32; } h1 { font-size: 32pt; } h2 { font-size: 22pt; margin: 28px 0 15px; } h3 { font-size: 14pt; margin: 16px 0 9px; } h4 { font-size: 10.5pt; margin: 14px 0 7px; } p { margin: 8px 0; } .lead { font-size: 13pt; } .table-scroll { overflow: visible; max-width: none; } table { min-width: 0; font-size: 8.5pt; line-height: 1.22; margin: 7px 0 10px; } th,td { padding: 3px 4px; } .chapter,.subchapter,.appendix { break-before: page; margin-top: 0; } nav ol { columns: 1; } a { text-decoration: none; } .definitions { font-size: 7.7pt; } .definitions table { font-size: 7.7pt; } .small { font-size: 8.5pt; } .costs h3 { font-size: 13pt; margin: 11px 0 5px; } .costs .table-scroll,.appendix .table-scroll { break-inside: avoid; } .references { break-inside: avoid; font-size: 8.3pt; line-height: 1.25; } .references p { margin: 6px 0; } }
"""


def render_html(
    stage: dict, png_bytes: bytes, correlation_png_bytes: bytes | None = None
) -> str:
    sid = stage["stage"]
    summary = stage["summary"]
    pp = indexed(stage["portfolio_rows"])
    cc = indexed(stage["control_rows"], "control_id")
    single = indexed(stage["QQQ_single_factor_rows"])
    joint = indexed(stage["six_passive_factor_rows"])
    current, bh = pp[(sid, IDS[0], 3)], cc[(sid, "QQQ_buy_and_hold", 3)]
    correlation_markup = ""
    if sid == "historical_OOS":
        if correlation_png_bytes is None:
            raise ValueError(
                "historical OOS needs its verified saved correlation raster"
            )
        correlation = {
            row["symbol"]: row
            for row in stage["baseline_active_strategy_correlation_rows"]
        }
        correlation_markup = (
            '<div class="subchapter"><h3>Active strategy return correlations</h3><p>This saved analysis uses the 700 historical OOS daily observations from 2024-01-02 through 2026-10-15 at baseline costs. It measures active net strategy returns, including flat and cash periods, not the passive ETF factors used in attribution.</p><p>QQQ and FDN strategy correlation is '
            + fmt(correlation["QQQ"]["FDN"], digits=6)
            + "; GDX and UNG is "
            + fmt(correlation["GDX"]["UNG"], digits=6)
            + '. These are sample descriptions, not future diversification guarantees, risk limits or a paired long-short strategy test.</p><figure><img alt="Historical OOS baseline daily active strategy return correlations" src="data:image/png;base64,'
            + base64.b64encode(correlation_png_bytes).decode("ascii")
            + '"><figcaption>Existing saved 700-observation aggregate matrix and raster only. No new correlation fit or daily numerical series is exported. No development or validation correlations are inferred from this OOS figure.</figcaption></figure></div>'
        )
    interpretation = {
        "development": "Equal initial capital has the highest baseline cash-excess Sharpe among these four saved allocations. Passive QQQ nevertheless has the higher CAGR. The daily-cap fit lowers observed daily drawdown relative to passive QQQ, but its weights were selected later, so this backward result is not independent discovery evidence.",
        "validation": "Equal initial capital again has the highest baseline Sharpe among the four allocations. The uncapped fit has negative cash-excess Sharpe, while its positive CAGR remains below the matched cash path over the stage. The current allocation has slightly lower Sharpe than passive QQQ, and its historical cap fails; these unfavorable results remain in the report.",
        "historical_OOS": "The uncapped fit has the highest baseline Sharpe but far lower CAGR than the other fitted allocations. The initial-only capped fit has higher CAGR than the daily-cap fit but does not enforce the required drifting-capital constraint. The daily-cap fit has lower CAGR and a smaller observed daily drawdown than passive QQQ. All of these comparisons are conditioned on examining this same historical sample.",
    }[sid]
    cost_comparison = f"For the current allocation, CAGR is {fmt(pp[(sid, IDS[0], 1)]['cagr'], True, 2)} at 1-bp slippage and {fmt(pp[(sid, IDS[0], 25)]['cagr'], True, 2)} at 25-bp slippage, with the additional 1-bp commission in both cases. No cost scenario triggers reselection or weight refitting."
    sections = [
        "Project goal",
        "Research outline",
        "Data",
        "Backtesting",
        "Execution and slippage",
        "Weighting",
        "Performance evaluation",
    ]
    pieces = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(TITLES[sid])} — ETF portfolios</title><style>{CSS}</style></head><body>',
        '<header><p class="eyebrow">Class project research report</p><h1>Trend Following and Mean Reversion ETF Portfolios</h1>',
        f'<p class="lead">{e(TITLES[sid])}</p><p class="date">Study endpoint 15 October 2026 · Report prepared 19 October 2026<br>Scored period {e(summary["scored_start"])} to {e(summary["scored_end"])}</p></header>',
        "<h2>Executive summary</h2>",
        f"<p>We compare four unchanged allocations across six fixed long/cash ETF strategies. At baseline costs, the historical daily-cap allocation has cash-excess Sharpe <strong>{fmt(current['cash_excess_sharpe'])}</strong>, CAGR <strong>{fmt(current['cagr'], True, 2)}</strong> and daily maximum drawdown <strong>{fmt(current['max_drawdown'], True, 2)}</strong>. Cost-matched passive QQQ has Sharpe {fmt(bh['cash_excess_sharpe'])}, CAGR {fmt(bh['cagr'], True, 2)} and drawdown {fmt(bh['max_drawdown'], True, 2)}.</p>",
        '<p class="warning"><strong>Retrospective evidence only.</strong> Configurations, ETF pruning and portfolio weights were chosen using the already examined 2024–2026 sample. Applying those weights backward does not create independent portfolio development or validation. The historical OOS label describes the parent strategy window, not an untouched portfolio test. This distinction matters after extensive candidate and allocation search [4].</p>',
    ]
    if sid == "validation":
        pieces.append(
            '<p class="warning"><strong>Historical cap failure preserved.</strong> UNG exceeds one-third of current portfolio capital on 41 daily valuations in each cost scenario; its baseline peak is 35.1826%. We do not refit weights, rebalance or remove these observations.</p>'
        )
    pieces += [
        '<nav aria-label="Report index"><h3>Index</h3><ol>'
        + "".join(
            f'<li><a href="#section{i}">{e(name)}</a></li>'
            for i, name in enumerate(sections, 1)
        )
        + "</ol></nav>",
        '<section class="chapter"><h2 id="section1">1 Project goal</h2><p>Our objective is to study whether combining causal trend following and oversold-recovery strategies can improve the return and drawdown profile relative to passive ETF exposure, after explicit execution costs. This is a reproducible historical research project, not a trading recommendation.</p><p>We ask how the same four static initial allocations behave in different periods, how costs change the result, how much return remains after passive-ETF attribution, and whether the historical capital-share constraint survives backward comparison.</p>',
        '<h2 id="section2">2 Research outline</h2><p>Trend persistence motivates the trend hypothesis [1], but our ETF implementation is not a replication of that paper. The parent study evaluated 379 definitions per ETF: 289 trend-following and 90 long/cash mean-reversion configurations. Independent development and validation qualification used a strict joint gate at 25-bp slippage: cash-excess Sharpe above matched own-ETF buy-and-hold and CAGR above two-thirds of its CAGR, except that a negative benchmark CAGR requires positive candidate CAGR. Nonfinite candidates cannot pass. Later ETF filtering and correlation pruning led to these six sleeves.</p><p>We retain four comparisons: a historical daily-cap Sharpe fit, an initial-only capped fit, an uncapped Sharpe fit and equal initial capital. We exclude the standalone maximum-CAGR 100%-GDX strategy allocation; GDX remains an underlying sleeve. These allocations are saved historical fits, not newly optimized solutions or global-optimum certificates.</p>',
        '<h2 id="section3">3 Data</h2><p>The parent universe spans 56 US-listed equity-index, international, sector, industry, bond and commodity ETFs. This portfolio report uses GDX, FXI, QQQ, UNG, FDN and BND. Data came from Alpha Vantage daily adjusted records and observed 30-minute bars: native raw captures where available, and matching-vintage-restored legacy captures otherwise. Daily anchors and available 15-minute observations provide same-provider reconciliation checks, not independent-vendor confirmation. The study does not establish point-in-time vendor availability. Daily feature history begins in 2015 where available.</p><p>Public inputs here are only saved aggregate statistics, definitions, exact initial weights and audited raster charts. Raw captures, trade-level accounts and full numerical daily paths remain private. Aggregate tables alone cannot reproduce original historical trades.</p>',
        table(
            ["Scored window", "Daily observations", "ACT365 years", "Initial account"],
            [
                [
                    f"{summary['scored_start']} to {summary['scored_end']}",
                    str(summary["observations"]),
                    f"{summary['elapsed_act365_years']:.12f}",
                    "$1,000",
                ]
            ],
            1,
        ),
        f'<p class="small">Fresh account opens {e(summary["initial_timestamp"])}. First daily valuation {e(summary["first_daily_valuation"])}; final valuation {e(summary["last_daily_valuation"])}. These are timestamped accounting observations, not claims of exchange fills at daily valuation time.</p></section>',
        '<section class="chapter"><h2 id="section4">4 Backtesting</h2><p>Indicators are causal and daily, observed with native half-hour checks. Entry and exit require the shared three-trading-hour confirmation, equivalent to seven consecutive half-hour checks, followed by execution at the next eligible observed bar open. Each stage starts flat with $1,000; only feature history is carried, not holdings, orders or confirmation streaks. Accounts are unlevered, fractional long/cash, with the parent study’s corporate-action, dividend/reinvestment and paid terminal-liquidation conventions preserved.</p><p>Cash accrues at 3% nominal ACT/365, event-compounded. It is neither downloaded Treasury return nor a 3% APY assumption. We do not splice stages into a single wealth curve or manufacture combined trade counts from six independent accounts.</p>',
        '<p class="formula">V<sub>c,t</sub> = Σ<sub>i</sub> w<sub>i</sub>E<sub>c,i,t</sub> &nbsp; and &nbsp; r<sub>c,t</sub> = [V<sub>c,t</sub> / V<sub>c,t−1</sub>] − 1</p><p>Here c identifies the cost scenario; E<sub>c,i,0</sub> = 1, V<sub>c,0</sub> = 1 and Σ<sub>i</sub>w<sub>i</sub> = 1. Each E<sub>c,i,t</sub> is saved sleeve wealth normalized to its initial account. Static initial wealth mixing is not constant-weight daily return averaging. The same exact weights apply to every cost and period, with no cross-sleeve cash funding or rebalance trades.</p>',
        "<h3>Metric definitions</h3><p>Cash-excess Sharpe is √252 times the mean daily return minus matched cash return, divided by its sample standard deviation with one degree-of-freedom correction. It does not mean outperformance relative to buy-and-hold [2]. Square-root-252 annualization is descriptive and does not supply dependence-robust statistical inference [3]. CAGR uses final normalized wealth and the actual initial-to-terminal ACT/365 clock. Volatility is the annualized sample standard deviation of net daily returns. Drawdown uses daily valuations and includes the initial balance; it is not the worst intraday loss. Matched cash has undefined Sharpe because its cash-excess variance is zero.</p>",
        "<h3>Attribution definitions</h3><p>We fit saved net cash-excess portfolio returns on passive QQQ cash-excess returns with an intercept, and separately on all six cost-matched passive ETF cash-excess returns jointly. The factors are passive buy-and-hold accounts, not active strategy returns. Annual arithmetic alpha is 252 times the daily intercept, not CAGR. Betas are conditional linear sensitivities, not portfolio weights; negative beta does not imply an executed short. R² is descriptive, with no significance or causal-skill claim.</p></section>",
        '<section class="chapter costs"><h2 id="section5">5 Execution and slippage</h2><p>Every purchase and sale pays 1-bp commission plus one-way slippage of 1, 3, 10 or 25 bps. The baseline is 3-bp slippage, or 4 bps total per side. No crypto-course fee assumptions are transferred to ETFs. Each scenario has its own cost-matched passive QQQ and cash control and retains the original paid liquidation. We do not change signals or weights when cost assumptions change.</p>',
    ]
    for cost in COSTS:
        metric_rows = [(ALIASES[pid], pp[(sid, pid, cost)]) for pid in IDS] + [
            ("QQQ buy and hold", cc[(sid, "QQQ_buy_and_hold", cost)]),
            ("Matched cash", cc[(sid, "matched_cash", cost)]),
        ]
        pieces += [
            f"<h3>{int(cost)} bp slippage each way</h3>",
            table(
                [
                    "Allocation or control",
                    "Sharpe",
                    "Total return",
                    "CAGR",
                    "Volatility",
                    "Daily max DD",
                    "Final $1,000",
                ],
                [
                    [
                        label,
                        fmt(r["cash_excess_sharpe"]),
                        fmt(number(r["terminal_normalized_equity"]) - 1, True, 2),
                        fmt(r["cagr"], True, 2),
                        fmt(r["annualized_return_volatility"], True, 2),
                        fmt(r["max_drawdown"], True, 2),
                        "$" + fmt(r["terminal_equity_from_1000"], digits=2),
                    ]
                    for label, r in metric_rows
                ],
            ),
        ]
    pieces += [
        '<p class="small">All rows include the additional 1-bp commission each way. “Undefined” is retained, not reported as zero. Full-precision aggregate values accompany this report in CSV and JSON.</p></section>',
        '<section class="chapter"><h2 id="section6">6 Weighting</h2><p>Capital is assigned once to six strategy sleeves, including their idle cash. In particular, the large BND allocation in the uncapped fit is not continuous passive bond exposure. The daily-cap fit was constrained on historical OOS daily sleeve capital shares in all four costs; it is not a future, intraday, ETF-holdings or risk-contribution limit. The initial-only constraint can drift after initialization.</p>',
        table(
            [
                "Strategy sleeve",
                "Daily cap fit",
                "Initial cap fit",
                "Uncapped fit",
                "Equal initial",
            ],
            [
                [s]
                + [
                    fmt(p["initial_weights"][s], True, 6)
                    for p in stage["initial_allocations"]
                ]
                for s in SYMBOLS
            ],
        ),
        '<p class="small">Table weights are rounded for readability. Full-precision JSON is authoritative. The initial-only fit retains its BND weight of 9.720788330706766 × 10⁻¹⁸; a displayed 0.000000% is not a zeroed input.</p>',
        "<h3>Unchanged strategy definitions</h3>",
        '<div class="definitions">'
        + table(
            ["ETF", "Saved rule", "Exact configuration identity"],
            [
                [r["symbol"], r["label"], r["candidate_id"]]
                for r in stage["strategy_definitions"]
            ],
            3,
        )
        + "</div>",
        '<div class="subchapter cap-chapter"><h3>Observed capital share diagnostics</h3><p>These diagnostics track each sleeve’s share of total saved portfolio wealth at every daily valuation. They do not alter initial weights, trigger cross-sleeve trades or impose new costs. All 16 allocation-cost cases remain in the comparison, whether the observed constraint passes or fails.</p>',
        table(
            [
                "Slippage bp",
                "Allocation",
                "Largest daily share",
                "Initial cap",
                "Every daily cap",
            ],
            [
                [
                    str(int(number(r["slippage_bps_each_way"]))),
                    ALIASES[r["portfolio_id"]],
                    fmt(r["max_daily_capital_share"], True, 4),
                    "Pass" if r["initial_cap_pass_diagnostic"] else "Fail",
                    "Pass" if r["daily_cap_pass_diagnostic"] else "Fail",
                ]
                for r in stage["cap_rows"]
            ],
            2,
        ),
    ]
    if sid == "validation":
        pieces.append(
            '<p class="warning">The current daily-cap historical fit fails the backward validation diagnostic: UNG reaches 35.1826% at baseline and exceeds one-third on 41 valuations at each cost. This recorded breach is intentionally retained. No hidden daily rebalancing is assumed.</p>'
        )
    else:
        pieces.append(
            "<p>The cap table is an observed historical diagnostic, not a newly enforced trading constraint. Its pass/fail status does not replace the frozen allocation or delete a cost scenario.</p>"
        )
    pieces += [
        '</div></section><section class="chapter"><h2 id="section7">7 Performance evaluation</h2><h3>Period interpretation</h3><p>'
        + e(interpretation)
        + "</p><p>"
        + e(cost_comparison)
        + "</p><h3>Baseline equity and daily drawdown</h3>",
        '<figure><img alt="Four unchanged strategy portfolios and passive QQQ baseline equity and daily drawdown" src="data:image/png;base64,'
        + base64.b64encode(png_bytes).decode("ascii")
        + '"><figcaption>Saved-path raster only. Four portfolios and cost-matched passive QQQ each start at $1,000, use 1-bp commission plus 3-bp slippage each way, and include initial balance and paid terminal liquidation. Numerical daily paths are not embedded in this report.</figcaption></figure>',
        '<div class="subchapter qqq-attribution"><h3>QQQ single factor attribution</h3><p>The table uses same-stage, same-cost passive QQQ. Alpha is annualized arithmetic percent per year. Betas and R² are descriptive fitted statistics; no unreported significance threshold is implied.</p>',
        table(
            [
                "Slippage bp",
                "Allocation",
                "Alpha annual",
                "QQQ beta",
                "R squared",
                "Residual vol",
            ],
            [
                [
                    str(int(cost)),
                    ALIASES[pid],
                    fmt(single[(sid, pid, cost)]["alpha_annual_arithmetic"], True, 2),
                    fmt(single[(sid, pid, cost)]["beta_QQQ"], digits=4),
                    fmt(single[(sid, pid, cost)]["r_squared"], True, 2),
                    fmt(
                        single[(sid, pid, cost)]["residual_annualized_volatility"],
                        True,
                        2,
                    ),
                ]
                for cost, pid in itertools.product(COSTS, IDS)
            ],
            2,
        ),
        '</div><div class="appendix"><h3>Joint six passive factor attribution</h3><p>Each row regresses on passive GDX, FXI, QQQ, UNG, FDN and BND jointly with an intercept. Partial slopes are not separate one-factor betas. Correlated factors can change coefficient interpretation, and higher in-sample R² does not establish predictive value.</p>',
    ]
    for cost in COSTS:
        pieces += [
            f"<h4>{int(cost)} bp slippage plus 1 bp commission each way</h4>",
            table(
                [
                    "Allocation",
                    "GDX β",
                    "FXI β",
                    "QQQ β",
                    "UNG β",
                    "FDN β",
                    "BND β",
                    "Alpha",
                    "R²",
                ],
                [
                    [ALIASES[pid]]
                    + [
                        fmt(joint[(sid, pid, cost)][f"beta_{s}"], digits=4)
                        for s in SYMBOLS
                    ]
                    + [
                        fmt(
                            joint[(sid, pid, cost)]["alpha_annual_arithmetic"], True, 2
                        ),
                        fmt(joint[(sid, pid, cost)]["r_squared"], True, 2),
                    ]
                    for pid in IDS
                ],
            ),
        ]
    pieces += [
        "</div><h3>Passive factor overlap diagnostics</h3>",
        table(
            ["Slippage bp", "Design rank", "Condition number", "QQQ VIF", "FDN VIF"],
            [
                [
                    str(int(r["slippage_bps_each_way"])),
                    str(r["regression_design_rank_including_intercept"]),
                    fmt(r["standardized_factor_condition_number"]),
                    fmt(r["VIF_QQQ"]),
                    fmt(r["VIF_FDN"]),
                ]
                for r in stage.get("factor_diagnostic_rows", [])
            ],
            1,
        ),
        '<p class="small">Rank includes the intercept. The condition number uses standardized passive factors. QQQ and FDN factor overlap can inflate coefficient uncertainty; a full-rank fit does not eliminate collinearity risk. No p-values or significance claims are reported.</p>',
        correlation_markup,
        '<div class="chapter conclusions"><h3>Conclusions and limitations</h3><p>The four allocations expose a genuine research trade-off: a high fitted Sharpe need not maximize compound growth, and apparent diversification can partly reflect cash-heavy sleeves rather than independent alpha. Comparisons across periods and costs are descriptive robustness checks. We do not select a new winner, alter parent-stage membership, refit weights, or claim the examined OOS sample became untouched again.</p><p>The assignment’s momentum and reversal themes are addressed through indicator-window trend and oversold-recovery rules, cost sensitivity, allocation comparisons and passive-factor attribution. News/activity filters, seasonal effects, mechanical rebalancing events, liquidity-driven reversals, pairs/spreads and macro-regime-conditioned signals were not separately tested. Those are future extensions, not findings of this report. This long/cash study is not market-neutral statistical arbitrage.</p><p>A prospective next step would require a new preregistered release, frozen identities and weights, explicit future evaluation dates, and a practical costed policy if capital-share limits are to be enforced. Nothing in this report authorizes live trading.</p><h3>Audit and reproducibility</h3><p>The report is generated only from hash-bound saved aggregate inputs. Companion CSV/JSON retain full precision for all 16 portfolio, 8 control, 16 cap, 16 single-factor and 16 joint-factor rows in this stage. The three reports do not pool returns or substitute another period’s clock. Public verification checks source/output hashes, identities, costs, stage boundaries, exact saved weights and chart endpoints; reproducing original trades still requires the private parent-study inputs and engine.</p><p>The earlier study uses development 2017–2020, validation 2021–2023 and historical OOS 2024–2026-10-15. A separately preserved corrected-split experiment is inactive and is neither merged into these reports nor used for selection.</p><h3>Sources and project requirements</h3><p>The user-provided ClassProject.docx assignment brief supplies the seven-section research outline and required performance dimensions. It is a requirements reference, not a historical result source or authorization for new tests. Numerical sources are the repository’s four_portfolios_three_periods aggregates, four saved portfolio definitions, six strategy definitions, all-period attribution tables and audited baseline PNGs. See each stage manifest and the root report manifest for exact portable input/output SHA256 bindings.</p><div class="references"><h3>Methodology references</h3><p>[1] Moskowitz, T. J., Ooi, Y. H., and Pedersen, L. H. (2012). Time Series Momentum. Journal of Financial Economics 104, 228–250. Primary research page: https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum</p><p>[2] Sharpe, W. F. (1994). The Sharpe Ratio. Journal of Portfolio Management. Author text: https://web.stanford.edu/~wfsharpe/art/sr/sr.htm</p><p>[3] Lo, A. W. (2002). The Statistics of Sharpe Ratios. Financial Analysts Journal 58, 36–52. Author research page: https://alo.mit.edu/research-page/the-statistics-of-sharpe-ratios/</p><p>[4] Bailey, D. H., Borwein, J., López de Prado, M., and Zhu, Q. J. (2017). The Probability of Backtest Overfitting. Journal of Computational Finance. DOI 10.21314/JCF.2016.322. University repository: https://scholarworks.wmich.edu/math_pubs/42/</p><p>References motivate methodology and caution, not the numerical outcomes. We do not claim a paper replication, a computed PBO or CSCV estimate, or inferential confidence intervals.</p></div></div></section><footer>Trend Following and Mean Reversion ETF Portfolios · Historical research only · Standalone offline report · Same HTML source for PDF rendering</footer></body></html>',
    ]
    return "\n".join(piece for piece in pieces if piece) + "\n"


def write_csv(path: Path, rows: list[dict]):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(buffer.getvalue(), encoding="utf-8")


def build(root: Path, output: Path) -> dict:
    root, output = root.resolve(), output.resolve()
    data = load_inputs(root)
    if output.exists() and any(output.iterdir()):
        raise ValueError(
            "output directory is not empty; preserve completed reports and choose a new directory"
        )
    output.mkdir(parents=True, exist_ok=True)
    outputs = {}
    stage_records = []
    for sid, (directory, stem) in DIRECTORIES.items():
        destination = output / directory
        destination.mkdir()
        stage = stage_data(data, sid)
        (destination / "report.json").write_text(safe_json(stage), encoding="utf-8")
        for key in (
            "portfolio_rows",
            "control_rows",
            "cap_rows",
            "QQQ_single_factor_rows",
            "six_passive_factor_rows",
        ):
            write_csv(destination / f"{key}.csv", stage[key])
        write_csv(
            destination / "factor_diagnostic_rows.csv", stage["factor_diagnostic_rows"]
        )
        if sid == "historical_OOS":
            write_csv(
                destination / "baseline_active_strategy_correlation_rows.csv",
                stage["baseline_active_strategy_correlation_rows"],
            )
        (destination / f"{stem}.html").write_text(
            render_html(
                stage,
                (root / FIGURES / f"{sid}_baseline.png").read_bytes(),
                (root / FIGURES / "oos_strategy_correlations.png").read_bytes()
                if sid == "historical_OOS"
                else None,
            ),
            encoding="utf-8",
        )
        files = {p.name: sha(p) for p in sorted(destination.iterdir()) if p.is_file()}
        record = {
            "schema": SCHEMA,
            "stage": sid,
            "stage_bounds": list(STAGES[sid][:2]),
            "aggregate_only": True,
            "static_initial_wealth": True,
            "retrospective_OOS_examined": True,
            "same_HTML_source_for_PDF": True,
            "files": files,
            "input_hashes": data["source_hashes"],
        }
        (destination / "manifest.json").write_text(safe_json(record), encoding="utf-8")
        for path in sorted(destination.iterdir()):
            outputs[path.relative_to(output).as_posix()] = sha(path)
        stage_records.append(
            {
                "stage": sid,
                "directory": directory,
                "html": f"{directory}/{stem}.html",
                "manifest": f"{directory}/manifest.json",
            }
        )
    manifest = {
        "schema": SCHEMA,
        "aggregate_only": True,
        "public_input_hashes": data["source_hashes"],
        "stages": stage_records,
        "files": outputs,
        "PDF_generation": "Render the exact completed HTML with an approved offline renderer; add PDF hashes in a separate rendering manifest without rewriting these source reports.",
    }
    (output / "manifest.json").write_text(safe_json(manifest), encoding="utf-8")
    verify(root, output)
    return manifest


def safe_relative(name: str) -> bool:
    p = Path(name)
    return (
        not p.is_absolute()
        and ".." not in p.parts
        and not any(part.startswith(".") for part in p.parts)
    )


def verify(root: Path, output: Path) -> dict:
    manifest = read_json(output / "manifest.json")
    if (
        manifest.get("schema") != SCHEMA
        or manifest.get("aggregate_only") is not True
        or len(manifest.get("stages", [])) != 3
    ):
        raise ValueError("report output manifest schema mismatch")
    for name, digest in manifest["public_input_hashes"].items():
        if not safe_relative(name) or sha(root / name) != digest:
            raise ValueError("public input hash binding failed")
    for name, digest in manifest["files"].items():
        if not safe_relative(name) or sha(output / name) != digest:
            raise ValueError("output file hash binding failed")
        if name.endswith(".html"):
            text = (output / name).read_text(encoding="utf-8")
            if (
                re.search(
                    r"<script\b|(?:src|href)\s*=\s*[\"\'](?:https?:|//|file:)",
                    text,
                    re.I,
                )
                or "/Users/" in text
                or ".cache/" in text
            ):
                raise ValueError("report is not sanitized standalone HTML")
            expected_rasters = (
                2 if name.startswith(DIRECTORIES["historical_OOS"][0] + "/") else 1
            )
            if text.count("data:image/png;base64,") != expected_rasters:
                raise ValueError("embedded raster count differs from stage scope")
    for entry in manifest["stages"]:
        sid = entry["stage"]
        if sid not in DIRECTORIES or entry["directory"] != DIRECTORIES[sid][0]:
            raise ValueError("output stage mapping mismatch")
        report = read_json(output / entry["directory"] / "report.json")
        if report["stage"] != sid or any(
            row["stage"] != sid
            for field in (
                "portfolio_rows",
                "control_rows",
                "cap_rows",
                "QQQ_single_factor_rows",
                "six_passive_factor_rows",
            )
            for row in report[field]
        ):
            raise ValueError("cross-stage report leakage")
        if [
            len(report[field])
            for field in (
                "portfolio_rows",
                "control_rows",
                "cap_rows",
                "QQQ_single_factor_rows",
                "six_passive_factor_rows",
            )
        ] != [16, 8, 16, 16, 16]:
            raise ValueError("stage report rows incomplete")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--output-dir", type=Path, default=Path("final_reports"))
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Read source/output hashes only; no calculations or rendering",
    )
    args = parser.parse_args(argv)
    try:
        output = (
            args.output_dir
            if args.output_dir.is_absolute()
            else args.root / args.output_dir
        )
        (verify if args.verify_only else build)(args.root, output)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
