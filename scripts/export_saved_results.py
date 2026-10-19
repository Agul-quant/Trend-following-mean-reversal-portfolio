#!/usr/bin/env python3
"""Export an allowlisted, aggregate-only snapshot from private saved research.

The external source manifest maps logical names to ``{path, sha256}`` records.
It must not be committed: paths, full saved accounts, source maps and private
receipts remain outside this repository. This utility never fetches market data
or evaluates a trading strategy. ``--verify-only`` compares existing exports
without writing any files. NumPy is needed for saved-array arithmetic checks.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np

SYMBOLS = ["GDX", "FXI", "QQQ", "UNG", "FDN", "BND"]
COSTS = [1.0, 3.0, 10.0, 25.0]
IDS = [
    "daily_capped_max_sharpe",
    "initial_capped_max_sharpe",
    "uncapped_max_sharpe",
    "equal_initial",
    "max_cagr_100pct_gdx",
]
PINNED_RECEIPTS = {
    "portfolio_receipt": "97991ae64bf617688f7b9885ea68d928352935e5bff5de91aacc143c6d607443",
    "capped_receipt": "a672bda0a23c7be1adc25e7edc25e3f1052cb97fa5a3018cd3820ed6dc57b070",
    "growth_receipt": "91986acfb94bef164a3c67451c336a5ae8d423cdd4ab2fc8024674b31453db53",
    "qqq_receipt": "128ebbd930fe8e7b5d7155a80c247b99ea95129c91a29224d4730bd43123f42c",
    "multifactor_receipt": "736633f6225e4fbb7eee925025aedd5ab1c3b2d0d91a1c2791873b256cd1710b",
    "correlation_receipt": "66ab8b0ef2dfe0d400fa38a17a0daad7d3c940b15ac27243576a418d5c95e4ae",
}
RECEIPT_BOUND_INPUTS = {
    "portfolio_result": ("portfolio_receipt", "result.json"),
    "portfolio_definition": ("portfolio_receipt", "contract.json"),
    "portfolio_paths": ("portfolio_receipt", "portfolio_daily_paths.npz"),
    "capped_result": ("capped_receipt", "result.json"),
    "growth_result": ("growth_receipt", "result.json"),
    "qqq_result": ("qqq_receipt", "result.json"),
    "multifactor_result": ("multifactor_receipt", "result.json"),
    "correlation_paths": ("correlation_receipt", "daily_returns.npz"),
}
PINNED_STRATEGY_COMPARISON = (
    "1ab8aeac7dbc584e71e6883bc7b128d2165f6197f918693a287b52f027563940"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if "payload" in value:
        canonical = json.dumps(
            value["payload"], sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        assert hashlib.sha256(canonical.encode()).hexdigest() == value["payload_sha256"]
        return value["payload"]
    return value


def only(record: dict, keys: list[str]) -> dict:
    return {key: record[key] for key in keys}


def json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"


def csv_text(rows: list[dict]) -> str:
    assert rows
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        assert set(row) == set(rows[0])
        writer.writerow(row)
    return handle.getvalue()


def metrics(nav: np.ndarray, cash: np.ndarray, years: float) -> dict:
    returns = nav / np.r_[1.0, nav[:-1]] - 1.0
    excess = returns - cash
    assert len(nav) == 700 and np.isfinite(nav).all() and np.min(nav) > 0.0
    return {
        "cash_excess_sharpe": float(
            np.sqrt(252.0) * excess.mean() / excess.std(ddof=1)
        ),
        "cagr": float(nav[-1] ** (1.0 / years) - 1.0),
        "max_drawdown": float(
            np.min(nav / np.maximum.accumulate(np.r_[1.0, nav])[1:] - 1.0)
        ),
        "annualized_net_volatility": float(np.sqrt(252.0) * returns.std(ddof=1)),
        "annualized_cash_excess_volatility": float(np.sqrt(252.0) * excess.std(ddof=1)),
        "terminal_equity_from_1000": float(1000.0 * nav[-1]),
    }


def regress(y: np.ndarray, x: np.ndarray) -> dict:
    if x.ndim == 1:
        x = x[:, None]
    n, p = x.shape
    assert (
        n == 700 and y.shape == (n,) and np.isfinite(x).all() and np.isfinite(y).all()
    )
    xc, yc = x - x.mean(axis=0), y - y.mean()
    assert np.linalg.matrix_rank(xc) == p
    beta = np.linalg.solve(xc.T @ xc, xc.T @ yc)
    alpha = float(y.mean() - x.mean(axis=0) @ beta)
    residual = y - alpha - x @ beta
    r2 = float(1.0 - (residual @ residual) / (yc @ yc))
    return {
        "betas": beta,
        "alpha_daily": alpha,
        "alpha_annual_arithmetic": 252.0 * alpha,
        "R_squared": r2,
        "adjusted_R_squared": 1.0 - (1.0 - r2) * (n - 1) / (n - p - 1),
    }


def export(source_manifest: Path, output_root: Path, verify_only: bool = False) -> dict:
    manifest = json.loads(source_manifest.read_text())
    inputs: dict[str, Path] = {}
    seen: dict[Path, str] = {}
    for name, item in manifest.items():
        assert set(item) == {"path", "sha256"}
        path = Path(item["path"]).resolve()
        assert path.is_file() and digest(path) == item["sha256"], (
            f"Input integrity failed: {name}"
        )
        inputs[name] = path
        seen[path] = item["sha256"]
    receipts = {}
    for name, expected in PINNED_RECEIPTS.items():
        assert digest(inputs[name]) == expected, f"Unexpected saved receipt: {name}"
        receipt = load_json(inputs[name])
        assert receipt["status"] == "complete"
        receipts[name] = receipt
        for relative, sha in receipt["files"].items():
            relative_path = Path(relative)
            assert not relative_path.is_absolute() and ".." not in relative_path.parts
            path = (inputs[name].parent / relative_path).resolve()
            assert digest(path) == sha
            seen[path] = sha
    for name, (receipt_name, filename) in RECEIPT_BOUND_INPUTS.items():
        assert digest(inputs[name]) == receipts[receipt_name]["files"][filename], (
            f"Receipt-bound input integrity failed: {name}"
        )
    assert digest(inputs["strategy_comparison"]) == PINNED_STRATEGY_COMPARISON
    data = {
        name: load_json(inputs[name])
        for name in [
            "portfolio_result",
            "portfolio_definition",
            "capped_result",
            "growth_result",
            "qqq_result",
            "multifactor_result",
            "strategy_comparison",
        ]
    }
    old, capped, growth = (
        data["portfolio_result"],
        data["capped_result"],
        data["growth_result"],
    )
    qqq, multi, comparison = (
        data["qqq_result"],
        data["multifactor_result"],
        data["strategy_comparison"],
    )
    for record in [old, qqq, multi]:
        source_map = record.get(
            "input_files_before_and_after",
            record.get("data", {}).get("input_files_rehashed_unchanged", {}),
        )
        for name, sha in source_map.items():
            path = Path(name)
            assert digest(path) == sha
            seen[path] = sha
    assert old["symbols"] == capped["symbols"] == growth["symbols"] == SYMBOLS
    assert multi["factor_symbols"] == SYMBOLS
    assert qqq["portfolios"] == multi["portfolios"]
    assert qqq["current_portfolio_id"] == multi["current_portfolio_id"] == IDS[0]
    assert [p["id"] for p in qqq["portfolios"]] == IDS
    assert qqq["sessions"] == multi["sessions"] == 700
    assert comparison["same_config_held_across_all_four_costs"] is True
    definitions = [
        only(row, ["symbol", "style", "candidate_id", "label", "definition"])
        for row in old["fixed_configurations"]
    ]
    assert [row["symbol"] for row in definitions] == SYMBOLS
    by_symbol = {row["symbol"]: row for row in definitions}
    for row in definitions:
        source = next(
            r for r in comparison["configurations"] if r["symbol"] == row["symbol"]
        )
        assert row == only(source, list(row))
    years = float(old["data"]["CAGR_ACT365_years"])
    assert (
        years
        == capped["CAGR_ACT365_years"]
        == data["portfolio_definition"]["CAGR_clock"]["ACT365_years"]
    )
    # Decode only integrity-verified, already evaluated saved accounts. Nothing
    # below runs indicators, fills orders or fetches a price history.
    with np.load(inputs["portfolio_paths"], allow_pickle=False) as saved:
        assert saved["symbols"].tolist() == SYMBOLS
        np.testing.assert_array_equal(saved["slippage_bps"], COSTS)
        wealth, cash, returns = (
            saved["sleeve_normalized_equity"].copy(),
            saved["cash_returns"].copy(),
            saved["sleeve_returns"].copy(),
        )
        timestamps = saved["timestamp"].copy()
    with np.load(inputs["correlation_paths"], allow_pickle=False) as saved:
        indices = [saved["symbols"].tolist().index(s) for s in SYMBOLS]
        bh = saved["buy_and_hold_returns"][:, :, indices].copy()
        np.testing.assert_array_equal(
            saved["cash_returns"],
            np.broadcast_to(cash[None, :, None], saved["cash_returns"].shape),
        )
        np.testing.assert_array_equal(saved["strategy_returns"][:, :, indices], returns)
        np.testing.assert_array_equal(saved["timestamp"], timestamps)
    assert wealth.shape == returns.shape == bh.shape == (4, 700, 6) and cash.shape == (
        700,
    )
    portfolio_records = []
    for p in qqq["portfolios"]:
        pid = p["id"]
        weights = p["weights"]
        assert (
            set(weights) == set(SYMBOLS)
            and min(weights.values()) >= 0.0
            and abs(sum(weights.values()) - 1.0) < 1e-12
        )
        if pid == "daily_capped_max_sharpe":
            scope, objective = (
                "historical_daily_valuation_all_four_costs",
                "cash_excess_sharpe",
            )
        elif pid == "initial_capped_max_sharpe":
            scope, objective = "initial_only", "cash_excess_sharpe"
        elif pid == "max_cagr_100pct_gdx":
            scope, objective = "none", "cagr"
        elif pid == "uncapped_max_sharpe":
            scope, objective = "none", "cash_excess_sharpe"
        else:
            scope, objective = "none", "equal_initial_comparator"
        portfolio_records.append(
            {
                "id": pid,
                "label": p["label"],
                "current_choice": p["current_human_choice"],
                "initial_weights": weights,
                "cap_scope": scope,
                "objective": objective,
                "global_optimum_certified": True if objective == "cagr" else False,
                "optimality_statement": "Exact maximum for uncapped static initial long-only terminal-wealth simplex"
                if objective == "cagr"
                else (
                    "Predefined comparator; not an optimization"
                    if pid == "equal_initial"
                    else "Numerically best-found; no global certificate"
                ),
            }
        )
    assert (
        next(p for p in portfolio_records if p["current_choice"])["cap_scope"]
        == "historical_daily_valuation_all_four_costs"
    )
    metric_rows, drift_rows, strategy_rows, bh_rows, pair_rows, correlation_rows = (
        [],
        [],
        [],
        [],
        [],
        [],
    )
    max_error = 0.0

    def check_number(actual: float, expected: float) -> None:
        nonlocal max_error
        assert np.isfinite(actual) and np.isfinite(expected)
        difference = abs(float(actual) - float(expected))
        assert difference < 1e-10
        max_error = max(max_error, difference)

    portfolio_returns = {}
    for p in portfolio_records:
        pid = p["id"]
        w = np.array([p["initial_weights"][s] for s in SYMBOLS])
        portfolio_returns[pid] = []
        for k, cost in enumerate(COSTS):
            nav = wealth[k] @ w
            metric = metrics(nav, cash, years)
            if pid in ["uncapped_max_sharpe", "equal_initial"]:
                key = (
                    "fixed_baseline_optimized_initial_weights"
                    if pid == "uncapped_max_sharpe"
                    else "equal_initial_weights"
                )
                expected = old["cost_results_same_baseline_weights"][k][key]
            elif pid == "max_cagr_100pct_gdx":
                expected = growth["cost_results"][k]["same_baseline_max_CAGR_weights"]
            else:
                key = (
                    "daily_all_costs"
                    if pid == "daily_capped_max_sharpe"
                    else "initial_only"
                )
                expected = capped["cases"][key]["fixed_weight_cost_results"][k][
                    "metrics"
                ]
            for field in [
                "cash_excess_sharpe",
                "cagr",
                "max_drawdown",
                "terminal_equity_from_1000",
            ]:
                check_number(metric[field], expected[field])
            fractions = wealth[k] * w / nav[:, None]
            if p["cap_scope"] != "none":
                assert w.max() <= 1.0 / 3.0 + 1e-12
            if p["cap_scope"] == "historical_daily_valuation_all_four_costs":
                assert fractions.max() <= 1.0 / 3.0 + 1e-12
            metric_rows.append(
                {
                    "portfolio_id": pid,
                    "commission_bps_each_way": 1.0,
                    "slippage_bps_each_way": cost,
                    **metric,
                    "max_observed_daily_sleeve_capital_share": float(fractions.max()),
                }
            )
            for i, s in enumerate(SYMBOLS):
                drift_rows.append(
                    {
                        "portfolio_id": pid,
                        "slippage_bps_each_way": cost,
                        "symbol": s,
                        "initial_weight": float(w[i]),
                        "terminal_sleeve_capital_share": float(fractions[-1, i]),
                        "max_observed_daily_sleeve_capital_share": float(
                            fractions[:, i].max()
                        ),
                    }
                )
            portfolio_returns[pid].append(nav / np.r_[1.0, nav[:-1]] - 1.0)
    for row in comparison["comparisons"]:
        if row["symbol"] not in SYMBOLS:
            continue
        s, cost = row["symbol"], row["slippage_bps_each_way"]
        i, k = SYMBOLS.index(s), COSTS.index(cost)
        assert row["candidate_id"] == by_symbol[s]["candidate_id"]
        for kind, target, nav in [
            ("strategy", strategy_rows, wealth[k, :, i]),
            ("buy_and_hold", bh_rows, np.cumprod(1.0 + bh[k, :, i])),
        ]:
            metric = metrics(nav, cash, years)
            for field in ["cash_excess_sharpe", "cagr", "max_drawdown"]:
                check_number(metric[field], row[kind][field])
            target.append(
                {
                    "symbol": s,
                    "style": row["style"]
                    if kind == "strategy"
                    else "passive_buy_and_hold",
                    "candidate_id": row["candidate_id"]
                    if kind == "strategy"
                    else "benchmark_buy_and_hold",
                    "commission_bps_each_way": 1.0,
                    "slippage_bps_each_way": cost,
                    **metric,
                    "completed_round_trips": row[kind]["trade_count"],
                    "fills": row[kind]["order_count"],
                }
            )
    assert len(strategy_rows) == len(bh_rows) == 24
    for k, cost in enumerate(COSTS):
        centered = returns[k] - returns[k].mean(axis=0)
        gram = centered.T @ centered
        sd = np.sqrt(np.diag(gram))
        correlation = gram / np.outer(sd, sd)
        for i, s in enumerate(SYMBOLS):
            correlation_rows.append(
                {
                    "slippage_bps_each_way": cost,
                    "symbol": s,
                    **dict(zip(SYMBOLS, correlation[i].tolist())),
                }
            )
        for i, j in itertools.combinations(range(6), 2):
            check_number(
                correlation[i, j],
                old["correlations_by_slippage_bps"][str(int(cost))][i][j],
            )
            pair_rows.append(
                {
                    "slippage_bps_each_way": cost,
                    "symbol_1": SYMBOLS[i],
                    "symbol_2": SYMBOLS[j],
                    "pearson_daily_net_strategy_returns": float(correlation[i, j]),
                }
            )
    (
        qqq_portfolios,
        qqq_sleeves,
        joint_portfolios,
        joint_sleeves,
        pair_portfolios,
        pair_sleeves,
    ) = [], [], [], [], [], []
    basic = ["alpha_daily", "alpha_annual_arithmetic", "R_squared", "observations"]
    for source, target, is_portfolio in [
        (qqq["portfolio_rows"], qqq_portfolios, True),
        (qqq["supplementary_six_single_strategy_rows"], qqq_sleeves, False),
    ]:
        for row in source:
            k = COSTS.index(row["slippage_bps_each_way"])
            y = (
                np.array(portfolio_returns[row["portfolio_id"]][k])
                if is_portfolio
                else returns[k, :, SYMBOLS.index(row["symbol"])]
            )
            fitted = regress(y - cash, bh[k, :, SYMBOLS.index("QQQ")] - cash)
            for field in basic[:-1]:
                check_number(row[field], fitted[field])
            check_number(row["beta_to_QQQ_BH"], fitted["betas"][0])
            target.append(
                {
                    ("portfolio_id" if is_portfolio else "symbol"): row["portfolio_id"]
                    if is_portfolio
                    else row["symbol"],
                    "commission_bps_each_way": 1.0,
                    "slippage_bps_each_way": row["slippage_bps_each_way"],
                    "benchmark": "QQQ_passive_buy_and_hold",
                    "beta_to_QQQ_BH": row["beta_to_QQQ_BH"],
                    **only(row, basic),
                }
            )
    for source, target, is_portfolio in [
        (multi["joint_portfolio_rows"], joint_portfolios, True),
        (multi["supplementary_joint_strategy_rows"], joint_sleeves, False),
    ]:
        for row in source:
            k = COSTS.index(row["slippage_bps_each_way"])
            identifier = row["portfolio_id"] if is_portfolio else row["strategy_symbol"]
            y = (
                np.array(portfolio_returns[identifier][k])
                if is_portfolio
                else returns[k, :, SYMBOLS.index(identifier)]
            )
            fitted = regress(y - cash, bh[k] - cash[:, None])
            for field in [*basic[:-1], "adjusted_R_squared"]:
                check_number(row[field], fitted[field])
            for i, s in enumerate(SYMBOLS):
                check_number(row["betas"][s], fitted["betas"][i])
            target.append(
                {
                    ("portfolio_id" if is_portfolio else "symbol"): identifier,
                    "commission_bps_each_way": 1.0,
                    "slippage_bps_each_way": row["slippage_bps_each_way"],
                    **{f"beta_{s}": row["betas"][s] for s in SYMBOLS},
                    **only(
                        row,
                        [
                            *basic,
                            "adjusted_R_squared",
                            "annualized_residual_volatility",
                        ],
                    ),
                }
            )
    for source, target, is_portfolio in [
        (multi["pairwise_portfolio_rows"], pair_portfolios, True),
        (multi["supplementary_pairwise_strategy_rows"], pair_sleeves, False),
    ]:
        for row in source:
            k = COSTS.index(row["slippage_bps_each_way"])
            identifier = row["portfolio_id"] if is_portfolio else row["strategy_symbol"]
            y = (
                np.array(portfolio_returns[identifier][k])
                if is_portfolio
                else returns[k, :, SYMBOLS.index(identifier)]
            )
            fitted = regress(y - cash, bh[k, :, SYMBOLS.index(row["factor"])] - cash)
            for field in basic[:-1]:
                check_number(row[field], fitted[field])
            check_number(row["beta"], fitted["betas"][0])
            target.append(
                {
                    ("portfolio_id" if is_portfolio else "symbol"): identifier,
                    "passive_ETF_factor": row["factor"],
                    "commission_bps_each_way": 1.0,
                    "slippage_bps_each_way": row["slippage_bps_each_way"],
                    "beta": row["beta"],
                    **only(row, basic),
                }
            )
    assert [
        len(v)
        for v in [
            qqq_portfolios,
            qqq_sleeves,
            joint_portfolios,
            joint_sleeves,
            pair_portfolios,
            pair_sleeves,
        ]
    ] == [20, 24, 20, 24, 120, 144]
    diagnostics = []
    for row in multi["factor_diagnostics_by_cost"]:
        diagnostics.append(
            only(
                row,
                [
                    "slippage_bps_each_way",
                    "rank_including_intercept",
                    "standardized_factor_condition_number",
                    "raw_design_condition_number",
                    "factor_cash_excess_correlation",
                    "variance_inflation_factors",
                ],
            )
        )
    protocol = {
        "schema": "six_sleeve_research_protocol_v1",
        "project_name": "Trend Following Study",
        "symbols": SYMBOLS,
        "development": {"start": "2017-01-01", "end": "2020-12-31"},
        "validation": {"start": "2021-01-01", "end": "2023-12-31"},
        "historical_OOS": {
            "start": "2024-01-01",
            "first_session": "2024-01-02",
            "end": "2026-10-15",
            "sessions": 700,
        },
        "ACT365_elapsed_years": years,
        "initial_cash_per_strategy_account": 1000.0,
        "cash": {
            "nominal_annual_rate": 0.03,
            "day_count": "ACT/365",
            "compounding": "event time; not 3% APY",
        },
        "costs": {
            "commission_bps_each_way": 1.0,
            "slippage_bps_each_way": COSTS,
            "primary_slippage_bps_each_way": 3.0,
        },
        "timing": {
            "daily_causal_indicators": True,
            "observations": "native half-hour",
            "shared_confirmation_hours": 3.0,
            "consecutive_checks": 7,
            "execution": "next eligible observed bar open",
        },
        "accounting": {
            "stage_accounts": "fresh flat $1000 accounts; feature history only carried",
            "feature_seed_start": "2015-01-01",
            "positions": "unlevered long/cash",
            "paid_terminal_liquidation": True,
        },
        "portfolio_model": "Static INITIAL sleeve capital, sum weights1; no cross-sleeve rebalancing or cash cross-funding",
        "Sharpe": "sqrt252 * mean(net daily return - matched cash return) / sample_sd(ddof1)",
        "CAGR": "aggregate terminal wealth raised to inverse frozen ACT365 years, minus1",
        "max_drawdown": "aggregate daily-valuation drawdown including initial balance; not intraday",
        "regression": "cash-excess OLS with intercept; alpha annualization252*daily, not CAGR",
        "factor_order": SYMBOLS,
        "factor_returns": "same-cost passive ETF buy-and-hold; not active strategy returns",
        "daily_cap_scope": "historical sleeve CAPITAL shares at all700 daily valuations/all4costs; not intraday, ETF holdings or a future guarantee",
        "selection_context": "ETF/configuration selection, pruning and allocations use examined OOS; retrospective descriptive fits, not untouched portfolio OOS",
        "prior_study_amended_qualification_gate": {
            "slippage_bps_each_way": 25.0,
            "Sharpe": "candidate net cash-excess Sharpe strictly exceeds its matched own-ETF buy-and-hold Sharpe",
            "CAGR": "candidate net CAGR strictly exceeds0 when matched BH CAGR is negative; otherwise strictly exceeds two-thirds of matched BH CAGR",
            "scope": "earlier development/validation qualification; not a new OOS selection or a portfolio allocation constraint",
        },
        "reproduction_scope": "Portable saved-account analytics; full original market-data/indicator/execution study is not included",
    }
    provenance = {
        "schema": "sanitized_saved_calculation_provenance_v1",
        "source_delivery_receipt_sha256": PINNED_RECEIPTS,
        "historical_numerical_sources": "Previously completed, privately retained saved strategy and passive-control accounts",
        "reproduction_requirement": "Historical values require the separately retained private saved-account inputs. Synthetic examples do not reproduce these market results.",
        "published_scope": "Selected aggregate definitions, weights, metrics, correlations and fitted coefficients only",
        "intentionally_excluded": [
            "daily account arrays",
            "market prices",
            "source snapshots",
            "private receipts and source maps",
            "credentials",
            "local filesystem paths",
        ],
        "QQQ_trade_count_caveat": "Frozen legacy counts are domain-checked; no event ledger exists for independent trade reconstruction",
        "trade_count_units": "completed round trips, including paid terminal liquidation; fills count individual buys/sells",
        "coefficient_caveat": "Partial slopes are not weights or causal effects; negative fitted beta is not an actual short position",
        "inference_caveat": "Post-selection fitted-history diagnostics; no significance, forecast, untouched-OOS or live-trading claim",
    }
    outputs = {
        "configs/selected_strategies.json": json_text(
            {
                "schema": "selected_six_strategy_definitions_v1",
                "symbols": SYMBOLS,
                "strategies": definitions,
            }
        ),
        "configs/portfolios.json": json_text(
            {
                "schema": "five_fixed_initial_sleeve_portfolios_v1",
                "symbols": SYMBOLS,
                "portfolios": portfolio_records,
            }
        ),
        "configs/research_protocol.json": json_text(protocol),
        "results/portfolio_metrics_all_costs.csv": csv_text(metric_rows),
        "results/portfolio_capital_drift_all_costs.csv": csv_text(drift_rows),
        "results/strategy_metrics_all_costs.csv": csv_text(strategy_rows),
        "results/own_ETF_buy_and_hold_metrics_all_costs.csv": csv_text(bh_rows),
        "results/strategy_correlation_matrices_all_costs.csv": csv_text(
            correlation_rows
        ),
        "results/strategy_correlation_pairs_all_costs.csv": csv_text(pair_rows),
        "results/QQQ_single_factor_portfolios_all_costs.csv": csv_text(qqq_portfolios),
        "results/QQQ_single_factor_strategy_sleeves_all_costs.csv": csv_text(
            qqq_sleeves
        ),
        "results/six_factor_portfolios_all_costs.csv": csv_text(joint_portfolios),
        "results/six_factor_strategy_sleeves_all_costs.csv": csv_text(joint_sleeves),
        "results/pairwise_portfolio_betas_all_costs.csv": csv_text(pair_portfolios),
        "results/pairwise_strategy_sleeve_betas_all_costs.csv": csv_text(pair_sleeves),
        "results/six_factor_diagnostics.json": json_text(
            {
                "schema": "passive_ETF_factor_diagnostics_v1",
                "factor_order": SYMBOLS,
                "diagnostics": diagnostics,
            }
        ),
        "results/provenance.json": json_text(provenance),
    }
    for path, sha in seen.items():
        assert digest(path) == sha
    verification = {
        "schema": "aggregate_export_verification_v1",
        "passed": True,
        "source_delivery_receipts_verified": len(receipts),
        "private_source_bindings_rehashed_unchanged": len(seen),
        "selected_strategies": 6,
        "portfolio_variants": 5,
        "cost_scenarios": 4,
        "common_sessions": 700,
        "aggregate_metric_rows": 20,
        "strategy_metric_rows": 24,
        "passive_control_metric_rows": 24,
        "correlation_pair_cost_rows": 60,
        "QQQ_single_factor_rows": 44,
        "six_factor_joint_rows": 44,
        "pairwise_rows": 264,
        "max_absolute_saved_value_vs_independent_arithmetic_error": max_error,
        "daily_cap_all_16800_valuation_sleeve_cost_inequalities_checked": True,
        "byte_identical_reexport_with_same_verified_inputs_and_numeric_runtime": True,
        "numeric_export_method": "allowlisted fields; metrics/correlations/regressions cross-checked against verified private saved paths",
        "full_daily_arrays_market_paths_source_maps_or_private_receipts_exported": False,
        "market_data_downloads_strategy_account_runs_or_optimization": False,
    }
    outputs["results/verification.json"] = json_text(verification)
    # Fail closed if an allowlist unexpectedly admits a local/private path.
    for text in outputs.values():
        assert str(Path.home()) not in text and ".cache/" not in text
        assert "file://" not in text and "project-file:" not in text
    output_hashes = {
        name: hashlib.sha256(text.encode()).hexdigest()
        for name, text in outputs.items()
    }
    outputs["results/export_manifest.json"] = json_text(
        {
            "schema": "sanitized_aggregate_export_manifest_v1",
            "files": output_hashes,
            "source_receipt_sha256": PINNED_RECEIPTS,
            "public_aggregate_only": True,
        }
    )
    for name, text in outputs.items():
        path = output_root / name
        if verify_only:
            assert path.is_file() and path.read_text() == text, (
                f"Export differs: {name}"
            )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x") as handle:
                handle.write(text)
    return {
        "passed": True,
        "verify_only": verify_only,
        "exported_files": len(outputs),
        "source_bindings_unchanged": len(seen),
        "max_numeric_error": max_error,
        "files": sorted(outputs),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-manifest",
        type=Path,
        required=True,
        help="External private manifest; never commit it",
    )
    parser.add_argument("--output-root", type=Path, default=Path.cwd())
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            export(args.source_manifest, args.output_root, args.verify_only),
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
