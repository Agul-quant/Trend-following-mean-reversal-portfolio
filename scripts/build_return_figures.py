#!/usr/bin/env python3
"""Render existing aggregate return curves; never read private ETF/account data."""

from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
STAGES = {
    "development": "2017–2020 development-period portfolio backcast (retrospective)",
    "validation": "2021–2023 validation-period portfolio backcast (retrospective)",
    "historical_OOS": "2024–2026-10-15 portfolio-selection sample (IN-SAMPLE)",
}
CURVES = {
    "initial_allocation": "Initial allocation; no rebalancing",
    "equal_initial": "Equal weight; no rebalancing",
    "weekly_corrections": "Weekly corrections",
    "monthly_corrections": "Monthly corrections",
    "QQQ_buy_and_hold": "QQQ buy-and-hold",
}


def main():
    release = json.loads((ROOT / "reports/reproducibility/manifest.json").read_text())
    destination = ROOT / "reports/etf_portfolios"
    manifest_path = destination / "figures_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["curve_names"] = list(CURVES.values())
    for stage, title in STAGES.items():
        source = ROOT / release["stages"][stage]["csv"]
        with source.open(newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["slippage_bps_each_way"] == "3"]
        dates = [
            datetime.fromisoformat(release["stages"][stage]["initial_timestamp_utc"])
        ]
        dates += [datetime.fromisoformat(r["valuation_timestamp_utc"]) for r in rows]
        fig, axes = plt.subplots(
            2,
            1,
            figsize=(12, 7.8),
            dpi=170,
            sharex=True,
            gridspec_kw={"height_ratios": [2.1, 1]},
        )
        colors = ["#2563eb", "#9333ea", "#d97706", "#16a34a", "#6b7280"]
        for (key, label), color in zip(CURVES.items(), colors):
            equity = 1000 * np.cumprod(
                [1] + [1 + float(r[key + "_return"]) for r in rows]
            )
            dd = equity / np.maximum.accumulate(equity) - 1
            axes[0].plot(dates, equity, label=label, color=color, linewidth=1.5)
            axes[1].plot(dates, dd * 100, color=color, linewidth=1.2)
        axes[0].set_ylabel("Portfolio wealth (USD; initial 1,000)")
        axes[1].set_ylabel("Daily drawdown (%)")
        axes[0].legend(loc="upper left", frameon=False, fontsize=9)
        for ax in axes:
            ax.grid(alpha=0.2)
            ax.spines[["top", "right"]].set_visible(False)
        axes[1].xaxis.set_major_formatter(
            mdates.ConciseDateFormatter(axes[1].xaxis.get_major_locator())
        )
        fig.suptitle(title, fontsize=13, fontweight="bold", y=0.97)
        fig.text(
            0.08,
            0.023,
            "Net of 1-bp commission + 3-bp slippage each way • Cash: modeled 3% nominal ACT/365\nFinal ETF/rule/weight selection used examined history; these are not untouched portfolio OOS results.",
            fontsize=8,
            color="#374151",
        )
        fig.subplots_adjust(top=0.90, bottom=0.13, hspace=0.1, left=0.095, right=0.97)
        filename = f"{stage}_baseline.png"
        fig.savefig(
            destination / filename,
            metadata={"Software": "Trend portfolio public-return renderer"},
        )
        plt.close(fig)
        item = manifest["figures"][stage]
        item.update(
            curves=list(CURVES.values()),
            public_return_columns=[key + "_return" for key in CURVES],
            sha256=hashlib.sha256((destination / filename).read_bytes()).hexdigest(),
            presentation_label=title,
            public_return_source=release["stages"][stage]["csv"],
            public_return_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        )
    manifest["rendered_from_public_derived_returns"] = True
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
