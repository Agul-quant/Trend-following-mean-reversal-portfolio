"""Public dataset documentation checks; no market data or private paths."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CATEGORIES = {
    "US equity indices": "SPY QQQ DIA IWM MDY VTI",
    "International / country equities": "EEM EFA EWA EWC EWJ EWT EWW EWY EWZ FXI INDA MCHI VGK",
    "Broad US sectors": "XLB XLE XLF XLI XLK XLP XLRE XLU XLV XLY",
    "Industries / subsectors": "FDN GDX GDXJ IBB ITB KBE KRE SMH SOXX XBI XHB XOP XRT",
    "Bonds": "BND HYG IEF IEI LQD MBB SHY TIP TLT",
    "Commodities / precious metals": "DBC GLD SLV UNG USO",
}


def test_readme_lists_exact_full_universe_without_duplicates():
    text = (ROOT / "README.md").read_text()
    section = text.split("### Full 56-ETF universe\n", 1)[1].split(
        "\nThe research window", 1
    )[0]
    rows = re.findall(r"^- \*\*(.*?) \((\d+)\):\*\* (.*?)\.$", section, re.M)
    assert len(rows) == len(EXPECTED_CATEGORIES)
    all_symbols = []
    for category, count, listed in rows:
        symbols = listed.split(", ")
        assert symbols == EXPECTED_CATEGORIES[category].split()
        assert len(symbols) == int(count)
        all_symbols.extend(symbols)
    assert len(all_symbols) == len(set(all_symbols)) == 56


def test_sources_distinguish_provider_calendar_cash_and_derived_inputs():
    readme = (ROOT / "README.md").read_text()
    detail = (ROOT / "docs/data_sources.md").read_text()
    for text in (readme, detail):
        assert "https://www.alphavantage.co/documentation/" in text
        assert "https://github.com/gerrymanoim/exchange_calendars" in text
        assert "TIME_SERIES_DAILY_ADJUSTED" in text
        assert "TIME_SERIES_INTRADAY" in text
    assert "not a complete all-symbol/all-date panel" in detail
    assert "not a FRED series" in detail
    assert "not Yahoo Finance" in detail
    assert "same-provider evidence" in detail


def test_corrected_split_and_original_snapshot_are_not_conflated():
    detail = (ROOT / "docs/data_sources.md").read_text()
    for period in (
        "2017-01-01–2020-12-31",
        "2021-01-01–2024-12-31",
        "2025-01-01–2026-10-15",
    ):
        assert period in detail
    assert "Earlier split, 700 common daily valuations" in detail
    assert "21,224" in detail and "84,896" in detail
    assert "missing pre-development intraday records are not invented" in detail


def test_full_data_availability_and_vintage_limitations_are_explicit():
    readme = (ROOT / "README.md").read_text()
    detail = (ROOT / "docs/data_sources.md").read_text()
    assert "not downloadable from this repository" in readme
    assert "No public full-data download is provided" in detail
    assert "matching historical daily adjustment vintage" in detail
    assert "Fresh downloads may differ" in detail
    assert "docs/data_sources.md" in readme
    for text in (readme, detail):
        for private_locator in ("/Users/", "/var/folders/", "github-ai:", "apikey="):
            assert private_locator not in text
