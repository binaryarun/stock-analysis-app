"""
data_provider.py
Thin wrapper around yfinance for fetching quote/fundamental snapshots and
historical OHLCV data. Centralizing this here means the rest of the app
(UI, analysis) never talks to yfinance directly, so the data source could
be swapped later (e.g. for a paid API) without touching UI code.

Notes on tickers:
  - US stocks: plain ticker, e.g. "AAPL", "MSFT"
  - NSE (India) stocks: ticker + ".NS", e.g. "RELIANCE.NS", "TCS.NS"
  - BSE (India) stocks: ticker + ".BO", e.g. "RELIANCE.BO"
"""

from __future__ import annotations
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class Quote:
    ticker: str
    name: str | None = None
    sector: str | None = None
    currency: str | None = None
    exchange: str | None = None
    price: float | None = None
    prev_close: float | None = None
    day_change_pct: float | None = None
    market_cap: float | None = None
    pe_ratio: float | None = None
    eps: float | None = None
    dividend_yield: float | None = None
    beta: float | None = None
    debt_to_equity: float | None = None
    profit_margin: float | None = None
    revenue_growth: float | None = None
    week52_high: float | None = None
    week52_low: float | None = None
    avg_volume: float | None = None
    volume: float | None = None
    error: str | None = None

    history: pd.DataFrame = field(default_factory=pd.DataFrame, repr=False)


def _safe_get(info: dict, *keys, default=None):
    for k in keys:
        v = info.get(k)
        if v is not None:
            return v
    return default


def _normalize_pct_fraction(x):
    """Yahoo's raw API has been inconsistent about whether dividendYield is a
    fraction (0.024 = 2.4%) or already a percent number (2.4 = 2.4%),
    depending on the data vintage/region. Real-world dividend yields are
    basically never >100%, so treat anything above 1.0 as "already a percent"
    and rescale it down to a fraction, keeping the rest of the app consistent.
    """
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x / 100 if x > 1.0 else x


def fetch_quote(ticker: str, history_period: str = "1y") -> Quote:
    """Fetch a single ticker's fundamentals + price history."""
    q = Quote(ticker=ticker)
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}

        q.name = _safe_get(info, "shortName", "longName", default=ticker)
        q.sector = _safe_get(info, "sector")
        q.currency = _safe_get(info, "currency")
        q.exchange = _safe_get(info, "exchange")
        q.price = _safe_get(info, "currentPrice", "regularMarketPrice")
        q.prev_close = _safe_get(info, "previousClose", "regularMarketPreviousClose")
        if q.price is not None and q.prev_close:
            q.day_change_pct = (q.price - q.prev_close) / q.prev_close * 100
        q.market_cap = _safe_get(info, "marketCap")
        q.pe_ratio = _safe_get(info, "trailingPE")
        q.eps = _safe_get(info, "trailingEps")
        q.dividend_yield = _normalize_pct_fraction(_safe_get(info, "dividendYield"))
        q.beta = _safe_get(info, "beta")
        q.debt_to_equity = _safe_get(info, "debtToEquity")
        q.profit_margin = _safe_get(info, "profitMargins")
        q.revenue_growth = _safe_get(info, "revenueGrowth")
        q.week52_high = _safe_get(info, "fiftyTwoWeekHigh")
        q.week52_low = _safe_get(info, "fiftyTwoWeekLow")
        q.avg_volume = _safe_get(info, "averageVolume")
        q.volume = _safe_get(info, "volume", "regularMarketVolume")

        hist = t.history(period=history_period, auto_adjust=False)
        if hist is not None and not hist.empty:
            q.history = hist
            # Fall back to history for price fields if .info was incomplete
            if q.price is None:
                q.price = float(hist["Close"].iloc[-1])
            if q.week52_high is None:
                q.week52_high = float(hist["High"].max())
            if q.week52_low is None:
                q.week52_low = float(hist["Low"].min())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch %s: %s", ticker, exc)
        q.error = str(exc)
    return q


def fetch_quotes(tickers: list[str], history_period: str = "1y",
                  max_workers: int = 8, progress_cb=None) -> list[Quote]:
    """Fetch multiple tickers concurrently. progress_cb(done, total) optional."""
    results: list[Quote] = []
    total = len(tickers)
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(fetch_quote, tkr, history_period): tkr for tkr in tickers
        }
        for fut in as_completed(futures):
            results.append(fut.result())
            done += 1
            if progress_cb:
                progress_cb(done, total)
    # Keep original ordering
    order = {tkr: i for i, tkr in enumerate(tickers)}
    results.sort(key=lambda q: order.get(q.ticker, 0))
    return results
