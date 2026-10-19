"""Private-input-free publication allowlist and aggregate scope fixtures."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import zipfile
import io

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("publication_verifier", ROOT / "scripts/verify_project.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def binding(root, relative):
    data = (root / relative).read_bytes()
    return {"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def minimal_allowlist(tmp_path):
    path = tmp_path / "README.md"
    path.write_text("# Project\n", encoding="utf-8")
    return {"schema": "earlier_four_portfolio_publication_v1", "aggregate_only": True,
            "files": [binding(tmp_path, "README.md")]}


def scope_rows(identities=None):
    identities = identities or verifier.PORTFOLIOS
    return [{"stage": stage, "portfolio_id": identity, "slippage_bps_each_way": cost,
             "commission_bps_each_way": 1, "observations": verifier.STAGES[stage][2]}
            for stage in verifier.STAGES for identity in identities for cost in verifier.COSTS]


def test_allowlist_accepts_bound_portable_file(tmp_path):
    data = minimal_allowlist(tmp_path)
    assert verifier.verify_files(tmp_path, data) == {"README.md"}


@pytest.mark.parametrize("name", ["../escape.json", "/absolute.json", "folder/../escape.json",
                                 "C:\\Users\\person\\data.json", "a\\b.json", "a//b.json",
                                 ".cache/secret.json", "private/inputs.json", "data/ohlcv.csv",
                                 "daily.npz", "daily.npy", "capture.parquet", "secret.key", ".env.local"])
def test_unsafe_or_data_paths_rejected(name):
    with pytest.raises(verifier.VerificationError):
        verifier.safe_relative(name)


def test_duplicate_allowlist_rejected(tmp_path):
    data = minimal_allowlist(tmp_path)
    data["files"].append(copy.deepcopy(data["files"][0]))
    with pytest.raises(verifier.VerificationError, match="Duplicate"):
        verifier.verify_files(tmp_path, data)


def test_tampered_hash_and_bytes_rejected(tmp_path):
    data = minimal_allowlist(tmp_path)
    (tmp_path / "README.md").write_text("# Altered\n", encoding="utf-8")
    with pytest.raises(verifier.VerificationError, match="Byte-count|SHA256"):
        verifier.verify_files(tmp_path, data)
    data = minimal_allowlist(tmp_path)
    data["files"][0]["sha256"] = "0" * 64
    with pytest.raises(verifier.VerificationError, match="SHA256"):
        verifier.verify_files(tmp_path, data)


def test_symlink_and_missing_file_rejected(tmp_path):
    data = minimal_allowlist(tmp_path)
    (tmp_path / "README.md").unlink()
    with pytest.raises(verifier.VerificationError, match="Missing"):
        verifier.verify_files(tmp_path, data)
    target = tmp_path / "target.md"
    target.write_text("# Project\n", encoding="utf-8")
    (tmp_path / "README.md").symlink_to(target)
    with pytest.raises(verifier.VerificationError, match="Symlink"):
        verifier.verify_files(tmp_path, data)


def test_unlisted_managed_payload_rejected(tmp_path):
    data = minimal_allowlist(tmp_path)
    path = tmp_path / "final_reports/01_development/unlisted.html"
    path.parent.mkdir(parents=True)
    path.write_text("report")
    with pytest.raises(verifier.VerificationError, match="Unlisted"):
        verifier.verify_files(tmp_path, data)


@pytest.mark.parametrize("value", ["/" + "Users/person/input.json", "file" + "://secret",
                                  {"nested": ["/" + "home/person/data"]}, list(range(129)),
                                  {"metric": float("nan")}])
def test_private_json_and_numeric_arrays_rejected(value):
    with pytest.raises(verifier.VerificationError):
        verifier.check_json_privacy(value)


def test_valid_aggregate_json_allowed():
    verifier.check_json_privacy({"source_sha256": "a" * 64, "rows": [{"cagr": 0.1}] * 48,
                                 "cash_sharpe": None, "private_arrays_exported": False})


def test_complete_three_stage_four_cost_scope_allowed():
    assert len(verifier.verify_row_scope(scope_rows(), verifier.PORTFOLIOS)) == 48


@pytest.mark.parametrize("kind", ["missing", "duplicate", "wrong_id", "wrong_cost", "wrong_stage", "wrong_fee", "wrong_count"])
def test_incomplete_or_unexpected_scope_rejected(kind):
    rows = scope_rows()
    if kind == "missing":
        rows.pop()
    elif kind == "duplicate":
        rows[-1] = rows[0].copy()
    elif kind == "wrong_id":
        rows[0]["portfolio_id"] = "max_cagr_100pct_gdx"
    elif kind == "wrong_cost":
        rows[0]["slippage_bps_each_way"] = 7
    elif kind == "wrong_stage":
        rows[0]["stage"] = "corrected_validation"
    elif kind == "wrong_fee":
        rows[0]["commission_bps_each_way"] = 0
    else:
        rows[0]["observations"] = 699
    with pytest.raises(verifier.VerificationError):
        verifier.verify_row_scope(rows, verifier.PORTFOLIOS)


def test_saved_csv_json_metric_disagreement_rejected():
    a = scope_rows()
    b = copy.deepcopy(a)
    verifier.verify_rows_equal(a, b)
    b[0]["commission_bps_each_way"] = 2
    with pytest.raises(verifier.VerificationError, match="metric mismatch"):
        verifier.verify_rows_equal(a, b)


def test_broken_relative_link_and_escape_rejected(tmp_path):
    path = tmp_path / "README.md"
    path.write_text("[Missing](missing.md)")
    with pytest.raises(verifier.VerificationError, match="Broken"):
        verifier.verify_markdown_links(tmp_path, {"README.md"})
    path.write_text("[Escape](../elsewhere.md)")
    with pytest.raises(verifier.VerificationError, match="escapes"):
        verifier.verify_markdown_links(tmp_path, {"README.md"})


def test_working_relative_link_and_fragment(tmp_path):
    (tmp_path / "README.md").write_text("[Section](notes.md#methods-and-costs)\n[Source](https://example.com)")
    (tmp_path / "notes.md").write_text("## Methods and costs\n")
    assert verifier.verify_markdown_links(tmp_path, {"README.md", "notes.md"}) == 1


def png_chunk(kind, value):
    return struct.pack(">I", len(value)) + kind + value + b"\0" * 4


def test_png_rejects_private_or_numeric_text_payload():
    raw = b"\x89PNG\r\n\x1a\n" + png_chunk(b"tEXt", b"daily_series\0[1,2,3]") + png_chunk(b"IEND", b"")
    with pytest.raises(verifier.VerificationError, match="Unexpected PNG"):
        verifier.check_png_metadata(raw)


def test_archive_rejects_private_array_member():
    handle = io.BytesIO()
    with zipfile.ZipFile(handle, "w") as z:
        z.writestr("daily.npz", b"hidden raw numerical payload")
    with pytest.raises(verifier.VerificationError, match="Forbidden"):
        verifier.check_archive(handle.getvalue())


def test_archive_manifest_hash_mismatch_rejected():
    handle = io.BytesIO()
    with zipfile.ZipFile(handle, "w") as z:
        z.writestr("README.md", "text")
        z.writestr("SUPPLEMENT_MANIFEST.json", json.dumps({"files": [
            {"path": "README.md", "sha256": "0" * 64, "bytes": 4}]}))
    with pytest.raises(verifier.VerificationError, match="Supplement hash"):
        verifier.check_archive(handle.getvalue())


def test_visible_table_parser_preserves_numeric_cells_and_unicode():
    parser = verifier.TableParser()
    parser.feed('<table><thead><tr><th>ETF</th><th>GDX β</th></tr></thead>'
                '<tbody><tr><td>Daily cap fit</td><td>−0.1250</td></tr></tbody></table>')
    assert parser.tables == [[['ETF', 'GDX β'], ['Daily cap fit', '−0.1250']]]


def test_display_metric_conventions_keep_undefined_and_signed_values():
    assert verifier.display_number(None) == 'Undefined'
    assert verifier.display_number(0.125, percent=True, digits=2) == '12.50%'
    assert verifier.display_number(-0.125, percent=True, digits=2) == '-12.50%'
    assert verifier.display_number(1234.567, digits=2) == '1,234.57'
