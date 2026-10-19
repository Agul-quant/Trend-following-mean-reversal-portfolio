#!/usr/bin/env python3
"""Independent saved-path oracle for five-ETF retrospective portfolio comparisons.

No engine, optimizer or project analytics module is imported. Numerical input is
opened only after a sealed release and every original/code hash have passed.
The output is aggregate-only; input paths and daily arrays are never serialized.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import numpy as np

SYMBOLS = ("GDX", "FXI", "QQQ", "UNG", "FDN")
SOURCE_SYMBOLS = SYMBOLS + ("BND",)
COSTS = (1.0, 3.0, 10.0, 25.0)
IDS = ("no_bond_daily_capped_max_sharpe", "no_bond_weekly_capped_max_sharpe",
       "no_bond_monthly_capped_max_sharpe", "no_bond_initial_capped_max_sharpe",
       "no_bond_uncapped_max_sharpe", "no_bond_equal_initial")
FREQUENCIES = ("daily", "weekly", "monthly")
STAGES = {"development": ("2017-01-01", "2020-12-31", 1007),
          "validation": ("2021-01-01", "2023-12-31", 753),
          "historical_OOS": ("2024-01-01", "2026-10-15", 700)}
CAP = 1 / 3
CAP_TOLERANCE = 1e-10
ORIGINAL_HASHES = {
    "configs/four_portfolios.json": "79badfecbb5e260523582301bcd3aecda746323bab08142aa365c8df1642cc3e",
    "reports/four_portfolios_three_periods/report.json": "2213a49db6c339841a06457a8dd762b2431a9d232ae512ff29541d9c90edd3b0",
    "results/four_portfolio_attribution/attribution.json": "f2f066ae9d32d759f202791bf95a315db9c7dfa4d5369bbdd2480620cdbdac84",
}
PRIVATE_TEXT = re.compile(r"/Users/|/home/|/var/folders/|file://|[A-Za-z]:[\\/]Users[\\/]"
                          r"|(?:apikey|api_key|api-key)=[A-Za-z0-9]{8,}", re.I)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError(f"Nonfinite JSON constant {value}")))


def public_json(value):
    """Reject private locators, nonfinite numbers and serialized daily arrays."""
    if isinstance(value, dict):
        for key, item in value.items():
            require(not PRIVATE_TEXT.search(str(key)), "Private public-JSON key")
            public_json(item)
    elif isinstance(value, list):
        require(not (len(value) > 128 and all(isinstance(x, (int, float)) for x in value)),
                "Daily numeric array in public JSON")
        for item in value:
            public_json(item)
    elif isinstance(value, float):
        require(math.isfinite(value), "Nonfinite public metric")
    elif isinstance(value, str):
        require(not PRIVATE_TEXT.search(value), "Private locator or credential in public JSON")


def utc_datetimes(timestamps):
    result = []
    for text in timestamps:
        value = datetime.fromisoformat(str(text))
        require(value.tzinfo is not None and value.utcoffset() is not None,
                "Naive daily timestamp")
        result.append(value.astimezone(timezone.utc))
    require(result and all(a < b for a, b in zip(result, result[1:])),
            "Duplicate or nonmonotonic daily timestamps")
    return result


def independent_checkpoints(timestamps, frequency):
    """Last observed NY session per ISO week/calendar month, terminal included."""
    require(frequency in FREQUENCIES, "Unknown checkpoint frequency")
    values = utc_datetimes(timestamps)
    dates = [value.astimezone(ZoneInfo("America/New_York")).date() for value in values]
    require(len(set(dates)) == len(dates), "Duplicate New York session date")
    if frequency == "daily":
        return np.arange(len(dates), dtype=int)
    groups = {}
    for index, day in enumerate(dates):
        key = (day.isocalendar().year, day.isocalendar().week) if frequency == "weekly" else (day.year, day.month)
        groups[key] = index
    return np.asarray(list(groups.values()), dtype=int)


def independent_weights(weights):
    result = np.asarray(weights, dtype=float)
    require(result.shape == (5,) and np.isfinite(result).all()
            and (result >= 0).all() and math.isclose(math.fsum(result), 1, abs_tol=1e-12, rel_tol=0),
            "Invalid five-sleeve initial weights")
    return result


def independent_wealth(equity, weights):
    equity = np.asarray(equity, dtype=float)
    weights = independent_weights(weights)
    require(equity.ndim == 2 and equity.shape[1] == 5 and len(equity)
            and np.isfinite(equity).all() and (equity > 0).all(), "Invalid sleeve wealth")
    return np.asarray([math.fsum(float(w) * float(e) for w, e in zip(weights, row)) for row in equity])


def independent_returns(wealth):
    wealth = np.asarray(wealth, dtype=float)
    require(wealth.ndim == 1 and len(wealth) >= 2
            and np.isfinite(wealth).all() and (wealth > 0).all(), "Invalid portfolio wealth")
    previous = 1.0
    result = []
    for value in wealth:
        result.append(float(value) / previous - 1)
        previous = float(value)
    return np.asarray(result)


def mean_sd(values):
    values = [float(x) for x in values]
    require(len(values) >= 2 and all(map(math.isfinite, values)), "Invalid sample")
    mean = math.fsum(values) / len(values)
    variance = math.fsum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return mean, math.sqrt(variance)


def independent_metrics(wealth, cash, years):
    returns = independent_returns(wealth)
    cash = np.asarray(cash, dtype=float)
    require(cash.shape == returns.shape and np.isfinite(cash).all() and (cash > -1).all()
            and math.isfinite(years) and years > 0, "Invalid aligned cash or ACT365 years")
    excess = returns - cash
    mean, sigma = mean_sd(excess)
    _, volatility = mean_sd(returns)
    zero = sigma <= 64 * np.finfo(float).eps * max(1.0, max(abs(float(x)) for x in excess))
    peak = 1.0
    drawdown = 0.0
    for value in wealth:
        peak = max(peak, float(value))
        drawdown = min(drawdown, float(value) / peak - 1)
    return {"cash_excess_sharpe": None if zero else math.sqrt(252) * mean / sigma,
            "cagr": float(wealth[-1]) ** (1 / years) - 1,
            "max_drawdown": drawdown,
            "annualized_return_volatility": math.sqrt(252) * volatility,
            "annualized_cash_excess_volatility": 0.0 if zero else math.sqrt(252) * sigma,
            "terminal_normalized_equity": float(wealth[-1]),
            "terminal_equity_from_1000": 1000 * float(wealth[-1]),
            "observations": len(returns), "elapsed_act365_years": years}


def independent_caps(equity, weights, checkpoints, cap=CAP):
    weights = independent_weights(weights)
    wealth = independent_wealth(equity, weights)
    shares = np.asarray(equity, dtype=float) * weights[None, :] / wealth[:, None]
    points = np.asarray(checkpoints)
    require(points.ndim == 1 and len(points) and points.dtype.kind in "iu"
            and (points >= 0).all() and (points < len(wealth)).all()
            and (np.diff(points) > 0).all() and points[-1] == len(wealth) - 1,
            "Invalid ordered checkpoints or missing terminal checkpoint")
    initial_pass = bool(max(weights) <= cap + CAP_TOLERANCE)
    checkpoint_max = float(shares[points].max())
    daily_max = float(shares.max())
    breach = np.any(shares > cap + CAP_TOLERANCE, axis=1)
    checkpoint_breaches = int(breach[points].sum())
    return {"cap_fraction": cap, "checkpoint_count": len(points),
            "initial_cap_pass_diagnostic": initial_pass,
            "checkpoint_cap_pass_diagnostic": bool(initial_pass and checkpoint_max <= cap + CAP_TOLERANCE),
            "daily_cap_pass_diagnostic": bool(initial_pass and daily_max <= cap + CAP_TOLERANCE),
            "max_checkpoint_capital_share": checkpoint_max,
            "max_daily_capital_share": daily_max,
            "max_capital_share_including_initial": max(float(max(weights)), daily_max),
            "checkpoint_breach_days": checkpoint_breaches,
            "daily_breach_days": int(breach.sum()),
            "between_checkpoint_breach_days": int(breach.sum()) - checkpoint_breaches,
            **{f"max_daily_share_{symbol}": float(shares[:, i].max()) for i, symbol in enumerate(SYMBOLS)}}


def independent_regression(returns, factors, cash):
    """Centered covariance normal equations, not the producer's lstsq routine."""
    returns, factors, cash = map(lambda x: np.asarray(x, dtype=float), (returns, factors, cash))
    require(returns.ndim == 1 and factors.ndim == 2 and cash.shape == returns.shape
            and factors.shape[0] == len(returns) and len(returns) > factors.shape[1] + 1
            and all(np.isfinite(x).all() for x in (returns, factors, cash)), "Invalid factor inputs")
    y, x = returns - cash, factors - cash[:, None]
    center_x, center_y = x - x.mean(axis=0), y - y.mean()
    require(np.linalg.matrix_rank(center_x) == x.shape[1], "Rank-deficient passive factors")
    beta = np.linalg.solve(center_x.T @ center_x, center_x.T @ center_y)
    alpha = float(y.mean() - x.mean(axis=0) @ beta)
    residual = y - alpha - x @ beta
    total = math.fsum(float(v) ** 2 for v in center_y)
    error = math.fsum(float(v) ** 2 for v in residual)
    r2 = None if total == 0 else 1 - error / total
    _, sigma = mean_sd(residual)
    n, k = x.shape
    singular = np.linalg.svd(np.column_stack([np.ones(n), x]), compute_uv=False)
    return {"alpha_daily": alpha, "alpha_annual_arithmetic": 252 * alpha,
            "betas": beta.tolist(), "r_squared": r2,
            "adjusted_r_squared": None if r2 is None else 1 - (1 - r2) * (n - 1) / (n - k - 1),
            "residual_annualized_volatility": math.sqrt(252) * sigma, "observations": n,
            "design_rank": k + 1, "design_condition_number": float(singular[0] / singular[-1])}


def verify_release(release_path, manifest_path):
    """Metadata/hash guards only; this function never opens an NPZ container."""
    release = read_json(release_path)
    payload = release.get("payload")
    require(isinstance(payload, dict), "Missing release payload")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                           allow_nan=False).encode()
    require(hashlib.sha256(canonical).hexdigest() == release.get("payload_sha256"),
            "Release payload seal mismatch")
    require(payload.get("authorized_saved_path_evaluation") is True, "No numerical-read release")
    sources, code = payload.get("source_file_sha256", {}), payload.get("code_file_sha256", {})
    require(isinstance(sources, dict) and len(sources) == 413, "Expected all 413 original guard bindings")
    require(isinstance(code, dict) and code, "Missing additive implementation seal")
    require(not (set(sources) & set(code)), "Source/code guard categories overlap")
    bindings = payload.get("files", {})
    require(isinstance(bindings, dict) and set(sources) | set(code) <= set(bindings),
            "Incomplete combined input/code guard")
    for path, value in {**sources, **code}.items():
        require(bindings[path] == value, "Contradictory combined hash binding")
    for path, expected in bindings.items():
        require(isinstance(path, str) and Path(path).is_absolute()
                and re.fullmatch(r"[0-9a-f]{64}", str(expected)), "Malformed private hash binding")
        require(digest(path) == expected, "Released source or implementation hash changed")
    own_path = str(Path(__file__).resolve())
    require(own_path in code and code[own_path] == digest(own_path), "Independent auditor is not code-bound")
    manifest_path = Path(manifest_path).resolve()
    require(bindings.get(str(manifest_path)) == digest(manifest_path)
            or payload.get("private_stage_manifest_sha256") == digest(manifest_path),
            "Unbound stage manifest")
    return payload, bindings


def recheck_bindings(bindings):
    for path, expected in bindings.items():
        require(digest(path) == expected, "Released inputs or implementation changed during audit")


def load_released_bundles(manifest, bindings, payload):
    records = manifest.get("stages", {})
    require(set(records) == set(STAGES), "Unauthorized or missing stage identity")
    result = {}
    for stage, (start, end, count) in STAGES.items():
        record = records[stage]
        require((record.get("scored_start"), record.get("scored_end")) == (start, end),
                "Unauthorized stage bounds")
        path = str(Path(record["input"]).resolve())
        expected = bindings.get(path) or payload.get("private_bundle_sha256", {}).get(path)
        require(expected is not None and expected == digest(path), "Unbound saved-path bundle")
        with np.load(path, allow_pickle=False) as archive:
            needed = {"timestamps", "symbols", "slippage_bps", "sleeve_normalized_equity",
                      "buy_and_hold_returns", "cash_returns"}
            require(set(archive.files) == needed, "Unexpected saved-path bundle members")
            bundle = {name: archive[name].copy() for name in needed}
        require(tuple(bundle["symbols"].tolist()) == SOURCE_SYMBOLS
                and tuple(bundle["slippage_bps"].tolist()) == COSTS,
                "Saved-path symbol/cost order changed")
        require(bundle["timestamps"].shape == (count,), "Incorrect stage observation count")
        times = utc_datetimes(bundle["timestamps"])
        local = [x.astimezone(ZoneInfo("America/New_York")) for x in times]
        require(all(x.hour == 17 and x.minute == x.second == x.microsecond == 0
                    and x.weekday() < 5 and start <= x.date().isoformat() <= end for x in local),
                "Unexpected New York valuation clock or out-of-stage input")
        require(bundle["sleeve_normalized_equity"].shape == (4, count, 6)
                and bundle["buy_and_hold_returns"].shape == (4, count, 6), "Incorrect saved-path shape")
        equity, factors = bundle["sleeve_normalized_equity"], bundle["buy_and_hold_returns"]
        require(np.isfinite(equity).all() and (equity > 0).all()
                and np.isfinite(factors).all() and (factors > -1).all(), "Invalid saved financial inputs")
        cash = bundle["cash_returns"]
        require(cash.shape in {(count,), (4, count)} and np.isfinite(cash).all() and (cash > -1).all(),
                "Invalid saved cash path")
        if cash.ndim == 2:
            require(all(np.array_equal(cash[0], row) for row in cash), "Cash differs between costs")
            cash = cash[0]
        initial = utc_datetimes([record["initial_timestamp"]])[0]
        require(initial < times[0], "Stage initial account is not before first valuation")
        bundle["sleeve_normalized_equity"] = equity[:, :, :5].copy()
        bundle["buy_and_hold_returns"] = factors[:, :, :5].copy()
        bundle["symbols"] = np.asarray(SYMBOLS)
        bundle["cash_returns"] = cash
        bundle["elapsed_act365_years"] = (times[-1] - initial).total_seconds() / (365 * 86400)
        result[stage] = bundle
    return result


def keyed(rows, identity="portfolio_id", frequency=False):
    result = {}
    for row in rows:
        key = (row["stage"], row[identity], float(row["slippage_bps_each_way"]))
        if frequency:
            key += (row["checkpoint_frequency"],)
        require(key not in result, "Duplicate aggregate identity")
        result[key] = row
    return result


def equal_scalar(left, right, name, differences, *, tolerance=1e-10):
    if left is None or isinstance(left, (bool, str)):
        require(left == right, f"Aggregate mismatch {name}")
        return
    require(not isinstance(right, bool) and isinstance(right, (int, float))
            and math.isfinite(float(right)), f"Invalid numeric aggregate {name}")
    delta = abs(float(left) - float(right))
    differences[name] = max(differences.get(name, 0.0), delta)
    require(math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance),
            f"Independent arithmetic mismatch {name}")


def compare_metrics(expected, actual, differences, fields=None):
    for field in expected if fields is None else fields:
        require(field in actual, f"Missing audited aggregate field {field}")
        equal_scalar(expected[field], actual[field], field, differences)


def validate_definitions(report):
    require(report.get("schema") == "five_etf_six_portfolio_comparison_v1", "Unexpected no-bond report schema")
    require(report.get("symbols") == list(SYMBOLS), "BND or unexpected active symbol")
    definitions = report.get("portfolios", [])
    require([row.get("id") for row in definitions] == list(IDS), "Incorrect six no-bond portfolio identities/order")
    weights = {}
    for record in definitions:
        mapping = record["initial_weights"]
        require(set(mapping) == set(SYMBOLS), "BND or unexpected initial-weight symbol")
        weights[record["id"]] = independent_weights([mapping[s] for s in SYMBOLS])
    for identity in IDS[:4]:
        require(max(weights[identity]) <= CAP + CAP_TOLERANCE, "Capped allocation violates initial one-third bound")
    require(all(value == .2 for value in weights[IDS[-1]]), "Equal initial must be exactly twenty percent each")
    return weights


def report_indices(report):
    expected = {(stage, identity, cost) for stage in STAGES for identity in IDS for cost in COSTS}
    result = {}
    for field, identity, frequency in (("portfolio_rows", "portfolio_id", False),
                                        ("control_rows", "control_id", False),
                                        ("checkpoint_rows", "portfolio_id", True),
                                        ("QQQ_single_factor_rows", "portfolio_id", False),
                                        ("five_passive_factor_rows", "portfolio_id", False)):
        rows = keyed(report.get(field, []), identity, frequency)
        wanted = ({(s, i, c) for s in STAGES for i in ("QQQ_buy_and_hold", "matched_cash") for c in COSTS}
                  if identity == "control_id" else
                  {key + (f,) for key in expected for f in FREQUENCIES} if frequency else expected)
        require(set(rows) == wanted, f"Incomplete or unknown {field} identities")
        for key, row in rows.items():
            require(row.get("commission_bps_each_way") == 1, "Wrong commission scenario")
            if "observations" in row:
                require(row["observations"] == STAGES[key[0]][2], "Wrong stage observation count")
        result[field] = rows
    for field, labels, keyname in (("strategy_correlations", SYMBOLS, "symbols"),
                                     ("portfolio_correlations", IDS + ("QQQ_buy_and_hold",), "portfolio_ids")):
        matrix_rows = {}
        for row in report.get(field, []):
            key = (row["stage"], float(row["slippage_bps_each_way"]))
            require(key not in matrix_rows and row.get(keyname) == list(labels)
                    and row.get("commission_bps_each_way") == 1, "Unexpected correlation identities/order")
            matrix = np.asarray(row["matrix"], dtype=float)
            require(matrix.shape == (len(labels), len(labels)) and np.isfinite(matrix).all()
                    and np.max(np.abs(matrix)) <= 1 + 1e-12
                    and np.allclose(matrix, matrix.T, atol=1e-12, rtol=0)
                    and np.allclose(np.diag(matrix), 1, atol=1e-12, rtol=0), "Invalid correlation matrix")
            matrix_rows[key] = row
        require(set(matrix_rows) == {(s, c) for s in STAGES for c in COSTS}, "Incomplete correlation scope")
        result[field] = matrix_rows
    return result


def preserved_controls(report, original):
    actual = keyed(report["control_rows"], "control_id")
    saved = keyed(original["control_rows"], "control_id")
    require(set(actual) == set(saved), "Original control scope changed")
    require(all(actual[key] == row for key, row in saved.items()), "Original control rows must remain exactly unchanged")


def audit_public_report(report, original_report):
    """Aggregate-only consistency, explicitly not the private saved-path oracle."""
    public_json(report)
    weights = validate_definitions(report)
    indexed = report_indices(report)
    preserved_controls(report, original_report)
    require(report.get("stage_summaries") == original_report["stage_summaries"], "Original stage clocks changed")
    require(report.get("slippage_bps_each_way") == list(COSTS)
            and report.get("commission_bps_each_way") == 1
            and report.get("initial_capital_each_stage") == 1000,
            "Wrong accounting/cost metadata")
    require(report.get("fit_stage") == "historical_OOS" and report.get("fit_baseline_slippage_bps") == 3,
            "Wrong fit period or baseline cost")
    text = " ".join(report.get("limitations", [])).lower()
    require("retrospective" in text and "not an untouched" in text and "best-found" in text
            and "not globally certified" in text, "Missing fit-selection limitations")
    require("no rebalancing" in report.get("method", "").lower(), "Incorrect wealth-mixing model")
    differences = {}
    for field in ("portfolio_rows", "control_rows"):
        for key, row in indexed[field].items():
            years = next(r["elapsed_act365_years"] for r in original_report["stage_summaries"] if r["stage"] == key[0])
            terminal = row["terminal_normalized_equity"]
            require(terminal > 0 and -1 < row["max_drawdown"] <= 0
                    and row["annualized_return_volatility"] >= 0
                    and row["annualized_cash_excess_volatility"] >= 0, "Invalid performance metric")
            compare_metrics({"elapsed_act365_years": years, "cagr": terminal ** (1 / years) - 1,
                             "terminal_equity_from_1000": terminal * 1000}, row, differences)
            if key[1] == "matched_cash":
                require(row["cash_excess_sharpe"] is None and row["annualized_cash_excess_volatility"] == 0,
                        "Cash Sharpe must remain undefined")
            else:
                require(isinstance(row["cash_excess_sharpe"], (int, float)), "Undefined noncash Sharpe")
    for key, row in indexed["checkpoint_rows"].items():
        stage, identity, _cost, frequency = key
        count = row["checkpoint_count"]
        require(isinstance(count, int) and not isinstance(count, bool) and 1 <= count <= STAGES[stage][2],
                "Invalid checkpoint count")
        if frequency == "daily":
            require(count == STAGES[stage][2], "Daily diagnostic omitted observations")
        point_max, daily_max = row["max_checkpoint_capital_share"], row["max_daily_capital_share"]
        require(row["cap_fraction"] == CAP and 0 < point_max <= daily_max + 1e-12 <= 1 + 1e-12,
                "Invalid cap fraction or capital shares")
        initial = bool(max(weights[identity]) <= CAP + CAP_TOLERANCE)
        require(row["initial_cap_pass_diagnostic"] is initial
                and row["checkpoint_cap_pass_diagnostic"] is bool(initial and point_max <= CAP + CAP_TOLERANCE),
                "Cap flag disagrees with initial/checkpoint constraints")
        point_breach, daily_breach, between = (row[name] for name in
                                              ("checkpoint_breach_days", "daily_breach_days", "between_checkpoint_breach_days"))
        require(all(isinstance(x, int) and not isinstance(x, bool) for x in (point_breach, daily_breach, between))
                and 0 <= point_breach <= count and 0 <= daily_breach <= STAGES[stage][2]
                and 0 <= between == daily_breach - point_breach <= STAGES[stage][2] - count,
                "Inconsistent breach-day counts")
        require((point_breach == 0) == (point_max <= CAP + CAP_TOLERANCE)
                and (daily_breach == 0) == (daily_max <= CAP + CAP_TOLERANCE), "Breach counts disagree with maxima")
        if stage == "historical_OOS":
            binding = dict(zip(IDS[:3], FREQUENCIES))
            if identity in binding and frequency == binding[identity]:
                require(row["checkpoint_cap_pass_diagnostic"], "Fitted portfolio violates all-cost binding cap")
    for field, factors in (("QQQ_single_factor_rows", ("QQQ",)), ("five_passive_factor_rows", SYMBOLS)):
        for row in indexed[field].values():
            require(all(f"beta_{symbol}" in row for symbol in factors)
                    and "beta_BND" not in row and row["design_rank"] == len(factors) + 1
                    and row["design_condition_number"] >= 1 and 0 <= row["r_squared"] <= 1 + 1e-12,
                    "Incorrect passive-factor scope or regression diagnostics")
            equal_scalar(252 * row["alpha_daily"], row["alpha_annual_arithmetic"], "alpha annualization", differences)
    solvers = report.get("solver_summaries", [])
    require([row.get("portfolio_id") for row in solvers] == list(IDS[:5]), "Incomplete five-refit solver identities")
    for solver, mode in zip(solvers, ("daily", "weekly", "monthly", "initial", "none")):
        identity = solver["portfolio_id"]
        require(solver["cap_mode"] == mode and solver["certified_global_optimum"] is False
                and solver["seed"] == 1729 and solver["lp_starts"] == 48
                and solver["ftol"] == 1e-12 and solver["maxiter"] == 2000,
                "Incorrect best-found search policy")
        require(solver["initial_weights"] == weights[identity].tolist(), "Solver/config weights differ")
        actual = indexed["portfolio_rows"][("historical_OOS", identity, 3.0)]["cash_excess_sharpe"]
        equal_scalar(actual, solver["baseline_cash_excess_sharpe"], "solver objective", differences)
        attempts = solver.get("attempts", [])
        require(len(attempts) >= 48 and all(isinstance(row.get("success"), bool) and isinstance(row.get("feasible"), bool)
                                          for row in attempts), "Missing numerical search attempts")
        if mode in {"weekly", "monthly"}:
            daily = indexed["portfolio_rows"][("historical_OOS", IDS[0], 3.0)]["cash_excess_sharpe"]
            require(actual >= daily - CAP_TOLERANCE, "Checkpoint fit worsened its feasible daily incumbent")
    return {"passed": True, "verification_scope": "public aggregate consistency only; private saved-path audit is separate",
            "rows_verified": {key: len(rows) for key, rows in indexed.items()},
            "original_control_rows_preserved_exactly": True,
            "no_bond_active_weights_or_factors": True,
            "maximum_absolute_consistency_differences": differences,
            "private_inputs_or_optimizer_required": False}


def independent_correlation(returns):
    centered = np.asarray(returns, dtype=float) - np.mean(returns, axis=0)
    cross = centered.T @ centered
    scale = np.sqrt(np.diag(cross))
    require((scale > 0).all(), "Undefined correlation due to constant net returns")
    return cross / scale[:, None] / scale[None, :]


def audit_report(report, bundles, original_report):
    public_result = audit_public_report(report, original_report)
    indexed = report_indices(report)
    weights = validate_definitions(report)
    differences = dict(public_result["maximum_absolute_consistency_differences"])
    for stage, bundle in bundles.items():
        cash, years = bundle["cash_returns"], bundle["elapsed_act365_years"]
        points = {f: independent_checkpoints(bundle["timestamps"], f) for f in FREQUENCIES}
        for ci, cost in enumerate(COSTS):
            equity, factors = bundle["sleeve_normalized_equity"][ci], bundle["buy_and_hold_returns"][ci]
            port_returns = []
            for identity in IDS:
                key = (stage, identity, cost)
                wealth = independent_wealth(equity, weights[identity])
                compare_metrics(independent_metrics(wealth, cash, years), indexed["portfolio_rows"][key], differences)
                returns = independent_returns(wealth)
                port_returns.append(returns)
                for frequency in FREQUENCIES:
                    expected = independent_caps(equity, weights[identity], points[frequency])
                    fields = ("cap_fraction", "checkpoint_count", "initial_cap_pass_diagnostic",
                              "checkpoint_cap_pass_diagnostic", "max_checkpoint_capital_share", "checkpoint_breach_days",
                              "max_daily_capital_share", "daily_breach_days", "between_checkpoint_breach_days")
                    compare_metrics(expected, indexed["checkpoint_rows"][key + (frequency,)], differences, fields)
                for field, columns in (("QQQ_single_factor_rows", [2]), ("five_passive_factor_rows", list(range(5)))):
                    fit = independent_regression(returns, factors[:, columns], cash)
                    coefficients = fit.pop("betas")
                    fit.update({f"beta_{SYMBOLS[column]}": beta for column, beta in zip(columns, coefficients)})
                    row = indexed[field][key]
                    for name, value in fit.items():
                        if name in row:
                            equal_scalar(value, row[name], name, differences)
            for identity, returns in (("QQQ_buy_and_hold", factors[:, 2]), ("matched_cash", cash)):
                compare_metrics(independent_metrics(np.cumprod(1 + returns), cash, years),
                                indexed["control_rows"][(stage, identity, cost)], differences)
            active_returns = np.column_stack([independent_returns(equity[:, i]) for i in range(5)])
            portfolio_returns = np.column_stack([*port_returns, factors[:, 2]])
            for field, returns in (("strategy_correlations", active_returns), ("portfolio_correlations", portfolio_returns)):
                expected = independent_correlation(returns)
                actual = np.asarray(indexed[field][(stage, cost)]["matrix"], dtype=float)
                delta = float(np.max(np.abs(expected - actual)))
                differences[field] = max(differences.get(field, 0), delta)
                require(np.allclose(expected, actual, atol=1e-10, rtol=1e-10), "Independent correlation mismatch")
    return {"passed": True, "schema": "independent_no_bond_saved_path_audit_v1",
            "rows_verified": public_result["rows_verified"],
            "no_bond_active_weights_or_factors": True,
            "original_control_rows_preserved_exactly": True,
            "calendar_endpoints_and_terminal_partial_period_verified": True,
            "all_five_binding_optimizer_constraint_scopes_verified": True,
            "maximum_absolute_metric_differences": differences,
            "account_or_optimizer_runs": False, "public_daily_arrays_or_private_paths": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-release", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--public-report", type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    original_path = root / "reports/four_portfolios_three_periods/report.json"
    if args.public_report:
        require(not any((args.input_release, args.manifest, args.report, args.output)), "Cannot mix public/private audit modes")
        for relative, expected in ORIGINAL_HASHES.items():
            require(digest(root / relative) == expected, "Original public reference changed")
        result = audit_public_report(read_json(args.public_report), read_json(original_path))
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0
    require(all((args.input_release, args.manifest, args.report, args.output)), "Private audit requires all four paths")
    require(not args.output.exists(), "Preserve completed/failed audit outputs; choose a new file")
    payload, bindings = verify_release(args.input_release, args.manifest)
    require(bindings.get(str(original_path)) == digest(original_path), "Unbound original reference report")
    before = digest(args.report)
    report = read_json(args.report)
    public_json(report)
    bundles = load_released_bundles(read_json(args.manifest), bindings, payload)
    result = audit_report(report, bundles, read_json(original_path))
    recheck_bindings(bindings)
    require(digest(args.report) == before, "Report changed during independent audit")
    result.update({"release_sha256": digest(args.input_release), "report_sha256": before,
                   "auditor_sha256": digest(__file__), "original_guard_files_verified": 413,
                   "all_bound_files_verified_before_and_after": len(bindings)})
    public_json(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"passed": True, "rows_verified": result["rows_verified"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

