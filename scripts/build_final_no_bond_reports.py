#!/usr/bin/env python3
"""Render the exact four-portfolio subset of the completed no-bond study.

This is saved-result selection and presentation only, not an account, regression,
correlation or optimizer run. The completed six-comparison source stays unchanged.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
from pathlib import Path
import re

_UTIL_SPEC = importlib.util.spec_from_file_location(
    "no_bond_aggregate_report_utilities",
    Path(__file__).with_name("build_no_bond_reports.py"),
)
assert _UTIL_SPEC and _UTIL_SPEC.loader
P = importlib.util.module_from_spec(_UTIL_SPEC)
_UTIL_SPEC.loader.exec_module(P)

SCHEMA = "five_etf_four_portfolio_comparison_v1"
SOURCE_REPORT_SHA = "55010e543ec1af7210b24b4b2d2794d0b40c85e67541241ba058e97f85ae9239"
SOURCE_IDS = P.IDS
IDS = (SOURCE_IDS[0], SOURCE_IDS[3], SOURCE_IDS[4], SOURCE_IDS[5])
SYMBOLS, STAGES, COSTS = P.SYMBOLS, P.STAGES, P.COSTS
CONTROL_IDS, STAGE_LABELS = P.CONTROL_IDS, P.STAGE_LABELS
ALIASES = {pid: P.ALIASES[pid] for pid in IDS}
MODES = ("daily", "initial", "none")
SELECTION = "Exact saved-result subset; no refit or account run"


def correlation_subset(row: dict):
    """Pure selection of saved cells; no correlation is calculated."""
    names = list(IDS) + [CONTROL_IDS[0]]
    positions = [row["portfolio_ids"].index(name) for name in names]
    return {
        **row,
        "portfolio_ids": names,
        "matrix": [[row["matrix"][i][j] for j in positions] for i in positions],
    }


def validate(report: dict, source: dict, source_sha: str):
    P.validate(source)
    if report.get("schema") != SCHEMA or tuple(report.get("symbols", ())) != SYMBOLS:
        raise ValueError("unexpected active four-portfolio schema or symbols")
    if (
        report.get("source_report_sha256") != source_sha
        or report.get("selection_method") != SELECTION
    ):
        raise ValueError("saved-source binding or exact-subset policy mismatch")
    expected = {
        "portfolios": [r for r in source["portfolios"] if r["id"] in IDS],
        "stage_summaries": source["stage_summaries"],
        "control_rows": source["control_rows"],
        "strategy_correlations": source["strategy_correlations"],
        "portfolio_rows": [
            r for r in source["portfolio_rows"] if r["portfolio_id"] in IDS
        ],
        "checkpoint_rows": [
            r
            for r in source["checkpoint_rows"]
            if r["portfolio_id"] in IDS and r["checkpoint_frequency"] == "daily"
        ],
        "QQQ_single_factor_rows": [
            r for r in source["QQQ_single_factor_rows"] if r["portfolio_id"] in IDS
        ],
        "five_passive_factor_rows": [
            r for r in source["five_passive_factor_rows"] if r["portfolio_id"] in IDS
        ],
        "solver_summaries": [
            r for r in source["solver_summaries"] if r["portfolio_id"] in IDS
        ],
        "portfolio_correlations": [
            correlation_subset(r) for r in source["portfolio_correlations"]
        ],
    }
    for field, saved in expected.items():
        if report.get(field) != saved:
            raise ValueError(f"{field} is not the exact saved-result subset")
    if [r["id"] for r in report["portfolios"]] != list(IDS):
        raise ValueError("four active allocation identity/order mismatch")
    for label, digest in report.get("source_hashes", {}).items():
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", label) or not re.fullmatch(
            r"[0-9a-f]{64}", digest
        ):
            raise ValueError("source hashes contain nonportable locators")
    return report


def validate_figures(report: dict, directory: Path):
    receipt = P.read_json(directory / "figures_verification.json")
    if (
        receipt.get("schema") != "five_etf_four_portfolio_raster_verification_v1"
        or receipt.get("symbols") != list(SYMBOLS)
        or receipt.get("series_ids") != list(IDS) + [CONTROL_IDS[0]]
        or receipt.get("initial_capital") != 1000
        or receipt.get("baseline_commission_bps_each_way") != 1
        or receipt.get("baseline_slippage_bps_each_way") != 3
        or receipt.get("no_rebalancing") is not True
        or receipt.get("raster_only") is not True
        or receipt.get("daily_input_arrays_exported") is not False
        or receipt.get("private_input_locators_exported") is not False
        or receipt.get("all_released_guards_unchanged") is not True
        or P.count(receipt.get("guard_count")) < 413
    ):
        raise ValueError("active four figure scope mismatch")
    rows = receipt.get("stage_figures", [])
    if [r.get("stage") for r in rows] != list(STAGES):
        raise ValueError("figure stage identity/order mismatch")
    portfolios = P.index(report["portfolio_rows"])
    controls = P.index(report["control_rows"], "control_id")
    figures = {}
    for row in rows:
        stage = row["stage"]
        name = f"{stage}_baseline.png"
        if (
            row["file"] != name
            or row["series"] != 5
            or row["points_per_series"] != STAGES[stage][2] + 1
            or row["initial_value"] != 1000
            or row.get("all_daily_points_rendered") is not True
        ):
            raise ValueError("five-series figure identity mismatch")
        path = directory / name
        if P.sha(path) != row["sha256"]:
            raise ValueError("figure hash mismatch")
        checks = row.get("saved_aggregate_checks", [])
        if [r.get("series_id") for r in checks] != list(IDS) + [CONTROL_IDS[0]]:
            raise ValueError("figure active identities mismatch")
        for check in checks:
            entity = check["series_id"]
            reference = (
                controls[(stage, entity, 3.0)]
                if entity == CONTROL_IDS[0]
                else portfolios[(stage, entity, 3.0)]
            )
            for metric in ("terminal_equity_from_1000", "max_drawdown"):
                P.near(check[metric], reference[metric], "figure endpoint")
        figures[stage] = P.png_check(path)
    return figures, receipt


def common_scope(doc):
    doc.paragraph(
        "The active final basket is GDX, FXI, QQQ, UNG and FDN. We retain Daily cap fit, Initial cap fit, Uncapped fit and Equal initial from the completed no-bond calculation. Equal initial assigns 20% to each strategy. Every exact weight and saved performance value is unchanged; removing comparisons does not refit or improve a portfolio."
    )
    doc.paragraph(
        "Retrospective evidence only. The retained fitted allocations were selected using the examined 2024-01-01–2026-10-15 historical OOS sample. Replaying the same weights backward is hindsight-conditioned, not independent portfolio development or validation. The historical OOS label is not an untouched portfolio test, and no numerical best-found fit has a global-optimality certificate.",
        True,
    )


def weights_table(doc, report):
    definitions = {r["id"]: r for r in report["portfolios"]}
    doc.heading("Four retained initial allocations")
    doc.table(
        ["Strategy sleeve"] + [ALIASES[p] for p in IDS],
        [
            [s] + [P.fmt(definitions[p]["initial_weights"][s], True, 6) for p in IDS]
            for s in SYMBOLS
        ],
    )
    doc.paragraph(
        "Weights allocate strategy-account wealth, including idle cash, rather than permanent ETF holdings. Capital is assigned once and sleeve shares drift with their wealth. The same exact initial weights apply in every period and all four costs, with no cross-sleeve transfers or rebalance trades. The newly filtered report does not renormalize, round or substitute the saved weights."
    )


def methods(doc):
    doc.heading("Cap scope and methods")
    doc.paragraph(
        "Daily cap fit was fitted to initial weights and every historical OOS daily sleeve-capital share, capped at one-third across all four costs. That is a historical path constraint, not ongoing rebalancing or a guarantee for future or intraday shares. Initial cap fit applies one-third only to starting allocations; there is no later enforcement. Uncapped fit and Equal initial have no ongoing cap. Development/validation daily-share exceedances are retained rather than repaired."
    )
    doc.paragraph(
        "Portfolio wealth is V(c,t)=sum_i w(i)E(c,t,i), with E(c,0,i)=1 and V(c,0)=1. Daily returns are V(c,t)/V(c,t−1)−1, not constant-weight daily return averages. Each stage starts independently with $1,000. Only causal feature history carries; holdings, orders, streaks and wealth do not. Stages are not spliced."
    )
    doc.paragraph(
        "Cash is 3% nominal ACT/365 event-compounded, not 3% APY. Cash-excess Sharpe is sqrt(252) times mean daily net return minus matched cash return, divided by the sample standard deviation of that difference with ddof 1. It is not excess over buy-and-hold. Net volatility is the annualized sample standard deviation of net returns. CAGR uses each actual initial-to-terminal ACT/365 clock; maximum drawdown uses daily valuations and includes the initial balance, not intraday losses. Undefined statistics remain Undefined, not zero."
    )
    doc.paragraph(
        "The original causal daily indicators, native half-hour observations, three-trading-hour/seven-check confirmation, next eligible observed bar-open execution, distributions, corporate actions, embedded costs and paid terminal liquidation are unchanged. This presentation runs no execution engine, optimizer, regression or correlation calculation and infers no new combined trade count."
    )
    doc.paragraph(
        "Attribution uses cost-matched passive QQQ or all five passive ETF cash-excess return factors with an intercept. Annual arithmetic alpha is 252 times the daily intercept, not CAGR. Joint betas are conditional linear slopes, not allocation weights, causal effects or executed shorts. R squared is descriptive without significance or predictive-skill claims. Strategy correlations use daily net account returns including flat/cash periods; they are not passive factor correlations."
    )
    doc.paragraph(
        "Week-end and month-end cap comparisons are removed from the active comparison and preserved only in the archived six-comparison no-bond study. Older bond-inclusive calculations and class-project reports likewise remain unchanged archives. No bond ETF or standalone Maximum CAGR portfolio is included in this active final set. GDX remains a strategy sleeve."
    )


def render_stage(report: dict, stage: str, png: bytes):
    if stage not in STAGES:
        raise ValueError("unknown stage")
    doc = P.Document(STAGE_LABELS[stage] + " four retained no bond portfolios")
    portfolios = P.index(report["portfolio_rows"])
    controls = P.index(report["control_rows"], "control_id")
    checkpoints = P.index(report["checkpoint_rows"], frequency=True)
    singles = P.index(report["QQQ_single_factor_rows"])
    joints = P.index(report["five_passive_factor_rows"])
    strategies = P.correlation_index(report["strategy_correlations"])
    correlations = P.correlation_index(report["portfolio_correlations"])
    doc.heading("Executive summary")
    common_scope(doc)
    doc.table(
        [
            "Baseline allocation or control",
            "Cash excess Sharpe",
            "CAGR",
            "Daily max drawdown",
        ],
        [
            [
                ALIASES[p],
                P.fmt(portfolios[(stage, p, 3)]["cash_excess_sharpe"]),
                P.fmt(portfolios[(stage, p, 3)]["cagr"], True, 2),
                P.fmt(portfolios[(stage, p, 3)]["max_drawdown"], True, 2),
            ]
            for p in IDS
        ]
        + [
            [
                "QQQ buy and hold",
                P.fmt(controls[(stage, CONTROL_IDS[0], 3)]["cash_excess_sharpe"]),
                P.fmt(controls[(stage, CONTROL_IDS[0], 3)]["cagr"], True, 2),
                P.fmt(controls[(stage, CONTROL_IDS[0], 3)]["max_drawdown"], True, 2),
            ]
        ],
    )
    summary = next(r for r in report["stage_summaries"] if r["stage"] == stage)
    doc.paragraph(
        f"Scored {summary['scored_start']} to {summary['scored_end']}; {summary['observations']} daily return observations; {P.fmt(summary['elapsed_act365_years'], digits=12)} ACT365 years. Every stage starts fresh at $1,000. The fixed study endpoint remains 15 October 2026."
    )
    doc.parts.append(
        '<nav aria-label="Report sections"><a href="#weights">Weights</a> · <a href="#performance">Costs and performance</a> · <a href="#attribution">Alpha and beta</a> · <a href="#capital">Capital shares</a> · <a href="#correlations">Correlations</a></nav><section class="chapter" id="weights">'
    )
    weights_table(doc, report)
    methods(doc)
    doc.parts.append('</section><section class="chapter">')
    doc.heading("Baseline equity and daily drawdown")
    caption = "Four retained static initial allocations and cost-matched passive QQQ, each starting at $1,000. Baseline costs: 1-bp commission plus 3-bp slippage each way. Saved-path raster includes initial balance and paid terminal liquidation. Numerical daily series are not embedded; nearly overlapping paths retain separate styles."
    doc.md.extend(
        [
            f"![{stage} baseline equity and drawdown]({stage}_baseline.png)",
            "",
            caption,
            "",
        ]
    )
    doc.parts.append(
        '<figure><img alt="Four retained no-bond portfolios and passive QQQ baseline equity and drawdown" src="data:image/png;base64,'
        + base64.b64encode(png).decode("ascii")
        + '"><figcaption>'
        + P.html.escape(caption)
        + '</figcaption></figure></section><section class="chapter">'
    )
    doc.heading("All four execution cost scenarios", identifier="performance")
    doc.paragraph(
        "Every purchase and sale pays 1-bp commission plus one-way slippage of 1, 3, 10 or 25 bps. Baseline is 3-bp slippage, or 4 bps total per side. Passive QQQ and cash controls are matched to the stage and cost. No period or cost scenario triggers refitting or reselection."
    )
    for cost in COSTS:
        doc.heading(f"{int(cost)} bp slippage each way", 3)
        rows = [(ALIASES[p], portfolios[(stage, p, cost)]) for p in IDS] + [
            ("QQQ buy and hold", controls[(stage, CONTROL_IDS[0], cost)]),
            ("Matched cash", controls[(stage, CONTROL_IDS[1], cost)]),
        ]
        doc.table(
            [
                "Allocation or control",
                "Sharpe",
                "CAGR",
                "Net volatility",
                "Daily max DD",
                "Final $1,000",
            ],
            [
                [
                    label,
                    P.fmt(row["cash_excess_sharpe"]),
                    P.fmt(row["cagr"], True, 2),
                    P.fmt(row["annualized_return_volatility"], True, 2),
                    P.fmt(row["max_drawdown"], True, 2),
                    "$" + P.fmt(row["terminal_equity_from_1000"], digits=2),
                ]
                for label, row in rows
            ],
        )
    doc.parts.append('</section><section class="chapter">')
    doc.heading("QQQ single factor attribution", identifier="attribution")
    doc.paragraph(
        "Each row uses the same-stage, same-cost passive QQQ factor. Alpha is arithmetic annualized percent; beta and R squared are descriptive, not significance or causal-skill evidence."
    )
    doc.table(
        ["Slippage bp", "Allocation", "Alpha annual", "QQQ beta", "R squared"],
        [
            [
                str(int(cost)),
                ALIASES[p],
                P.fmt(singles[(stage, p, cost)]["alpha_annual_arithmetic"], True, 2),
                P.fmt(singles[(stage, p, cost)]["beta_QQQ"], digits=4),
                P.fmt(singles[(stage, p, cost)]["r_squared"], True, 2),
            ]
            for cost, p in P.itertools.product(COSTS, IDS)
        ],
    )
    doc.parts.append('</section><section class="chapter">')
    doc.heading("Joint five passive ETF factor attribution")
    for cost in COSTS:
        doc.heading(f"{int(cost)} bp slippage each way", 3)
        doc.table(
            ["Allocation"]
            + [s + " beta" for s in SYMBOLS]
            + ["Alpha annual", "R squared"],
            [
                [ALIASES[p]]
                + [
                    P.fmt(joints[(stage, p, cost)][f"beta_{s}"], digits=4)
                    for s in SYMBOLS
                ]
                + [
                    P.fmt(joints[(stage, p, cost)]["alpha_annual_arithmetic"], True, 2),
                    P.fmt(joints[(stage, p, cost)]["r_squared"], True, 2),
                ]
                for p in IDS
            ],
        )
    doc.parts.append('</section><section class="chapter">')
    doc.heading("Observed daily capital share diagnostics", identifier="capital")
    doc.paragraph(
        "A breach day means at least one sleeve exceeds one-third at that daily valuation, not the number of offending sleeves. The daily-cap fit has a historical OOS path constraint; the other three comparisons have no promised ongoing daily limit. This table does not trigger trades or remove unfavorable replay outcomes."
    )
    doc.table(
        [
            "Slippage bp",
            "Allocation",
            "Daily observations",
            "Peak daily share",
            "Days above one third",
        ],
        [
            [
                str(int(cost)),
                ALIASES[p],
                str(
                    P.count(
                        (row := checkpoints[(stage, p, cost, "daily")])[
                            "checkpoint_count"
                        ]
                    )
                ),
                P.fmt(row["max_daily_capital_share"], True, 4),
                str(P.count(row["daily_breach_days"])),
            ]
            for cost, p in P.itertools.product(COSTS, IDS)
        ],
    )
    doc.parts.append('</section><section class="chapter">')
    doc.heading("Active strategy and portfolio correlations", identifier="correlations")
    doc.paragraph(
        "Matrices use same-stage daily net account returns including cash/flat periods, at the stated costs. The five-series portfolio matrix adds matched passive QQQ to the four retained allocations. High correlations between related fitted allocations may reflect nearly coincident paths. These are saved sample descriptions, not future diversification guarantees or a pairs-trading strategy test."
    )
    for cost in COSTS:
        doc.heading(f"{int(cost)} bp slippage strategy correlations", 3)
        matrix = strategies[(stage, cost)]["matrix"]
        doc.table(
            ["Strategy"] + list(SYMBOLS),
            [
                [symbol] + [P.fmt(v, digits=4) for v in matrix[i]]
                for i, symbol in enumerate(SYMBOLS)
            ],
        )
        doc.heading(f"{int(cost)} bp slippage portfolio correlations", 3)
        labels = [ALIASES[p] for p in IDS] + ["QQQ buy and hold"]
        matrix = correlations[(stage, cost)]["matrix"]
        doc.table(
            ["Portfolio"] + labels,
            [
                [label] + [P.fmt(v, digits=4) for v in matrix[i]]
                for i, label in enumerate(labels)
            ],
        )
    doc.parts.append("</section>")
    return doc.finish()


def overview(report):
    rows, controls = (
        P.index(report["portfolio_rows"]),
        P.index(report["control_rows"], "control_id"),
    )
    table = P.markdown_table(
        ["Allocation or control", "Cash excess Sharpe", "CAGR", "Daily max drawdown"],
        [
            [
                ALIASES[p],
                P.fmt(rows[("historical_OOS", p, 3)]["cash_excess_sharpe"]),
                P.fmt(rows[("historical_OOS", p, 3)]["cagr"], True, 2),
                P.fmt(rows[("historical_OOS", p, 3)]["max_drawdown"], True, 2),
            ]
            for p in IDS
        ]
        + [
            [
                "QQQ buy and hold",
                P.fmt(
                    controls[("historical_OOS", CONTROL_IDS[0], 3)][
                        "cash_excess_sharpe"
                    ]
                ),
                P.fmt(controls[("historical_OOS", CONTROL_IDS[0], 3)]["cagr"], True, 2),
                P.fmt(
                    controls[("historical_OOS", CONTROL_IDS[0], 3)]["max_drawdown"],
                    True,
                    2,
                ),
            ]
        ],
    )
    return "\n".join(
        [
            "# Four retained portfolios without bond ETFs",
            "",
            "Active basket: GDX, FXI, QQQ, UNG and FDN. Retained allocations: Daily cap fit, Initial cap fit, Uncapped fit and Equal initial (20% per sleeve). All saved weights and retained outcomes are unchanged; no refit, account run or rebalancing occurred for this removal.",
            "",
            "## Read the reports",
            "",
            "- [Development 2017–2020](development.html)",
            "- [Validation 2021–2023](validation.html)",
            "- [Historical OOS 2024–15 October 2026](historical_OOS.html)",
            "- [Combined full tables](combined_report.md)",
            "",
            "Each offline HTML includes a five-series baseline equity/drawdown raster, all four costs, matched QQQ/cash, QQQ and joint-five-ETF alpha/beta, daily capital-share diagnostics and strategy/portfolio correlations. Numerical daily paths are not embedded.",
            "",
            "## Historical OOS baseline comparison",
            "",
            table,
            "",
            "Baseline costs: 1-bp commission plus 3-bp slippage each way. Cash is 3% nominal ACT/365 event-compounded. Weights mix static initial sleeve wealth; they are not daily rebalanced returns. The Daily cap fit is a historical OOS daily-share constraint only; Initial cap fit has no cap after initialization.",
            "",
            "All retained fitted weights use already examined historical OOS. Backward replay does not create untouched portfolio development or validation evidence. This is retrospective research, not a live allocation or globally certified optimum.",
            "",
            "Weekly and Monthly cap fits are inactive and retained only in the [archived six-comparison study](../no_bond_portfolios/README.md). Original bond-inclusive class-project reports remain unchanged archives. No bond ETF or standalone Maximum CAGR portfolio is active.",
            "",
        ]
    )


def build(report_path: Path, figures_dir: Path, output: Path, source_report: Path):
    report_path, figures_dir, output, source_report = (
        p.resolve() for p in (report_path, figures_dir, output, source_report)
    )
    if P.sha(source_report) != SOURCE_REPORT_SHA:
        raise ValueError("completed six-comparison source hash changed")
    report = validate(
        P.read_json(report_path), P.read_json(source_report), P.sha(source_report)
    )
    figures, receipt = validate_figures(report, figures_dir)
    if receipt.get("saved_report_sha256") != P.sha(report_path):
        raise ValueError("figure saved report hash mismatch")
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory is not empty; preserve completed attempts")
    rendered = {stage: render_stage(report, stage, figures[stage]) for stage in STAGES}
    for _, standalone in rendered.values():
        if (
            re.search(
                r"<script\b|(?:src|href)\s*=\s*[\"'](?:https?:|//|file:)",
                standalone,
                re.I,
            )
            or "/Users/" in standalone
            or ".cache/" in standalone
            or standalone.count("data:image/png;base64,") != 1
        ):
            raise ValueError("unsafe or non-offline HTML output")
    output.mkdir(parents=True, exist_ok=True)
    (output / "README.md").write_text(overview(report), encoding="utf-8")
    combined = []
    for stage, (markdown, standalone) in rendered.items():
        (output / f"{stage}.html").write_text(standalone, encoding="utf-8")
        (output / f"{stage}_baseline.png").write_bytes(figures[stage])
        combined.append(markdown)
    (output / "combined_report.md").write_text(
        "\n\n---\n\n".join(combined), encoding="utf-8"
    )
    manifest = {
        "schema": "five_etf_four_portfolio_report_render_v1",
        "aggregate_only": True,
        "no_account_or_optimizer_run": True,
        "source_report_sha256": P.sha(report_path),
        "archived_six_report_sha256": P.sha(source_report),
        "figure_receipt_sha256": P.sha(figures_dir / "figures_verification.json"),
        "portfolio_ids": list(IDS),
        "symbols": list(SYMBOLS),
        "files": {p.name: P.sha(p) for p in sorted(output.iterdir()) if p.is_file()},
    }
    (output / "render_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--figures-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--source-report",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "reports/no_bond_portfolios/report.json",
    )
    args = parser.parse_args(argv)
    try:
        build(args.report, args.figures_dir, args.output_dir, args.source_report)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
