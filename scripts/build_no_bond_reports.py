#!/usr/bin/env python3
"""Create offline reports from independently audited no-bond aggregate results.

No market data, account arrays, selection, optimization or regression is run.
Completed or failed output directories are preserved; choose a fresh directory.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import itertools
import json
import math
from pathlib import Path
import re
import struct
import zlib

SCHEMA = "five_etf_six_portfolio_comparison_v1"
SYMBOLS = ("GDX", "FXI", "QQQ", "UNG", "FDN")
MODES = ("daily", "weekly", "monthly", "initial", "none")
IDS = tuple(
    "no_bond_" + suffix
    for suffix in (
        "daily_capped_max_sharpe",
        "weekly_capped_max_sharpe",
        "monthly_capped_max_sharpe",
        "initial_capped_max_sharpe",
        "uncapped_max_sharpe",
        "equal_initial",
    )
)
ALIASES = dict(
    zip(
        IDS,
        (
            "Daily cap fit",
            "Weekly cap fit",
            "Monthly cap fit",
            "Initial cap fit",
            "Uncapped fit",
            "Equal initial",
        ),
    )
)
COSTS = (1.0, 3.0, 10.0, 25.0)
FREQUENCIES = ("daily", "weekly", "monthly")
CONTROL_IDS = ("QQQ_buy_and_hold", "matched_cash")
STAGES = {
    "development": ("2017-01-01", "2020-12-31", 1007),
    "validation": ("2021-01-01", "2023-12-31", 753),
    "historical_OOS": ("2024-01-01", "2026-10-15", 700),
}
STAGE_LABELS = {
    "development": "Development 2017–2020",
    "validation": "Validation 2021–2023",
    "historical_OOS": "Historical OOS 2024–15 October 2026",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda x: (_ for _ in ()).throw(
            ValueError(f"nonfinite JSON {x}")
        ),
    )


def number(value, *, nullable=False):
    if value is None and nullable:
        return None
    if value is None or isinstance(value, bool):
        raise ValueError("metric must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("metric must be a finite number") from error
    if not math.isfinite(result):
        raise ValueError("metric must be finite")
    return result


def count(value):
    result = number(value)
    if result < 0 or result != int(result):
        raise ValueError("count must be a nonnegative integer")
    return int(result)


def near(left, right, name):
    if not math.isclose(number(left), number(right), abs_tol=1e-10, rel_tol=1e-10):
        raise ValueError(f"{name} mismatch")


def identity(row, entity="portfolio_id", *, frequency=False):
    result = (row["stage"], row[entity], number(row["slippage_bps_each_way"]))
    return result + (row["checkpoint_frequency"],) if frequency else result


def index(rows, entity="portfolio_id", *, frequency=False):
    result = {}
    for row in rows:
        key = identity(row, entity, frequency=frequency)
        if key in result:
            raise ValueError("duplicate aggregate identity")
        result[key] = row
    return result


def correlation_index(rows):
    result = {}
    for row in rows:
        key = (row["stage"], number(row["slippage_bps_each_way"]))
        if key in result:
            raise ValueError("duplicate correlation stage/cost identity")
        result[key] = row
    return result


def validate(report: dict) -> dict:
    """Reject scope/identity errors without touching numerical daily inputs."""
    if report.get("schema") != SCHEMA or tuple(report.get("symbols", ())) != SYMBOLS:
        raise ValueError("unexpected five-ETF six-portfolio schema or symbols")
    definitions = report.get("portfolios", [])
    if [r.get("id") for r in definitions] != list(IDS):
        raise ValueError("six new portfolio identity/order mismatch")
    for position, definition in enumerate(definitions):
        weights = definition["initial_weights"]
        if set(weights) != set(SYMBOLS):
            raise ValueError(
                "active weights must contain exactly five non-bond sleeves"
            )
        values = [number(weights[s]) for s in SYMBOLS]
        if min(values) < 0 or not math.isclose(sum(values), 1, abs_tol=1e-12):
            raise ValueError("invalid saved initial weights")
        if position < 4 and max(values) > 1 / 3 + 1e-10:
            raise ValueError("capped fit violates its initial one-third limit")
        if position == 5 and any(v != 0.2 for v in values):
            raise ValueError("equal initial comparator must be exactly 20 percent each")
    summaries = report.get("stage_summaries", [])
    if [r.get("stage") for r in summaries] != list(STAGES):
        raise ValueError("stage summaries incomplete or reordered")
    years = {}
    for row in summaries:
        stage = row["stage"]
        start, end, observations = STAGES[stage]
        if (row["scored_start"], row["scored_end"], row["observations"]) != (
            start,
            end,
            observations,
        ):
            raise ValueError("stage boundary or daily observation count changed")
        if number(row["fresh_initial_capital"]) != 1000:
            raise ValueError("stage must start independently with 1000")
        years[stage] = number(row["elapsed_act365_years"])
        if years[stage] <= 0:
            raise ValueError("invalid ACT365 clock")
    expected = set(itertools.product(STAGES, IDS, COSTS))
    control_expected = set(itertools.product(STAGES, CONTROL_IDS, COSTS))
    for field, entity, keys in (
        ("portfolio_rows", "portfolio_id", expected),
        ("control_rows", "control_id", control_expected),
    ):
        rows = index(report.get(field, []), entity)
        if set(rows) != keys:
            raise ValueError(f"{field} incomplete or unknown identity")
        for (stage, entity_id, _), row in rows.items():
            if (
                number(row["commission_bps_each_way"]) != 1
                or count(row["observations"]) != STAGES[stage][2]
            ):
                raise ValueError("metric commission or observation count changed")
            near(row["elapsed_act365_years"], years[stage], "stage clock")
            wealth = number(row["terminal_equity_from_1000"])
            if wealth <= 0 or not -1 < number(row["max_drawdown"]) <= 0:
                raise ValueError("invalid wealth or drawdown")
            near(row["terminal_normalized_equity"], wealth / 1000, "terminal units")
            near(row["cagr"], (wealth / 1000) ** (1 / years[stage]) - 1, "CAGR")
            sharpe = number(row["cash_excess_sharpe"], nullable=True)
            if entity_id == "matched_cash" and sharpe is not None:
                raise ValueError("matched cash Sharpe must remain undefined")
            for metric in (
                "annualized_return_volatility",
                "annualized_cash_excess_volatility",
            ):
                if number(row[metric]) < 0:
                    raise ValueError("negative volatility")
    checkpoints = index(report.get("checkpoint_rows", []), frequency=True)
    if set(checkpoints) != {
        key + (frequency,) for key in expected for frequency in FREQUENCIES
    }:
        raise ValueError("216 checkpoint rows incomplete or unknown identity")
    for (stage, _, _, frequency), row in checkpoints.items():
        near(row["cap_fraction"], 1 / 3, "cap fraction")
        if number(row["commission_bps_each_way"]) != 1:
            raise ValueError("checkpoint commission changed")
        checks, breach, daily, between = (
            count(row[field])
            for field in (
                "checkpoint_count",
                "checkpoint_breach_days",
                "daily_breach_days",
                "between_checkpoint_breach_days",
            )
        )
        if (
            not 0 < checks <= STAGES[stage][2]
            or breach > checks
            or daily > STAGES[stage][2]
            or breach + between != daily
        ):
            raise ValueError("invalid checkpoint or breach counts")
        peak, daily_peak = (
            number(row["max_checkpoint_capital_share"]),
            number(row["max_daily_capital_share"]),
        )
        if not 0 < peak <= daily_peak + 1e-10 <= 1 + 1e-10:
            raise ValueError("invalid checkpoint or daily capital share")
        if not isinstance(row["initial_cap_pass_diagnostic"], bool) or not isinstance(
            row["checkpoint_cap_pass_diagnostic"], bool
        ):
            raise ValueError("checkpoint flags must be boolean")
        if row["checkpoint_cap_pass_diagnostic"] != (breach == 0):
            raise ValueError("checkpoint pass flag mismatch")
        if frequency == "daily" and (checks != STAGES[stage][2] or between != 0):
            raise ValueError("daily checkpoint count or between-days mismatch")
    for key in expected:
        reference = checkpoints[key + ("daily",)]
        for frequency in FREQUENCIES[1:]:
            row = checkpoints[key + (frequency,)]
            near(
                row["max_daily_capital_share"],
                reference["max_daily_capital_share"],
                "same-path daily share",
            )
            if row["daily_breach_days"] != reference["daily_breach_days"]:
                raise ValueError("same-path daily breach counts disagree")
    for field, factors in (
        ("QQQ_single_factor_rows", ("QQQ",)),
        ("five_passive_factor_rows", SYMBOLS),
    ):
        rows = index(report.get(field, []))
        if set(rows) != expected:
            raise ValueError("attribution rows incomplete or unknown identity")
        for (stage, _, _), row in rows.items():
            if (
                count(row["observations"]) != STAGES[stage][2]
                or number(row["commission_bps_each_way"]) != 1
            ):
                raise ValueError("attribution stage or commission changed")
            near(
                row["alpha_annual_arithmetic"],
                252 * number(row["alpha_daily"]),
                "arithmetic alpha scaling",
            )
            if not 0 <= number(row["r_squared"]) <= 1:
                raise ValueError("invalid attribution R squared")
            for factor in factors:
                number(row[f"beta_{factor}"])
            if "beta_BND" in row:
                raise ValueError("bond factor leaked into active attribution")
    solvers = report.get("solver_summaries", [])
    if isinstance(solvers, dict):
        solvers = list(solvers.values())
    if len(solvers) != 5 or {r.get("portfolio_id") for r in solvers} != set(IDS[:5]):
        raise ValueError("five new fitted solver summaries required")
    for row in solvers:
        position = IDS.index(row["portfolio_id"])
        mode = row.get("cap_mode")
        if mode != MODES[position] or row.get("certified_global_optimum") is not False:
            raise ValueError("solver mode or global certificate scope mismatch")
        number(row["baseline_cash_excess_sharpe"])
        if count(row["seed"]) != 1729:
            raise ValueError("optimizer seed changed")
    expected_correlation = set(itertools.product(STAGES, COSTS))
    for field, entity_field, names in (
        ("strategy_correlations", "symbols", SYMBOLS),
        ("portfolio_correlations", "portfolio_ids", IDS + (CONTROL_IDS[0],)),
    ):
        rows = correlation_index(report.get(field, []))
        if set(rows) != expected_correlation:
            raise ValueError("correlation stage/cost records incomplete")
        for row in rows.values():
            if (
                tuple(row.get(entity_field, ())) != names
                or number(row["commission_bps_each_way"]) != 1
            ):
                raise ValueError("correlation entity or cost mapping changed")
            matrix = row["matrix"]
            if len(matrix) != len(names) or any(
                len(values) != len(names) for values in matrix
            ):
                raise ValueError("correlation matrix dimensions mismatch")
            for i, values in enumerate(matrix):
                for j, value in enumerate(values):
                    value = number(value, nullable=True)
                    opposite = number(matrix[j][i], nullable=True)
                    if (value is None) != (opposite is None):
                        raise ValueError("correlation undefined symmetry mismatch")
                    if value is not None:
                        if abs(value) > 1 + 1e-10:
                            raise ValueError("correlation outside unit interval")
                        near(value, opposite, "correlation symmetry")
                        if i == j:
                            near(value, 1, "correlation diagonal")
    for label, digest in report.get("source_hashes", {}).items():
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", label) or not re.fullmatch(
            r"[0-9a-f]{64}", digest
        ):
            raise ValueError(
                "source hashes must use logical names without private locators"
            )
    return report


def png_check(path: Path):
    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("figure is not a PNG")
    offset, dimensions = 8, None
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
            raise ValueError("unsafe PNG metadata")
        if kind == b"IHDR":
            dimensions = struct.unpack(">II", payload[:8])
        offset += length + 12
        if kind == b"IEND":
            break
    if offset != len(raw) or dimensions is None or min(dimensions) <= 0:
        raise ValueError("invalid PNG framing")
    return raw


def validate_figures(report: dict, directory: Path):
    """Receipt details are aggregate endpoints and hashes, never daily arrays."""
    receipt_path = directory / "figures_verification.json"
    receipt = read_json(receipt_path)
    if (
        receipt.get("baseline_commission_bps_each_way") != 1
        or receipt.get("baseline_slippage_bps_each_way") != 3
        or receipt.get("raster_only") is not True
        or receipt.get("daily_input_arrays_exported") is not False
        or receipt.get("private_input_locators_exported") is not False
    ):
        raise ValueError("no-bond baseline figure scope mismatch")
    if (
        receipt.get("schema") != "five_etf_six_portfolio_raster_verification_v1"
        or receipt.get("series_ids") != list(IDS) + [CONTROL_IDS[0]]
        or receipt.get("symbols") != list(SYMBOLS)
        or receipt.get("initial_capital") != 1000
        or receipt.get("no_rebalancing") is not True
        or receipt.get("all_released_guards_unchanged") is not True
        or count(receipt.get("guard_count")) < 413
    ):
        raise ValueError("no-bond figure identity or unchanged guard scope mismatch")
    figures = receipt.get("stage_figures", [])
    if [r.get("stage") for r in figures] != list(STAGES):
        raise ValueError("figure stage identity/order mismatch")
    portfolios = index(report["portfolio_rows"])
    controls = index(report["control_rows"], "control_id")
    result = {}
    for row in figures:
        stage = row["stage"]
        name = f"{stage}_baseline.png"
        if (
            row["file"] != name
            or row["series"] != 7
            or row["points_per_series"] != STAGES[stage][2] + 1
            or row["initial_value"] != 1000
            or row.get("all_daily_points_rendered") is not True
        ):
            raise ValueError("seven-series no-bond figure identity mismatch")
        path = directory / name
        if sha(path) != row["sha256"]:
            raise ValueError("figure hash mismatch")
        checks = row.get("saved_aggregate_checks", [])
        if len(checks) != 7 or [r.get("series_id") for r in checks] != list(IDS) + [
            CONTROL_IDS[0]
        ]:
            raise ValueError("figure active series identities mismatch")
        for check in checks:
            entity = check["series_id"]
            source = (
                controls[(stage, entity, 3.0)]
                if entity == CONTROL_IDS[0]
                else portfolios[(stage, entity, 3.0)]
            )
            for metric in ("terminal_equity_from_1000", "max_drawdown"):
                near(check[metric], source[metric], "figure endpoint")
        result[stage] = png_check(path)
    return result, receipt


def fmt(value, percent=False, digits=3):
    if value is None:
        return "Undefined"
    return f"{number(value) * (100 if percent else 1):,.{digits}f}" + (
        "%" if percent else ""
    )


def markdown_table(headers, rows):
    def escape(value):
        return str(value).replace("|", "\\|").replace("\n", " ")

    return "\n".join(
        [
            "| " + " | ".join(map(escape, headers)) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
        + ["| " + " | ".join(map(escape, row)) + " |" for row in rows]
    )


def html_table(headers, rows):
    def cells(tag, row):
        return "".join(f"<{tag}>{html.escape(str(value))}</{tag}>" for value in row)

    return (
        '<div class="table-scroll"><table><thead><tr>'
        + cells("th", headers)
        + "</tr></thead><tbody>"
        + "".join("<tr>" + cells("td", row) + "</tr>" for row in rows)
        + "</tbody></table></div>"
    )


CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; } body { max-width: 1100px; margin: 0 auto; padding: 38px; color: #171717; background: white; font: 15px/1.48 Arial,Helvetica,sans-serif; }
h1,h2,h3,h4 { color: #111; line-height: 1.16; break-after: avoid; } h1 { font-size: 43px; margin: 14px 0 24px; letter-spacing: -.9px; } h2 { font-size: 29px; margin: 36px 0 16px; } h3 { font-size: 21px; margin: 26px 0 13px; } h4 { font-size: 16px; }
p { margin: 12px 0; } .eyebrow,.caption { color: #666; font-size: 12px; } .lead { font-size: 19px; } .warning { border-left: 3px solid #888; padding-left: 15px; margin: 22px 0; }
.table-scroll { width: 100%; overflow-x: auto; } table { width: 100%; min-width: 620px; border-collapse: collapse; margin: 14px 0 22px; font-size: 12px; font-variant-numeric: tabular-nums; } th,td { border-bottom: 1px solid #ddd; padding: 7px 6px; text-align: right; vertical-align: top; } th:first-child,td:first-child { text-align: left; } th { color: #111; background: #f4f4f4; border-top: 1px solid #ccc; } tr { break-inside: avoid; } thead { display: table-header-group; }
figure { margin: 20px 0; break-inside: avoid; } img { width: 100%; height: auto; display: block; } figcaption { color: #666; font-size: 12px; margin-top: 8px; } a { color: #222; } nav { margin: 22px 0; } footer { border-top: 1px solid #ddd; margin-top: 30px; padding-top: 12px; color: #666; font-size: 11px; }
@media(max-width:600px) { body { padding: 22px 16px; } h1 { font-size: 32px; } h2 { font-size: 25px; } }
@media print { body { padding: 0; font-size: 10pt; line-height: 1.34; } h1 { font-size: 29pt; } h2 { font-size: 20pt; } h3 { font-size: 13pt; } .lead { font-size: 12pt; } .chapter { break-before: page; } .table-scroll { overflow: visible; } table { min-width: 0; font-size: 8pt; line-height: 1.2; } th,td { padding: 4px; } a { text-decoration: none; } }
"""


class Document:
    def __init__(self, title):
        self.md = ["# " + title, ""]
        self.parts = [
            '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
            "<title>"
            + html.escape(title)
            + "</title><style>"
            + CSS
            + '</style></head><body><header><p class="eyebrow">Trend Following and Mean Reversion ETF Portfolios</p><h1>'
            + html.escape(title)
            + "</h1></header>",
        ]

    def heading(self, text, level=2, identifier=None):
        self.md.extend(["#" * level + " " + text, ""])
        anchor = f' id="{identifier}"' if identifier else ""
        self.parts.append(f"<h{level}{anchor}>{html.escape(text)}</h{level}>")

    def paragraph(self, text, warning=False):
        self.md.extend([text, ""])
        self.parts.append(
            "<p"
            + (' class="warning"' if warning else "")
            + ">"
            + html.escape(text)
            + "</p>"
        )

    def table(self, headers, rows):
        self.md.extend([markdown_table(headers, rows), ""])
        self.parts.append(html_table(headers, rows))

    def figure(self, stage, png):
        caption = "Six new static initial allocations and cost-matched passive QQQ, each starting at $1,000. Baseline costs are 1-bp commission plus 3-bp slippage each way. Saved-path raster includes initial balance and paid terminal liquidation; no numerical daily series is embedded."
        self.md.extend(
            [
                f"![{stage} baseline equity and daily drawdown]({stage}_baseline.png)",
                "",
                caption,
                "",
            ]
        )
        self.parts.append(
            '<figure><img alt="Six no-bond portfolios and passive QQQ baseline equity and daily drawdown" src="data:image/png;base64,'
            + base64.b64encode(png).decode("ascii")
            + '"><figcaption>'
            + html.escape(caption)
            + "</figcaption></figure>"
        )

    def finish(self):
        self.parts.append(
            "<footer>Historical research only · New five-ETF comparison · Standalone offline HTML · No trading authorization</footer></body></html>"
        )
        return "\n".join(self.md) + "\n", "\n".join(self.parts) + "\n"


def common_scope(doc: Document):
    doc.paragraph(
        "The final strategy universe is GDX, FXI, QQQ, UNG and FDN. All bond ETFs are excluded from the active set. All five optimized portfolios were refitted using the examined 2024-01-01–2026-10-15 historical OOS window at baseline costs; Equal initial is a newly defined 20% allocation to each sleeve. These are six new allocation identities, not renormalized replacements silently substituted into old results."
    )
    doc.paragraph(
        "Retrospective evidence only. Strategy selection, ETF pruning and all five portfolio fits use examined history. Earlier-period replay is hindsight-conditioned, not independent portfolio development or validation. The historical OOS name labels the parent strategy window, not an untouched portfolio test. No weight set is a live-trading recommendation or a certified global optimum.",
        True,
    )


def weights_table(doc, report):
    definitions = {r["id"]: r for r in report["portfolios"]}
    doc.heading("New initial strategy allocations")
    doc.table(
        ["Strategy sleeve"] + [ALIASES[p] for p in IDS],
        [
            [symbol]
            + [fmt(definitions[p]["initial_weights"][symbol], True, 6) for p in IDS]
            for symbol in SYMBOLS
        ],
    )
    doc.paragraph(
        "Weights allocate saved strategy-account wealth, including idle cash, not permanent holdings of the named ETFs. Capital is assigned once; each sleeve’s share later drifts with its wealth. There are no daily, weekly or monthly portfolio transfer or rebalance trades. The same exact full-precision weights are replayed in every period and all four costs."
    )


def cap_scope(doc):
    doc.heading("What the different caps mean")
    doc.paragraph(
        "Daily cap fit constrains initial weights and every historical OOS daily sleeve-capital share to at most one-third. Weekly cap fit and Monthly cap fit constrain initial weights and the last observed New York trading valuation in each ISO week or calendar month, respectively, including the terminal incomplete week/month at the fixed cutoff. Each fit constrains all four cost scenarios. Between-checkpoint daily shares may exceed one-third without triggering any trade."
    )
    doc.paragraph(
        "Initial cap fit applies one-third only to starting allocations; there is no later cap enforcement. Uncapped fit and Equal initial have no ongoing cap. Replayed development and validation concentration diagnostics are observations, not newly fitted constraints. Weekly and monthly checkpoint sets are not generally nested, so one cannot infer a theoretical ordering between their optimum Sharpes. All numerical fits are best-found, not globally certified, and no cap promises future or intraday enforcement."
    )


def methods(doc):
    doc.heading("Methods and limitations")
    doc.paragraph(
        "Portfolio wealth is V(c,t) = sum_i w(i)E(c,t,i), with each saved sleeve normalized to E(c,0,i)=1, V(c,0)=1 and sum_i w(i)=1. Daily returns are V(c,t)/V(c,t−1)−1, not constant-weight daily return averages. Each stage starts independently with $1,000; holdings, orders, streaks and wealth do not carry across stages. Only causal feature history carries."
    )
    doc.paragraph(
        "Cash is 3% nominal ACT/365 event-compounded, not 3% APY. Cash-excess Sharpe is sqrt(252) times mean daily net return minus matched cash return, divided by the sample standard deviation of that difference with ddof 1. It does not mean excess over buy-and-hold. Net volatility is the annualized sample standard deviation of daily net returns. CAGR uses each actual initial-to-terminal ACT/365 clock; daily drawdown includes the initial balance and is not an intraday measure. Undefined Sharpe/correlations are retained, not replaced with zero."
    )
    doc.paragraph(
        "The original strategy identities, daily causal indicators, native half-hour observations, shared three-trading-hour/seven-consecutive-check confirmation, next eligible observed bar-open execution, corporate actions, distributions, embedded costs and paid terminal liquidation are unchanged. No original market data or execution engine was rerun for this allocation study. No new combined trade count is inferred from the independent sleeves."
    )
    doc.paragraph(
        "Attribution uses portfolio net cash-excess returns and cost-matched passive QQQ or all five passive ETF cash-excess returns with an intercept. Joint partial betas are not weights, causal effects or short positions. Annual arithmetic alpha is 252 times the daily intercept, not CAGR. R squared is descriptive, not a significance or predictive-skill claim. Active strategy correlations use net daily account returns including cash/flat periods; they are not passive factor correlations."
    )
    doc.paragraph(
        "Older six-sleeve calculations and the original four-portfolio class-project reports remain preserved archives. Their BND cash-rich sleeve is excluded from every active allocation, correlation matrix and passive-factor regression here. The standalone Maximum CAGR/100%-GDX portfolio remains excluded; GDX remains an underlying strategy sleeve. No earlier result is silently overwritten."
    )


def render_stage(report: dict, stage: str, png: bytes):
    if stage not in STAGES:
        raise ValueError("unknown report stage")
    doc = Document(STAGE_LABELS[stage] + " without bond ETFs")
    portfolios = index(report["portfolio_rows"])
    controls = index(report["control_rows"], "control_id")
    checkpoints = index(report["checkpoint_rows"], frequency=True)
    singles = index(report["QQQ_single_factor_rows"])
    joints = index(report["five_passive_factor_rows"])
    strategies = correlation_index(report["strategy_correlations"])
    portfolio_corr = correlation_index(report["portfolio_correlations"])
    doc.heading("Executive summary", identifier="summary")
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
                fmt(portfolios[(stage, p, 3)]["cash_excess_sharpe"]),
                fmt(portfolios[(stage, p, 3)]["cagr"], True, 2),
                fmt(portfolios[(stage, p, 3)]["max_drawdown"], True, 2),
            ]
            for p in IDS
        ]
        + [
            [
                "QQQ buy and hold",
                fmt(controls[(stage, CONTROL_IDS[0], 3)]["cash_excess_sharpe"]),
                fmt(controls[(stage, CONTROL_IDS[0], 3)]["cagr"], True, 2),
                fmt(controls[(stage, CONTROL_IDS[0], 3)]["max_drawdown"], True, 2),
            ]
        ],
    )
    summary = next(r for r in report["stage_summaries"] if r["stage"] == stage)
    doc.paragraph(
        f"Scored {summary['scored_start']} to {summary['scored_end']}; {summary['observations']} daily return observations; {fmt(summary['elapsed_act365_years'], digits=12)} ACT365 years. Every account starts fresh at $1,000. The study endpoint remains 15 October 2026."
    )
    doc.parts.append(
        '<nav aria-label="Report sections"><a href="#weights">Weights</a> · <a href="#performance">Costs and performance</a> · <a href="#attribution">Alpha and beta</a> · <a href="#capital">Capital shares</a> · <a href="#correlations">Correlations</a></nav>'
    )
    doc.parts.append('<section class="chapter" id="weights">')
    weights_table(doc, report)
    cap_scope(doc)
    doc.parts.append('</section><section class="chapter">')
    doc.heading("Baseline equity and daily drawdown")
    doc.figure(stage, png)
    doc.parts.append('</section><section class="chapter">')
    doc.heading("All four execution cost scenarios", identifier="performance")
    doc.paragraph(
        "Each purchase and sale pays 1-bp commission plus one-way slippage of 1, 3, 10 or 25 bps. Baseline is 3-bp slippage, or 4 bps total per side. Cost-matched passive QQQ and matched cash are retained at every cost. Neither signals nor weights are refitted when costs or replay periods change."
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
                    fmt(r["cash_excess_sharpe"]),
                    fmt(r["cagr"], True, 2),
                    fmt(r["annualized_return_volatility"], True, 2),
                    fmt(r["max_drawdown"], True, 2),
                    "$" + fmt(r["terminal_equity_from_1000"], digits=2),
                ]
                for label, r in rows
            ],
        )
    doc.parts.append('</section><section class="chapter">')
    doc.heading("QQQ single factor attribution", identifier="attribution")
    doc.paragraph(
        "Same-stage, same-cost passive QQQ is the explanatory factor. Alpha is annual arithmetic percent, not compound growth. Betas and R squared are descriptive fitted quantities, with no significance or causal-skill claim."
    )
    doc.table(
        ["Slippage bp", "Allocation", "Alpha annual", "QQQ beta", "R squared"],
        [
            [
                str(int(cost)),
                ALIASES[p],
                fmt(singles[(stage, p, cost)]["alpha_annual_arithmetic"], True, 2),
                fmt(singles[(stage, p, cost)]["beta_QQQ"], digits=4),
                fmt(singles[(stage, p, cost)]["r_squared"], True, 2),
            ]
            for cost, p in itertools.product(COSTS, IDS)
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
                    fmt(joints[(stage, p, cost)][f"beta_{s}"], digits=4)
                    for s in SYMBOLS
                ]
                + [
                    fmt(joints[(stage, p, cost)]["alpha_annual_arithmetic"], True, 2),
                    fmt(joints[(stage, p, cost)]["r_squared"], True, 2),
                ]
                for p in IDS
            ],
        )
    doc.parts.append('</section><section class="chapter">')
    doc.heading("Checkpoint and daily capital share diagnostics", identifier="capital")
    doc.paragraph(
        "Each row describes the same saved portfolio path at one checkpoint schedule. A breach day means at least one sleeve exceeds one-third at that valuation, not the number of offending sleeves. Between-checkpoint breach days exclude the scheduled checkpoints. Initial and uncapped/equal comparisons have no promised ongoing limit; backward replay breaches of new fitted limits are retained rather than repaired."
    )
    for cost in COSTS:
        doc.heading(f"{int(cost)} bp slippage diagnostics", 3)
        doc.table(
            [
                "Allocation",
                "Checks",
                "Count",
                "Peak check",
                "Check breach days",
                "Peak daily",
                "Daily breach days",
                "Between days",
            ],
            [
                [
                    ALIASES[p],
                    frequency,
                    str(
                        count(
                            (r := checkpoints[(stage, p, cost, frequency)])[
                                "checkpoint_count"
                            ]
                        )
                    ),
                    fmt(r["max_checkpoint_capital_share"], True, 4),
                    str(count(r["checkpoint_breach_days"])),
                    fmt(r["max_daily_capital_share"], True, 4),
                    str(count(r["daily_breach_days"])),
                    str(count(r["between_checkpoint_breach_days"])),
                ]
                for p, frequency in itertools.product(IDS, FREQUENCIES)
            ],
        )
    doc.parts.append('</section><section class="chapter">')
    doc.heading("Active strategy and portfolio correlations", identifier="correlations")
    doc.paragraph(
        "All matrices use the same stage’s daily net account returns, including flat/cash periods, at the stated costs. The seven-series portfolio matrix adds matched passive QQQ to the six new allocations. These are sample correlations, not future diversification guarantees, passive-factor correlations or a pairs-trading strategy test. Closely related fitted allocations may have very high correlations."
    )
    for cost in COSTS:
        doc.heading(f"{int(cost)} bp slippage active strategy correlations", 3)
        matrix = strategies[(stage, cost)]["matrix"]
        doc.table(
            ["Strategy"] + list(SYMBOLS),
            [
                [symbol] + [fmt(v, digits=4) for v in matrix[i]]
                for i, symbol in enumerate(SYMBOLS)
            ],
        )
        doc.heading(f"{int(cost)} bp slippage portfolio correlations", 3)
        labels = [ALIASES[p] for p in IDS] + ["QQQ buy and hold"]
        matrix = portfolio_corr[(stage, cost)]["matrix"]
        doc.table(
            ["Portfolio"] + labels,
            [
                [label] + [fmt(v, digits=4) for v in matrix[i]]
                for i, label in enumerate(labels)
            ],
        )
    doc.parts.append('</section><section class="chapter">')
    methods(doc)
    doc.parts.append("</section>")
    return doc.finish()


def overview(report):
    text = [
        "# Five ETF portfolios without bonds",
        "",
        "Six new static initial allocations across GDX, FXI, QQQ, UNG and FDN. Development 2017–2020; validation 2021–2023; historical OOS 2024–15 October 2026.",
        "",
        "All five optimized allocations were refitted on the already examined historical OOS sample; Equal initial assigns 20% to each strategy. This is retrospective allocation research, not an untouched portfolio test or live trading recommendation.",
        "",
        "## Read the reports",
        "",
        "- [Development report](development.html)",
        "- [Validation report](validation.html)",
        "- [Historical OOS report](historical_OOS.html)",
        "- [Combined full tables](combined_report.md)",
        "",
        "Each offline HTML embeds its seven-series baseline equity/drawdown PNG and includes all four cost scenarios, matched QQQ/cash controls, QQQ and joint-five-ETF alpha/beta, capital-share diagnostics and both correlation matrices. No numerical daily paths are embedded.",
        "",
        "## Historical OOS baseline comparison",
        "",
    ]
    rows = index(report["portfolio_rows"])
    controls = index(report["control_rows"], "control_id")
    text += [
        markdown_table(
            [
                "Allocation or control",
                "Cash excess Sharpe",
                "CAGR",
                "Daily max drawdown",
            ],
            [
                [
                    ALIASES[p],
                    fmt(rows[("historical_OOS", p, 3)]["cash_excess_sharpe"]),
                    fmt(rows[("historical_OOS", p, 3)]["cagr"], True, 2),
                    fmt(rows[("historical_OOS", p, 3)]["max_drawdown"], True, 2),
                ]
                for p in IDS
            ]
            + [
                [
                    "QQQ buy and hold",
                    fmt(
                        controls[("historical_OOS", CONTROL_IDS[0], 3)][
                            "cash_excess_sharpe"
                        ]
                    ),
                    fmt(
                        controls[("historical_OOS", CONTROL_IDS[0], 3)]["cagr"], True, 2
                    ),
                    fmt(
                        controls[("historical_OOS", CONTROL_IDS[0], 3)]["max_drawdown"],
                        True,
                        2,
                    ),
                ]
            ],
        ),
        "",
        "Baseline costs: 1-bp commission plus 3-bp slippage each way. Cash: 3% nominal ACT/365 event-compounded. The same full-precision initial weights are used in every period and cost, without rebalancing.",
        "",
        "Daily/weekly/monthly caps are historical checkpoint constraints. Weekly and monthly fits use separate, non-nested week-end/month-end sets, including the terminal incomplete period. Between-checkpoint daily breaches are allowed. Initial-only cap has no later enforcement; no model guarantees future or intraday compliance.",
        "",
        "Original four-portfolio class-project reports and six-sleeve source records remain unchanged archives. Bond ETFs and the standalone Maximum CAGR portfolio are absent from the active comparison. See the accompanying aggregate source JSON and render manifest for inspectable full precision and SHA256 bindings.",
        "",
    ]
    return "\n".join(text)


def build(report_path: Path, figures_dir: Path, output: Path):
    report_path, figures_dir, output = (
        report_path.resolve(),
        figures_dir.resolve(),
        output.resolve(),
    )
    report = validate(read_json(report_path))
    figures, receipt = validate_figures(report, figures_dir)
    if receipt.get("saved_report_sha256") != sha(report_path):
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
            raise ValueError("unsafe or non-offline rendered report")
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
        "schema": "five_etf_six_portfolio_report_render_v1",
        "aggregate_only": True,
        "no_account_or_optimizer_run": True,
        "source_report_sha256": sha(report_path),
        "figure_receipt_sha256": sha(figures_dir / "figures_verification.json"),
        "portfolio_ids": list(IDS),
        "symbols": list(SYMBOLS),
        "files": {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()},
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
    args = parser.parse_args(argv)
    try:
        build(args.report, args.figures_dir, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
