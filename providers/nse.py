"""
providers/nse.py
Provider backed by nseindia.com's own JSON API (the same endpoints the
nseindia.com website calls for quote pages). Used for `.NS`/`.BO` tickers.

NSE sits behind Akamai and will 403 any request that doesn't look like a
real browser session: a plain GET to /api/... without first visiting an
HTML page to pick up cookies (nsit, bm_sv, etc.) gets rejected outright.
We warm up by GETting the site's quote page for the symbol, then reuse
that session's cookies for the JSON endpoints.

Note: Akamai also blocks at the IP/ASN level independent of headers --
requests from cloud/datacenter IPs (and apparently from this dev sandbox)
get a 403 on the homepage itself, before any cookie logic runs. This
provider is written to the documented behavior of the site and needs to
be validated from a residential/non-datacenter network (see
tasks/01-data-sources.md).
"""

from __future__ import annotations
import logging
import time

import pandas as pd
import requests

from providers.base import Provider

logger = logging.getLogger(__name__)

BASE_URL = "https://www.nseindia.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

REQUEST_TIMEOUT = 10
COOKIE_TTL_SECONDS = 5 * 60  # NSE session cookies are short-lived
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 1.5


class NSEProvider(Provider):
    name = "nse"

    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._session.headers.update(HEADERS)
        self._cookies_set_at: float = 0.0

    def _ensure_session(self, symbol: str) -> None:
        if time.monotonic() - self._cookies_set_at < COOKIE_TTL_SECONDS:
            return
        self._session.cookies.clear()
        self._session.get(BASE_URL, timeout=REQUEST_TIMEOUT)
        resp = self._session.get(
            f"{BASE_URL}/get-quotes/equity?symbol={symbol}",
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        self._cookies_set_at = time.monotonic()

    def _get_json(self, path: str, symbol: str, params: dict | None = None) -> dict:
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                self._ensure_session(symbol)
                resp = self._session.get(
                    f"{BASE_URL}{path}",
                    params=params,
                    headers={"Referer": f"{BASE_URL}/get-quotes/equity?symbol={symbol}"},
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code == 401 or resp.status_code == 403:
                    # Likely a stale/rejected session -- force a fresh warm-up.
                    self._cookies_set_at = 0.0
                    raise requests.HTTPError(
                        f"NSE rejected request ({resp.status_code})", response=resp
                    )
                resp.raise_for_status()
                return resp.json()
            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE_SECONDS * (2 ** attempt))
        assert last_exc is not None
        raise last_exc

    def get_quote(self, ticker: str) -> dict:
        symbol = ticker.split(".")[0]
        data = self._get_json("/api/quote-equity", symbol, {"symbol": symbol})

        out: dict = {}
        info = data.get("info") or {}
        meta = data.get("metadata") or {}
        price_info = data.get("priceInfo") or {}
        security_info = data.get("securityInfo") or {}

        if info.get("companyName"):
            out["name"] = info["companyName"]
        out["exchange"] = "NSE"
        out["currency"] = "INR"
        if info.get("industry"):
            out["sector"] = info["industry"]

        price = price_info.get("lastPrice")
        if price is not None:
            out["price"] = float(price)
        prev_close = price_info.get("previousClose") or meta.get("previousClose")
        if prev_close is not None:
            out["prev_close"] = float(prev_close)
        if out.get("price") is not None and prev_close:
            out["day_change_pct"] = (out["price"] - float(prev_close)) / float(prev_close) * 100

        wk_range = price_info.get("weekHighLow") or {}
        if wk_range.get("min") is not None:
            out["week52_low"] = float(wk_range["min"])
        if wk_range.get("max") is not None:
            out["week52_high"] = float(wk_range["max"])

        if security_info.get("faceValue") is not None:
            pass  # not currently mapped onto Quote

        pre_open = data.get("preOpenMarket") or {}
        total_traded = price_info.get("totalTradedVolume")
        if total_traded is not None:
            out["volume"] = float(total_traded)

        return out

    def get_history(self, ticker: str, period: str = "1y") -> pd.DataFrame:
        symbol = ticker.split(".")[0]
        days = _PERIOD_DAYS.get(period, 365)
        todate = pd.Timestamp.utcnow().date()
        fromdate = todate - pd.Timedelta(days=days)
        data = self._get_json(
            "/api/historical/cm/equity",
            symbol,
            {
                "symbol": symbol,
                "series": '["EQ"]',
                "from": fromdate.strftime("%d-%m-%Y"),
                "to": todate.strftime("%d-%m-%Y"),
            },
        )
        rows = data.get("data") or []
        if not rows:
            raise ValueError(f"NSE returned no historical rows for {symbol}")

        records = []
        for row in rows:
            records.append(
                {
                    "Date": pd.to_datetime(row["CH_TIMESTAMP"]),
                    "Open": float(row["CH_OPENING_PRICE"]),
                    "High": float(row["CH_TRADE_HIGH_PRICE"]),
                    "Low": float(row["CH_TRADE_LOW_PRICE"]),
                    "Close": float(row["CH_CLOSING_PRICE"]),
                    "Volume": float(row["CH_TOT_TRADED_QTY"]),
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
