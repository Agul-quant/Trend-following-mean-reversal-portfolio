#!/usr/bin/env python3
"""Run the portable aggregate-only interface from an uninstalled checkout."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trend_portfolio.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
