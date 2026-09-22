"""
providers/nasdaq.py
Provider backed by api.nasdaq.com's public quote endpoints (the same ones
nasdaq.com's own site calls). Covers both S&P 500 and NASDAQ-100/Composite
constituents, since the endpoint serves quotes for any US-listed ticker
regardless of exchange. No API key or session/cookie bootstrap needed --
unlike NSE, these endpoints only check for a browser-like User-Agent.
"""

from __future__ import annotations
import logging
import re
from datetime import datetime, timedelta

import pandas as pd
import requests

from providers.base import Provider

logger = logging.getLogger(__name__)

BASE_URL = "https://api.nasdaq.com/api/quote"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}

REQUEST_TIMEOUT = 10


def _parse_money(s) -> float | None:
    if s is None:
        return None
    s = str(s).strip()
    if not s or s in ("N/A", "NA"):
        return None
    s = s.replace("$", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_pct(s) -> float | None:
    if s is None:
        return None
    s = str(s).strip().replace("%", "").replace(",", "")
    if not s or s in ("N/A", "NA"):
        return None
    try:
        return float(s) / 100
    except ValueError:
        return None


def _parse_52wk_range(s) -> tuple[float | None, float | None]:
    if not s or s in ("N/A", "NA"):
        return None, None
    m = re.match(r"\$?([\d.,]+)\s*-\s*\$?([\d.,]+)", str(s))
    if not m:
        return None, None
    lo, hi = m.group(1).replace(",", ""), m.group(2).replace(",", "")
    try:
        return float(lo), float(hi)
    except ValueError:
        return None, None


class NasdaqProvider(Provider):
    name = "nasdaq"

    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()

    def _get(self, path: str, ticker: str, params: dict) -> dict:
        url = f"{BASE_URL}/{ticker.upper()}/{path}"
        resp = self._session.get(
            url, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("data") is None:
            raise ValueError(
                f"nasdaq.com returned no data for {ticker}: "
                f"{payload.get('status')}"
            )
        return payload["data"]

    def get_quote(self, ticker: str) -> dict:
        info = self._get("info", ticker, {"assetclass": "stocks"})
        summary = self._get("summary", ticker, {"assetclass": "stocks"})

        out: dict = {}

        out["name"] = info.get("companyName")
        out["exchange"] = info.get("exchange")

        primary = info.get("primaryData") or {}
        price = _parse_money(primary.get("lastSalePrice"))
        if price is not None:
            out["price"] = price

        week52_low, week52_high = _parse_52wk_range(
            (info.get("keyStats") or {}).get("fiftyTwoWeekHighLow", {}).get("value")
        )
        if week52_low is not None:
            out["week52_low"] = week52_low
        if week52_high is not None:
            out["week52_high"] = week52_high

        sd = summary.get("summaryData") or {}

        def sval(key):
            return (sd.get(key) or {}).get("value")

        if sd.get("Sector"):
            out["sector"] = sval("Sector")
        prev_close = _parse_money(sval("PreviousClose"))
        if prev_close is not None:
            out["prev_close"] = prev_close
        if price is not None and prev_close:
            out["day_change_pct"] = (price - prev_close) / prev_close * 100
        market_cap = _parse_money(sval("MarketCap"))
        if market_cap is not None:
            out["market_cap"] = market_cap
        avg_volume = _parse_money(sval("AverageVolume"))
        if avg_volume is not None:
            out["avg_volume"] = avg_volume
        volume = _parse_money(sval("ShareVolume"))
        if volume is not None:
            out["volume"] = volume
        dividend_yield = _parse_pct(sval("Yield"))
        if dividend_yield is not None:
            out["dividend_yield"] = dividend_yield

        # 52wk range from summary as a fallback if info's keyStats omitted it
        if "week52_low" not in out or "week52_high" not in out:
            lo, hi = _parse_52wk_range(sval("FiftTwoWeekHighLow"))
            out.setdefault("week52_low", lo)
            out.setdefault("week52_high", hi)

        return out

    def get_history(self, ticker: str, period: str = "1y") -> pd.DataFrame:
        days = _PERIOD_DAYS.get(period, 365)
        todate = datetime.utcnow().date()
        fromdate = todate - timedelta(days=days)
        data = self._get(
            "historical",
            ticker,
            {
                "assetclass": "stocks",
                "fromdate": fromdate.isoformat(),
                "todate": todate.isoformat(),
                "limit": 9999,
            },
        )
        rows = (data.get("tradesTable") or {}).get("rows") or []
        if not rows:
            raise ValueError(f"nasdaq.com returned no historical rows for {ticker}")

        records = []
        for row in rows:
            date = pd.to_datetime(row["date"], format="%m/%d/%Y")
            records.append(
                {
                    "Date": date,
                    "Open": _parse_money(row.get("open")),
                    "High": _parse_money(row.get("high")),
                    "Low": _parse_money(row.get("low")),
                    "Close": _parse_money(row.get("close")),
                    "Volume": _parse_money(row.get("volume")),
                }
            )
        df = pd.DataFrame.from_records(records).set_index("Date").sort_index()
        return df


_PERIOD_DAYS = {
    "1mo": 31,
    "3mo": 93,
    "6mo": 186,
    "1y": 366,
    "2y": 731,
    "5y": 1827,
    "max": 3653,
}
