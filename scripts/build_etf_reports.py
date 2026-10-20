#!/usr/bin/env python3
"""Present pinned saved ETF aggregates; never read market or account data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from trend_portfolio.cap_publication import (
    SOURCE_SHA,
    publish_report,
    read_json,
    require,
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
        "Saved source aggregate SHA256 changed",
    )
    report = publish_report(read_json(args.source_report))
    validate_config(read_json(args.config), report)
    require(args.source_report.read_bytes() == raw, "Source changed during copy")
    write_outputs(report, args.output_dir)
    require(args.source_report.read_bytes() == raw, "Source changed during rendering")
    print(
        json.dumps(
            {
                "completed": True,
                "unchanged_performance_rows": 36,
                "unchanged_controls": 15,
                "optimizer_account_or_market_reads": False,
                "metrics_recomputed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
