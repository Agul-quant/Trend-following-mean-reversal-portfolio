"""Portable, aggregate-only publication of unchanged saved cap results.

No execution engine, optimizer, market file or account path is imported here.
The completed local source is byte-bound during selection. The detached public
digest binds every retained full-precision value without publishing Daily rows.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re

SOURCE_SHA = "2a940582ceac6b9a108e3a9baf9319ef26b1c74eff29bedddf66e3bfd3472171"
RETAINED_SHA = "6757f4c392301fb31089809aa5af96bdcd61dffe7b402263e18da5896f77fde9"
SOURCE_SCHEMA = "actual_cap_rebalance_aggregate_report_v1"
SCHEMA = "final_actual_cap_rebalance_aggregate_report_v1"
CONFIG_SCHEMA = "final_cap_rebalancing_policy_v1"
RETAINED_FREQUENCIES = ("none", "weekly", "monthly")
SYMBOLS = ("GDX", "FXI", "QQQ", "UNG", "FDN")
COSTS = (1, 3, 10, 25)
STAGES = {
    "development": ("2017-01-01", "2020-12-31", 1007),
    "validation": ("2021-01-01", "2023-12-31", 753),
    "historical_OOS": ("2024-01-01", "2026-10-15", 700),
}
LABELS = {
    "none": "Initial allocation; no rebalancing",
    "weekly": "Weekly corrections",
    "monthly": "Monthly corrections",
}
SELECTION = (
    "Exact saved aggregate subset; no refit, account run or metric recomputation"
)
PAYLOAD_KEYS = (
    "baseline_slippage_bps",
    "cap_fraction",
    "commission_bps_each_way",
    "controls",
    "created_at_utc",
    "independent_audit_passed",
    "initial_weights",
    "metrics",
    "optimized",
    "original_frozen_sources_unchanged",
    "periods",
    "rebalancing",
    "retrospective",
    "rows",
    "slippage_bps_each_way",
    "symbols",
)
CONFIG_KEYS = (
    "symbols",
    "initial_weights",
    "periods",
    "slippage_bps_each_way",
    "commission_bps_each_way",
    "cap_fraction",
    "baseline_slippage_bps",
)
PRIVATE_TEXT = re.compile(
    r"/Users/|/home/|/var/folders/|file://|[A-Za-z]:[\\/]Users[\\/]"
    r"|(?:apikey|api_key|api-key)=[A-Za-z0-9]{8,}",
    re.I,
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical_sha(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_json(path):
    def reject(value):
        raise ValueError(f"Nonfinite JSON constant {value}")

    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject)


def public_json(value):
    """Reject nonfinite values, private locators and serialized daily arrays."""
    if isinstance(value, dict):
        for key, item in value.items():
            require(not PRIVATE_TEXT.search(str(key)), "Private public-JSON key")
            public_json(item)
    elif isinstance(value, list):
        require(
            not (len(value) > 128 and all(isinstance(x, (int, float)) for x in value)),
            "Serialized daily numeric array",
        )
        for item in value:
            public_json(item)
    elif isinstance(value, float):
        require(math.isfinite(value), "Nonfinite public value")
    elif isinstance(value, str):
        require(not PRIVATE_TEXT.search(value), "Private locator or credential")


def retained_payload(report):
    return {key: report[key] for key in PAYLOAD_KEYS}


def expected_config(report):
    return {
        "schema": CONFIG_SCHEMA,
        **{key: copy.deepcopy(report[key]) for key in CONFIG_KEYS},
        "frequencies": list(RETAINED_FREQUENCIES),
        "source_report_sha256": SOURCE_SHA,
    }


def validate_config(config, report):
    public_json(config)
    expected = expected_config(report)
    for key, value in expected.items():
        require(config.get(key) == value, f"Active cap config mismatch: {key}")
    return config


def _scope(report):
    public_json(report)
    require(report.get("symbols") == list(SYMBOLS), "Unexpected ETF universe")
    require(report.get("slippage_bps_each_way") == list(COSTS), "Incorrect costs")
    require(report.get("commission_bps_each_way") == 1, "Incorrect commission")
    require(report.get("baseline_slippage_bps") == 3, "Incorrect baseline")
    require(report.get("cap_fraction") == 1 / 3, "Incorrect cap")
    require(
        report.get("periods") == {k: list(v[:2]) for k, v in STAGES.items()},
        "Incorrect stage bounds",
    )
    require(
        report.get("optimized") is False and report.get("retrospective") is True,
        "Refit or holdout interpretation changed",
    )
    require(
        report.get("independent_audit_passed") is True
        and report.get("original_frozen_sources_unchanged") is True,
        "Completed source audit flags changed",
    )
    weights = report.get("initial_weights", {})
    require(
        set(weights) == set(SYMBOLS)
        and all(
            isinstance(w, (int, float)) and not isinstance(w, bool) and 0 <= w <= 1 / 3
            for w in weights.values()
        )
        and math.isclose(math.fsum(weights.values()), 1, rel_tol=0, abs_tol=1e-14),
        "Invalid original Initial cap weights",
    )
    desired = {(f, s, c) for f in RETAINED_FREQUENCIES for s in STAGES for c in COSTS}
    rows = report.get("rows", [])
    identities = [
        (r.get("frequency"), r.get("stage"), r.get("slippage_bps")) for r in rows
    ]
    require(
        len(rows) == 36 and len(set(identities)) == 36 and set(identities) == desired,
        "Incorrect retained frequency/stage/cost scope",
    )
    for row in rows:
        require(
            row.get("observations") == STAGES[row["stage"]][2],
            "Incorrect observation count",
        )
        require(
            row["trade_counts_by_symbol"].keys() == weights.keys(),
            "Trade-count ETF identities changed",
        )
    controls = report.get("controls", [])
    desired_controls = {(s, "QQQ_buy_and_hold", c) for s in STAGES for c in COSTS}
    desired_controls |= {(s, "cash", None) for s in STAGES}
    identities = [
        (r.get("stage"), r.get("control"), r.get("slippage_bps")) for r in controls
    ]
    require(
        len(controls) == 15
        and len(set(identities)) == 15
        and set(identities) == desired_controls,
        "Incorrect saved control scope",
    )
    for row in controls:
        require(
            row.get("observations") == STAGES[row["stage"]][2],
            "Incorrect control observation count",
        )
        if row["control"] == "cash":
            require(
                row["cash_excess_sharpe"] is None, "Cash Sharpe must remain undefined"
            )


def validate_report(report, config=None):
    _scope(report)
    require(report.get("schema") == SCHEMA, "Incorrect public cap schema")
    require(
        report.get("source_report_sha256") == SOURCE_SHA, "Saved source binding changed"
    )
    require(
        report.get("retained_frequencies") == list(RETAINED_FREQUENCIES)
        and report.get("removed_frequencies") == ["daily"],
        "Removal identity changed",
    )
    require(report.get("selection_method") == SELECTION, "Subset method changed")
    require(
        report.get("retained_source_payload_sha256") == RETAINED_SHA
        and canonical_sha(retained_payload(report)) == RETAINED_SHA,
        "Retained saved values or metadata changed",
    )
    if config is not None:
        validate_config(config, report)
    return report


def select_report(source):
    require(source.get("schema") == SOURCE_SCHEMA, "Incorrect completed source schema")
    identities = [
        (r.get("frequency"), r.get("stage"), r.get("slippage_bps"))
        for r in source.get("rows", [])
    ]
    desired = {
        (f, s, c)
        for f in ("none", "daily", "weekly", "monthly")
        for s in STAGES
        for c in COSTS
    }
    require(
        len(identities) == 48
        and len(set(identities)) == 48
        and set(identities) == desired,
        "Incomplete completed source scope",
    )
    result = {key: copy.deepcopy(source[key]) for key in PAYLOAD_KEYS}
    result["rows"] = [
        copy.deepcopy(r)
        for r in source["rows"]
        if r["frequency"] in RETAINED_FREQUENCIES
    ]
    result.update(
        schema=SCHEMA,
        title="Weekly and Monthly Cap-Triggered Rebalancing",
        source_report_sha256=SOURCE_SHA,
        retained_source_payload_sha256=RETAINED_SHA,
        retained_frequencies=list(RETAINED_FREQUENCIES),
        removed_frequencies=["daily"],
        selection_method=SELECTION,
    )
    return validate_report(result)


CSV_KEYS = (
    "stage",
    "frequency",
    "slippage_bps",
    "cash_excess_sharpe",
    "cagr",
    "max_drawdown",
    "terminal_normalized_equity",
    "observations",
    "years_act365",
    "mean_etf_exposure",
    "strategy_round_trips",
    "cap_executions",
    "paid_cap_orders",
    "commission_paid",
    "slippage_paid",
    "total_cost",
    "extra_cap_commission",
    "extra_cap_slippage",
    "gross_raw_turnover",
    "turnover_fraction_of_initial",
    "daily_cap_breach_days",
    "max_daily_capital_share",
    "observed_common_open_breaches_before_cap",
    "observed_common_open_count",
    "max_observed_common_open_share_before_cap",
    "max_post_execution_capital_share",
)
CONTROL_KEYS = (
    "stage",
    "control",
    "slippage_bps",
    "cash_excess_sharpe",
    "cagr",
    "max_drawdown",
    "terminal_normalized_equity",
    "observations",
)


def csv_text(rows, keys):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=keys, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def source_audit(report):
    validate_report(report)
    return {
        "schema": "detached_final_cap_subset_audit_v1",
        "passed": True,
        "source_report_sha256": SOURCE_SHA,
        "source_schema": SOURCE_SCHEMA,
        "retained_source_payload_sha256": RETAINED_SHA,
        "retained_frequencies": list(RETAINED_FREQUENCIES),
        "removed_frequencies": ["daily"],
        "retained_performance_rows": 36,
        "removed_performance_rows": 12,
        "unchanged_control_rows": 15,
        "exact_saved_full_precision_values": True,
        "same_original_initial_weights": True,
        "optimizer_or_account_run": False,
        "metrics_recomputed": False,
        "private_market_or_account_inputs_read": False,
        "verification_scope": "Detached aggregate identity and exact-value verification; inherits completed independent financial audit, does not rerun it",
        "daily_variant_results_exported": False,
        "canonical_digest": "SHA256 of UTF-8 JSON with sorted keys and compact separators for the published retained payload keys",
        "retained_payload_keys": list(PAYLOAD_KEYS),
    }


def _number(value, percent=False, digits=3):
    if value is None:
        return "Undefined"
    return f"{value * (100 if percent else 1):.{digits}f}" + ("%" if percent else "")


def markdown(report):
    validate_report(report)
    rows = {(r["stage"], r["frequency"], r["slippage_bps"]): r for r in report["rows"]}
    controls = {
        (r["stage"], r["control"], r["slippage_bps"]): r for r in report["controls"]
    }
    out = [
        "# Weekly and Monthly Cap-Triggered Rebalancing",
        "",
        "## Scope and method",
        "",
        "The active comparison retains **Weekly corrections**, **Monthly corrections** and the **Initial allocation; no rebalancing** comparator. Daily corrections have been removed. This is an exact subset of completed independently audited calculations—not a new optimizer, account run or performance improvement. All retained full-precision values are unchanged.",
        "",
        "The unchanged long/cash strategy sleeves are **GDX, FXI, QQQ, UNG and FDN**. There are no bond ETFs, shorts, leverage or standalone Maximum CAGR allocation. Each period starts independently with **$1,000**, flat accounts and empty orders/confirmation streaks; causal feature history alone carries across stages.",
        "",
        "### Same saved starting weights for every frequency, period and cost",
        "",
        "| Strategy sleeve | Initial weight |",
        "|---|---:|",
    ]
    out += [
        f"| {s} | {_number(report['initial_weights'][s], True, 9)} |" for s in SYMBOLS
    ]
    out += [
        "",
        "At the last actual trading session of each ISO week or calendar month, the **17:00 New York** valuation queues a correction only when a sleeve's whole strategy-account capital (ETF plus cash) exceeds one-third. October 15, 2026 is not an artificial week/month end. Execution waits for the next simultaneous eligible observed native 30-minute bar open, strictly after the decision. Corporate actions, original dividend reinvestment and normal confirmed strategy fills occur first; a vanished breach cancels the intent.",
        "",
        "At execution, trim oversized sleeves and redistribute excess proportionally to the other sleeves' **current capital**, recursively respecting the one-third post-cost limit. This is **not a reset to starting weights**. Long-signal recipients buy ETF shares; cash-signal recipients remain in cash. Partial cap orders do not alter logical signals or restart the original seven-consecutive-check/three-trading-hour confirmation.",
        "",
        "Cash earns **3% nominal ACT/365 event-compounded**, not 3% APY. Paid strategy, cap and terminal ETF orders pay **1 bp commission plus 1/3/10/25 bps one-way slippage, each way**; baseline slippage is 3 bps. The inherited **fee-free dividend-reinvestment proxy** is unchanged. Internal cash transfers have no trading fee. Original corporate-action and paid terminal-close liquidation conventions remain; no order netting, taxes or additional market impact are modeled.",
        "",
        "**Not a continuous cap:** between-check drift, daily closing breaches and overnight gaps remain possible. The one-third limit is tested immediately after an executed correction, not at every market tick. It concerns sleeve capital, not ETF exposure or risk contribution.",
        "",
        "**Retrospective evidence:** strategy identities and starting weights used previously examined OOS history. The historical stage names do not make this an untouched portfolio holdout, optimal-frequency finding or live trading instruction.",
        "",
        "## All periods and four cost scenarios",
        "",
        "Sharpe is net **cash-excess** Sharpe: sqrt(252) times mean daily portfolio return minus matched cash return divided by its sample standard deviation (ddof 1), not excess over buy-and-hold. CAGR uses the actual initial-to-terminal ACT/365 elapsed time. Drawdown uses daily marked wealth including initial capital, not intraday extrema. Undefined metrics remain undefined. Each stage restarts; stages are not spliced.",
        "",
        "Trips are completed strategy round trips including paid terminal exits. Partial cap orders are separate orders, not extra completed trips. Cap executions can be cash transfers without an ETF order. Extra cap costs are direct cap-order commissions plus slippage, not the change in total costs versus the comparator; later strategy-order sizes may also change.",
        "",
    ]
    for stage, (start, end, _) in STAGES.items():
        out += [
            f"### {stage.replace('_', ' ')} — {start} to {end}",
            "",
            "| Portfolio / control | Slippage (bp) | Sharpe | CAGR | Max DD | Trips | Cap executions / ETF orders | Extra cap costs ($) |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for cost in COSTS:
            for frequency in RETAINED_FREQUENCIES:
                r = rows[(stage, frequency, cost)]
                out.append(
                    f"| {LABELS[frequency]} | {cost} | {_number(r['cash_excess_sharpe'])} | {_number(r['cagr'], True, 2)} | {_number(r['max_drawdown'], True, 2)} | {r['strategy_round_trips']} | {r['cap_executions']} / {r['paid_cap_orders']} | {_number(r['extra_cap_commission'] + r['extra_cap_slippage'], digits=4)} |"
                )
            r = controls[(stage, "QQQ_buy_and_hold", cost)]
            out.append(
                f"| QQQ buy-and-hold | {cost} | {_number(r['cash_excess_sharpe'])} | {_number(r['cagr'], True, 2)} | {_number(r['max_drawdown'], True, 2)} | 1 | — | — |"
            )
        r = controls[(stage, "cash", None)]
        out += [
            f"| Matched cash | — | Undefined | {_number(r['cagr'], True, 2)} | {_number(r['max_drawdown'], True, 2)} | 0 | — | — |",
            "",
        ]
    out += [
        "## Baseline cap diagnostics",
        "",
        "These observations cover daily valuations and common eligible opens only. Opening breaches are measured after normal strategy orders and before a cap correction. They are not an every-tick risk test.",
        "",
        "| Period | Model | Daily breach days | Max daily sleeve share | Observed open breaches | Max observed open share | Max share after correction |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for stage in STAGES:
        for frequency in RETAINED_FREQUENCIES:
            r = rows[(stage, frequency, 3)]
            post = (
                "—"
                if r["max_post_execution_capital_share"] is None
                else _number(r["max_post_execution_capital_share"], True, 4)
            )
            out.append(
                f"| {stage} | {LABELS[frequency]} | {r['daily_cap_breach_days']} | {_number(r['max_daily_capital_share'], True, 2)} | {r['observed_common_open_breaches_before_cap']} | {_number(r['max_observed_common_open_share_before_cap'], True, 2)} | {post} |"
            )
    out += [
        "",
        "## Baseline equity and drawdown curves",
        "",
        "Each panel restarts at $1,000 and compares the three retained models with cost-matched QQQ buy-and-hold. Raster images contain no embedded numerical daily series.",
        "",
    ]
    for stage in STAGES:
        out += [f"![{stage} baseline equity and drawdown]({stage}_baseline.png)", ""]
    out += [
        "## Audit and portable verification",
        "",
        "The completed financial audit checked disabled-rebalancing equivalence to all five original frozen sleeve paths and matched cash across all periods/costs, then independently checked chronological cash, corporate actions, inherited dividend reinvestment, signal fills, cap orders, self-financing transfers, post-cost caps and daily statistics. Those sources and completed results remain unchanged.",
        "",
        "This publication's verifier checks the exact 36-row saved subset, 15 original controls, saved weights, metadata and canonical full-precision digest using only public aggregate artifacts. It does **not** reproduce the private financial audit or derive results anew. Daily variant outcomes and private market/account paths are not exported. Alpha and betas in JSON are descriptive regressions; annual alpha is the arithmetic intercept times 252, not CAGR. Joint beta order is GDX, FXI, QQQ, UNG, FDN.",
        "",
        f"- Completed source aggregate SHA256: `{SOURCE_SHA}`",
        f"- Canonical retained payload SHA256: `{RETAINED_SHA}`",
        "- [Exact aggregate results](report.json) · [Full-precision performance CSV](performance.csv) · [Controls CSV](controls.csv) · [Detached subset audit](source_subset_audit.json)",
        "",
        "From the repository root: `PYTHONPATH=src python scripts/verify_final_cap.py --report-dir reports/final_cap_rebalancing --config configs/final_cap_rebalancing.json`.",
        "",
    ]
    return "\n".join(out)


def write_outputs(report, directory):
    validate_report(report)
    directory = Path(directory)
    names = (
        "report.json",
        "source_subset_audit.json",
        "performance.csv",
        "controls.csv",
        "report.md",
    )
    if any((directory / name).exists() for name in names):
        raise FileExistsError(
            "Preserve previous aggregate outputs; choose a new directory"
        )
    directory.mkdir(parents=True, exist_ok=True)
    for filename, value in (
        ("report.json", report),
        ("source_subset_audit.json", source_audit(report)),
    ):
        (directory / filename).write_text(
            json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    (directory / "performance.csv").write_text(
        csv_text(report["rows"], CSV_KEYS), encoding="utf-8", newline=""
    )
    (directory / "controls.csv").write_text(
        csv_text(report["controls"], CONTROL_KEYS), encoding="utf-8", newline=""
    )
    (directory / "report.md").write_text(markdown(report), encoding="utf-8")
