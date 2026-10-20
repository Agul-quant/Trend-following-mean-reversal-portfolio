#!/usr/bin/env python3
"""Refresh bytes/hashes of an EXISTING explicit publication allowlist only.

Does not discover or add files, touch raw data, alter financial results, or push.
Run the independent verification scripts afterward. Model source hashes in the
paper freeze are immutable and must never be refreshed here.
"""

from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    for name in (
        "metadata/etf_portfolio_manifest.json",
        "metadata/project_manifest.json",
    ):
        path = ROOT / name
        value = json.loads(path.read_text())
        for item in value["files"]:
            relative = Path(item["path"])
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or any(
                    p in (".cache", "private", "data", ".git") for p in relative.parts
                )
            ):
                raise ValueError("Unsafe manifest path")
            source = ROOT / relative
            if (
                source.is_symlink()
                or not source.is_file()
                or source.resolve() != source.absolute()
            ):
                raise ValueError("Missing or symlinked manifest file")
            raw = source.read_bytes()
            item.update(bytes=len(raw), sha256=sha256(raw).hexdigest())
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
