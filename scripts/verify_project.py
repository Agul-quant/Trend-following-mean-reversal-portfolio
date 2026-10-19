#!/usr/bin/env python3
"""Verify the public aggregate-only project snapshot without private inputs.

This is an integrity/reporting check, not a financial account or optimizer run.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import math
import re
import struct
import sys
import zipfile
from pathlib import Path, PurePosixPath
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

STAGES = {
    "development": ("2017-01-01", "2020-12-31", 1007),
    "validation": ("2021-01-01", "2023-12-31", 753),
    "historical_OOS": ("2024-01-01", "2026-10-15", 700),
}
PORTFOLIOS = {
    "daily_capped_max_sharpe", "initial_capped_max_sharpe",
    "uncapped_max_sharpe", "equal_initial",
}
SYMBOLS = ["GDX", "FXI", "QQQ", "UNG", "FDN", "BND"]
COSTS = {1.0, 3.0, 10.0, 25.0}
# These are existing saved definitions/archives, not newly selected solutions.
IMMUTABLE_BINDINGS = {
    "configs/four_portfolios.json": "79badfecbb5e260523582301bcd3aecda746323bab08142aa365c8df1642cc3e",
    "configs/selected_strategies.json": "0d983ac0bbb3a292d5223c5cd00c0e84997f542e7fff4c6e775079dc51cd68f9",
    "configs/portfolios.json": "1ca3d1669994437b80898de3e655b42160f77414324ea84fd0d67f17e5bb83fc",
    "results/export_manifest.json": "5bdc714b1175ba4c32ed5a36cbcc602b78932644cd81c47bfbeecd97cb345144",
    "reports/four_portfolios_three_periods/manifest.json": "8b4aa571d06a761974bad9fa4426f562fc5836081232e8b8100fdad69a81a83d",
}
MANAGED_DIRECTORIES = (
    "final_reports", "results/four_portfolio_attribution", "assets/periods",
)
FORBIDDEN_SUFFIXES = {
    ".npz", ".npy", ".parquet", ".pkl", ".pickle", ".h5", ".hdf5",
    ".sqlite", ".sqlite3", ".pem", ".key", ".env", ".log",
}
PRIVATE_TEXT = re.compile(
    r"/Users/|/home/|/var/folders/|file://|[A-Za-z]:[\\/]Users[\\/]"
    r"|(?:apikey|api_key|api-key)=[A-Za-z0-9]{8,}", re.IGNORECASE,
)


class VerificationError(ValueError):
    """A public artifact violates its declared integrity or scope."""


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def safe_relative(value):
    require(isinstance(value, str) and value, "Empty/non-string artifact path")
    path = PurePosixPath(value)
    require(
        not path.is_absolute() and ".." not in path.parts
        and "\\" not in value and not re.match(r"^[A-Za-z]:", value)
        and str(path) == value,
        f"Unsafe or noncanonical artifact path: {value}",
    )
    require(not ({".git", ".cache", "private", "data"} & set(path.parts)),
            f"Private directory in artifact path: {value}")
    require(path.suffix.lower() not in FORBIDDEN_SUFFIXES
            and not path.name.startswith(".env"),
            f"Forbidden private-data artifact: {value}")
    return path


def artifact_path(root, relative):
    safe_relative(relative)
    path = root / relative
    require(not any(p.is_symlink() for p in [path, *path.parents] if p.is_relative_to(root)),
            f"Symlink is not a portable artifact: {relative}")
    require(path.is_file(), f"Missing artifact: {relative}")
    require(path.resolve().is_relative_to(root.resolve()),
            f"Artifact escapes project root: {relative}")
    return path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise VerificationError(f"Invalid JSON: {path.name}") from exc


def check_json_privacy(value):
    if isinstance(value, dict):
        for item in value.values():
            check_json_privacy(item)
    elif isinstance(value, list):
        require(not (len(value) > 128 and all(isinstance(x, (int, float)) for x in value)),
                "Long numeric daily array in public JSON")
        for item in value:
            check_json_privacy(item)
    elif isinstance(value, float):
        require(math.isfinite(value), "Nonfinite public JSON metric")
    elif isinstance(value, str):
        require(not PRIVATE_TEXT.search(value), "Private locator or credential in public JSON")


def check_png_metadata(payload):
    require(payload[:8] == b"\x89PNG\r\n\x1a\n", "Invalid PNG signature")
    position = 8
    while position < len(payload):
        require(position + 12 <= len(payload), "Truncated PNG")
        size = struct.unpack(">I", payload[position:position + 4])[0]
        kind = payload[position + 4:position + 8]
        body = payload[position + 8:position + 8 + size]
        require(len(body) == size and position + size + 12 <= len(payload), "Truncated PNG chunk")
        if kind == b"tEXt":
            key, _, text = body.partition(b"\0")
            require(key == b"Software" and len(text) < 128, "Unexpected PNG text metadata")
            require(not PRIVATE_TEXT.search(text.decode("latin1")), "Private PNG metadata")
        require(kind not in {b"zTXt", b"iTXt", b"eXIf"}, "Unexpected rich PNG metadata")
        position += size + 12
        if kind == b"IEND":
            require(position == len(payload), "Trailing PNG payload")
            return
    raise VerificationError("PNG has no terminal chunk")


def check_archive(payload, *, is_docx=False):
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise VerificationError("Invalid public ZIP/DOCX container") from exc
    with archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "Duplicate archive members")
        for name in names:
            if name.endswith("/"):
                continue
            safe_relative(name)
            raw = archive.read(name)
            suffix = PurePosixPath(name).suffix.lower()
            if suffix == ".png":
                check_png_metadata(raw)
            elif suffix in {".json", ".xml", ".rels", ".md", ".csv", ".txt", ".html", ".toml"}:
                text = raw.decode("utf-8")
                require(not PRIVATE_TEXT.search(text), f"Private locator inside archive: {name}")
                if suffix == ".json":
                    check_json_privacy(json.loads(text))
            elif suffix in {".npz", ".npy", ".parquet"}:
                raise VerificationError(f"Private array inside archive: {name}")
        if not is_docx and "SUPPLEMENT_MANIFEST.json" in names:
            manifest = json.loads(archive.read("SUPPLEMENT_MANIFEST.json"))
            listed = set()
            for item in manifest["files"]:
                name = item["path"]
                require(name not in listed, "Duplicate supplement manifest member")
                listed.add(name)
                raw = archive.read(name)
                require(hashlib.sha256(raw).hexdigest() == item["sha256"]
                        and len(raw) == item["bytes"], f"Supplement hash mismatch: {name}")
            require(set(names) == listed | {"SUPPLEMENT_MANIFEST.json"},
                    "Unlisted supplement payload")


def verify_files(root, manifest):
    require(manifest.get("schema") == "earlier_four_portfolio_publication_v1",
            "Unknown publication schema")
    require(manifest.get("aggregate_only") is True, "Publication must be aggregate-only")
    files = manifest.get("files")
    require(isinstance(files, list) and files, "Empty publication allowlist")
    listed = set()
    for item in files:
        relative = item.get("path")
        require(relative not in listed, f"Duplicate publication member: {relative}")
        path = artifact_path(root, relative)
        listed.add(relative)
        require(re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")) is not None,
                f"Invalid SHA256 binding: {relative}")
        require(isinstance(item.get("bytes"), int) and not isinstance(item.get("bytes"), bool)
                and path.stat().st_size == item["bytes"], f"Byte-count mismatch: {relative}")
        require(sha256(path) == item["sha256"], f"SHA256 mismatch: {relative}")
        suffix = path.suffix.lower()
        if suffix == ".json":
            check_json_privacy(read_json(path))
        elif suffix == ".png":
            check_png_metadata(path.read_bytes())
        elif suffix in {".zip", ".docx"}:
            check_archive(path.read_bytes(), is_docx=suffix == ".docx")
        elif suffix == ".pdf":
            raw = path.read_bytes()
            require(raw.startswith(b"%PDF-") and b"%%EOF" in raw[-1024:],
                    f"Invalid PDF framing: {relative}")
        elif suffix in {".md", ".html", ".csv", ".txt"}:
            require(not PRIVATE_TEXT.search(path.read_text(encoding="utf-8")),
                    f"Private locator in public artifact: {relative}")
    for relative in MANAGED_DIRECTORIES:
        directory = root / relative
        if directory.exists():
            for path in directory.rglob("*"):
                if path.is_file() or path.is_symlink():
                    require(path.relative_to(root).as_posix() in listed,
                            f"Unlisted managed artifact: {path.relative_to(root)}")
    return listed


def csv_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def row_key(row, id_column):
    try:
        return row["stage"], row[id_column], float(row["slippage_bps_each_way"])
    except (KeyError, ValueError, TypeError) as exc:
        raise VerificationError("Malformed aggregate row identity") from exc


def verify_row_scope(rows, identifiers, id_column="portfolio_id"):
    expected = {(stage, identity, cost) for stage in STAGES for identity in identifiers for cost in COSTS}
    keys = [row_key(row, id_column) for row in rows]
    require(len(keys) == len(set(keys)), "Duplicate aggregate row identity")
    require(set(keys) == expected, "Incomplete or unexpected stage/configuration/cost identities")
    for row in rows:
        stage = row["stage"]
        require(float(row["commission_bps_each_way"]) == 1, "Incorrect commission scenario")
        if "observations" in row:
            require(int(row["observations"]) == STAGES[stage][2], "Incorrect stage observation count")
    return {row_key(row, id_column): row for row in rows}


def same_scalar(a, b):
    if a is None:
        return b is None or b == ""
    if isinstance(a, bool):
        return b == a or b == str(a)
    if isinstance(a, (int, float)):
        try:
            return math.isfinite(float(b)) and math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False
    return a == b


def verify_rows_equal(json_rows, csv_data, id_column="portfolio_id"):
    a = {row_key(x, id_column): x for x in json_rows}
    b = {row_key(x, id_column): x for x in csv_data}
    require(len(a) == len(json_rows) and len(b) == len(csv_data) and set(a) == set(b),
            "JSON/CSV row identity mismatch")
    for key, row in a.items():
        require(set(row) == set(b[key]), "JSON/CSV column mismatch")
        for column, value in row.items():
            require(same_scalar(value, b[key][column]), f"JSON/CSV metric mismatch: {key} {column}")


class TableParser(HTMLParser):
    """Collect visible HTML table cells, independently of the report builder."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            require(self.table is None, "Nested report tables are unsupported")
            self.table = []
        elif self.table is not None and tag == "tr":
            self.row = []
        elif self.row is not None and tag in {"th", "td"}:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"th", "td"} and self.cell is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def display_number(value, *, percent=False, digits=3):
    if value is None or value == "":
        return "Undefined"
    return f"{float(value) * (100 if percent else 1):,.{digits}f}" + ("%" if percent else "")


def verify_html_tables(html, stage, source_rows, source_single, source_joint, config):
    parser = TableParser()
    parser.feed(html)
    aliases = {
        "daily_capped_max_sharpe": "Daily cap fit",
        "initial_capped_max_sharpe": "Initial cap fit",
        "uncapped_max_sharpe": "Uncapped fit", "equal_initial": "Equal initial",
        "QQQ_buy_and_hold": "QQQ buy and hold", "matched_cash": "Matched cash",
    }
    order = [x["id"] for x in config["portfolios"]]
    pp = {row_key(x, "portfolio_id"): x for x in source_rows["portfolio_rows"]}
    cc = {row_key(x, "control_id"): x for x in source_rows["control_rows"]}
    single = {row_key(x, "portfolio_id"): x for x in source_single}
    joint = {row_key(x, "portfolio_id"): x for x in source_joint}
    metric_tables = [t for t in parser.tables if t and t[0][:2] == ["Allocation or control", "Sharpe"]]
    require(len(metric_tables) == 4, "Expected four cost performance tables")
    cells = 0
    for cost, table in zip(sorted(COSTS), metric_tables):
        expected = []
        for identity in order + ["QQQ_buy_and_hold", "matched_cash"]:
            row = (pp if identity in PORTFOLIOS else cc)[(stage, identity, cost)]
            expected.append([
                aliases[identity], display_number(row["cash_excess_sharpe"]),
                display_number(float(row["terminal_normalized_equity"]) - 1, percent=True, digits=2),
                display_number(row["cagr"], percent=True, digits=2),
                display_number(row["annualized_return_volatility"], percent=True, digits=2),
                display_number(row["max_drawdown"], percent=True, digits=2),
                "$" + display_number(row["terminal_equity_from_1000"], digits=2),
            ])
        require(table[1:] == expected, "Visible HTML performance cells differ from saved metrics")
        cells += sum(len(row) for row in expected)
    weight_tables = [t for t in parser.tables if t and t[0][:2] == ["Strategy sleeve", "Daily cap fit"]]
    expected = [[symbol] + [display_number(x["initial_weights"][symbol], percent=True, digits=6)
                           for x in config["portfolios"]] for symbol in SYMBOLS]
    require(len(weight_tables) == 1 and weight_tables[0][1:] == expected, "Visible HTML weight mismatch")
    cells += sum(len(row) for row in expected)
    single_tables = [t for t in parser.tables if t and t[0][:3] == ["Slippage bp", "Allocation", "Alpha annual"]]
    expected = []
    for cost in sorted(COSTS):
        for identity in order:
            row = single[(stage, identity, cost)]
            expected.append([str(int(cost)), aliases[identity],
                             display_number(row["alpha_annual_arithmetic"], percent=True, digits=2),
                             display_number(row["beta_QQQ"], digits=4),
                             display_number(row["r_squared"], percent=True, digits=2),
                             display_number(row["residual_annualized_volatility"], percent=True, digits=2)])
    require(len(single_tables) == 1 and single_tables[0][1:] == expected,
            "Visible HTML QQQ attribution mismatch")
    cells += sum(len(row) for row in expected)
    joint_tables = [t for t in parser.tables if t and t[0][:2] == ["Allocation", "GDX β"]]
    require(len(joint_tables) == 4, "Expected four joint attribution tables")
    for cost, table in zip(sorted(COSTS), joint_tables):
        expected = []
        for identity in order:
            row = joint[(stage, identity, cost)]
            expected.append([aliases[identity]] + [display_number(row[f"beta_{symbol}"], digits=4)
                                                  for symbol in SYMBOLS] + [
                display_number(row["alpha_annual_arithmetic"], percent=True, digits=2),
                display_number(row["r_squared"], percent=True, digits=2)])
        require(table[1:] == expected, "Visible HTML joint attribution mismatch")
        cells += sum(len(row) for row in expected)
    cap_tables = [t for t in parser.tables if t and t[0][:3] == ["Slippage bp", "Allocation", "Largest daily share"]]
    caps = [r for r in source_rows["cap_rows"] if r["stage"] == stage]
    expected = [[str(int(float(r["slippage_bps_each_way"]))), aliases[r["portfolio_id"]],
                 display_number(r["max_daily_capital_share"], percent=True, digits=4),
                 "Pass" if r["initial_cap_pass_diagnostic"] else "Fail",
                 "Pass" if r["daily_cap_pass_diagnostic"] else "Fail"] for r in caps]
    require(len(cap_tables) == 1 and cap_tables[0][1:] == expected, "Visible HTML cap table mismatch")
    cells += sum(len(row) for row in expected)
    return cells


def verify_stage_reports(root, manifest, source, attribution, config, strategies):
    counts = {}
    render_manifest = read_json(root / "final_reports/render_manifest.json")
    require(render_manifest.get("schema") == "same_html_pdf_rendering_v1"
            and render_manifest.get("same_HTML_source") is True
            and render_manifest.get("external_network_requests") == 0,
            "PDFs need an offline same-HTML rendering receipt")
    render_rows = {x["stage"]: x for x in render_manifest.get("reports", [])}
    require(set(render_rows) == set(STAGES) and len(render_manifest["reports"]) == 3,
            "Incomplete PDF rendering receipt")
    for entry in manifest["reports"]:
        stage = entry["stage"]
        directory = entry["directory"]
        record = read_json(artifact_path(root, entry["manifest"]))
        require(record.get("schema") == "four_fixed_portfolios_offline_class_reports_v1"
                and record.get("stage") == stage and record.get("aggregate_only") is True
                and record.get("stage_bounds") == list(STAGES[stage][:2]),
                "Incorrect stage report manifest")
        for name, digest in record["files"].items():
            safe_relative(name)
            require(sha256(artifact_path(root, f"{directory}/{name}")) == digest,
                    "Stage output hash mismatch")
        for name, digest in record["input_hashes"].items():
            require(sha256(artifact_path(root, name)) == digest, "Stage input hash mismatch")
        data = read_json(artifact_path(root, f"{directory}/report.json"))
        require(data.get("stage") == stage, "Cross-stage report metadata")
        require(data.get("summary") == next(r for r in source["stage_summaries"] if r["stage"] == stage),
                "Stage summary differs from saved clock")
        require(data.get("initial_allocations") == source["portfolios"]
                and data.get("strategy_definitions") == strategies["strategies"],
                "Stage definitions differ from saved inputs")
        for field, id_column in (("portfolio_rows", "portfolio_id"), ("control_rows", "control_id"),
                                 ("cap_rows", "portfolio_id"), ("QQQ_single_factor_rows", "portfolio_id"),
                                 ("six_passive_factor_rows", "portfolio_id")):
            parent = source if field in source else attribution
            expected = [r for r in parent[field] if r["stage"] == stage]
            verify_rows_equal(expected, data[field], id_column)
            verify_rows_equal(data[field], csv_rows(artifact_path(root, f"{directory}/{field}.csv")), id_column)
        expected_diagnostics = [r for r in attribution["factor_diagnostic_rows"] if r["stage"] == stage]
        require(len(expected_diagnostics) == 4 and data.get("factor_diagnostic_rows") == expected_diagnostics,
                "Stage factor diagnostics differ from saved fits")
        diagnostic_csv = csv_rows(artifact_path(root, f"{directory}/factor_diagnostic_rows.csv"))
        require(len(diagnostic_csv) == 4, "Incomplete stage diagnostic CSV")
        for saved, row in zip(expected_diagnostics, diagnostic_csv):
            require(set(saved) == set(row) and all(same_scalar(v, row[k]) for k, v in saved.items()),
                    "Stage factor diagnostic CSV differs from saved fits")
        if stage == "validation":
            warning = read_json(root / "reports/four_portfolios_three_periods/provenance.json")["validation_current_daily_cap"]
            require(data.get("audited_cap_warning") == warning and warning["days_above_one_third_each_cost"] == 41,
                    "Recorded validation cap breach must remain visible")
        if stage == "historical_OOS":
            full_correlation = csv_rows(root / "results/strategy_correlation_matrices_all_costs.csv")
            baseline = [r for r in full_correlation if float(r["slippage_bps_each_way"]) == 3]
            expected = [{"symbol": r["symbol"], **{s: float(r[s]) for s in SYMBOLS}} for r in baseline]
            require(len(expected) == 6 and [r["symbol"] for r in expected] == SYMBOLS
                    and data.get("baseline_active_strategy_correlation_rows") == expected,
                    "OOS baseline correlations differ from saved active-strategy matrix")
            correlations = csv_rows(artifact_path(root, f"{directory}/baseline_active_strategy_correlation_rows.csv"))
            require(len(correlations) == 6, "Incomplete OOS correlation CSV")
            for saved, row in zip(expected, correlations):
                require(set(saved) == set(row) and all(same_scalar(v, row[k]) for k, v in saved.items()),
                        "OOS correlation CSV differs from saved matrix")
        html = artifact_path(root, entry["html"]).read_text(encoding="utf-8")
        require(not re.search(r"<script\b|(?:src|href)\s*=\s*[\"'](?:https?:|//|file:)", html, re.I),
                "Stage HTML is not standalone and script-free")
        rasters = re.findall(r"data:image/png;base64,([A-Za-z0-9+/=]+)", html)
        expected_images = [root / f"assets/periods/{stage}_baseline.png"]
        if stage == "historical_OOS":
            expected_images.append(root / "assets/periods/oos_strategy_correlations.png")
        require(len(rasters) == len(expected_images) and html.count("data:") == len(expected_images),
                "Expected only audited rasters, not serialized account data")
        raster_hashes = [hashlib.sha256(base64.b64decode(item, validate=True)).hexdigest() for item in rasters]
        require(raster_hashes == [sha256(path) for path in expected_images],
                "Report rasters differ from audited stage images")
        cells = verify_html_tables(html, stage, source,
                                   attribution["QQQ_single_factor_rows"],
                                   attribution["six_passive_factor_rows"], config)
        rendered = render_rows[stage]
        require(rendered["html_sha256"] == sha256(root / entry["html"])
                and rendered["pdf_sha256"] == sha256(root / entry["pdf"]),
                "PDF rendering does not bind the completed HTML/PDF")
        counts[stage] = {"portfolio_rows": len(data["portfolio_rows"]),
                         "control_rows": len(data["control_rows"]),
                         "visible_html_table_cells": cells}
    return counts


def verify_snapshot(root, manifest):
    for relative, expected in IMMUTABLE_BINDINGS.items():
        require(sha256(artifact_path(root, relative)) == expected,
                f"Saved definition/archive changed: {relative}")
    archive = read_json(root / "results/export_manifest.json")
    require(len(archive["files"]) == 18, "Historical aggregate archive is incomplete")
    for relative, expected in archive["files"].items():
        require(sha256(artifact_path(root, relative)) == expected,
                f"Historical five-portfolio archive changed: {relative}")
    presentation = read_json(root / "configs/study_presentation.json")
    require(manifest.get("study") == presentation, "Presentation metadata binding mismatch")
    require(presentation.get("active_study") == "earlier_four_fixed_portfolio_study",
            "Unexpected active study")
    require(set(presentation.get("portfolio_ids", [])) == PORTFOLIOS
            and len(presentation["portfolio_ids"]) == 4, "Expected four retained portfolios")
    for stage, (start, end, _) in STAGES.items():
        require(presentation.get(stage) == {"start": start, "end": end}, "Incorrect active stage bounds")
    config = read_json(root / "configs/four_portfolios.json")
    strategies = read_json(root / "configs/selected_strategies.json")
    require(config.get("symbols") == strategies.get("symbols") == SYMBOLS,
            "Incorrect six-sleeve order")
    require({x["id"] for x in config["portfolios"]} == PORTFOLIOS
            and len(config["portfolios"]) == 4, "Unexpected portfolio configuration")
    for row in config["portfolios"]:
        weights = row["initial_weights"]
        require(set(weights) == set(SYMBOLS) and all(math.isfinite(x) and x >= 0 for x in weights.values())
                and math.isclose(sum(weights.values()), 1, abs_tol=1e-14), "Invalid fixed weights")
    require(len(strategies["strategies"]) == 6
            and [x["symbol"] for x in strategies["strategies"]] == SYMBOLS,
            "Incorrect selected strategy definitions")
    directory = root / "reports/four_portfolios_three_periods"
    saved_manifest = read_json(directory / "manifest.json")
    require(len(saved_manifest["files"]) == 7, "Saved three-period aggregate is incomplete")
    for name, expected in saved_manifest["files"].items():
        safe_relative(name)
        require(sha256(artifact_path(root, f"reports/four_portfolios_three_periods/{name}")) == expected,
                f"Saved three-period aggregate changed: {name}")
    report = read_json(directory / "report.json")
    counts = {}
    for key, filename, identifiers, id_column in (
        ("portfolio_rows", "portfolio_rows.csv", PORTFOLIOS, "portfolio_id"),
        ("control_rows", "control_rows.csv", {"QQQ_buy_and_hold", "matched_cash"}, "control_id"),
        ("cap_rows", "cap_rows.csv", PORTFOLIOS, "portfolio_id"),
    ):
        rows = csv_rows(directory / filename)
        verify_row_scope(rows, identifiers, id_column)
        verify_rows_equal(report[key], rows, id_column)
        counts[key] = len(rows)
    summaries = csv_rows(directory / "stage_summaries.csv")
    require(len(summaries) == 3 and {x["stage"] for x in summaries} == set(STAGES), "Incomplete stage clocks")
    for row in summaries:
        start, end, count = STAGES[row["stage"]]
        require((row["scored_start"], row["scored_end"], int(row["observations"])) == (start, end, count),
                "Incorrect saved stage bounds")
        require(float(row["fresh_initial_capital"]) == 1000, "Incorrect initial stage account")
    attribution_dir = root / "results/four_portfolio_attribution"
    attribution = read_json(attribution_dir / "attribution.json")
    for key, filename in (
        ("QQQ_single_factor_rows", "QQQ_single_factor_all_periods_all_costs.csv"),
        ("six_passive_factor_rows", "six_passive_factor_all_periods_all_costs.csv"),
    ):
        rows = csv_rows(attribution_dir / filename)
        verify_row_scope(rows, PORTFOLIOS)
        require(key in attribution, f"Attribution JSON missing {key}")
        verify_rows_equal(attribution[key], rows)
        counts[key] = len(rows)
    reports = manifest.get("reports", [])
    require(len(reports) == 3 and {x.get("stage") for x in reports} == set(STAGES),
            "Expected three separately identified stage reports")
    for entry in reports:
        for key in ("html", "pdf", "manifest"):
            artifact_path(root, entry[key])
        require(entry["html"].startswith(entry["directory"] + "/")
                and entry["pdf"].startswith(entry["directory"] + "/"), "Report escaped stage directory")
    counts["stage_reports"] = verify_stage_reports(root, manifest, report, attribution, config, strategies)
    return counts


def markdown_anchor(value):
    value = re.sub(r"<[^>]*>", "", value).strip().lower()
    return re.sub(r"[^\w\- ]", "", value).replace(" ", "-")


def verify_markdown_links(root, listed):
    checked = 0
    for relative in sorted(listed):
        path = root / relative
        if path.suffix.lower() != ".md":
            continue
        text = path.read_text(encoding="utf-8")
        # Fenced examples are documentation, not actual navigation targets.
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        links = re.findall(r"!?\[[^\]]*\]\(([^\s)]+)(?:\s+[^)]*)?\)", text)
        for target in links:
            target = target.strip("<>")
            url = urlsplit(target)
            if url.scheme or url.netloc:
                require(url.scheme not in {"file", "javascript", "data"}, "Unsafe documentation URL")
                continue
            destination = (path.parent / unquote(url.path)).resolve() if url.path else path.resolve()
            require(destination.is_relative_to(root.resolve()), f"Documentation link escapes project: {relative}")
            require(destination.exists(), f"Broken documentation link: {relative} -> {target}")
            if url.fragment and destination.suffix.lower() in {".md", ".html"}:
                body = destination.read_text(encoding="utf-8")
                if destination.suffix.lower() == ".md":
                    anchors = {markdown_anchor(x) for x in re.findall(r"^#{1,6}\s+(.+)$", body, re.M)}
                else:
                    anchors = set(re.findall(r'\bid=[\"\']([^\"\']+)', body))
                require(unquote(url.fragment) in anchors, f"Missing documentation fragment: {target}")
            checked += 1
    return checked


def verify(root, manifest_path):
    root = Path(root).resolve()
    manifest = read_json(root / manifest_path)
    listed = verify_files(root, manifest)
    counts = verify_snapshot(root, manifest)
    links = verify_markdown_links(root, listed)
    return {"passed": True, "public_files_verified": len(listed),
            "aggregate_counts": counts, "relative_documentation_links_verified": links,
            "private_inputs_or_account_runs_required": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="metadata/project_manifest.json")
    args = parser.parse_args(argv)
    try:
        result = verify(args.root, args.manifest)
    except (VerificationError, KeyError, OSError, ValueError, TypeError) as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
