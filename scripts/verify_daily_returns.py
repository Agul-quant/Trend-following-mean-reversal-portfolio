#!/usr/bin/env python3
"""Reproduce released daily-return metrics with no private or market data.

Usage: python scripts/verify_daily_returns.py [--root /portable/project]
Only Python's standard library is needed; no installed project package required.
"""

from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    root = args.root.resolve()
    spec = importlib.util.spec_from_file_location(
        "return_verification", root / "src/trend_portfolio/return_verification.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    print(json.dumps(module.verify_release(root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
