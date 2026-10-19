"""Private-input-free checks of the published baseline raster assets."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import struct
import zlib
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PORTFOLIOS = [
    "daily_capped_max_sharpe",
    "initial_capped_max_sharpe",
    "uncapped_max_sharpe",
    "equal_initial",
    "max_cagr_100pct_gdx",
]
FIGURES = {"baseline_equity.png", "baseline_drawdown.png"}


def read_json(relative):
    return json.loads((ROOT / relative).read_text())


def manifest():
    return read_json("assets/baseline_charts_manifest.json")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(relative):
    with (ROOT / relative).open(newline="") as handle:
        return list(csv.DictReader(handle))


def png_chunks(path):
    """Read PNG framing/metadata without a plotting or imaging dependency."""
    raw = path.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    position, chunks = 8, []
    while position < len(raw):
        length = struct.unpack(">I", raw[position : position + 4])[0]
        kind = raw[position + 4 : position + 8]
        payload = raw[position + 8 : position + 8 + length]
        assert len(payload) == length
        crc = struct.unpack(">I", raw[position + 8 + length : position + 12 + length])[0]
        assert crc == zlib.crc32(kind + payload) & 0xFFFFFFFF
        chunks.append((kind, payload))
        position += length + 12
        if kind == b"IEND":
            break
    assert position == len(raw)
    return chunks


def test_chart_scope_clocks_costs_and_initial_point():
    data = manifest()
    protocol = read_json("configs/research_protocol.json")
    assert data["schema"] == "baseline_raster_charts_v1"
    assert [row["id"] for row in data["series_summary"]] == PORTFOLIOS + ["QQQ_buy_and_hold"]
    assert data["daily_return_observations"] == protocol["historical_OOS"]["sessions"] == 700
    assert data["plotted_points_per_series_including_initial"] == 701
    assert data["initial_capital_usd"] == protocol["initial_cash_per_strategy_account"] == 1000
    assert data["baseline_costs_bps_each_way"] == {"commission": 1, "slippage": 3}
    assert data["scored_period"] == {"start": "2024-01-01", "end": "2026-10-15"}
    assert data["account_initial_timestamp"] == "2024-01-02T14:30:00+00:00"
    assert data["first_daily_valuation"] == "2024-01-02T22:00:00+00:00"
    assert data["last_daily_valuation"] == "2026-10-15T21:00:00+00:00"
    initial = datetime.fromisoformat(data["account_initial_timestamp"])
    terminal = datetime.fromisoformat(data["last_daily_valuation"])
    years = (terminal - initial).total_seconds() / (365 * 86400)
    assert years == data["ACT365_elapsed_years"] == protocol["ACT365_elapsed_years"]
    assert data["checks"]["initial_balance_included"] is True
    assert data["checks"]["all_700_daily_observations_preserved"] is True
    assert data["checks"]["QQQ_uses_passive_control_not_active_strategy"] is True


def test_all_six_summaries_match_published_matched_cost_aggregates():
    data = manifest()
    baseline = {
        row["portfolio_id"]: row
        for row in csv_rows("results/portfolio_metrics_all_costs.csv")
        if float(row["commission_bps_each_way"]) == 1
        and float(row["slippage_bps_each_way"]) == 3
    }
    controls = [
        row
        for row in csv_rows("results/own_ETF_buy_and_hold_metrics_all_costs.csv")
        if row["symbol"] == "QQQ"
        and float(row["commission_bps_each_way"]) == 1
        and float(row["slippage_bps_each_way"]) == 3
    ]
    assert set(baseline) == set(PORTFOLIOS) and len(controls) == 1
    assert controls[0]["style"] == "passive_buy_and_hold"
    assert controls[0]["candidate_id"] == "benchmark_buy_and_hold"
    baseline["QQQ_buy_and_hold"] = controls[0]
    names = {
        "terminal_equity_usd": "terminal_equity_from_1000",
        "max_daily_drawdown": "max_drawdown",
        "cagr": "cagr",
        "cash_excess_sharpe": "cash_excess_sharpe",
    }
    for row in data["series_summary"]:
        assert row["initial_equity_usd"] == 1000
        for published, column in names.items():
            assert math.isfinite(row[published])
            assert row[published] == pytest.approx(float(baseline[row["id"]][column]), rel=0, abs=1e-10)
        assert row["cagr"] == pytest.approx(
            (row["terminal_equity_usd"] / 1000) ** (1 / data["ACT365_elapsed_years"]) - 1,
            rel=0,
            abs=1e-12,
        )
        assert -1 < row["max_daily_drawdown"] <= 0
    assert data["checks"]["all_six_series_match_published_baseline_aggregates"] is True
    assert data["checks"]["maximum_absolute_aggregate_difference"] < 1e-10


def test_png_bytes_dimensions_and_only_nonprivate_raster_metadata():
    data = manifest()
    assert set(data["figures"]) == FIGURES
    assert data["png_metadata_keys"] == ["Software", "dpi"]
    for filename, info in data["figures"].items():
        path = ROOT / "assets" / filename
        assert sha(path) == info["sha256"]
        assert info["format"] == "PNG"
        chunks = png_chunks(path)
        assert chunks[0][0] == b"IHDR" and chunks[-1] == (b"IEND", b"")
        assert {kind for kind, _ in chunks} == {b"IHDR", b"tEXt", b"pHYs", b"IDAT", b"IEND"}
        width, height = struct.unpack(">II", chunks[0][1][:8])
        assert (width, height) == (info["width_px"], info["height_px"]) == (1920, 1152)
        texts = [payload for kind, payload in chunks if kind == b"tEXt"]
        assert texts == [b"Software\x00Trend Following Study"]
        density = [payload for kind, payload in chunks if kind == b"pHYs"]
        assert len(density) == 1 and struct.unpack(">IIB", density[0]) == (6299, 6299, 1)
    assert sorted(path.name for path in (ROOT / "assets").iterdir()) == [
        "baseline_charts_manifest.json", "baseline_drawdown.png", "baseline_equity.png"
    ]


def test_generator_config_bindings_and_original_aggregate_export_unchanged():
    data = manifest()
    expected = {
        "configs/portfolios.json", "configs/research_protocol.json",
        "scripts/plot_portfolios.py", "src/trend_portfolio/analytics.py",
        "src/trend_portfolio/cli.py", "src/trend_portfolio/plotting.py",
    }
    assert set(data["public_generator_and_config_sha256"]) == expected
    for relative, digest in data["public_generator_and_config_sha256"].items():
        assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
        assert sha(ROOT / relative) == digest
    export = read_json("results/export_manifest.json")
    assert len(export["files"]) == 18
    for relative, digest in export["files"].items():
        assert sha(ROOT / relative) == digest
    assert sha(ROOT / "results/export_manifest.json") == "5bdc714b1175ba4c32ed5a36cbcc602b78932644cd81c47bfbeecd97cb345144"
    receipts = read_json("results/provenance.json")["source_delivery_receipt_sha256"]
    assert data["parent_delivery_receipt_sha256_by_logical_role"] == {
        "saved_passive_benchmark_bundle": receipts["multifactor_receipt"],
        "saved_strategy_sleeve_equity_bundle": receipts["capped_receipt"],
    }
    assert data["original_aggregate_export_unchanged"] is True


def test_readme_embeds_both_assets_and_documents_accounting_scope():
    readme = (ROOT / "README.md").read_text()
    for filename in FIGURES:
        assert re.search(r"!\[[^\]]+\]\(assets/" + re.escape(filename) + r"\)", readme)
    assert "docs/charts.md" in readme
    explanation = (ROOT / "docs/charts.md").read_text().lower()
    for term in ("700", "$1,000", "passive", "initial", "daily", "drawdown"):
        assert term in explanation
    assert "before the first daily return" in explanation
    assert "not an untouched portfolio test" in readme.lower()


def test_manifest_is_aggregate_only_with_no_private_locators_or_daily_arrays():
    data = manifest()
    assert data["published_numeric_daily_paths"] is False
    assert data["new_market_data_downloads_strategy_runs_or_optimization"] is False
    assert "not untouched" in data["interpretation"]
    forbidden_keys = {
        "daily_returns", "equity_values", "daily_equity", "timestamps",
        "private_input_path", "source_paths", "source_maps", "authorization",
    }

    def check(value):
        if isinstance(value, dict):
            assert not (set(value) & forbidden_keys)
            for item in value.values():
                check(item)
        elif isinstance(value, list):
            assert len(value) <= 6  # Six aggregate rows, never the 700 daily observations.
            for item in value:
                check(item)
        elif isinstance(value, str):
            assert not value.startswith(("/", "file:", "~/"))
            assert not re.match(r"^[A-Za-z]:[\\/]", value)
            assert ".cache/" not in value

    check(data)
    for group in (
        "private_input_sha256_by_logical_role",
        "parent_delivery_receipt_sha256_by_logical_role",
    ):
        assert set(data[group]) == {"saved_passive_benchmark_bundle", "saved_strategy_sleeve_equity_bundle"}
        assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in data[group].values())
    for row in data["series_summary"]:
        assert set(row) == {
            "id", "label", "initial_equity_usd", "terminal_equity_usd",
            "cagr", "cash_excess_sharpe", "max_daily_drawdown",
        }
