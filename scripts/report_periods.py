#!/usr/bin/env python3
"""Report four saved fixed allocations across three independently initialized stages."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trend_portfolio.periods import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
