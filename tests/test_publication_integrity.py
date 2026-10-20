"""Portable export integrity; all failure fixtures are synthetic."""

import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import zlib

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("publication_integrity", ROOT / "scripts/verify_publication.py")
PUBLIC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUBLIC)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def refresh(root, manifest):
    for record in manifest["files"]:
        raw = (root / record["path"]).read_bytes()
        record.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    write_json(root / "metadata/project_manifest.json", manifest)


@pytest.fixture
def tree(tmp_path):
    active = ["GDX", "FXI", "QQQ", "UNG", "FDN"]
    # Distinct synthetic uppercase identifiers; no market values are present.
    universe = active + ["ZZ" + chr(65 + i // 26) + chr(65 + i % 26) for i in range(42)]
    study = {"universe_config": "configs/universe.json", "strategies_config": "configs/strategies.json",
             "policy_config": "configs/policy.json", "report_directory": "reports/comparison"}
    payloads = {
        study["universe_config"]: {"schema": "etf_research_universe_v1", "universe_size": 47,
                                   "symbols": universe, "selected_symbols": active,
                                   "categories": {"Synthetic group": universe}},
        study["strategies_config"]: {"symbols": active, "strategies": [{"symbol": s} for s in active]},
        study["policy_config"]: {"symbols": active, "frequencies": ["none", "weekly", "monthly"]},
        "reports/comparison/report.json": {"symbols": active,
            "retained_frequencies": ["none", "weekly", "monthly"], "rows": [{} for _ in range(36)],
            "controls": [{} for _ in range(15)]},
    }
    for name, value in payloads.items():
        write_json(tmp_path / name, value)
    (tmp_path / "README.md").write_text("[Saved report](reports/comparison/report.json)\n")
    manifest = {"schema": PUBLIC.SCHEMA, "aggregate_only": True, "universe_size": 47, "study": study,
                "files": [{"path": p} for p in sorted([*payloads, "README.md"])]}
    refresh(tmp_path, manifest)
    return tmp_path, manifest


def test_synthetic_tree_passes_without_private_reads(tree):
    root, _ = tree
    receipt = PUBLIC.verify(root)
    assert receipt["passed"] and receipt["public_files"] == 6
    assert receipt["private_market_or_account_inputs_read"] is False
    assert receipt["financial_audit_reproduced"] is False


@pytest.mark.parametrize("mutation", [
    lambda m: m.update(schema="unknown"),
    lambda m: m.update(aggregate_only=False),
    lambda m: m.update(universe_size=48),
    lambda m: m["files"].append(m["files"][0].copy()),
    lambda m: m["files"][0].update(path="../outside.json"),
    lambda m: m["files"][0].update(path=".cache/private.json"),
    lambda m: m["files"][0].update(bytes=True),
    lambda m: m["files"][0].update(sha256="0" * 64),
    lambda m: m["study"].update(policy_config="unlisted.json"),
])
def test_manifest_corruption_rejected(tree, mutation):
    root, manifest = tree
    mutation(manifest)
    write_json(root / "metadata/project_manifest.json", manifest)
    with pytest.raises(ValueError):
        PUBLIC.verify(root)


def test_post_manifest_file_mutation_rejected(tree):
    root, _ = tree
    (root / "README.md").write_text("changed")
    with pytest.raises(ValueError, match="byte count|SHA256"):
        PUBLIC.verify(root)


def test_symlinked_public_path_rejected(tree):
    root, manifest = tree
    original = root / "configs/universe.json"
    hidden = root / ".cache"
    hidden.mkdir()
    original.rename(hidden / "universe.json")
    original.symlink_to(hidden / "universe.json")
    with pytest.raises(ValueError, match="symlink"):
        PUBLIC.verify(root)


def test_category_counts_cannot_disagree_with_universe(tree):
    root, manifest = tree
    path = root / manifest["study"]["universe_config"]
    value = json.loads(path.read_text())
    value["categories"]["Synthetic group"].pop()
    write_json(path, value)
    refresh(root, manifest)
    with pytest.raises(ValueError, match="denominators"):
        PUBLIC.verify(root)


@pytest.mark.parametrize("bad", [
    {"locator": "/Users/synthetic/private.csv"},
    {"locator": "file://private"},
    {"token": "api_key=abcdefghijk"},
    {"daily_values": list(range(129))},
    {"x": float("inf")},
])
def test_json_safety_rejects_unpublished_content(bad):
    with pytest.raises(ValueError):
        PUBLIC.safe_json(bad)


def test_json_safety_runs_even_when_hashes_recomputed(tree):
    root, manifest = tree
    path = root / manifest["study"]["universe_config"]
    value = json.loads(path.read_text())
    value["extra"] = list(range(129))
    write_json(path, value)
    refresh(root, manifest)
    with pytest.raises(ValueError, match="Long numeric"):
        PUBLIC.verify(root)


@pytest.mark.parametrize("target", ["missing.md", "../outside.md", "file://private"])
def test_broken_or_unsafe_markdown_rejected(tree, target):
    root, manifest = tree
    (root / "README.md").write_text(f"[Invalid]({target})\n")
    refresh(root, manifest)
    with pytest.raises(ValueError):
        PUBLIC.verify(root)


def test_link_to_unlisted_local_file_rejected(tree):
    root, manifest = tree
    (root / "unpublished.md").write_text("not exported")
    (root / "README.md").write_text("[Private artifact](unpublished.md)\n")
    refresh(root, manifest)
    with pytest.raises(ValueError, match="unpublished"):
        PUBLIC.verify(root)


def png_chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def png(extra=b""):
    return (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + extra + png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00")) + png_chunk(b"IEND", b""))


def test_raster_png_accepts_only_small_software_text():
    PUBLIC.verify_png(png(png_chunk(b"tEXt", b"Software\x00Synthetic renderer")))
    with pytest.raises(ValueError, match="Rich PNG"):
        PUBLIC.verify_png(png(png_chunk(b"tEXt", b"Daily array\x001,2,3")))
    with pytest.raises(ValueError, match="Unexpected PNG"):
        PUBLIC.verify_png(png(png_chunk(b"iTXt", b"unapproved")))
    with pytest.raises(ValueError, match="Incomplete PNG"):
        PUBLIC.verify_png(png() + b"hidden")


@pytest.mark.parametrize("which", ["universe", "selected", "frequency", "rows"])
def test_scope_cannot_change_by_refreshing_manifest(tree, which):
    root, manifest = tree
    key = {"universe": "universe_config", "selected": "strategies_config", "frequency": "policy_config"}.get(which)
    name = manifest["study"][key] if key else "reports/comparison/report.json"
    value = json.loads((root / name).read_text())
    if which == "universe":
        value["symbols"][-1] = value["symbols"][0]
    elif which == "selected":
        value["symbols"].pop()
    elif which == "frequency":
        value["frequencies"].append("daily")
    else:
        value["rows"].pop()
    write_json(root / name, value)
    refresh(root, manifest)
    with pytest.raises(ValueError):
        PUBLIC.verify(root)


def test_unlisted_managed_report_file_rejected(tree):
    root, _ = tree
    (root / "reports/comparison/unlisted.md").write_text("unexpected")
    with pytest.raises(ValueError, match="Unlisted file"):
        PUBLIC.verify(root)


def test_current_public_export_contract():
    receipt = PUBLIC.verify(ROOT)
    assert receipt["passed"]
    assert receipt["universe_size"] == 47
    assert receipt["performance_rows"] == 36 and receipt["control_rows"] == 15
