#!/usr/bin/env python3
"""Verify the portable public export, not private financial calculations.

Only explicit manifest paths are read. No Git checkout, price files,
credentials or saved account paths are needed.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import importlib.util
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import struct
from urllib.parse import unquote, urlsplit
import zlib


SCHEMA = "etf_portfolio_publication_v1"
SAFE_SUFFIXES = {
    ".md",
    ".json",
    ".py",
    ".toml",
    ".yml",
    ".yaml",
    ".txt",
    ".csv",
    ".png",
}
SPECIAL_NAMES = {".gitignore", ".gitattributes"}
PRIVATE = re.compile(
    r"/Users/|/home/|/var/folders/|file://|[A-Za-z]:[\\/]Users[\\/]"
    r"|(?:apikey|api_key|api-key)=[A-Za-z0-9]{8,}",
    re.I,
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
    require(
        isinstance(name, str) and name and "\\" not in name and "\x00" not in name,
        "Invalid public relative path",
    )
    relative = PurePosixPath(name)
    require(
        not relative.is_absolute()
        and relative.as_posix() == name
        and all(
            part not in {".", "..", ".cache", "private", "data", ".git"}
            for part in relative.parts
        ),
        "Unsafe public relative path",
    )
    require(
        relative.suffix.lower() in SAFE_SUFFIXES or relative.name in SPECIAL_NAMES,
        "Unexpected public file type",
    )
    path = root / name
    require(
        path.is_file() and not path.is_symlink(),
        f"Missing or symlinked public file: {name}",
    )
    require(
        path.resolve().is_relative_to(root) and path.resolve() == path.absolute(),
        "Public path escapes root or uses a symlinked directory",
    )
    return path


def safe_json(value):
    if isinstance(value, dict):
        for key, item in value.items():
            require(not PRIVATE.search(str(key)), "Private JSON key")
            safe_json(item)
    elif isinstance(value, list):
        require(
            not (len(value) > 128 and all(isinstance(x, (int, float)) for x in value)),
            "Long numeric array in public JSON",
        )
        for item in value:
            safe_json(item)
    elif isinstance(value, str):
        require(
            not PRIVATE.search(value), "Private locator or credential in public JSON"
        )
    elif isinstance(value, float):
        require(math.isfinite(value), "Nonfinite public JSON value")


def verify_png(raw):
    require(raw.startswith(b"\x89PNG\r\n\x1a\n"), "Invalid PNG signature")
    position, chunks = 8, []
    while position < len(raw):
        require(position + 12 <= len(raw), "Truncated PNG chunk")
        length = struct.unpack(">I", raw[position : position + 4])[0]
        tag = raw[position + 4 : position + 8]
        end = position + 12 + length
        require(end <= len(raw), "Truncated PNG data")
        data = raw[position + 8 : position + 8 + length]
        crc = struct.unpack(">I", raw[position + 8 + length : end])[0]
        require(zlib.crc32(tag + data) & 0xFFFFFFFF == crc, "PNG CRC mismatch")
        require(
            tag
            in {
                b"IHDR",
                b"IDAT",
                b"IEND",
                b"pHYs",
                b"tEXt",
                b"sRGB",
                b"gAMA",
                b"cHRM",
                b"PLTE",
                b"tRNS",
            },
            "Unexpected PNG metadata",
        )
        if tag == b"tEXt":
            require(
                data.startswith(b"Software\x00") and len(data) <= 512,
                "Rich PNG text metadata is not public",
            )
            require(not PRIVATE.search(data.decode("latin1")), "Private PNG metadata")
        if tag == b"IHDR":
            require(length == 13, "Invalid PNG header")
            width, height = struct.unpack(">II", data[:8])
            require(
                0 < width <= 20000 and 0 < height <= 20000, "Invalid PNG dimensions"
            )
        chunks.append(tag)
        position = end
        if tag == b"IEND":
            break
    require(
        position == len(raw)
        and chunks
        and chunks[0] == b"IHDR"
        and chunks[-1] == b"IEND"
        and b"IDAT" in chunks,
        "Incomplete PNG",
    )


def verify_links(root, path, allowed):
    text = path.read_text(encoding="utf-8")
    for match in MD_LINK.finditer(text):
        target = match.group(1).strip("<>")
        parsed = urlsplit(target)
        if parsed.scheme:
            require(
                parsed.scheme in {"https", "http", "mailto"},
                "Unsafe Markdown link scheme",
            )
            continue
        if not parsed.path:
            continue
        require(not parsed.netloc, "Unexpected network-path Markdown link")
        destination = (path.parent / unquote(parsed.path)).resolve()
        require(
            destination.is_relative_to(root), "Markdown link escapes publication root"
        )
        require(destination.is_file(), f"Broken Markdown link in {path.name}: {target}")
        require(
            destination.relative_to(root).as_posix() in allowed,
            f"Markdown link targets an unpublished file: {target}",
        )


def _study(manifest, root, allowed):
    study = manifest.get("study")
    require(isinstance(study, dict), "Missing study paths")
    names = (
        "universe_config",
        "strategies_config",
        "policy_config",
        "report_directory",
    )
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
    require(
        universe.get("schema") == "etf_research_universe_v1"
        and universe.get("universe_size") == 47,
        "Incorrect ETF universe schema",
    )
    require(
        isinstance(symbols, list)
        and all(isinstance(s, str) and re.fullmatch(r"[A-Z]{2,5}", s) for s in symbols)
        and len(symbols) == len(set(symbols)) == 47,
        "Universe must contain exactly 47 unique ETF symbols",
    )
    categories = universe.get("categories")
    require(
        isinstance(categories, dict)
        and categories
        and all(
            isinstance(v, list) and all(isinstance(s, str) for s in v)
            for v in categories.values()
        ),
        "Missing ETF universe categories",
    )
    categorized = [s for values in categories.values() for s in values]
    require(
        len(categorized) == 47 and set(categorized) == set(symbols),
        "ETF category denominators do not match universe",
    )
    active = selected.get("symbols")
    require(
        active == ["GDX", "FXI", "QQQ", "UNG", "FDN"],
        "Selected strategy identities changed",
    )
    require(
        set(active) <= set(symbols), "Selected strategies outside declared universe"
    )
    require(
        universe.get("selected_symbols") == active,
        "Universe and selected strategy subset differ",
    )
    require(
        [s.get("symbol") for s in selected.get("strategies", [])] == active,
        "Selected definitions do not match selected symbol order",
    )
    require(
        policy.get("symbols") == active and report.get("symbols") == active,
        "Aggregate or policy symbol mismatch",
    )
    frequencies = ["none", "weekly", "monthly"]
    require(
        policy.get("frequencies") == frequencies
        and report.get("retained_frequencies") == frequencies,
        "Active frequency scope changed",
    )
    require(
        len(report.get("rows", [])) == 36 and len(report.get("controls", [])) == 15,
        "Active aggregate row count changed",
    )
    directory = (root / study["report_directory"]).resolve()
    require(directory.is_relative_to(root), "Report directory escapes root")
    for path in directory.rglob("*"):
        if path.is_file():
            require(
                path.relative_to(root).as_posix() in allowed,
                "Unlisted file in managed report directory",
            )


def _derived_returns(manifest, root, allowed):
    name = manifest["derived_returns"].get("manifest")
    require(
        name == "reports/reproducibility/manifest.json" and name in allowed,
        "Missing authorized derived-return release",
    )
    release = read_json(safe_path(root, name))
    require(
        release.get("derived_returns_only") is True
        and release.get("raw_market_data_published") is False,
        "Raw data is outside the authorized release",
    )
    require(
        all(r.get("path") in allowed for r in release.get("files", [])),
        "Derived release references an unpublished file",
    )
    module_path = "src/trend_portfolio/return_verification.py"
    require(module_path in allowed, "Missing portable return verifier")
    spec = importlib.util.spec_from_file_location(
        "authorized_return_verifier", root / module_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.verify_release(root)


def _paper(manifest, root, allowed):
    names = manifest.get("paper_tracking", {})
    require(
        names
        == {
            "freeze": "configs/paper_portfolio_freeze.json",
            "status": "reports/paper_tracking/status.json",
            "daily_returns": "reports/paper_tracking/daily_returns.csv",
        },
        "Missing frozen paper-tracking paths",
    )
    require(
        all(n in allowed for n in names.values()), "Paper artifact is not allowlisted"
    )
    envelope = read_json(safe_path(root, names["freeze"]))
    payload = envelope.get("payload", {})
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    fingerprint = hashlib.sha256(canonical).hexdigest()
    require(
        envelope.get("schema") == "forward_paper_portfolio_freeze_v1"
        and envelope.get("payload_sha256") == fingerprint,
        "Paper freeze checksum changed",
    )
    policy = read_json(root / "configs/final_cap_rebalancing.json")
    require(
        payload.get("primary_frequency") == "none"
        and payload.get("symbols") == policy["symbols"]
        and payload.get("initial_weights") == policy["initial_weights"],
        "Paper portfolio changed",
    )
    require(
        datetime.fromisoformat(payload["frozen_at_utc"])
        < datetime.fromisoformat(payload["start_open_utc"]),
        "Paper freeze must precede the future open",
    )
    require(
        bool(payload.get("source_hashes")), "Missing frozen operational source closure"
    )
    for name, expected in payload["source_hashes"].items():
        require(
            name in allowed
            and hashlib.sha256(safe_path(root, name).read_bytes()).hexdigest()
            == expected,
            "Frozen operational source/config changed",
        )
    status = read_json(safe_path(root, names["status"]))
    require(
        status.get("freeze_sha256") == fingerprint,
        "Paper status belongs to another freeze",
    )
    with safe_path(root, names["daily_returns"]).open(newline="") as f:
        reader = csv.DictReader(f)
        require(
            reader.fieldnames
            == [
                "session",
                "timestamp",
                "slippage_bps",
                "portfolio_return",
                "cash_return",
                "qqq_bh_return",
            ],
            "Only aggregate forward returns may be published",
        )
        seen = set()
        for row in reader:
            require(
                set(row) == set(reader.fieldnames) and None not in row.values(),
                "Malformed paper return row",
            )
            require(
                row["session"] >= payload["start_session"],
                "Backdated paper observation",
            )
            require(
                row["slippage_bps"] in {"1", "3", "10", "25"},
                "Unknown paper cost scenario",
            )
            clock = datetime.fromisoformat(row["timestamp"])
            require(
                clock.utcoffset() is not None
                and clock.date().isoformat() == row["session"],
                "Invalid paper clock",
            )
            key = (row["session"], row["slippage_bps"])
            require(key not in seen, "Duplicate paper observation")
            seen.add(key)
            require(
                all(
                    math.isfinite(float(row[k])) and float(row[k]) > -1
                    for k in ("portfolio_return", "cash_return", "qqq_bh_return")
                ),
                "Invalid derived paper return",
            )
    sessions = sorted({day for day, _ in seen})
    require(
        all(
            {cost for day, cost in seen if day == session} == {"1", "3", "10", "25"}
            for session in sessions
        ),
        "Paper session is missing cost scenarios",
    )
    require(
        len(sessions) == status.get("accepted_sessions", -1),
        "Paper return/status count mismatch",
    )
    require(
        status.get("performance_available") is bool(seen),
        "Paper performance availability is inconsistent",
    )
    if seen:
        require(
            sessions[0] == payload["start_session"],
            "Paper inception was silently moved",
        )
        require(
            status.get("status")
            in {"tracking_completed_sessions", "awaiting_next_qa_sealed_native_data"},
            "Unrecognized active paper status",
        )
        # The frozen tracker validates the private prior receipt and CSV hash
        # before emitting an awaiting-next status, but omits its public digest.
        # The enclosing explicit publication manifest still pins BOTH artifacts.
        public_digest = status.get("daily_returns_sha256")
        require(
            status["status"] == "awaiting_next_qa_sealed_native_data"
            or public_digest is not None,
            "Tracking status is missing its return digest",
        )
        if public_digest is not None:
            require(
                public_digest
                == hashlib.sha256(
                    (root / names["daily_returns"]).read_bytes()
                ).hexdigest(),
                "Paper return/status digest mismatch",
            )
    else:
        require(
            status.get("status") == "awaiting_qa_sealed_native_data",
            "Invalid empty paper status",
        )


def verify(root, manifest_path="metadata/project_manifest.json"):
    root = Path(root).resolve()
    manifest_file = safe_path(root, manifest_path)
    manifest = read_json(manifest_file)
    safe_json(manifest)
    authorized_returns = (
        manifest.get("aggregate_only") is False
        and manifest.get("public_data_scope")
        == "aggregate_metrics_and_derived_portfolio_returns"
        and isinstance(manifest.get("derived_returns"), dict)
    )
    require(
        manifest.get("schema") == SCHEMA
        and (manifest.get("aggregate_only") is True or authorized_returns),
        "Incorrect publication manifest scope",
    )
    require(manifest.get("universe_size") == 47, "Incorrect publication universe size")
    records = manifest.get("files")
    require(isinstance(records, list) and records, "Empty public allowlist")
    allowed = {manifest_path}
    for record in records:
        require(isinstance(record, dict), "Invalid allowlist entry")
        name = record.get("path")
        require(
            isinstance(name, str) and name not in allowed, "Duplicate manifest path"
        )
        path = safe_path(root, name)
        raw = path.read_bytes()
        require(
            isinstance(record.get("bytes"), int)
            and not isinstance(record["bytes"], bool)
            and record["bytes"] == len(raw),
            f"Public byte count mismatch: {name}",
        )
        require(
            isinstance(record.get("sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", record["sha256"])
            and hashlib.sha256(raw).hexdigest() == record["sha256"],
            f"Public SHA256 mismatch: {name}",
        )
        allowed.add(name)
        if path.suffix.lower() == ".json":
            safe_json(read_json(path))
        elif path.suffix.lower() == ".png":
            verify_png(raw)
    _study(manifest, root, allowed)
    if authorized_returns:
        _derived_returns(manifest, root, allowed)
        _paper(manifest, root, allowed)
    for name in sorted(allowed):
        if name.endswith(".md"):
            verify_links(root, root / name, allowed)
    return {
        "schema": "portable_publication_verification_v1",
        "passed": True,
        "public_files": len(allowed),
        "universe_size": 47,
        "performance_rows": 36,
        "control_rows": 15,
        "private_market_or_account_inputs_read": False,
        "financial_audit_reproduced": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--manifest", default="metadata/project_manifest.json")
    args = parser.parse_args(argv)
    print(json.dumps(verify(args.root, args.manifest), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
