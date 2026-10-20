#!/usr/bin/env python3
"""Plot every released baseline DAILY return, not wealth or drawdown.

Only the public derived-return CSV release is read. This is a presentation
operation: it does not import the account engine or calculate new model returns.
Install the project's ``plots`` extra, then run this script from any directory.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, PercentFormatter
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STAGES = {
    "development": "2017–2020 development-period portfolio backcast (retrospective)",
    "validation": "2021–2023 validation-period portfolio backcast (retrospective)",
    "historical_OOS": "2024–2026-10-15 portfolio-selection sample (IN-SAMPLE)",
}
OBSERVATIONS = {"development": 1007, "validation": 753, "historical_OOS": 700}
CURVES = {
    "initial_allocation": "Initial allocation; no rebalancing",
    "equal_initial": "Equal weight; no rebalancing",
    "weekly_corrections": "Weekly corrections",
    "monthly_corrections": "Monthly corrections",
    "QQQ_buy_and_hold": "QQQ buy-and-hold",
}
COLORS = ("#2563eb", "#9333ea", "#d97706", "#16a34a", "#6b7280")
RELEASE_SERIES = (
    "initial_allocation",
    "weekly_corrections",
    "monthly_corrections",
    "equal_initial",
    "QQQ_buy_and_hold",
    "matched_cash",
)
COSTS = (1, 3, 10, 25)
BASELINE = 3
HEADER = (
    "stage",
    "date",
    "valuation_timestamp_utc",
    "commission_bps_each_way",
    "slippage_bps_each_way",
    *[f"{key}_return" for key in RELEASE_SERIES],
)
RETURN_FORMULA = "r_t = E_t / E_previous - 1; first denominator is fresh stage capital."


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _public_file(root, name):
    require(isinstance(name, str) and name and "\\" not in name, "Invalid public path")
    relative = PurePosixPath(name)
    require(
        not relative.is_absolute()
        and relative.as_posix() == name
        and not any(
            x in {".", "..", ".cache", "private", "data", ".git"}
            for x in relative.parts
        ),
        "Unsafe public path",
    )
    path = root / name
    require(
        path.is_file()
        and not path.is_symlink()
        and path.resolve() == path.absolute()
        and path.resolve().is_relative_to(root),
        "Missing or symlinked public file",
    )
    return path


def _clock(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("Invalid UTC clock") from exc
    require(
        result.utcoffset() is not None and result.utcoffset().total_seconds() == 0,
        "Clock must be explicit UTC",
    )
    return result


def load_baseline(root, stage):
    """Validate the released four-cost stage and return unaltered baseline data.

    ``returns`` maps the five plotted series IDs to finite decimal-return arrays.
    Dates are the actual released daily valuation clocks, with no initial zero,
    resampling, cash subtraction, interpolation, missing-date fill or clipping.
    The other costs and cash column are validated but not plotted.
    """
    root = Path(root).resolve()
    require(stage in STAGES, "Unknown stage")
    release = json.loads(
        _public_file(root, "reports/reproducibility/manifest.json").read_text()
    )
    require(
        release.get("schema") == "aggregate_daily_returns_release_v1"
        and release.get("derived_returns_only") is True
        and release.get("raw_market_data_published") is False
        and release.get("series") == list(RELEASE_SERIES)
        and release.get("slippage_bps_each_way") == list(COSTS)
        and release.get("commission_bps_each_way") == 1
        and release.get("baseline_slippage_bps_each_way") == BASELINE
        and set(release.get("stages", {})) == set(STAGES),
        "Unexpected derived-return release scope",
    )
    metadata = release["stages"][stage]
    require(
        metadata.get("observations") == OBSERVATIONS[stage],
        "Unexpected observation count",
    )
    source_name = metadata["csv"]
    require(
        source_name == f"reports/reproducibility/{stage}.csv", "Unexpected stage CSV"
    )
    source = _public_file(root, source_name)
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    records = [item for item in release["files"] if item.get("path") == source_name]
    require(
        len(records) == 1
        and records[0].get("sha256") == digest
        and records[0].get("bytes") == len(raw),
        "Released CSV SHA256 or byte count changed",
    )
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        require(
            tuple(reader.fieldnames or ()) == HEADER,
            "Unexpected daily-return CSV header",
        )
        rows = list(reader)
    require(len(rows) == OBSERVATIONS[stage] * len(COSTS), "Incomplete four-cost stage")
    grouped = {cost: [] for cost in COSTS}
    for row in rows:
        require(
            None not in row and all(value is not None for value in row.values()),
            "Malformed CSV row",
        )
        require(
            row["stage"] == stage and row["commission_bps_each_way"] == "1",
            "Stage or commission changed",
        )
        require(
            row["slippage_bps_each_way"] in tuple(map(str, COSTS)), "Unexpected cost"
        )
        t = _clock(row["valuation_timestamp_utc"])
        local = t.astimezone(ZoneInfo("America/New_York"))
        require(
            local.hour == 17
            and local.minute == local.second == local.microsecond == 0
            and local.date().isoformat() == row["date"]
            and metadata["scored_start"] <= row["date"] <= metadata["scored_end"],
            "Invalid daily valuation clock or scored date",
        )
        for series in RELEASE_SERIES:
            value = float(row[f"{series}_return"])
            require(
                math.isfinite(value) and value > -1,
                "Nonfinite or invalid simple return",
            )
        grouped[int(row["slippage_bps_each_way"])].append(row)
    clocks = None
    for cost, cost_rows in grouped.items():
        require(len(cost_rows) == OBSERVATIONS[stage], f"Incomplete {cost}-bp cost")
        actual = tuple(_clock(row["valuation_timestamp_utc"]) for row in cost_rows)
        require(
            all(a < b for a, b in zip(actual, actual[1:])),
            "Duplicate or unordered valuation clocks",
        )
        require(
            actual[0] == _clock(metadata["first_valuation_timestamp_utc"]),
            "First valuation clock changed",
        )
        require(
            actual[-1] == _clock(metadata["terminal_valuation_timestamp_utc"]),
            "Terminal valuation clock changed",
        )
        require(
            _clock(metadata["initial_timestamp_utc"]) < actual[0],
            "Initial account clock is not before first valuation",
        )
        require(
            clocks is None or clocks == actual, "Four cost calendars are not aligned"
        )
        clocks = actual
    baseline = grouped[BASELINE]
    return {
        "stage": stage,
        "dates": clocks,
        "date_strings": tuple(row["date"] for row in baseline),
        "returns": {
            key: np.array([float(row[f"{key}_return"]) for row in baseline])
            for key in CURVES
        },
        "source": source_name,
        "source_sha256": digest,
        "observations": len(baseline),
        "initial_timestamp_utc": metadata["initial_timestamp_utc"],
        "scored_start": metadata["scored_start"],
        "scored_end": metadata["scored_end"],
        "presentation_label": STAGES[stage],
    }


def common_limits(data_by_stage):
    """Symmetric percentage bounds covering every point in all three figures."""
    peak = max(
        float(np.max(np.abs(values))) * 100
        for data in data_by_stage.values()
        for values in data["returns"].values()
    )
    limit = max(2.0, 2 * math.ceil(peak * 1.06 / 2))
    return (-limit, limit)


def _date_ticks(dates):
    first, last = dates[0], dates[-1]
    ticks = [first]
    for year in range(first.year + 1, last.year + 1):
        annual = datetime(year, 1, 1, tzinfo=timezone.utc)
        if first < annual < last and (last - annual).days >= 100:
            ticks.append(annual)
    return ticks + [last]


def render_baseline(data, destination, limits):
    """Render five aligned daily-return stem plots and return their audit record."""
    destination = Path(destination)
    require(destination.is_dir(), "Missing figure destination")
    fig, axes = plt.subplots(
        5, 1, figsize=(12, 10.6), dpi=170, sharex=True, sharey=True
    )
    for ax, (key, label), color in zip(axes, CURVES.items(), COLORS):
        # Separate zero-to-return segments show actual daily observations without
        # connecting across weekends/holidays or implying intervening values.
        ax.vlines(
            data["dates"],
            0,
            data["returns"][key] * 100,
            color=color,
            linewidth=0.65,
            alpha=0.95,
        )
        ax.axhline(0, color="#4b5563", linewidth=0.65, zorder=0)
        ax.set_ylim(*limits)
        ax.yaxis.set_major_locator(MultipleLocator(10))
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
        ax.tick_params(axis="both", labelsize=9)
        ax.grid(axis="y", alpha=0.18)
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["bottom", "left"]].set_color("#d1d5db")
        ax.text(
            0.012,
            0.89,
            label,
            transform=ax.transAxes,
            fontsize=10,
            color=color,
            va="top",
            fontweight="semibold",
        )
    dates = data["dates"]
    axes[-1].set_xlim(dates[0], dates[-1])
    axes[-1].set_xticks(_date_ticks(dates))
    axes[-1].xaxis.set_major_formatter(
        mdates.DateFormatter("%Y-%m-%d", tz=timezone.utc)
    )
    axes[-1].get_xticklabels()[0].set_ha("left")
    axes[-1].get_xticklabels()[-1].set_ha("right")
    axes[-1].set_xlabel("Actual daily valuation dates", fontsize=10, labelpad=10)
    fig.supylabel(
        "Net simple total return per daily valuation interval (%)", fontsize=11, x=0.025
    )
    fig.suptitle(
        "Daily net returns — not cumulative performance",
        fontsize=16,
        fontweight="bold",
        y=0.975,
    )
    fig.text(0.095, 0.937, data["presentation_label"], fontsize=11, color="#111827")
    fig.text(
        0.095,
        0.912,
        f"1-bp commission + 3-bp slippage each way  |  {data['observations']:,} daily observations per series  |  Common scale across all periods",
        fontsize=9,
        color="#4b5563",
    )
    fig.text(
        0.095,
        0.038,
        "All released observations; no smoothing, aggregation, interpolation or clipping. Returns are total, not cash-excess.\nFirst return starts from fresh stage capital; final return includes paid liquidation. Cash: modeled 3% nominal ACT/365.\nETF/rule/weight selection used examined history; earlier backcasts are also retrospective, not untouched portfolio OOS.",
        fontsize=8,
        color="#374151",
        linespacing=1.5,
    )
    fig.subplots_adjust(top=0.89, bottom=0.135, hspace=0.11, left=0.095, right=0.97)
    filename = f"{data['stage']}_daily_returns_baseline.png"
    path = destination / filename
    fig.savefig(
        path, metadata={"Software": "Trend portfolio public daily-return renderer"}
    )
    plt.close(fig)
    return {
        "stage": data["stage"],
        "filename": filename,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "width_px": 2040,
        "height_px": 1802,
        "metadata_keys": ["Software", "dpi"],
        "daily_observations": data["observations"],
        "curves": list(CURVES.values()),
        "public_return_columns": [key + "_return" for key in CURVES],
        "public_return_source": data["source"],
        "public_return_source_sha256": data["source_sha256"],
        "presentation_label": data["presentation_label"],
        "scored_period": [data["scored_start"], data["scored_end"]],
        "first_valuation_timestamp_utc": data["dates"][0].isoformat(),
        "terminal_valuation_timestamp_utc": data["dates"][-1].isoformat(),
        "baseline_slippage_bps_each_way": BASELINE,
        "commission_bps_each_way": 1,
        "return_formula": RETURN_FORMULA,
        "unit": "percent net simple total daily return; not cash-excess",
        "y_limits_percent": list(limits),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    data = {stage: load_baseline(root, stage) for stage in STAGES}
    limits = common_limits(data)
    destination = root / "reports/etf_portfolios"
    manifest_path = _public_file(root, "reports/etf_portfolios/figures_manifest.json")
    manifest = json.loads(manifest_path.read_text())
    # This is additive only: existing wealth/drawdown figures and records remain
    # byte-equivalent when their JSON values are canonically encoded.
    manifest["daily_return_figures"] = {
        "schema": "public_daily_return_raster_figures_v1",
        "renderer": "scripts/build_daily_return_figures.py",
        "rendered_from_public_derived_returns": True,
        "raw_market_data_read": False,
        "saved_financial_results_or_forward_freeze_changed": False,
        "numeric_daily_series_or_private_locators_embedded": False,
        "plot_type": "five vertically stacked zero-to-return daily stems; one series per panel",
        "return_formula": RETURN_FORMULA,
        "unit": "percent net simple total daily return; not cash-excess",
        "aggregation_smoothing_interpolation_clipping": "none",
        "commission_bps_each_way": 1,
        "baseline_slippage_bps_each_way": BASELINE,
        "shared_y_limits_percent": list(limits),
        "figures": {
            stage: render_baseline(item, destination, limits)
            for stage, item in data.items()
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
