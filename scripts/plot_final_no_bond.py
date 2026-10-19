#!/usr/bin/env python3
"""Raster views of four fixed five-ETF portfolios and their matched passive QQQ.

Read separately authorized saved accounts only. No optimizer, account engine,
market refresh, cross-sleeve transfer, new fee or daily-array export occurs here.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from trend_portfolio.cli import load_bundle  # noqa: E402
from trend_portfolio.plotting import prepare_plot_data  # noqa: E402


IDS = ("no_bond_daily_capped_max_sharpe", "no_bond_initial_capped_max_sharpe",
       "no_bond_uncapped_max_sharpe", "no_bond_equal_initial")
SYMBOLS = ("GDX", "FXI", "QQQ", "UNG", "FDN")
SOURCE_SYMBOLS = (*SYMBOLS, "BND")
STAGES = ("development", "validation", "historical_OOS")
COUNTS = {"development": 1007, "validation": 753, "historical_OOS": 700}
NAMES = {"development": "Development: 2017–2020", "validation": "Validation: 2021–2023",
         "historical_OOS": "Historical OOS: 2024–October 15, 2026"}
LABELS = ("Daily cap fit", "Initial cap fit", "Uncapped fit", "Equal initial", "QQQ buy-and-hold")
COLORS = ("#0072B2", "#D08B00", "#009E73", "#875AA7", "#252525")
STYLES = ("-", (0, (5, 2, 1, 2)), (0, (1, 1.6)), "-.", (0, (5, 2.5)))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def verify_release(path: Path, required: list[Path]) -> dict[str, str]:
    """Rehash every released guard, including all original 413 source bindings."""
    release = json.loads(path.read_text(encoding="utf-8"))
    if "payload" in release:
        payload = release["payload"]
        if hashlib.sha256(canonical(payload)).hexdigest() != release.get("payload_sha256"):
            raise ValueError("private release checksum mismatch")
    else:
        payload = release
    if payload.get("authorized_saved_path_evaluation") is not True:
        raise ValueError("saved-path visualization is not authorized")
    files, original = payload.get("files", {}), payload.get("source_file_sha256", {})
    if (not isinstance(files, dict) or not isinstance(original, dict) or len(original) < 413
            or any(files.get(name) != expected for name, expected in original.items())):
        raise ValueError("all original 413 source guards must be released unchanged")
    normalized = {str(Path(name).resolve()): value for name, value in files.items()}
    if len(normalized) != len(files) or any(not Path(name).is_absolute() for name in files):
        raise ValueError("released paths must be unique absolute file bindings")
    if any(str(item.resolve()) not in normalized for item in required):
        raise ValueError("required plotting input or implementation is unsealed")
    for name, expected in normalized.items():
        if not isinstance(expected, str) or len(expected) != 64 or digest(Path(name)) != expected:
            raise ValueError("released source or input changed before or during visualization")
    return normalized


def without_bonds(source: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Slice out BND only after validating original saved axes, without rescaling."""
    if tuple(source["symbols"].tolist()) != SOURCE_SYMBOLS:
        raise ValueError("source accounts must have the unchanged original six-symbol order")
    if not np.array_equal(source["slippage_bps"], [1, 3, 10, 25]):
        raise ValueError("source costs must be the unchanged four scenarios")
    cash = np.asarray(source["cash_returns"])
    n = len(source["timestamps"])
    if cash.shape == (4, n) and not np.array_equal(cash, np.broadcast_to(cash[0], cash.shape)):
        raise ValueError("all four saved costs must use the same matched cash path")
    return {**source, "symbols": source["symbols"][:5].copy(),
            "sleeve_normalized_equity": source["sleeve_normalized_equity"][:, :, :5].copy(),
            "buy_and_hold_returns": source["buy_and_hold_returns"][:, :, :5].copy()}


def fixed_portfolios(report: dict) -> list[dict]:
    if (report.get("schema") != "five_etf_four_portfolio_comparison_v1"
            or tuple(report.get("symbols", ())) != SYMBOLS
            or tuple(portfolio.get("id") for portfolio in report.get("portfolios", [])) != IDS):
        raise ValueError("report must identify all four fixed five-ETF portfolios in exact order")
    records = []
    for portfolio in report["portfolios"]:
        weights = portfolio["initial_weights"]
        if not isinstance(weights, dict) or set(weights) != set(SYMBOLS):
            raise ValueError("each fixed allocation must contain exactly the five retained ETFs")
        # Validation is delegated to the existing shared static-wealth contract.
        records.append({"id": portfolio["id"], "initial_weights": [weights[symbol] for symbol in SYMBOLS]})
    return records


def prepare_no_bond_data(source: dict, report: dict, initial_timestamp: str):
    bundle = without_bonds(source)
    data = prepare_plot_data(bundle, fixed_portfolios(report), initial_timestamp=initial_timestamp,
                             initial_capital=1000, baseline_slippage=3)
    if data.series_ids != (*IDS, "QQQ_buy_and_hold"):
        raise ValueError("plot series identities changed")
    return replace(data, labels=LABELS)


def check_saved_metrics(data, report: dict, stage: str) -> dict:
    """Independently walk daily peaks and match all five saved curve endpoints."""
    checked = []
    for column, identifier in enumerate(data.series_ids):
        field = "control_id" if identifier == "QQQ_buy_and_hold" else "portfolio_id"
        rows = report["control_rows" if field == "control_id" else "portfolio_rows"]
        matches = [row for row in rows if row["stage"] == stage
                   and row[field] == identifier and row["slippage_bps_each_way"] == 3]
        if len(matches) != 1:
            raise ValueError("saved aggregate identity is absent or duplicated")
        row = matches[0]
        values = data.equity[:, column]
        peak, worst = 1000.0, 0.0
        for value in values:
            peak = max(peak, float(value))
            worst = min(worst, float(value) / peak - 1)
        if (row["observations"] != len(values) - 1 or row["commission_bps_each_way"] != 1
                or not np.isclose(values[-1], row["terminal_equity_from_1000"], rtol=1e-12, atol=1e-9)
                or not np.isclose(worst, row["max_drawdown"], rtol=1e-12, atol=1e-12)
                or not np.isclose(worst, data.drawdown[:, column].min(), rtol=1e-12, atol=1e-12)):
            raise ValueError("raster path disagrees with saved endpoint, drawdown, cost or clock")
        checked.append({"series_id": identifier, "terminal_equity_from_1000": float(values[-1]),
                        "max_drawdown": worst})
    return {"stage": stage, "series": len(checked), "points_per_series": len(data.timestamps),
            "initial_value": 1000, "saved_aggregate_checks": checked}


def render_combined(data, stage: str, target: Path) -> None:
    """One raster-only 6.5 by 5.05 inch equity/drawdown figure, five curves."""
    if stage not in STAGES or data.series_ids != (*IDS, "QQQ_buy_and_hold"):
        raise ValueError("unexpected stage or plotted membership")
    if target.exists():
        raise ValueError("figure already exists; preserve all earlier attempts")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.ticker import FuncFormatter, MaxNLocator, PercentFormatter

    with matplotlib.rc_context({"path.simplify": False, "font.family": "DejaVu Sans"}):
        figure = Figure(figsize=(6.5, 5.05), dpi=200, facecolor="white")
        FigureCanvasAgg(figure)
        equity_ax = figure.add_axes([.125, .48, .80, .265])
        drawdown_ax = figure.add_axes([.125, .17, .80, .225], sharex=equity_ax)
        for index in range(5):
            for axes, values in ((equity_ax, data.equity), (drawdown_ax, data.drawdown)):
                axes.plot(data.timestamps, values[:, index], color=COLORS[index], linestyle=STYLES[index],
                          linewidth=1.5 if index == 4 else 1.2, label=LABELS[index],
                          zorder=5 if index == 4 else 2, alpha=.95)
        for axes in (equity_ax, drawdown_ax):
            axes.grid(axis="y", color="#DCE1E5", linewidth=.5)
            axes.spines[["top", "right"]].set_visible(False)
            axes.spines[["left", "bottom"]].set_color("#7C8791")
            axes.tick_params(labelsize=9, length=3)
            axes.set_xlim(data.timestamps[0], data.timestamps[-1])
        equity_ax.set_ylim(bottom=0)
        equity_ax.set_ylabel("Value (USD)", fontsize=9.5, labelpad=4)
        equity_ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
        equity_ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"${value:,.0f}"))
        equity_ax.tick_params(labelbottom=False)
        drawdown_ax.set_ylim(min(-.01, float(data.drawdown.min()) * 1.08), 0)
        drawdown_ax.set_ylabel("Drawdown", fontsize=9.5, labelpad=4)
        drawdown_ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
        decimals = 1 if abs(float(data.drawdown.min())) < .05 else 0
        drawdown_ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=decimals))
        middle_year = int((data.timestamps[0].year + data.timestamps[-1].year) / 2)
        middle = datetime(middle_year, 7, 1, tzinfo=timezone.utc)
        ticks = [data.timestamps[0]]
        if data.timestamps[0] < middle < data.timestamps[-1]:
            ticks.append(middle)
        ticks.append(data.timestamps[-1])
        drawdown_ax.set_xticks(ticks)
        drawdown_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d", tz=timezone.utc))
        drawdown_ax.tick_params(axis="x", labelrotation=0, pad=5)
        figure.text(.125, .965, NAMES[stage], fontsize=12.5, weight="bold", color="#000000")
        figure.text(.125, .925, "Five ETFs • $1,000 fresh start • 1-bp commission + 3-bp slippage each way",
                    fontsize=8.6, color="#405263")
        handles, labels = equity_ax.get_legend_handles_labels()
        figure.legend(handles, labels, loc="center left", bbox_to_anchor=(.117, .835),
                      ncol=2, frameon=False, fontsize=8.5, handlelength=3,
                      columnspacing=1.6, labelspacing=.35, borderaxespad=0)
        figure.text(.125, .077, "Static initial allocation; no cross-sleeve rebalancing. Similar paths may overlap.",
                    fontsize=8, color="#475765")
        figure.text(.125, .038, "Retrospective fitted allocations; not untouched portfolio OOS. Stage-specific y scales.",
                    fontsize=8, color="#475765")
        figure.savefig(target, format="png", dpi=200, facecolor="white",
                       metadata={"Software": "Trend Following and Mean Reversion ETF Portfolios"})
        figure.clear()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--input-release", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        parser.error("output directory exists; preserve previous attempts")
    records = json.loads(args.manifest.read_text(encoding="utf-8"))["stages"]
    if set(records) != set(STAGES):
        parser.error("the three unchanged saved stages are required")
    bundles = {}
    for stage in STAGES:
        path = Path(records[stage]["input"])
        bundles[stage] = path if path.is_absolute() else args.manifest.parent / path
    required = [args.manifest, args.report, Path(__file__),
                ROOT / "src/trend_portfolio/analytics.py", ROOT / "src/trend_portfolio/cli.py",
                ROOT / "src/trend_portfolio/plotting.py", *bundles.values()]
    before = verify_release(args.input_release, required)  # ALL guards before any NPZ read.
    report = json.loads(args.report.read_text(encoding="utf-8"))
    fixed_portfolios(report)
    # Public new-fit report must state the exact original cost/account conventions.
    if (report.get("commission_bps_each_way") != 1 or report.get("initial_capital_each_stage") != 1000
            or report.get("slippage_bps_each_way") != [1, 3, 10, 25]):
        raise ValueError("saved report cost or fresh-stage account convention changed")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    figures = []
    for stage in STAGES:
        source = load_bundle(bundles[stage])
        if len(source["timestamps"]) != COUNTS[stage]:
            raise ValueError("saved daily observation count changed")
        data = prepare_no_bond_data(source, report, records[stage]["initial_timestamp"])
        evidence = check_saved_metrics(data, report, stage)
        target = args.output_dir / f"{stage}_baseline.png"
        render_combined(data, stage, target)
        figures.append({**evidence, "file": target.name, "sha256": digest(target),
                        "all_daily_points_rendered": True})
    after = verify_release(args.input_release, required)
    if before != after:
        raise ValueError("released visualization inputs changed during rendering")
    verification = {"schema": "five_etf_four_portfolio_raster_verification_v1",
                    "baseline_commission_bps_each_way": 1, "baseline_slippage_bps_each_way": 3,
                    "series_ids": [*IDS, "QQQ_buy_and_hold"], "symbols": list(SYMBOLS),
                    "initial_capital": 1000, "no_rebalancing": True, "raster_only": True,
                    "daily_input_arrays_exported": False, "private_input_locators_exported": False,
                    "all_released_guards_unchanged": True, "guard_count": len(before),
                    "saved_report_sha256": digest(args.report), "stage_figures": figures}
    (args.output_dir / "figures_verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
