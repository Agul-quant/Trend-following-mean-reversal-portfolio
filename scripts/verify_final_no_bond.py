#!/usr/bin/env python3
"""Verify the four retained portfolios as exact subsets of the audited six-fit study.

Aggregate JSON only. This does not read daily arrays, rerun financial accounts,
fit a regression or optimize weights. The numerical oracle is inherited from the
unchanged SHA256-bound six-fit report; this audit checks the removal itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

SOURCE_SHA256 = "55010e543ec1af7210b24b4b2d2794d0b40c85e67541241ba058e97f85ae9239"
SYMBOLS = ("GDX", "FXI", "QQQ", "UNG", "FDN")
IDS = ("no_bond_daily_capped_max_sharpe", "no_bond_initial_capped_max_sharpe",
       "no_bond_uncapped_max_sharpe", "no_bond_equal_initial")
REMOVED_IDS = ("no_bond_weekly_capped_max_sharpe", "no_bond_monthly_capped_max_sharpe")
SOURCE_IDS = (IDS[0], *REMOVED_IDS, *IDS[1:])
COSTS = (1.0, 3.0, 10.0, 25.0)
STAGES = {"development": ("2017-01-01", "2020-12-31", 1007),
          "validation": ("2021-01-01", "2023-12-31", 753),
          "historical_OOS": ("2024-01-01", "2026-10-15", 700)}
PRIVATE_TEXT = re.compile(r"/Users/|/home/|/var/folders/|file://|[A-Za-z]:[\\/]Users[\\/]"
                          r"|(?:apikey|api_key|api-key)=[A-Za-z0-9]{8,}", re.I)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError(f"Nonfinite JSON constant {value}")))


def public_json(value):
    if isinstance(value, dict):
        for key, item in value.items():
            require(not PRIVATE_TEXT.search(str(key)), "Private public-JSON key")
            public_json(item)
    elif isinstance(value, list):
        require(not (len(value) > 128 and all(isinstance(x, (int, float)) for x in value)),
                "Serialized daily numeric array")
        for item in value:
            public_json(item)
    elif isinstance(value, float):
        require(math.isfinite(value), "Nonfinite public metric")
    elif isinstance(value, str):
        require(not PRIVATE_TEXT.search(value), "Private locator or credential")


def indexed(rows, identity="portfolio_id", frequency=False):
    result = {}
    for row in rows:
        cost = row["slippage_bps_each_way"]
        require(not isinstance(cost, bool) and isinstance(cost, (int, float))
                and math.isfinite(cost), "Invalid aggregate cost identity")
        key = (row["stage"], row[identity], float(cost))
        if frequency:
            key += (row["checkpoint_frequency"],)
        require(key not in result, "Duplicate aggregate identity")
        result[key] = row
    return result


def sliced_correlations(source):
    result = []
    labels = list(IDS) + ["QQQ_buy_and_hold"]
    for row in source:
        original = row["portfolio_ids"]
        require(original == list(SOURCE_IDS) + ["QQQ_buy_and_hold"], "Unexpected source correlation identity order")
        positions = [original.index(label) for label in labels]
        require(len(row["matrix"]) == 7 and all(len(x) == 7 for x in row["matrix"]), "Invalid source correlation dimensions")
        result.append({**row, "portfolio_ids": labels,
                       "matrix": [[row["matrix"][i][j] for j in positions] for i in positions]})
    return result


def verify_subset(report, source):
    public_json(report)
    require(source.get("schema") == "five_etf_six_portfolio_comparison_v1", "Incorrect archived source schema")
    require(report.get("schema") == "five_etf_four_portfolio_comparison_v1", "Incorrect active four-portfolio schema")
    require([p.get("id") for p in source.get("portfolios", [])] == list(SOURCE_IDS), "Incorrect archived six-fit definitions")
    expected_definitions = [p for p in source["portfolios"] if p["id"] in IDS]
    require(report.get("portfolios") == expected_definitions, "Active weights/definitions are not the exact saved subset")
    require(report.get("symbols") == source.get("symbols") == list(SYMBOLS), "BND or unexpected active symbol")
    for field in ("slippage_bps_each_way", "commission_bps_each_way", "initial_capital_each_stage",
                  "fit_stage", "fit_baseline_slippage_bps", "stage_summaries"):
        require(field in source and report.get(field) == source[field], f"Saved metadata changed: {field}")
    require(report["slippage_bps_each_way"] == list(COSTS)
            and report["commission_bps_each_way"] == 1
            and report["initial_capital_each_stage"] == 1000
            and report["fit_stage"] == "historical_OOS"
            and report["fit_baseline_slippage_bps"] == 3, "Incorrect study scope or costs")
    summaries = report["stage_summaries"]
    require([r.get("stage") for r in summaries] == list(STAGES), "Incomplete stage clocks")
    for row in summaries:
        start, end, count = STAGES[row["stage"]]
        require((row["scored_start"], row["scored_end"], row["observations"]) == (start, end, count),
                "Incorrect development/validation/OOS bounds")
        require(row["fresh_initial_capital"] == 1000 and row["elapsed_act365_years"] > 0,
                "Changed fresh-stage accounting")
    for definition in expected_definitions:
        weights = definition["initial_weights"]
        require(set(weights) == set(SYMBOLS) and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                                                   and math.isfinite(x) and x >= 0 for x in weights.values())
                and math.isclose(math.fsum(weights.values()), 1, abs_tol=1e-12, rel_tol=0), "Invalid five-ETF initial allocation")
        if definition["id"] in IDS[:2]:
            require(max(weights.values()) <= 1 / 3 + 1e-10, "Capped initial allocation changed")
    require(all(value == .2 for value in expected_definitions[-1]["initial_weights"].values()),
            "Equal initial must remain twenty percent each")
    desired = {(s, i, c) for s in STAGES for i in IDS for c in COSTS}
    counts = {}
    for field, identity in (("portfolio_rows", "portfolio_id"), ("control_rows", "control_id"),
                            ("checkpoint_rows", "portfolio_id"), ("QQQ_single_factor_rows", "portfolio_id"),
                            ("five_passive_factor_rows", "portfolio_id")):
        expected = [r for r in source[field]
                    if (identity == "control_id" or r["portfolio_id"] in IDS)
                    and (field != "checkpoint_rows" or r["checkpoint_frequency"] == "daily")]
        require(report.get(field) == expected, f"Saved row subset changed: {field}")
        rows = indexed(report[field], identity, field == "checkpoint_rows")
        keys = ({(s, i, c) for s in STAGES for i in ("QQQ_buy_and_hold", "matched_cash") for c in COSTS}
                if identity == "control_id" else
                {key + ("daily",) for key in desired} if field == "checkpoint_rows" else desired)
        require(set(rows) == keys, f"Incorrect active stage/configuration/cost scope: {field}")
        for key, row in rows.items():
            require(row["commission_bps_each_way"] == 1, "Incorrect row commission")
            if "observations" in row:
                require(row["observations"] == STAGES[key[0]][2], "Incorrect row observation count")
            if identity == "control_id" and key[1] == "matched_cash":
                require(row["cash_excess_sharpe"] is None, "Cash Sharpe must remain undefined")
            if field == "five_passive_factor_rows":
                require({name for name in row if name.startswith("beta_")} == {"beta_" + s for s in SYMBOLS},
                        "Incorrect active passive-factor universe")
            if field == "QQQ_single_factor_rows":
                require({name for name in row if name.startswith("beta_")} == {"beta_QQQ"},
                        "Incorrect QQQ single-factor universe")
        counts[field] = len(rows)
    require(report.get("strategy_correlations") == source["strategy_correlations"], "Five-strategy correlations changed")
    require(report.get("portfolio_correlations") == sliced_correlations(source["portfolio_correlations"]),
            "Portfolio correlation submatrix has wrong labels/indices/values")
    for field, keyname, labels in (("strategy_correlations", "symbols", list(SYMBOLS)),
                                   ("portfolio_correlations", "portfolio_ids", list(IDS) + ["QQQ_buy_and_hold"])):
        pairs = []
        for row in report[field]:
            pairs.append((row["stage"], float(row["slippage_bps_each_way"])))
            require(row[keyname] == labels and row["commission_bps_each_way"] == 1,
                    "Correlation labels or cost changed")
            matrix = row["matrix"]
            require(len(matrix) == 5 and all(len(r) == 5 for r in matrix), "Expected five-by-five matrix")
        require(len(pairs) == 12 and len(set(pairs)) == 12
                and set(pairs) == {(s, c) for s in STAGES for c in COSTS}, "Incomplete correlation stage/cost scope")
        counts[field] = len(pairs)
    solvers = [row for row in source["solver_summaries"] if row["portfolio_id"] in IDS]
    require(report.get("solver_summaries") == solvers
            and [row["portfolio_id"] for row in solvers] == list(IDS[:3]), "Changed or removed solver summary leaked into active report")
    require([row["cap_mode"] for row in solvers] == ["daily", "initial", "none"]
            and all(row["certified_global_optimum"] is False for row in solvers), "Incorrect active optimizer labels")
    inherited = report.get("source_hashes", {})
    require(all(inherited.get(name) == value for name, value in source.get("source_hashes", {}).items()),
            "Original source hash bindings changed")
    require(inherited.get("archived_six_portfolio_report") == SOURCE_SHA256, "Missing audited six-fit source binding")
    require(report.get("source_report_sha256") == SOURCE_SHA256, "Missing top-level archived report binding")
    require(report.get("dropped_portfolio_ids") == list(REMOVED_IDS), "Incorrect explicit removal metadata")
    require(report.get("selection_method") == "Exact saved-result subset; no refit or account run",
            "Final reduction must not claim a new financial run")
    require("no rebalancing" in report.get("method", "").lower(), "Incorrect static-wealth interpretation")
    limitations = " ".join(report.get("limitations", [])).lower()
    require("retrospective" in limitations and "not an untouched" in limitations
            and "best-found" in limitations and "not globally certified" in limitations,
            "Missing retrospective/best-found qualifications")
    return {"passed": True, "schema": "independent_final_no_bond_subset_audit_v1",
            "source_report_sha256": SOURCE_SHA256, "active_portfolio_ids": list(IDS),
            "symbols": list(SYMBOLS), "rows_verified": counts,
            "exact_saved_definition_metric_solver_subsets": True,
            "daily_only_cap_diagnostics": True, "exact_portfolio_correlation_submatrix": True,
            "unchanged_original_controls": True,
            "financial_metrics_recomputed_or_weights_refitted": False,
            "private_numerical_arrays_read": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--source-report", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    require(digest(args.source_report) == SOURCE_SHA256, "Archived six-fit source SHA256 changed")
    before = digest(args.report)
    result = verify_subset(read_json(args.report), read_json(args.source_report))
    require(digest(args.report) == before, "Active report changed during audit")
    result["active_report_sha256"] = before
    public_json(result)
    if args.output:
        require(not args.output.exists(), "Preserve existing audit output")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, sort_keys=True, indent=2, allow_nan=False)
            handle.write("\n")
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
