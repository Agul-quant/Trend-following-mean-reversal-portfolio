"""Synthetic arithmetic/negative fixtures plus the explicitly released return tables.

These tests never load private accounts, prices or market-data files.
"""

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

import pytest
from trend_portfolio import return_verification as v

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def test_hand_compounding_first_return_and_initial_peak():
    result = v.recompute([-0.1, 0.1, 0.2], [0, 0, 0], 2)
    assert result["terminal_normalized_equity"] == pytest.approx(1.188)
    assert result["cagr"] == pytest.approx(math.sqrt(1.188) - 1)
    assert result["max_drawdown"] == pytest.approx(-0.1)
    excess = [-0.1, 0.1, 0.2]
    assert result["cash_excess_sharpe"] == pytest.approx(
        math.sqrt(252) * statistics.mean(excess) / statistics.stdev(excess)
    )
    assert result["iid_mean_excess_t"] == pytest.approx(
        result["cash_excess_sharpe"] * math.sqrt(3 / 252)
    )


def test_cash_excess_is_not_total_return_or_benchmark_excess():
    result = v.recompute([0.01, 0.02, -0.01], [0.002, 0.003, 0.004], 1)
    excess = [0.008, 0.017, -0.014]
    assert result["cash_excess_sharpe"] == pytest.approx(
        math.sqrt(252) * statistics.mean(excess) / statistics.stdev(excess)
    )
    assert result["cagr"] == pytest.approx(1.01 * 1.02 * 0.99 - 1)


def test_cash_has_undefined_excess_statistic_not_zero():
    result = v.recompute([0.001, 0.002, 0.003], [0.001, 0.002, 0.003], 1)
    assert result["cash_excess_sharpe"] is None
    assert result["iid_mean_excess_t"] is None
    assert result["newey_west_mean_excess_t"] is None
    assert all(row["mean_excess_t"] is None for row in result["newey_west_sensitivity"])


def test_hac_lag_zero_is_exact_iid_and_hand_bartlett_variance():
    x = [0.01, 0.03, 0.02, -0.02, -0.01, 0.04]
    mean = statistics.mean(x)
    n = len(x)
    assert v.mean_excess_t(x, 0) == pytest.approx(
        mean / (statistics.stdev(x) / math.sqrt(n))
    )
    centered = [r - mean for r in x]
    # Independent full covariance-kernel quadratic form, not the implementation loop.
    lag = 2
    meat = sum(
        centered[i] * centered[j] * max(0, 1 - abs(i - j) / (lag + 1))
        for i in range(n)
        for j in range(n)
    )
    se = math.sqrt(meat / (n * (n - 1)))
    assert v.mean_excess_t(x, lag) == pytest.approx(mean / se)


@pytest.mark.parametrize("n,lag", [(2, 1), (700, 6), (753, 6), (1007, 6)])
def test_predeclared_hac_sample_size_rule(n, lag):
    assert v.newey_west_lags(n) == lag


def test_exact_act365_clock_not_number_of_rows():
    assert v.elapsed_years(
        "2024-01-02T14:30:00+00:00", "2026-10-15T21:00:00+00:00"
    ) == pytest.approx(2.7870433789954334)


@pytest.mark.parametrize(
    "returns,cash,years",
    [
        ([0], [0], 1),
        ([0, float("nan")], [0, 0], 1),
        ([0, float("inf")], [0, 0], 1),
        ([-1, 0], [0, 0], 1),
        ([-1.1, 0], [0, 0], 1),
        ([0, 0], [0], 1),
        ([0, 0], [-1, 0], 1),
        ([0, 0], [0, 0], 0),
        ([0, 0], [0, 0], float("nan")),
    ],
)
def test_invalid_return_inputs_rejected(returns, cash, years):
    with pytest.raises(ValueError):
        v.recompute(returns, cash, years)


@pytest.mark.parametrize(
    "value", ["2024-01-01", "2024-01-01T00:00:00-05:00", "nonsense", None]
)
def test_non_utc_or_missing_timestamp_rejected(value):
    with pytest.raises(ValueError):
        v.utc_clock(value)


def refresh(root, manifest):
    for record in manifest["files"]:
        raw = (root / record["path"]).read_bytes()
        record.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    write_json(root / "reports/reproducibility/manifest.json", manifest)


@pytest.fixture
def synthetic(tmp_path):
    """Tiny independent three-stage/four-cost release: no real market observations."""
    stage_info, rows, aggregate_rows, controls, file_names = {}, [], [], [], []
    for k, stage in enumerate(v.STAGES):
        initial = datetime(2017 + 4 * k, 1, 1, tzinfo=timezone.utc)
        clocks = [(initial + timedelta(days=d)).isoformat() for d in range(1, 7)]
        years = v.elapsed_years(initial.isoformat(), clocks[-1])
        path = f"reports/reproducibility/{stage}.csv"
        file_names.append(path)
        stage_info[stage] = {
            "csv": path,
            "initial_timestamp_utc": initial.isoformat(),
            "first_valuation_timestamp_utc": clocks[0],
            "terminal_valuation_timestamp_utc": clocks[-1],
            "elapsed_act365_years": years,
            "observations": 6,
            "scored_start": initial.date().isoformat(),
            "scored_end": clocks[-1][:10],
        }
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        with (tmp_path / path).open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(v.HEADER)
            for cost in v.COSTS:
                values = {
                    name: [0.003 + j * 0.0001, -0.002, 0.001, 0.002, -0.001, 0.004]
                    for j, name in enumerate(v.SERIES)
                }
                values["matched_cash"] = [0.0001] * 6
                for t, clock in enumerate(clocks):
                    writer.writerow(
                        [
                            stage,
                            clock[:10],
                            clock,
                            1,
                            cost,
                            *[values[s][t] for s in v.SERIES],
                        ]
                    )
                for name in v.SERIES:
                    computed = v.recompute(values[name], values["matched_cash"], years)
                    row = {
                        "stage": stage,
                        "series": name,
                        "slippage_bps_each_way": cost,
                        **computed,
                    }
                    rows.append(row)
                    core = {"stage": stage, "slippage_bps": cost, **computed}
                    if name in v.SERIES[:3]:
                        aggregate_rows.append(
                            {
                                **core,
                                "frequency": {
                                    "initial_allocation": "none",
                                    "weekly_corrections": "weekly",
                                    "monthly_corrections": "monthly",
                                }[name],
                            }
                        )
                    elif name == "QQQ_buy_and_hold":
                        controls.append({**core, "control": name})
                    elif name == "matched_cash" and cost == 1:
                        controls.append(
                            {**core, "slippage_bps": None, "control": "cash"}
                        )
    stats_json = "reports/etf_portfolios/statistical_comparison.json"
    stats_csv = "reports/etf_portfolios/statistical_comparison.csv"
    file_names += [stats_json, stats_csv]
    write_json(
        tmp_path / stats_json,
        {"schema": "aggregate_return_statistical_comparison_v1", "rows": rows},
    )
    with (tmp_path / stats_csv).open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["stage", "series", "slippage_bps_each_way", *v.METRICS],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)
    aggregate = "reports/etf_portfolios/report.json"
    write_json(tmp_path / aggregate, {"rows": aggregate_rows, "controls": controls})
    manifest = {
        "schema": v.SCHEMA,
        "derived_returns_only": True,
        "series": list(v.SERIES),
        "commission_bps_each_way": 1,
        "slippage_bps_each_way": list(v.COSTS),
        "stages": stage_info,
        "statistics_json": stats_json,
        "statistics_csv": stats_csv,
        "historical_aggregate_report": aggregate,
        "files": [{"path": p} for p in file_names],
        "daily_rows": 72,
    }
    refresh(tmp_path, manifest)
    return tmp_path, manifest


def test_synthetic_release_and_original_aggregate_verified_without_private_reads(
    synthetic,
):
    root, _ = synthetic
    result = v.verify_release(root)
    assert (
        result["passed"]
        and result["daily_rows"] == 72
        and result["statistics_rows"] == 72
    )
    assert result["historical_model_rows_verified"] == 36
    assert not result["raw_market_or_private_account_inputs_read"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda m: m.update(schema="unknown"),
        lambda m: m.update(derived_returns_only=False),
        lambda m: m.update(series=list(reversed(v.SERIES))),
        lambda m: m.update(commission_bps_each_way=0),
        lambda m: m.update(slippage_bps_each_way=[3]),
        lambda m: m.update(daily_rows=1),
        lambda m: m["files"][0].update(path="../secret.csv"),
        lambda m: m["files"][0].update(sha256="0" * 64),
        lambda m: m["stages"]["development"].update(observations=5),
        lambda m: m["stages"]["development"].update(
            initial_timestamp_utc="2017-01-02T00:00:00+00:00"
        ),
        lambda m: m["stages"]["development"].update(elapsed_act365_years=1),
    ],
)
def test_corrupted_manifest_rejected(synthetic, mutation):
    root, manifest = synthetic
    mutation(manifest)
    write_json(root / "reports/reproducibility/manifest.json", manifest)
    with pytest.raises(ValueError):
        v.verify_release(root)


@pytest.mark.parametrize(
    "column,value",
    [
        ("stage", "validation"),
        ("date", "2017-01-03"),
        ("commission_bps_each_way", "0"),
        ("slippage_bps_each_way", "2"),
        ("initial_allocation_return", "nan"),
        ("QQQ_buy_and_hold_return", "-1"),
        ("weekly_corrections_return", ".999"),
    ],
)
def test_daily_row_changes_cannot_pass_even_with_rehashed_file(
    synthetic, column, value
):
    root, manifest = synthetic
    path = root / manifest["stages"]["development"]["csv"]
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    rows[0][column] = value
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=v.HEADER)
        writer.writeheader()
        writer.writerows(rows)
    refresh(root, manifest)
    with pytest.raises(ValueError):
        v.verify_release(root)


def test_json_summary_and_historical_aggregate_cannot_silently_diverge(synthetic):
    root, manifest = synthetic
    aggregate = root / manifest["historical_aggregate_report"]
    obj = json.loads(aggregate.read_text())
    obj["rows"][0]["cagr"] += 0.1
    write_json(aggregate, obj)
    with pytest.raises(ValueError, match="historical aggregate"):
        v.verify_release(root)


def test_released_saved_accounts_reproduced_from_public_returns_only():
    result = v.verify_release(ROOT)
    assert result["daily_rows"] == 9840 and result["return_values"] == 59040
    assert (
        result["statistics_rows"] == 72
        and not result["account_engine_or_optimizer_run"]
    )


def test_portable_cli_uses_only_stdlib_without_installed_package():
    result = subprocess.run(
        [sys.executable, "-S", str(ROOT / "scripts/verify_daily_returns.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["passed"]
