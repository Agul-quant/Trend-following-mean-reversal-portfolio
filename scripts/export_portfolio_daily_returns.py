#!/usr/bin/env python3
"""Export authorized derived aggregate returns from existing private saved accounts.

Reporting only: never runs a strategy/account engine, optimizer or downloader.
Private inputs are explicit CLI arguments, not dependencies of the public verifier.
Do not pass raw ETF prices: the inputs must be saved portfolio/sleeve wealth and
matched control returns. Extra saved sleeves are never exported or used.
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
from trend_portfolio.return_verification import (  # noqa: E402
    COSTS,
    HEADER,
    METRICS,
    SCHEMA,
    SERIES,
    STAGES,
    assert_close,
    elapsed_years,
    read_json,
    recompute,
    require,
    verify_release,
)

SYMBOLS = ["GDX", "FXI", "QQQ", "UNG", "FDN"]
FREQUENCIES = {
    "initial_allocation": "none",
    "weekly_corrections": "weekly",
    "monthly_corrections": "monthly",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def saved_returns(equity, initial=1.0):
    equity = np.asarray(equity, dtype=float)
    require(
        equity.ndim == 1 and np.isfinite(equity).all() and (equity > 0).all(),
        "Invalid saved account wealth",
    )
    return equity / np.r_[float(initial), equity[:-1]] - 1


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-manifest", type=Path, required=True)
    parser.add_argument("--account-root", type=Path, required=True)
    parser.add_argument("--equal-reference", type=Path, required=True)
    parser.add_argument(
        "--receipt",
        type=Path,
        required=True,
        help="New ignored .cache receipt; contains private input provenance",
    )
    args = parser.parse_args()
    require(
        args.receipt.resolve().is_relative_to((ROOT / ".cache").resolve()),
        "Receipt must stay private in .cache",
    )
    output = ROOT / "reports/reproducibility"
    stats_json = ROOT / "reports/etf_portfolios/statistical_comparison.json"
    stats_csv = stats_json.with_suffix(".csv")
    destinations = [output / f"{s}.csv" for s in STAGES] + [
        output / "manifest.json",
        stats_json,
        stats_csv,
        args.receipt,
    ]
    require(
        not any(p.exists() for p in destinations),
        "Refuse to overwrite an existing release/receipt",
    )
    original = ROOT / "reports/etf_portfolios/report.json"
    guards = {
        p.resolve(): digest(p)
        for p in (original, args.stage_manifest, args.equal_reference)
    }
    historical = read_json(original)
    equal_reference = read_json(args.equal_reference)
    require(
        equal_reference["symbols"] == SYMBOLS and historical["symbols"] == SYMBOLS,
        "Saved five-ETF identity mismatch",
    )
    equal_candidates = [
        p
        for p in equal_reference["portfolios"]
        if p["initial_weights"] == dict.fromkeys(SYMBOLS, 0.2)
    ]
    require(
        len(equal_candidates) == 1,
        "Exactly one frozen equal-initial comparator is required",
    )
    equal_id = equal_candidates[0]["id"]
    equal_rows = {
        (r["stage"], int(r["slippage_bps_each_way"])): r
        for r in equal_reference["portfolio_rows"]
        if r["portfolio_id"] == equal_id
    }
    require(len(equal_rows) == 12, "Frozen equal-initial comparator incomplete")
    stage_manifest = read_json(args.stage_manifest)["stages"]
    require(set(stage_manifest) == set(STAGES), "Unexpected saved stage scope")
    all_stats, public_stages, csv_payloads = [], {}, {}
    for stage in STAGES:
        stage_info = stage_manifest[stage]
        bundle_path = Path(stage_info["input"])
        guards[bundle_path.resolve()] = digest(bundle_path)
        with np.load(bundle_path, allow_pickle=False) as bundle:
            # Assert positional identities before selecting ONLY the five active sleeves.
            require(
                bundle["symbols"].tolist()[:5] == SYMBOLS
                and len(set(bundle["symbols"].tolist())) == len(bundle["symbols"]),
                "Saved positional ETF identities mismatch",
            )
            require(
                bundle["slippage_bps"].tolist() == list(COSTS), "Saved costs mismatch"
            )
            timestamps = bundle["timestamps"].tolist()
            sleeve = bundle["sleeve_normalized_equity"][:, :, :5].copy()
            bh = bundle["buy_and_hold_returns"][:, :, SYMBOLS.index("QQQ")].copy()
            cash = bundle["cash_returns"].copy()
        require(
            sleeve.shape == (4, len(timestamps), 5)
            and bh.shape == (4, len(timestamps))
            and cash.shape == (len(timestamps),),
            "Saved bundle dimensions mismatch",
        )
        years = elapsed_years(stage_info["initial_timestamp"], timestamps[-1])
        public_stages[stage] = {
            "csv": f"reports/reproducibility/{stage}.csv",
            "scored_start": stage_info["scored_start"],
            "scored_end": stage_info["scored_end"],
            "initial_timestamp_utc": stage_info["initial_timestamp"],
            "first_valuation_timestamp_utc": timestamps[0],
            "terminal_valuation_timestamp_utc": timestamps[-1],
            "elapsed_act365_years": years,
            "observations": len(timestamps),
            "presentation_label": {
                "development": "2017–2020 retrospective development sample",
                "validation": "2021–2023 retrospective validation sample",
                "historical_OOS": "2024–2026 retrospective portfolio-selection sample (in-sample)",
            }[stage],
        }
        daily_rows = []
        for cost_index, cost in enumerate(COSTS):
            values = {
                "equal_initial": saved_returns(sleeve[cost_index].mean(axis=1)),
                "QQQ_buy_and_hold": bh[cost_index],
                "matched_cash": cash,
            }
            for name, frequency in FREQUENCIES.items():
                folder = (
                    "baseline_attempt1" if frequency == "none" else "models_attempt1"
                )
                path = (
                    args.account_root
                    / folder
                    / f"{stage}_{frequency}_{cost}bp/paths.npz"
                )
                guards[path.resolve()] = digest(path)
                with np.load(path, allow_pickle=False) as saved:
                    require(
                        saved["symbols"].tolist() == SYMBOLS,
                        "Account ETF identities mismatch",
                    )
                    require(
                        saved["timestamps"].tolist() == timestamps,
                        "Saved account calendars mismatch",
                    )
                    require(
                        np.allclose(
                            saved["initial_weights"],
                            [historical["initial_weights"][s] for s in SYMBOLS],
                            rtol=0,
                            atol=0,
                        ),
                        "Saved exact initial weights mismatch",
                    )
                    values[name] = saved_returns(
                        saved["portfolio_equity"], initial=1000
                    )
                    require(
                        np.allclose(
                            saved_returns(saved["cash_reference"], initial=1000),
                            cash,
                            rtol=0,
                            atol=3e-14,
                        ),
                        "Saved matched cash mismatch",
                    )
            for name in SERIES:
                computed = recompute(values[name], cash, years)
                if name == "equal_initial":
                    target = equal_rows[(stage, cost)]
                    for metric in (
                        "observations",
                        "cash_excess_sharpe",
                        "cagr",
                        "max_drawdown",
                        "terminal_normalized_equity",
                    ):
                        assert_close(
                            computed[metric],
                            target[metric],
                            f"Frozen equal-initial {stage} {cost} {metric}",
                        )
                row = {
                    "stage": stage,
                    "series": name,
                    "commission_bps_each_way": 1,
                    "slippage_bps_each_way": cost,
                    "elapsed_act365_years": years,
                    **computed,
                }
                if name in FREQUENCIES:
                    target = next(
                        r
                        for r in historical["rows"]
                        if r["stage"] == stage
                        and r["slippage_bps"] == cost
                        and r["frequency"] == FREQUENCIES[name]
                    )
                    row.update(
                        mean_etf_exposure=target["mean_etf_exposure"],
                        strategy_round_trips=target["strategy_round_trips"],
                    )
                all_stats.append(row)
            for t, stamp in enumerate(timestamps):
                daily_rows.append(
                    [
                        stage,
                        stamp[:10],
                        stamp,
                        1,
                        cost,
                        *[format(float(values[name][t]), ".17g") for name in SERIES],
                    ]
                )
        csv_payloads[stage] = daily_rows
    # All provenance and numerical checks complete before creating public outputs.
    for path, expected in guards.items():
        require(
            digest(path) == expected, "An original saved source changed during export"
        )
    output.mkdir(parents=True, exist_ok=True)
    for stage, rows in csv_payloads.items():
        with (output / f"{stage}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(HEADER)
            writer.writerows(rows)
    statistics_report = {
        "schema": "aggregate_return_statistical_comparison_v1",
        "interpretation": "Descriptive retrospective comparison. All allocations/rules inherit examined history; not untouched portfolio OOS.",
        "equal_initial_definition": "20% to each of the same five fixed strategy sleeves once at stage start; capital then drifts, with no rebalancing.",
        "inference": {
            "quantity": "t-statistic for the mean daily net portfolio return minus matched cash return, not regression alpha",
            "iid": "mean(excess)/(sample_sd(excess)/sqrt(n)); also cash_excess_sharpe*sqrt(n/252)",
            "hac": "Intercept-only Bartlett Newey–West variance with HC1 n/(n-1) scaling; no factor regression",
            "lag_rule": "min(n-1, floor(4*(n/100)^(2/9))); fixed sample-size rule, not fit to t-statistic",
            "sensitivity_lags": "0,5,10,20 and primary lag, deduplicated and bounded by n-1",
            "limitations": "No p-value or investment-significance claim. HAC addresses some serial dependence, not ETF/rule/weight selection, multiple testing, structural breaks or small trade counts.",
        },
        "rows": all_stats,
    }
    write_json(stats_json, statistics_report)
    columns = [
        "stage",
        "series",
        "commission_bps_each_way",
        "slippage_bps_each_way",
        "elapsed_act365_years",
        *METRICS,
    ]
    with stats_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=columns, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(all_stats)
    file_names = [f"reports/reproducibility/{s}.csv" for s in STAGES] + [
        stats_json.relative_to(ROOT).as_posix(),
        stats_csv.relative_to(ROOT).as_posix(),
    ]
    manifest = {
        "schema": SCHEMA,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "derived_returns_only": True,
        "raw_market_data_published": False,
        "series": list(SERIES),
        "symbols": SYMBOLS,
        "commission_bps_each_way": 1,
        "slippage_bps_each_way": list(COSTS),
        "baseline_slippage_bps_each_way": 3,
        "daily_rows": sum(len(r) for r in csv_payloads.values()),
        "stages": public_stages,
        "statistics_json": stats_json.relative_to(ROOT).as_posix(),
        "statistics_csv": stats_csv.relative_to(ROOT).as_posix(),
        "historical_aggregate_report": "reports/etf_portfolios/report.json",
        "return_definition": "Net simple total portfolio return E_t/E_previous-1; first denominator is fresh stage capital, not first daily close. Strategy/cap/terminal costs and distributions are already embedded.",
        "valuation_clock": "Saved daily valuation is 17:00 America/New_York, represented in UTC. First return starts at initial eligible open; gaps include overnight/weekend cash accrual. Final return includes paid terminal liquidation.",
        "wealth_reconstruction": "Start normalized wealth1 before first row and compound product(1+r). No equity levels, prices, holdings or sleeve paths are exported.",
        "cash_convention": "3% nominal ACT/365 event-compounded; matched cash daily returns, not constant3%/252 and not3%APY.",
        "metrics": "Sharpe uses sqrt252 mean daily net excess/sample SD ddof1. CAGR uses exact elapsed ACT/365 clocks. Max drawdown includes initial wealth1.",
        "model_scope": "Three unchanged saved models plus equal-initial static comparator. Equal initial is not equal-weight rebalancing and does not remove ETF/rule-selection bias.",
        "in_sample_notice": "The internal stage historical_OOS is retained for compatibility only; 2024–2026 is portfolio-selection in-sample, not untouched portfolio OOS. Earlier periods are retrospective diagnostics of the final chosen portfolio.",
        "files": [
            {
                "path": name,
                "bytes": (ROOT / name).stat().st_size,
                "sha256": digest(ROOT / name),
            }
            for name in file_names
        ],
    }
    write_json(output / "manifest.json", manifest)
    verification = verify_release(ROOT)
    require(
        digest(original) == guards[original.resolve()],
        "Original historical report was changed",
    )
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        args.receipt,
        {
            "public_release": "reports/reproducibility/manifest.json",
            "verification": verification,
            "saved_input_guards": [
                {"path": str(p), "sha256": h} for p, h in guards.items()
            ],
            "saved_equal_initial_aggregate_rows_verified": 12,
            "all_saved_sources_unchanged": all(
                digest(p) == h for p, h in guards.items()
            ),
        },
    )
    print(json.dumps(verification, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
