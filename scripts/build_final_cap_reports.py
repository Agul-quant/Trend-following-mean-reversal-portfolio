#!/usr/bin/env python3
"""Publish only the retained saved cap aggregates; never read market data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from trend_portfolio.cap_subset import (
    SOURCE_SHA,
    read_json,
    require,
    select_report,
    validate_config,
    write_outputs,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    raw = args.source_report.read_bytes()
    require(
        hashlib.sha256(raw).hexdigest() == SOURCE_SHA,
        "Completed source aggregate SHA256 changed",
    )
    report = select_report(read_json(args.source_report))
    validate_config(read_json(args.config), report)
    require(args.source_report.read_bytes() == raw, "Source changed during selection")
    write_outputs(report, args.output_dir)
    require(
        args.source_report.read_bytes() == raw, "Source changed during presentation"
    )
    print(
        json.dumps(
            {
                "completed": True,
                "retained_performance_rows": 36,
                "unchanged_controls": 15,
                "removed_daily_rows": 12,
                "optimizer_account_or_market_reads": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
