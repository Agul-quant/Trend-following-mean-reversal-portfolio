#!/usr/bin/env python3
"""Filter completed no-bond results to four unchanged active allocations.

This operation never opens numerical daily inputs or calls an optimizer.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path

SOURCE_SHA = "55010e543ec1af7210b24b4b2d2794d0b40c85e67541241ba058e97f85ae9239"
IDS = (
    "no_bond_daily_capped_max_sharpe",
    "no_bond_initial_capped_max_sharpe",
    "no_bond_uncapped_max_sharpe",
    "no_bond_equal_initial",
)
SYMBOLS = ("GDX", "FXI", "QQQ", "UNG", "FDN")
DROPPED = ("no_bond_weekly_capped_max_sharpe", "no_bond_monthly_capped_max_sharpe")


def select(source: dict) -> dict:
    if source.get("schema") != "five_etf_six_portfolio_comparison_v1" or source.get(
        "symbols"
    ) != list(SYMBOLS):
        raise ValueError("Unexpected completed source comparison")
    result = copy.deepcopy(source)
    result.update(
        schema="five_etf_four_portfolio_comparison_v1",
        source_report_sha256=SOURCE_SHA,
        selection_method="Exact saved-result subset; no refit or account run",
        dropped_portfolio_ids=list(DROPPED),
        method="Four unchanged static initial sleeve allocations; no rebalancing, transfers, optimizer or account rerun.",
        checkpoint_policy="Daily capital-share diagnostics across all four costs; initial weights also checked. Only Daily cap fit has fitted ongoing historical daily constraints.",
    )
    result["portfolios"] = [
        copy.deepcopy(next(p for p in source["portfolios"] if p["id"] == identifier))
        for identifier in IDS
    ]
    for key in (
        "portfolio_rows",
        "QQQ_single_factor_rows",
        "five_passive_factor_rows",
        "solver_summaries",
    ):
        result[key] = [
            copy.deepcopy(row) for row in source[key] if row["portfolio_id"] in IDS
        ]
    result["checkpoint_rows"] = [
        copy.deepcopy(row)
        for row in source["checkpoint_rows"]
        if row["portfolio_id"] in IDS and row["checkpoint_frequency"] == "daily"
    ]
    labels = list(IDS) + ["QQQ_buy_and_hold"]
    for record in result["portfolio_correlations"]:
        positions = [record["portfolio_ids"].index(label) for label in labels]
        record["matrix"] = [
            [record["matrix"][i][j] for j in positions] for i in positions
        ]
        record["portfolio_ids"] = labels.copy()
    result["source_hashes"]["archived_six_portfolio_report"] = SOURCE_SHA
    result["limitations"] = [
        "Retrospective OOS-fitted strategy/allocation choices; not an untouched portfolio test or live allocation.",
        "Four saved allocations retained unchanged; removed models remain only in the archived source comparison.",
        "Numerically best-found source fits, not globally certified; no new optimizer or account run.",
        "Daily cap constrains examined historical OOS daily shares at all four costs, not future or intraday shares.",
        "Initial cap applies only at the start, with no later enforcement or rebalancing; Uncapped and Equal initial also drift.",
        "Earlier-period daily concentration breaches are retained, not hidden, used to refit, or called clean validation.",
        "Same full-precision initial weights and original cash/cost conventions in all periods and costs.",
        "Cash remains 3% nominal ACT/365 event-compounded; undefined cash Sharpe is null, not zero.",
        "BND and standalone Maximum CAGR allocation are excluded from the active comparison; no trade counts inferred.",
    ]
    expected = {
        "portfolio_rows": 48,
        "control_rows": 24,
        "checkpoint_rows": 48,
        "QQQ_single_factor_rows": 48,
        "five_passive_factor_rows": 48,
        "strategy_correlations": 12,
        "portfolio_correlations": 12,
        "solver_summaries": 3,
    }
    if any(len(result[key]) != count for key, count in expected.items()):
        raise ValueError("Incomplete or duplicated source/active outcome scope")
    return result


def write_outputs(report: dict, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    for key in (
        "stage_summaries",
        "portfolio_rows",
        "control_rows",
        "checkpoint_rows",
        "QQQ_single_factor_rows",
        "five_passive_factor_rows",
    ):
        rows = report[key]
        with (directory / f"{key}.csv").open("x", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=list(dict.fromkeys(k for row in rows for k in row))
            )
            writer.writeheader()
            writer.writerows(rows)
    for key in ("strategy_correlations", "portfolio_correlations"):
        with (directory / f"{key}.csv").open("x", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "stage",
                    "slippage_bps_each_way",
                    "commission_bps_each_way",
                    "left",
                    "right",
                    "correlation",
                ],
            )
            writer.writeheader()
            for record in report[key]:
                names = record.get("symbols", record.get("portfolio_ids"))
                for i, left in enumerate(names):
                    for j, right in enumerate(names):
                        writer.writerow(
                            {
                                key: record[key]
                                for key in (
                                    "stage",
                                    "slippage_bps_each_way",
                                    "commission_bps_each_way",
                                )
                            }
                            | {
                                "left": left,
                                "right": right,
                                "correlation": record["matrix"][i][j],
                            }
                        )
    (directory / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n"
    )
    config = {
        "schema": "five_etf_four_static_portfolios_v1",
        "symbols": report["symbols"],
        "portfolios": report["portfolios"],
        "fit_stage": "historical_OOS",
        "fit_baseline_slippage_bps": 3,
        "source_report_sha256": SOURCE_SHA,
        "selection_method": report["selection_method"],
    }
    (directory / "portfolios.json").write_text(
        json.dumps(config, indent=2, allow_nan=False) + "\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        parser.error("Preserve previous attempts; choose a new output directory")
    raw = args.source_report.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        parser.error("Completed six-portfolio source report changed")
    report = select(json.loads(raw))
    write_outputs(report, args.output_dir)
    if args.source_report.read_bytes() != raw:
        raise ValueError("Source changed while filtering")
    print(
        json.dumps(
            {
                "completed": True,
                "retained_portfolios": 4,
                "performance_rows": 48,
                "no_optimizer_or_account_runs": True,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
