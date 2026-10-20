"""Independent, portable arithmetic on authorized aggregate daily RETURNS only.

This module deliberately does not import the strategy/account engine or optimizer.
It needs no market prices, fills, holdings, sleeve paths or private source files.
"""

from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import statistics

SCHEMA = "aggregate_daily_returns_release_v1"
STAGES = ("development", "validation", "historical_OOS")
COSTS = (1, 3, 10, 25)
SERIES = (
    "initial_allocation",
    "weekly_corrections",
    "monthly_corrections",
    "equal_initial",
    "QQQ_buy_and_hold",
    "matched_cash",
)
HEADER = (
    "stage",
    "date",
    "valuation_timestamp_utc",
    "commission_bps_each_way",
    "slippage_bps_each_way",
    *[f"{name}_return" for name in SERIES],
)
METRICS = (
    "observations",
    "cash_excess_sharpe",
    "cagr",
    "max_drawdown",
    "terminal_normalized_equity",
    "mean_daily_cash_excess_return",
    "iid_mean_excess_t",
    "newey_west_lags",
    "newey_west_mean_excess_t",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    def reject(value):
        raise ValueError(f"Nonfinite JSON constant: {value}")

    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject)


def public_file(root, name):
    require(isinstance(name, str) and name and "\\" not in name, "Invalid release path")
    p = PurePosixPath(name)
    require(
        not p.is_absolute()
        and p.as_posix() == name
        and all(
            x not in {".", "..", ".cache", "private", "data", ".git"} for x in p.parts
        ),
        "Unsafe release path",
    )
    path = root / name
    require(
        path.is_file()
        and not path.is_symlink()
        and path.resolve() == path.absolute()
        and path.resolve().is_relative_to(root),
        "Missing or symlinked release file",
    )
    return path


def utc_clock(value):
    require(isinstance(value, str), "Timestamp must be an explicit UTC string")
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid UTC timestamp") from exc
    require(
        t.utcoffset() is not None and t.utcoffset().total_seconds() == 0,
        "Timestamp is not UTC",
    )
    return t


def elapsed_years(initial, terminal):
    value = (utc_clock(terminal) - utc_clock(initial)).total_seconds() / (365 * 86400)
    require(value > 0, "Nonpositive ACT/365 interval")
    return value


def _valid_returns(values, name):
    x = [float(v) for v in values]
    require(
        len(x) >= 2 and all(math.isfinite(v) and v > -1 for v in x),
        f"{name} requires at least two finite simple returns greater than -1",
    )
    return x


def newey_west_lags(n):
    """Predeclared sample-size-only lag rule; not selected for a favorable t-stat."""
    require(isinstance(n, int) and n >= 2, "Invalid observation count")
    return min(n - 1, math.floor(4 * (n / 100) ** (2 / 9)))


def mean_excess_t(excess, lags=0):
    """Intercept-only HAC t (Bartlett NW), HC1 n/(n-1) finite-sample scaling.

    gamma_l = sum_{t=l}^{n-1}(x_t-xbar)(x_{t-l}-xbar)/n.
    Var(xbar) = [gamma_0 + 2 sum_l(1-l/(L+1))*gamma_l] / (n-1).
    L=0 is exactly the conventional IID sample-standard-deviation mean t.
    No regression factors or post-selection correction are involved.
    """
    x = [float(v) for v in excess]
    n = len(x)
    require(n >= 2 and all(math.isfinite(v) for v in x), "Invalid excess returns")
    require(isinstance(lags, int) and 0 <= lags < n, "Invalid HAC lag count")
    mean = statistics.fmean(x)
    residual = [v - mean for v in x]
    square = math.fsum(v * v for v in residual)
    sigma = math.sqrt(square / (n - 1))
    if sigma <= 64 * math.ulp(1.0) * max(1, max(map(abs, x))):
        return None
    meat = square
    for lag in range(1, lags + 1):
        product = math.fsum(residual[t] * residual[t - lag] for t in range(lag, n))
        meat += 2 * (1 - lag / (lags + 1)) * product
    variance_mean = meat / (n * (n - 1))
    return None if variance_mean <= 0 else mean / math.sqrt(variance_mean)


def recompute(returns, cash_returns, years):
    """Rebuild normalized wealth from RETURNS and initial 1; no saved equity used."""
    returns = _valid_returns(returns, "Portfolio")
    cash = _valid_returns(cash_returns, "Matched cash")
    require(len(returns) == len(cash), "Returns and cash are not aligned")
    require(math.isfinite(years) and years > 0, "Invalid ACT/365 years")
    n = len(returns)
    excess = [r - c for r, c in zip(returns, cash)]
    mean = statistics.fmean(excess)
    sigma = statistics.stdev(excess)
    zero = sigma <= 64 * math.ulp(1.0) * max(1, max(map(abs, excess)))
    wealth, peak, drawdown = 1.0, 1.0, 0.0
    for r in returns:
        wealth *= 1 + r
        require(math.isfinite(wealth) and wealth > 0, "Invalid compounded wealth")
        peak = max(peak, wealth)
        drawdown = min(drawdown, wealth / peak - 1)
    lag = newey_west_lags(n)
    return {
        "observations": n,
        "cash_excess_sharpe": None if zero else math.sqrt(252) * mean / sigma,
        "cagr": math.expm1(math.log(wealth) / years),
        "max_drawdown": drawdown,
        "terminal_normalized_equity": wealth,
        "mean_daily_cash_excess_return": mean,
        "iid_mean_excess_t": mean_excess_t(excess, 0),
        "newey_west_lags": lag,
        "newey_west_mean_excess_t": mean_excess_t(excess, lag),
        "newey_west_sensitivity": [
            {
                "lags": sensitivity_lag,
                "mean_excess_t": mean_excess_t(excess, sensitivity_lag),
            }
            for sensitivity_lag in sorted(
                {0, min(5, n - 1), min(10, n - 1), min(20, n - 1), lag}
            )
        ],
    }


def assert_close(actual, expected, name):
    if actual is None or expected is None:
        require(
            actual is None and expected is None, f"Undefined metric differs: {name}"
        )
    else:
        require(
            isinstance(expected, (int, float))
            and not isinstance(expected, bool)
            and math.isfinite(expected)
            and math.isfinite(actual)
            and math.isclose(actual, expected, rel_tol=2e-10, abs_tol=2e-11),
            f"Recomputed metric differs: {name}: {actual} vs {expected}",
        )


def _verify_aggregate(rows, aggregate):
    model = {
        "initial_allocation": "none",
        "weekly_corrections": "weekly",
        "monthly_corrections": "monthly",
    }
    expected = {}
    for row in aggregate["rows"]:
        expected[(row["stage"], int(row["slippage_bps"]), row["frequency"])] = row
    controls = {
        (r["stage"], r["control"], int(r.get("slippage_bps") or 0)): r
        for r in aggregate["controls"]
    }
    require(
        len(expected) == 36 and len(controls) == 15,
        "Historical aggregate scope changed",
    )
    for row in rows:
        key = row["stage"], row["slippage_bps_each_way"]
        if row["series"] in model:
            target = expected[(*key, model[row["series"]])]
        elif row["series"] == "QQQ_buy_and_hold":
            target = controls[(key[0], "QQQ_buy_and_hold", key[1])]
        elif row["series"] == "matched_cash":
            target = next(
                r
                for r in aggregate["controls"]
                if r["stage"] == key[0] and r["control"] == "cash"
            )
        else:
            continue
        for metric in (
            "observations",
            "cash_excess_sharpe",
            "cagr",
            "max_drawdown",
            "terminal_normalized_equity",
        ):
            assert_close(
                row[metric], target[metric], f"historical aggregate {key} {metric}"
            )


def verify_release(root, manifest_name="reports/reproducibility/manifest.json"):
    """Verify every released row + all72 statistic rows, and original36model metrics."""
    root = Path(root).resolve()
    manifest = read_json(public_file(root, manifest_name))
    require(
        manifest.get("schema") == SCHEMA
        and manifest.get("derived_returns_only") is True,
        "Incorrect derived-return release scope",
    )
    require(
        manifest.get("series") == list(SERIES)
        and manifest.get("slippage_bps_each_way") == list(COSTS)
        and manifest.get("commission_bps_each_way") == 1,
        "Unexpected series or cost scope",
    )
    files = manifest.get("files")
    require(
        isinstance(files, list) and len({f["path"] for f in files}) == len(files) == 5,
        "Exactly three CSVs and two statistic files are required",
    )
    require(set(manifest.get("stages", {})) == set(STAGES), "Stage scope differs")
    expected_files = {
        manifest["statistics_json"],
        manifest["statistics_csv"],
        *[manifest["stages"][stage]["csv"] for stage in STAGES],
    }
    require(
        {record["path"] for record in files} == expected_files
        and len(expected_files) == 5,
        "Release file allowlist differs",
    )
    for record in files:
        raw = public_file(root, record["path"]).read_bytes()
        require(len(raw) == record["bytes"], "Release byte count changed")
        require(
            hashlib.sha256(raw).hexdigest() == record["sha256"],
            "Release SHA256 changed",
        )
    statistics_json = read_json(public_file(root, manifest["statistics_json"]))
    require(
        statistics_json.get("schema") == "aggregate_return_statistical_comparison_v1",
        "Incorrect statistical comparison schema",
    )
    expected = {
        (r["stage"], r["slippage_bps_each_way"], r["series"]): r
        for r in statistics_json["rows"]
    }
    require(
        len(expected) == len(statistics_json["rows"]) == 72
        and set(expected)
        == {
            (stage, cost, name) for stage in STAGES for cost in COSTS for name in SERIES
        },
        "Statistics row count or identities differ",
    )
    actual_rows, total = [], 0
    require(set(manifest["stages"]) == set(STAGES), "Stage scope differs")
    for stage in STAGES:
        metadata = manifest["stages"][stage]
        path = public_file(root, metadata["csv"])
        series = {cost: {name: [] for name in SERIES} for cost in COSTS}
        clocks = {cost: [] for cost in COSTS}
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            require(reader.fieldnames == list(HEADER), "Unexpected daily CSV columns")
            for row in reader:
                require(
                    None not in row and all(v is not None for v in row.values()),
                    "Malformed daily row",
                )
                require(
                    row["stage"] == stage and row["commission_bps_each_way"] == "1",
                    "Daily row scope differs",
                )
                require(
                    row["slippage_bps_each_way"] in {str(c) for c in COSTS},
                    "Unknown cost",
                )
                cost = int(row["slippage_bps_each_way"])
                clock = utc_clock(row["valuation_timestamp_utc"])
                require(
                    row["date"] == clock.date().isoformat(), "Date/timestamp mismatch"
                )
                require(
                    not clocks[cost] or clock > clocks[cost][-1],
                    "Duplicate or unsorted timestamps",
                )
                require(
                    metadata["scored_start"] <= row["date"] <= metadata["scored_end"],
                    "Out-of-stage row",
                )
                clocks[cost].append(clock)
                for name in SERIES:
                    value = float(row[f"{name}_return"])
                    require(
                        math.isfinite(value) and value > -1,
                        "Invalid daily simple return",
                    )
                    series[cost][name].append(value)
                total += 1
        first = clocks[COSTS[0]]
        require(
            len(first) == metadata["observations"]
            and first
            and first[0] == utc_clock(metadata["first_valuation_timestamp_utc"])
            and first[-1] == utc_clock(metadata["terminal_valuation_timestamp_utc"]),
            "Observation clock differs",
        )
        require(
            utc_clock(metadata["initial_timestamp_utc"]) < first[0],
            "Initial clock not before first return",
        )
        years = elapsed_years(
            metadata["initial_timestamp_utc"],
            metadata["terminal_valuation_timestamp_utc"],
        )
        assert_close(years, metadata["elapsed_act365_years"], "ACT/365 interval")
        for cost in COSTS:
            require(clocks[cost] == first, "Cost calendars differ")
            require(
                series[cost]["matched_cash"] == series[COSTS[0]]["matched_cash"],
                "Cost-specific cash differs",
            )
            for name in SERIES:
                values = recompute(
                    series[cost][name], series[cost]["matched_cash"], years
                )
                key = stage, cost, name
                wanted = expected[key]
                for metric in METRICS:
                    assert_close(values[metric], wanted[metric], f"{key} {metric}")
                require(
                    len(values["newey_west_sensitivity"])
                    == len(wanted["newey_west_sensitivity"]),
                    "HAC sensitivity count differs",
                )
                for a, b in zip(
                    values["newey_west_sensitivity"], wanted["newey_west_sensitivity"]
                ):
                    require(a["lags"] == b["lags"], "HAC sensitivity lags differ")
                    assert_close(
                        a["mean_excess_t"], b["mean_excess_t"], "HAC sensitivity"
                    )
                actual_rows.append(
                    {
                        "stage": stage,
                        "slippage_bps_each_way": cost,
                        "series": name,
                        **values,
                    }
                )
    require(total == manifest["daily_rows"], "Total daily row count differs")
    # CSV is an independently readable representation of all72 JSON summaries.
    with public_file(root, manifest["statistics_csv"]).open(
        newline="", encoding="utf-8"
    ) as f:
        flat = list(csv.DictReader(f))
    require(len(flat) == 72, "Statistics CSV row count differs")
    seen = set()
    for row in flat:
        key = row["stage"], int(row["slippage_bps_each_way"]), row["series"]
        require(
            key not in seen and key in expected,
            "Duplicate or unknown statistics CSV row",
        )
        seen.add(key)
        for metric in METRICS:
            assert_close(
                None if row[metric] == "" else float(row[metric]),
                expected[key][metric],
                f"Statistics CSV {key} {metric}",
            )
    aggregate = read_json(public_file(root, manifest["historical_aggregate_report"]))
    _verify_aggregate(actual_rows, aggregate)
    return {
        "passed": True,
        "daily_rows": total,
        "return_values": total * len(SERIES),
        "statistics_rows": len(actual_rows),
        "historical_model_rows_verified": 36,
        "raw_market_or_private_account_inputs_read": False,
        "account_engine_or_optimizer_run": False,
        "interpretation": "Retrospective descriptive arithmetic; no untouched OOS or selection-adjusted inference.",
    }
