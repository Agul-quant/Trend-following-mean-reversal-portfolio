#!/usr/bin/env python3
"""Verify the portable public export, not private financial calculations.

Only explicit manifest paths are read. No Git checkout, price files,
credentials or saved account paths are needed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import struct
from urllib.parse import unquote, urlsplit
import zlib


SCHEMA = "etf_portfolio_publication_v1"
SAFE_SUFFIXES = {".md", ".json", ".py", ".toml", ".yml", ".yaml", ".txt", ".csv", ".png"}
SPECIAL_NAMES = {".gitignore", ".gitattributes"}
PRIVATE = re.compile(
    r"/Users/|/home/|/var/folders/|file://|[A-Za-z]:[\\/]Users[\\/]"
    r"|(?:apikey|api_key|api-key)=[A-Za-z0-9]{8,}", re.I
)
MD_LINK = re.compile(r"!?\[[^\]]*\]\((<[^>]*>|[^\s)]+)(?:\s+\"[^\"]*\")?\)")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    def reject(value):
        raise ValueError(f"Nonfinite JSON constant: {value}")

    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject)


def safe_path(root, name):
    require(isinstance(name, str) and name and "\\" not in name and "\x00" not in name,
            "Invalid public relative path")
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and relative.as_posix() == name
            and all(part not in {".", "..", ".cache", "private", "data", ".git"}
                    for part in relative.parts), "Unsafe public relative path")
    require(relative.suffix.lower() in SAFE_SUFFIXES or relative.name in SPECIAL_NAMES,
            "Unexpected public file type")
    path = root / name
    require(path.is_file() and not path.is_symlink(), f"Missing or symlinked public file: {name}")
    require(path.resolve().is_relative_to(root) and path.resolve() == path.absolute(),
            "Public path escapes root or uses a symlinked directory")
    return path


def safe_json(value):
    if isinstance(value, dict):
        for key, item in value.items():
            require(not PRIVATE.search(str(key)), "Private JSON key")
            safe_json(item)
    elif isinstance(value, list):
        require(not (len(value) > 128 and all(isinstance(x, (int, float)) for x in value)),
                "Long numeric array in public JSON")
        for item in value:
            safe_json(item)
    elif isinstance(value, str):
        require(not PRIVATE.search(value), "Private locator or credential in public JSON")
    elif isinstance(value, float):
        require(math.isfinite(value), "Nonfinite public JSON value")


def verify_png(raw):
    require(raw.startswith(b"\x89PNG\r\n\x1a\n"), "Invalid PNG signature")
    position, chunks = 8, []
    while position < len(raw):
        require(position + 12 <= len(raw), "Truncated PNG chunk")
        length = struct.unpack(">I", raw[position:position + 4])[0]
        tag = raw[position + 4:position + 8]
        end = position + 12 + length
        require(end <= len(raw), "Truncated PNG data")
        data = raw[position + 8:position + 8 + length]
        crc = struct.unpack(">I", raw[position + 8 + length:end])[0]
        require(zlib.crc32(tag + data) & 0xFFFFFFFF == crc, "PNG CRC mismatch")
        require(tag in {b"IHDR", b"IDAT", b"IEND", b"pHYs", b"tEXt", b"sRGB",
                        b"gAMA", b"cHRM", b"PLTE", b"tRNS"}, "Unexpected PNG metadata")
        if tag == b"tEXt":
            require(data.startswith(b"Software\x00") and len(data) <= 512,
                    "Rich PNG text metadata is not public")
            require(not PRIVATE.search(data.decode("latin1")), "Private PNG metadata")
        if tag == b"IHDR":
            require(length == 13, "Invalid PNG header")
            width, height = struct.unpack(">II", data[:8])
            require(0 < width <= 20000 and 0 < height <= 20000, "Invalid PNG dimensions")
        chunks.append(tag)
        position = end
        if tag == b"IEND":
            break
    require(position == len(raw) and chunks and chunks[0] == b"IHDR"
            and chunks[-1] == b"IEND" and b"IDAT" in chunks, "Incomplete PNG")


def verify_links(root, path, allowed):
    text = path.read_text(encoding="utf-8")
    for match in MD_LINK.finditer(text):
        target = match.group(1).strip("<>")
        parsed = urlsplit(target)
        if parsed.scheme:
            require(parsed.scheme in {"https", "http", "mailto"}, "Unsafe Markdown link scheme")
            continue
        if not parsed.path:
            continue
        require(not parsed.netloc, "Unexpected network-path Markdown link")
        destination = (path.parent / unquote(parsed.path)).resolve()
        require(destination.is_relative_to(root), "Markdown link escapes publication root")
        require(destination.is_file(), f"Broken Markdown link in {path.name}: {target}")
        require(destination.relative_to(root).as_posix() in allowed,
                f"Markdown link targets an unpublished file: {target}")


def _study(manifest, root, allowed):
    study = manifest.get("study")
    require(isinstance(study, dict), "Missing study paths")
    names = ("universe_config", "strategies_config", "policy_config", "report_directory")
    require(all(isinstance(study.get(k), str) for k in names), "Incomplete study paths")
    for key in names[:3]:
        require(study[key] in allowed, f"Unlisted study input: {key}")
    report_path = str(PurePosixPath(study["report_directory"]) / "report.json")
    require(report_path in allowed, "Unlisted study aggregate")
    universe = read_json(safe_path(root, study["universe_config"]))
    selected = read_json(safe_path(root, study["strategies_config"]))
    policy = read_json(safe_path(root, study["policy_config"]))
    report = read_json(safe_path(root, report_path))
    symbols = universe.get("symbols")
    require(universe.get("schema") == "etf_research_universe_v1"
            and universe.get("universe_size") == 47, "Incorrect ETF universe schema")
    require(isinstance(symbols, list)
            and all(isinstance(s, str) and re.fullmatch(r"[A-Z]{2,5}", s) for s in symbols)
            and len(symbols) == len(set(symbols)) == 47,
            "Universe must contain exactly 47 unique ETF symbols")
    categories = universe.get("categories")
    require(isinstance(categories, dict) and categories
            and all(isinstance(v, list) and all(isinstance(s, str) for s in v)
                    for v in categories.values()), "Missing ETF universe categories")
    categorized = [s for values in categories.values() for s in values]
    require(len(categorized) == 47 and set(categorized) == set(symbols),
            "ETF category denominators do not match universe")
    active = selected.get("symbols")
    require(active == ["GDX", "FXI", "QQQ", "UNG", "FDN"], "Selected strategy identities changed")
    require(set(active) <= set(symbols), "Selected strategies outside declared universe")
    require(universe.get("selected_symbols") == active,
            "Universe and selected strategy subset differ")
    require([s.get("symbol") for s in selected.get("strategies", [])] == active,
            "Selected definitions do not match selected symbol order")
    require(policy.get("symbols") == active and report.get("symbols") == active,
            "Aggregate or policy symbol mismatch")
    frequencies = ["none", "weekly", "monthly"]
    require(policy.get("frequencies") == frequencies
            and report.get("retained_frequencies") == frequencies,
            "Active frequency scope changed")
    require(len(report.get("rows", [])) == 36 and len(report.get("controls", [])) == 15,
            "Active aggregate row count changed")
    directory = (root / study["report_directory"]).resolve()
    require(directory.is_relative_to(root), "Report directory escapes root")
    for path in directory.rglob("*"):
        if path.is_file():
            require(path.relative_to(root).as_posix() in allowed,
                    "Unlisted file in managed report directory")


def verify(root, manifest_path="metadata/project_manifest.json"):
    root = Path(root).resolve()
    manifest_file = safe_path(root, manifest_path)
    manifest = read_json(manifest_file)
    safe_json(manifest)
    require(manifest.get("schema") == SCHEMA and manifest.get("aggregate_only") is True,
            "Incorrect publication manifest scope")
    require(manifest.get("universe_size") == 47, "Incorrect publication universe size")
    records = manifest.get("files")
    require(isinstance(records, list) and records, "Empty public allowlist")
    allowed = {manifest_path}
    for record in records:
        require(isinstance(record, dict), "Invalid allowlist entry")
        name = record.get("path")
        require(isinstance(name, str) and name not in allowed, "Duplicate manifest path")
        path = safe_path(root, name)
        raw = path.read_bytes()
        require(isinstance(record.get("bytes"), int) and not isinstance(record["bytes"], bool)
                and record["bytes"] == len(raw), f"Public byte count mismatch: {name}")
        require(isinstance(record.get("sha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}", record["sha256"])
                and hashlib.sha256(raw).hexdigest() == record["sha256"],
                f"Public SHA256 mismatch: {name}")
        allowed.add(name)
        if path.suffix.lower() == ".json":
            safe_json(read_json(path))
        elif path.suffix.lower() == ".png":
            verify_png(raw)
    _study(manifest, root, allowed)
    for name in sorted(allowed):
        if name.endswith(".md"):
            verify_links(root, root / name, allowed)
    return {"schema": "portable_publication_verification_v1", "passed": True,
            "public_files": len(allowed), "universe_size": 47,
            "performance_rows": 36, "control_rows": 15,
            "private_market_or_account_inputs_read": False,
            "financial_audit_reproduced": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="metadata/project_manifest.json")
    args = parser.parse_args(argv)
    print(json.dumps(verify(args.root, args.manifest),
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
