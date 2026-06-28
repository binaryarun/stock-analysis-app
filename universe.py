"""
universe.py
Provides ticker universes used for screening: Nifty 50 (NSE) and a US
large-cap universe (S&P 500 / Dow 30). Tries to fetch a live, up-to-date
list first; falls back to an embedded static list if offline or the
source page changes/unavailable. The static fallback lists are not
guaranteed to be perfectly current (index constituents change a few
times a year) but are good enough for screening purposes.
"""

from __future__ import annotations
import io
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static fallback lists
# ---------------------------------------------------------------------------

_NIFTY50_FALLBACK = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BPCL", "BHARTIARTL",
    "BRITANNIA", "CIPLA", "COALINDIA", "DIVISLAB", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "ITC",
    "INDUSINDBK", "INFY", "JSWSTEEL", "KOTAKBANK", "LTIM",
    "LT", "M&M", "MARUTI", "NTPC", "NESTLEIND",
    "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN",
    "SUNPHARMA", "TCS", "TATACONSUM", "TATAMOTORS", "TATASTEEL",
    "TECHM", "TITAN", "UPL", "ULTRACEMCO", "WIPRO",
]

_DOW30_FALLBACK = [
    "AAPL", "AMGN", "AXP", "BA", "CAT",
    "CRM", "CSCO", "CVX", "DIS", "DOW",
    "GS", "HD", "HON", "IBM", "INTC",
    "JNJ", "JPM", "KO", "MCD", "MMM",
    "MRK", "MSFT", "NKE", "NVDA", "PG",
    "TRV", "UNH", "V", "VZ", "WMT",
]

# A modest, broadly representative S&P 500 subset used if the live fetch
# fails. Skews toward well-known large caps across sectors.
_SP500_FALLBACK = _DOW30_FALLBACK + [
    "ABBV", "ABT", "ADBE", "AMD", "AMZN", "AVGO", "BAC", "BRK-B", "C",
    "COST", "GOOGL", "GOOG", "LIN", "LLY", "MA", "META", "MU", "NFLX",
    "NOW", "ORCL", "PEP", "PFE", "PYPL", "QCOM", "T", "TMO", "TSLA",
    "TXN", "UNP", "UPS", "XOM",
]


def _nse_suffix(symbols: list[str]) -> list[str]:
    return [f"{s}.NS" for s in symbols]


def get_nifty50(timeout: int = 8) -> list[str]:
    """Return Nifty 50 constituents as Yahoo Finance tickers (.NS suffix)."""
    try:
        import requests

        url = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        import csv

        reader = csv.DictReader(io.StringIO(resp.text))
        symbols = [row["Symbol"].strip() for row in reader if row.get("Symbol")]
        if len(symbols) >= 45:
            return _nse_suffix(symbols)
        logger.warning("Nifty50 live fetch returned too few rows, using fallback")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Nifty50 live fetch failed (%s), using fallback", exc)
    return _nse_suffix(_NIFTY50_FALLBACK)


def get_dow30() -> list[str]:
    return list(_DOW30_FALLBACK)


def get_sp500(timeout: int = 8) -> list[str]:
    """Return S&P 500 constituents as Yahoo Finance tickers."""
    try:
        import pandas as pd
        import requests

        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))
        df = tables[0]
        symbols = df["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()
        if len(symbols) >= 400:
            return symbols
        logger.warning("S&P500 live fetch returned too few rows, using fallback")
    except Exception as exc:  # noqa: BLE001
        logger.warning("S&P500 live fetch failed (%s), using fallback", exc)
    return list(_SP500_FALLBACK)


UNIVERSE_CHOICES = {
    "Nifty 50 (NSE)": get_nifty50,
    "Dow 30 (US)": get_dow30,
    "S&P 500 (US)": get_sp500,
}


# Default watchlist used the first time the app runs (no saved watchlist yet)
DEFAULT_WATCHLIST = [
    # Indian large-caps
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "LT.NS",
    # US mega-caps
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "JPM", "V", "BRK-B",
]
