"""Raster-only views of fixed saved portfolio and passive benchmark paths.

No optimizer, trading-engine run, new costs or cash adjustment occurs here.
Private numerical daily paths stay in memory and are never exported as arrays.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .analytics import portfolio_equity
from .cli import load_bundle, load_portfolios


_LABELS = {
    "daily_capped_max_sharpe": "Daily-capped max Sharpe (current)",
    "initial_capped_max_sharpe": "Initial-only capped max Sharpe",
    "uncapped_max_sharpe": "Uncapped max Sharpe",
    "equal_initial": "Equal initial allocation",
    "max_cagr_100pct_gdx": "Max CAGR: 100% GDX strategy",
}


@dataclass(frozen=True)
class PlotData:
    """Private in-memory plot inputs. Do not serialize the daily numerical arrays."""

    timestamps: tuple[datetime, ...]
    series_ids: tuple[str, ...]
    labels: tuple[str, ...]
    equity: np.ndarray  # (initial + daily valuations, portfolios + passive benchmark)
    drawdown: np.ndarray
    baseline_slippage: float
    initial_capital: float
    benchmark_symbol: str


def _instant(value: Any) -> datetime:
    if isinstance(value, datetime):
        instant = value
    else:
        try:
            instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("plot timestamps must be ISO-8601 instants") from error
    if instant.tzinfo is None:
        raise ValueError("plot timestamps must have an explicit UTC offset")
    return instant.astimezone(timezone.utc)


def prepare_plot_data(
    bundle: dict[str, np.ndarray],
    portfolios: list[dict[str, Any]],
    *,
    initial_timestamp: str | datetime,
    initial_capital: float = 1000,
    baseline_slippage: float = 3,
    benchmark_symbol: str = "QQQ",
) -> PlotData:
    """Mix saved normalized WEALTH; append matched passive benchmark wealth.

    The independent initial capital point precedes the first net return, so first
    transaction costs and initial-to-first loss remain visible in drawdown.
    Paid terminal liquidation stays in the final saved valuation.
    """
    if not np.isfinite(initial_capital) or initial_capital <= 0:
        raise ValueError("initial capital must be finite and positive")
    costs = np.asarray(bundle["slippage_bps"], dtype=float)
    if costs.ndim != 1 or not np.isfinite(baseline_slippage):
        raise ValueError("baseline slippage must be a finite cost-axis value")
    baseline_matches = np.flatnonzero(costs == baseline_slippage)
    if len(baseline_matches) != 1:
        raise ValueError("baseline slippage must identify exactly one input cost")
    baseline = int(baseline_matches[0])
    symbols = np.asarray(bundle["symbols"]).astype(str).tolist()
    if symbols.count(benchmark_symbol) != 1:
        raise ValueError("passive benchmark must identify exactly one input symbol")
    equity = np.asarray(bundle["sleeve_normalized_equity"], dtype=float)
    factors = np.asarray(bundle["buy_and_hold_returns"], dtype=float)
    if equity.ndim != 3 or factors.shape != equity.shape or equity.shape[0] != len(costs):
        raise ValueError("saved sleeve equity and passive returns must share cost,time,sleeve axes")
    if equity.shape[2] != len(symbols):
        raise ValueError("symbols must match the sleeve axis")
    times = tuple(_instant(value) for value in bundle["timestamps"])
    initial = _instant(initial_timestamp)
    if len(times) != equity.shape[1] or not times or initial >= times[0]:
        raise ValueError("initial timestamp must precede all matching saved daily valuations")
    if any(left >= right for left, right in zip(times, times[1:])):
        raise ValueError("daily valuations must be unique and strictly increasing")
    if not portfolios:
        raise ValueError("at least one fixed portfolio is required")
    normalized_paths = []
    ids = []
    labels = []
    for portfolio in portfolios:
        identifier = portfolio["id"]
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("portfolio ids must be nonempty strings")
        ids.append(identifier)
        labels.append(_LABELS.get(identifier, identifier.replace("_", " ")))
        normalized_paths.append(portfolio_equity(equity[baseline], portfolio["initial_weights"]))
    if len(set(ids)) != len(ids):
        raise ValueError("portfolio ids must be unique")
    passive = factors[baseline, :, symbols.index(benchmark_symbol)]
    if not np.isfinite(passive).all() or np.any(passive <= -1):
        raise ValueError("passive benchmark returns must be finite simple returns greater than -1")
    # Passive factor returns already embed the identical one-way entry/exit costs.
    # Never replace them with the active QQQ strategy, or charge costs twice.
    passive_equity = np.cumprod(1 + passive)
    if not np.isfinite(passive_equity).all() or np.any(passive_equity <= 0):
        raise ValueError("passive benchmark cumulative wealth must remain finite and positive")
    normalized_paths.append(passive_equity)
    ids.append(f"{benchmark_symbol}_buy_and_hold")
    labels.append(f"{benchmark_symbol} buy-and-hold")
    paths = initial_capital * np.vstack([np.ones(len(ids)), np.column_stack(normalized_paths)])
    peaks = np.maximum.accumulate(paths, axis=0)
    drawdown = paths / peaks - 1
    return PlotData(
        timestamps=(initial, *times), series_ids=tuple(ids), labels=tuple(labels),
        equity=paths, drawdown=drawdown, baseline_slippage=float(baseline_slippage),
        initial_capital=float(initial_capital), benchmark_symbol=benchmark_symbol,
    )


def render_plots(data: PlotData, output_dir: Path, *, commission_bps: float = 1) -> dict[str, Path]:
    """Write exactly two new raster PNGs; refuse to overwrite earlier attempts.

    ``commission_bps`` labels the already embedded input cost; it is not charged
    here. PNG metadata contains only a generic Software label and resolution.
    """
    if not np.isfinite(commission_bps) or commission_bps < 0:
        raise ValueError("commission label must be finite and nonnegative")
    if (data.equity.shape != data.drawdown.shape
            or data.equity.shape != (len(data.timestamps), len(data.series_ids))
            or len(data.labels) != len(data.series_ids)):
        raise ValueError("plot arrays must match the time and series axes")
    output_dir = Path(output_dir)
    targets = {"equity": output_dir / "baseline_equity.png", "drawdown": output_dir / "baseline_drawdown.png"}
    if any(path.exists() for path in targets.values()):
        raise ValueError("plot outputs already exist; choose a new attempt directory")
    # Matplotlib is optional for numeric/CLI users; load only for rendering.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.ticker import FuncFormatter, PercentFormatter

    colors = ["#0072B2", "#E69F00", "#009E73", "#8C5AA8", "#D55E00"]
    line_styles = ["-", (0, (6, 2)), (0, (2, 2)), "-.", (0, (8, 2, 2, 2))]
    output_dir.mkdir(parents=True, exist_ok=True)
    with matplotlib.rc_context({"path.simplify": False}):
        for kind, values in (("equity", data.equity), ("drawdown", data.drawdown)):
            figure = Figure(figsize=(12, 7.2), dpi=160, facecolor="white")
            FigureCanvasAgg(figure)
            # Leave room beyond the final centered date label at README width.
            axes = figure.add_axes([.09, .27, .83, .53])
            for index, label in enumerate(data.labels):
                benchmark = index == len(data.labels) - 1
                axes.plot(data.timestamps, values[:, index], label=label,
                          color="#262626" if benchmark else colors[index % len(colors)],
                          linestyle=(0, (5, 3)) if benchmark else line_styles[index % len(line_styles)],
                          linewidth=2.35 if benchmark or index == 0 else 1.95,
                          zorder=5 if benchmark else (4 if index == 0 else 2), alpha=.96)
            axes.set_facecolor("white")
            axes.grid(axis="y", color="#D9DEE3", linewidth=.7)
            axes.spines[["top", "right"]].set_visible(False)
            axes.spines[["left", "bottom"]].set_color("#87929C")
            axes.tick_params(axis="both", labelsize=12)
            ticks = [data.timestamps[0]]
            first_year = data.timestamps[0].year
            last_year = data.timestamps[-1].year
            for year in range(first_year, last_year + 1):
                for month in (1, 7):
                    tick = datetime(year, month, 1, tzinfo=timezone.utc)
                    if data.timestamps[0] < tick < data.timestamps[-1]:
                        ticks.append(tick)
            ticks.append(data.timestamps[-1])
            # Endpoints are explicit, not silently rounded away by auto-date locators.
            axes.set_xticks(ticks)
            axes.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d", tz=timezone.utc))
            axes.set_xlim(data.timestamps[0], data.timestamps[-1])
            axes.tick_params(axis="x", labelrotation=0)
            if kind == "equity":
                axes.set_ylabel("Account value (USD)", fontsize=13, labelpad=10)
                axes.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"${value:,.0f}"))
                axes.set_ylim(bottom=0)
                title = f"Equity curves: {len(data.labels) - 1} fixed portfolios vs {data.benchmark_symbol}"
                description = f"${data.initial_capital:,.0f} initial capital · linear scale · saved net daily valuations"
            else:
                axes.set_ylabel("Drawdown from prior daily peak", fontsize=13, labelpad=10)
                axes.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
                lower = min(-.01, float(values.min()) * 1.08)
                axes.set_ylim(lower, 0)
                title = f"Daily drawdowns: {len(data.labels) - 1} fixed portfolios vs {data.benchmark_symbol}"
                description = "Signed daily peak-to-trough loss · includes the initial capital point"
            figure.text(.09, .94, title, fontsize=20, weight="bold", color="#172B3A")
            figure.text(.09, .89, description, fontsize=12.5, color="#415264")
            figure.text(.09, .845,
                        f"Baseline costs already included: {commission_bps:g}-bp commission + {data.baseline_slippage:g}-bp slippage each way",
                        fontsize=12, color="#415264")
            handles, labels = axes.get_legend_handles_labels()
            figure.legend(handles, labels, loc="lower center", bbox_to_anchor=(.53, .07),
                          ncol=2, frameon=False, fontsize=11.5, handlelength=3.1,
                          columnspacing=2, labelspacing=.75)
            figure.text(.09, .025,
                        "Retrospective selection and fitting; not untouched portfolio OOS. Static initial allocation; no cross-sleeve rebalancing.",
                        fontsize=10.2, color="#526170")
            # No PDF/SVG, serialized curves, local path or timestamp metadata.
            figure.savefig(targets[kind], format="png", dpi=160, facecolor="white",
                           metadata={"Software": "Trend Following Study"})
            figure.clear()
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Private saved-path NPZ; not committed")
    parser.add_argument("--portfolios", required=True, type=Path, help="Fixed allocation JSON; no refitting")
    parser.add_argument("--output-dir", required=True, type=Path, help="New attempt directory for two raster PNGs")
    parser.add_argument("--initial-timestamp", required=True, help="Timezone-aware stage start before the first daily valuation")
    parser.add_argument("--initial-capital", type=float, default=1000)
    parser.add_argument("--baseline-slippage", type=float, default=3)
    parser.add_argument("--commission-bps", type=float, default=1, help="Already embedded commission label, not an additional charge")
    args = parser.parse_args(argv)
    try:
        bundle = load_bundle(args.input)
        portfolios = load_portfolios(args.portfolios, bundle["symbols"].tolist())
        data = prepare_plot_data(bundle, portfolios, initial_timestamp=args.initial_timestamp,
                                 initial_capital=args.initial_capital, baseline_slippage=args.baseline_slippage)
        render_plots(data, args.output_dir, commission_bps=args.commission_bps)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))
    return 0
