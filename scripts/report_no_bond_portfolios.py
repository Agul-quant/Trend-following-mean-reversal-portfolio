#!/usr/bin/env python3
"""New five-ETF static portfolios from sealed saved accounts; never market data.

All original portfolios/accounts remain unchanged. Fit examined historical OOS,
then replay identical new weights in all three independent stage accounts.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from trend_portfolio.analytics import (  # noqa: E402
    checked_weights,
    joint_regression,
    optimize_sharpe,
    portfolio_equity,
    returns_from_equity,
)
from trend_portfolio.checkpoint_caps import (  # noqa: E402
    checkpoint_cap_diagnostics,
    optimize_checkpoint_sharpe,
)
from trend_portfolio.cli import _json_safe  # noqa: E402
from trend_portfolio.periods import (  # noqa: E402
    COSTS,
    _row_metrics,
    _validated_stage,
    load_stage_manifest,
)

SYMBOLS = ("GDX", "FXI", "QQQ", "UNG", "FDN")
MODES = ("daily", "weekly", "monthly", "initial", "none")
IDS = (
    "no_bond_daily_capped_max_sharpe",
    "no_bond_weekly_capped_max_sharpe",
    "no_bond_monthly_capped_max_sharpe",
    "no_bond_initial_capped_max_sharpe",
    "no_bond_uncapped_max_sharpe",
    "no_bond_equal_initial",
)
LABELS = (
    "Daily cap fit",
    "Weekly cap fit",
    "Monthly cap fit",
    "Initial cap fit",
    "Uncapped fit",
    "Equal initial",
)
SCHEMA = "five_etf_six_portfolio_comparison_v1"
ORIGINAL_CONFIG = ROOT / "configs/four_portfolios.json"
ORIGINAL_REPORT = ROOT / "reports/four_portfolios_three_periods/report.json"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def verify_release(path, manifest):
    document = json.loads(Path(path).read_text())
    payload = document["payload"]
    if hashlib.sha256(canonical(payload)).hexdigest() != document.get("payload_sha256"):
        raise ValueError("Private release checksum mismatch")
    if payload.get("authorized_saved_path_evaluation") is not True or payload.get(
        "symbols"
    ) != list(SYMBOLS):
        raise ValueError("Five-ETF saved-path scope not authorized")
    sources, files = payload.get("source_file_sha256", {}), payload.get("files", {})
    if len(sources) < 413 or any(files.get(k) != v for k, v in sources.items()):
        raise ValueError("Original 413-file guard missing")
    if payload.get("private_stage_manifest_sha256") != digest(manifest):
        raise ValueError("Unexpected saved-stage manifest")
    if payload.get("original_four_config_sha256") != digest(
        ORIGINAL_CONFIG
    ) or payload.get("original_report_sha256") != digest(ORIGINAL_REPORT):
        raise ValueError("Original financial definitions/results changed")
    required = [
        Path(__file__).resolve(),
        Path(manifest).resolve(),
        ORIGINAL_CONFIG,
        ORIGINAL_REPORT,
        ROOT / "src/trend_portfolio/checkpoint_caps.py",
        ROOT / "src/trend_portfolio/analytics.py",
        ROOT / "src/trend_portfolio/periods.py",
        ROOT / "src/trend_portfolio/cli.py",
    ]
    for stage in json.loads(Path(manifest).read_text())["stages"].values():
        source = Path(stage["input"])
        required.append(
            source if source.is_absolute() else Path(manifest).parent / source
        )
    if any(str(p.resolve()) not in files for p in required):
        raise ValueError("Unsealed implementation or account input")
    for name, expected in files.items():
        source = Path(name)
        if (
            not source.is_absolute()
            or not source.is_file()
            or digest(source) != expected
        ):
            raise ValueError(f"Sealed file changed: {source.name}")
    return payload


def prepare_stages(stages):
    """Validate authentic six-column saved inputs FIRST, then exclude BND exactly."""
    prepared = []
    for stage in stages:
        equity, factors, cash, times, initial, years = _validated_stage(stage)
        if not np.array_equal(cash, np.broadcast_to(cash[0], cash.shape)):
            raise ValueError("Original cash reference differs across costs")
        prepared.append(
            {
                "id": stage["id"],
                "scored_start": stage["scored_start"],
                "scored_end": stage["scored_end"],
                "equity": equity[:, :, :5],
                "factors": factors[:, :, :5],
                "cash": cash,
                "times": times,
                "initial": initial,
                "years": years,
            }
        )
    if {s["id"] for s in prepared} != {
        "development",
        "validation",
        "historical_OOS",
    } or len(prepared) != 3:
        raise ValueError("Exactly three existing stages required")
    return prepared


def fit_models(stage, original_config, progress=lambda **kwargs: None):
    equity, cash, times = stage["equity"], stage["cash"], stage["times"]
    old = next(
        p
        for p in original_config["portfolios"]
        if p["id"] == "initial_capped_max_sharpe"
    )
    incumbent = np.array([old["initial_weights"][s] for s in SYMBOLS])
    incumbent /= incumbent.sum()
    results = {}
    for mode in ("daily", "initial", "none"):
        progress(status="fitting_new_no_bond_portfolio", cap_mode=mode)
        result = optimize_sharpe(
            equity,
            cash[1],
            baseline_index=1,
            cap_mode=mode,
            cap=1 / 3,
            starts=48,
            seed=1729,
        )
        result.update(
            lp_starts=48,
            ftol=1e-12,
            maxiter=2000,
            selected_candidate_source="multistart_solver",
        )
        # Preserve feasible incumbents as candidates, without changing old results.
        if mode in ("initial", "none"):
            candidates = [
                ("original_initial_excluding_BND", incumbent),
                ("new_daily_cap_fit", np.array(results["daily"]["initial_weights"])),
            ]
            if mode == "none":
                candidates.append(
                    (
                        "new_initial_cap_fit",
                        np.array(results["initial"]["initial_weights"]),
                    )
                )
            for name, weights in candidates:
                bound = 1 / 3 if mode == "initial" else 1.0
                checked_weights(weights, 5)
                if weights.max() > bound + 1e-10:
                    continue
                value = _row_metrics(equity[1] @ weights, cash[1], stage["years"])[
                    "cash_excess_sharpe"
                ]
                if np.isfinite(value) and value > result["baseline_cash_excess_sharpe"]:
                    result.update(
                        initial_weights=weights.tolist(),
                        baseline_cash_excess_sharpe=value,
                        selected_candidate_source=name,
                    )
        results[mode] = result
    for mode in ("weekly", "monthly"):
        progress(status="fitting_new_no_bond_portfolio", cap_mode=mode)
        results[mode] = optimize_checkpoint_sharpe(
            equity,
            cash,
            times,
            mode,
            baseline_index=1,
            cap=1 / 3,
            starts=48,
            seed=1729,
            known_weights=results["daily"]["initial_weights"],
        )
    return results


def regression(returns, factors, cash, symbols):
    result = joint_regression(returns, factors, cash)
    coefficients = result.pop("betas")
    return {**result, **{f"beta_{s}": float(x) for s, x in zip(symbols, coefficients)}}


def compare_controls(rows, saved):
    def keyed(values):
        return {
            (r["stage"], r["control_id"], r["slippage_bps_each_way"]): r for r in values
        }

    a, b = keyed(_json_safe(rows)), keyed(saved)
    if set(a) != set(b):
        raise ValueError("Original control identities changed")
    for identity, original in b.items():
        for field, value in original.items():
            actual = a[identity].get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if not np.isclose(actual, value, atol=2e-11, rtol=2e-11):
                    raise ValueError(
                        f"Original control statistic changed: {identity}/{field}"
                    )
            elif actual != value:
                raise ValueError("Original control field changed")


def make_report(stages, results, original_report, release_sha):
    portfolios = []
    for identifier, label, mode in zip(IDS[:5], LABELS[:5], MODES):
        fit = results[mode]
        portfolios.append(
            {
                "id": identifier,
                "label": label,
                "initial_weights": dict(zip(SYMBOLS, fit["initial_weights"])),
                "cap_scope": mode,
                "objective": "cash_excess_sharpe",
                "fit_stage": "historical_OOS",
                "global_optimum_certified": False,
            }
        )
    portfolios.append(
        {
            "id": IDS[-1],
            "label": LABELS[-1],
            "initial_weights": dict.fromkeys(SYMBOLS, 0.2),
            "cap_scope": "none",
            "objective": "equal_initial_comparator",
            "fit_stage": None,
            "global_optimum_certified": False,
        }
    )
    report = {
        "schema": SCHEMA,
        "symbols": list(SYMBOLS),
        "excluded_etfs": ["BND"],
        "portfolios": portfolios,
        "slippage_bps_each_way": list(COSTS),
        "commission_bps_each_way": 1.0,
        "initial_capital_each_stage": 1000,
        "fit_stage": "historical_OOS",
        "fit_baseline_slippage_bps": 3,
        "method": "Static initial sleeve wealth, no rebalancing or transfers. Five new optimized allocations plus equal initial; original frozen portfolios unchanged.",
        "checkpoint_policy": "Last observed New York ISO-week/calendar-month daily valuation; terminal partial period included. Capped fits also cap initial weights. All four costs constrained.",
        "limitations": [
            "Retrospective fitted to already examined historical OOS; not an untouched portfolio test, causal validation, or trading authorization.",
            "All optimized portfolios are numerically best-found, not globally certified; common 48 LP starts, seed1729, analytic-gradient SLSQP.",
            "Weekly/monthly cap applies only at checkpoints and permits intermediate daily breaches; initial cap has no later enforcement.",
            "Weekly and monthly checkpoint sets are not generally nested. No future or intraday cap guarantee.",
            "Objective uses daily full-period cash-excess returns; no weekly/monthly Sharpe resampling and no CAGR floor.",
            "Same new weights replayed unchanged in independent earlier-period accounts; this does not remove post-OOS selection bias.",
            "Cash is 3% nominal ACT/365 event-compounded, not 3% APY. Undefined cash Sharpe is null, not zero.",
            "Embedded original account costs/actions/reinvestment/paid terminal liquidation unchanged; no new trade counts inferred.",
            "BND is removed from both active strategy allocations and active joint passive-factor regressions; historical archives remain unchanged.",
        ],
        "stage_summaries": original_report["stage_summaries"],
        "portfolio_rows": [],
        "control_rows": [dict(r) for r in original_report["control_rows"]],
        "checkpoint_rows": [],
        "QQQ_single_factor_rows": [],
        "five_passive_factor_rows": [],
        "strategy_correlations": [],
        "portfolio_correlations": [],
        "solver_summaries": [
            {"portfolio_id": i, **results[m]} for i, m in zip(IDS[:5], MODES)
        ],
        "source_hashes": {
            "private_input_release": release_sha,
            "original_stage_report": digest(ORIGINAL_REPORT),
            "original_four_portfolio_definitions": digest(ORIGINAL_CONFIG),
        },
        "initial_weight_rebalance_policy": "Allocate once; no rebalancing. Sleeve account capital includes idle cash, not only ETF holdings.",
    }
    recalculated_controls = []
    for stage in stages:
        equity, factors, cash, times, years = (
            stage["equity"],
            stage["factors"],
            stage["cash"],
            stage["times"],
            stage["years"],
        )
        wealths = []
        for p in portfolios:
            weights = checked_weights([p["initial_weights"][s] for s in SYMBOLS], 5)
            wealth = portfolio_equity(equity, weights)
            wealths.append(wealth)
            for ci, cost in enumerate(COSTS):
                identity = {
                    "stage": stage["id"],
                    "portfolio_id": p["id"],
                    "slippage_bps_each_way": cost,
                    "commission_bps_each_way": 1.0,
                }
                report["portfolio_rows"].append(
                    {
                        **identity,
                        "elapsed_act365_years": years,
                        **_row_metrics(wealth[ci], cash[ci], years),
                    }
                )
                for frequency in ("daily", "weekly", "monthly"):
                    diagnostic = checkpoint_cap_diagnostics(
                        equity[ci : ci + 1], weights, times, frequency
                    )
                    d = diagnostic["per_cost"][0]
                    report["checkpoint_rows"].append(
                        {
                            **identity,
                            "checkpoint_frequency": frequency,
                            "cap_fraction": 1 / 3,
                            "checkpoint_count": diagnostic["checkpoint_count"],
                            "initial_cap_pass_diagnostic": diagnostic[
                                "initial_cap_satisfied"
                            ],
                            "checkpoint_cap_pass_diagnostic": d[
                                "checkpoint_cap_satisfied"
                            ],
                            "max_checkpoint_capital_share": d[
                                "checkpoint_max_capital_share"
                            ],
                            "checkpoint_breach_days": d["checkpoint_breach_days"],
                            "max_daily_capital_share": d["daily_max_capital_share"],
                            "daily_breach_days": d["daily_breach_days"],
                            "between_checkpoint_breach_days": d[
                                "between_checkpoint_breach_days"
                            ],
                        }
                    )
                returns = returns_from_equity(wealth[ci])
                report["QQQ_single_factor_rows"].append(
                    {
                        **identity,
                        **regression(returns, factors[ci][:, [2]], cash[ci], ("QQQ",)),
                    }
                )
                report["five_passive_factor_rows"].append(
                    {**identity, **regression(returns, factors[ci], cash[ci], SYMBOLS)}
                )
        for ci, cost in enumerate(COSTS):
            for control, returns in (
                ("QQQ_buy_and_hold", factors[ci, :, 2]),
                ("matched_cash", cash[ci]),
            ):
                recalculated_controls.append(
                    {
                        "stage": stage["id"],
                        "control_id": control,
                        "slippage_bps_each_way": cost,
                        "commission_bps_each_way": 1.0,
                        "elapsed_act365_years": years,
                        **_row_metrics(np.cumprod(1 + returns), cash[ci], years),
                    }
                )
            identity = {
                "stage": stage["id"],
                "slippage_bps_each_way": cost,
                "commission_bps_each_way": 1.0,
            }
            sleeve_returns = returns_from_equity(equity[ci].T).T
            report["strategy_correlations"].append(
                {
                    **identity,
                    "symbols": list(SYMBOLS),
                    "matrix": np.corrcoef(sleeve_returns, rowvar=False).tolist(),
                }
            )
            port_returns = np.column_stack(
                [returns_from_equity(w[ci]) for w in wealths] + [factors[ci, :, 2]]
            )
            report["portfolio_correlations"].append(
                {
                    **identity,
                    "portfolio_ids": list(IDS) + ["QQQ_buy_and_hold"],
                    "matrix": np.corrcoef(port_returns, rowvar=False).tolist(),
                }
            )
    compare_controls(recalculated_controls, original_report["control_rows"])
    expected = {
        "portfolio_rows": 72,
        "control_rows": 24,
        "checkpoint_rows": 216,
        "QQQ_single_factor_rows": 72,
        "five_passive_factor_rows": 72,
        "strategy_correlations": 12,
        "portfolio_correlations": 12,
    }
    if any(len(report[k]) != v for k, v in expected.items()):
        raise ValueError("Five-ETF outcome dimensions changed")
    return _json_safe(report)


def write_outputs(report, directory):
    directory = Path(directory)
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
                labels = record.get("symbols", record.get("portfolio_ids"))
                for i, left in enumerate(labels):
                    for j, right in enumerate(labels):
                        writer.writerow(
                            {
                                k: record[k]
                                for k in (
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
        "schema": "five_etf_fixed_initial_portfolios_v1",
        "symbols": report["symbols"],
        "portfolios": report["portfolios"],
        "scope": report["method"],
        "fit_stage": "historical_OOS",
        "fit_baseline_slippage_bps": 3,
    }
    (directory / "portfolios.json").write_text(
        json.dumps(config, indent=2, allow_nan=False) + "\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--input-release", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        parser.error("Preserve completed/failed attempts; use a new output directory")
    verify_release(args.input_release, args.manifest)
    args.output_dir.mkdir(parents=True, exist_ok=False)

    def progress(**record):
        (args.output_dir / "progress.json").write_text(
            json.dumps(
                {**record, "utc": datetime.now(timezone.utc).isoformat()}, indent=2
            )
            + "\n"
        )

    try:
        progress(status="reading_authorized_saved_accounts_excluding_BND")
        stages = prepare_stages(load_stage_manifest(args.manifest))
        original = json.loads(ORIGINAL_CONFIG.read_text())
        oos = next(s for s in stages if s["id"] == "historical_OOS")
        results = fit_models(oos, original, progress)
        (args.output_dir / "locked_new_fits.json").write_text(
            json.dumps(_json_safe(results), indent=2, allow_nan=False) + "\n"
        )
        progress(status="new_weights_locked_replaying_three_periods")
        report = make_report(
            stages,
            results,
            json.loads(ORIGINAL_REPORT.read_text()),
            digest(args.input_release),
        )
        write_outputs(report, args.output_dir)
        verify_release(args.input_release, args.manifest)
        progress(
            status="completed", portfolio_rows=72, control_rows=24, checkpoint_rows=216
        )
        print(
            json.dumps(
                {
                    "status": "completed",
                    "report_sha256": digest(args.output_dir / "report.json"),
                }
            )
        )
    except Exception as error:
        progress(
            status="failed_preserved", error_type=type(error).__name__, error=str(error)
        )
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
