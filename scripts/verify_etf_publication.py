#!/usr/bin/env python3
"""Verify pinned public ETF aggregates without private inputs or archives.

The digest is a publication-integrity pin, not a reproduction of the private
financial audit or proof from an unavailable original account.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from trend_portfolio.cap_publication import (
    COMPLETED_SOURCE_SHA,
    CONTROL_KEYS,
    CSV_KEYS,
    RETAINED_FREQUENCIES,
    RETAINED_SHA,
    SOURCE_SHA,
    csv_text,
    markdown,
    read_json,
    require,
    source_audit,
    validate_report,
)


def verify(directory, config_path):
    directory = Path(directory)
    report = read_json(directory / "report.json")
    validate_report(report, read_json(config_path))
    require(
        read_json(directory / "source_subset_audit.json") == source_audit(report),
        "Detached saved-aggregate receipt changed",
    )
    comparison_path = directory / "statistical_comparison.json"
    comparison = read_json(comparison_path) if comparison_path.is_file() else None
    expected = {
        "performance.csv": csv_text(report["rows"], CSV_KEYS),
        "controls.csv": csv_text(report["controls"], CONTROL_KEYS),
        "report.md": markdown(report, comparison),
    }
    for name, text in expected.items():
        require(
            (directory / name).read_bytes() == text.encode("utf-8"),
            f"Saved aggregate presentation changed: {name}",
        )
    return {
        "passed": True,
        "schema": "portable_etf_portfolio_integrity_verification_v1",
        "report_sha256": hashlib.sha256(
            (directory / "report.json").read_bytes()
        ).hexdigest(),
        "completed_source_report_sha256": COMPLETED_SOURCE_SHA,
        "presentation_source_report_sha256": SOURCE_SHA,
        "retained_source_payload_sha256": RETAINED_SHA,
        "frequencies": list(RETAINED_FREQUENCIES),
        "retained_performance_rows": 36,
        "unchanged_control_rows": 15,
        "released_equal_weight_comparison_rows": 12 if comparison is not None else 0,
        "private_market_or_account_inputs_read": False,
        "financial_audit_reproduced": False,
        "unpinned_recomputed_proof_accepted": False,
        "scope": "Pinned aggregate values, exact config, scope, detached receipt and rendered tables; source equivalence was checked separately before publication",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(verify(args.report_dir, args.config), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
