"""
data_provider.py
Fetches quote/fundamental snapshots and historical OHLCV data, picking a
provider by ticker suffix: NSE for `.NS`/`.BO`, api.nasdaq.com for plain US
tickers, falling back to yfinance for either if the dedicated provider
fails. A local TTL cache (cache.py) sits in front of all of this so
repeated screener scans don't re-hit the network for tickers fetched
recently. Centralizing this here means the rest of the app (UI, analysis)
never talks to a specific data source directly.

Notes on tickers:
  - US stocks: plain ticker, e.g. "AAPL", "MSFT"
  - NSE (India) stocks: ticker + ".NS", e.g. "RELIANCE.NS", "TCS.NS"
  - BSE (India) stocks: ticker + ".BO", e.g. "RELIANCE.BO"
"""

from __future__ import annotations
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace

import pandas as pd
import yfinance as yf

from cache import get_cache
from providers.base import Provider
from providers.nasdaq import NasdaqProvider
from providers.nse import NSEProvider

logger = logging.getLogger(__name__)

_nse_provider = NSEProvider()
_nasdaq_provider = NasdaqProvider()


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
    source: str | None = None

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


def _provider_for(ticker: str) -> Provider:
    if ticker.upper().endswith((".NS", ".BO")):
        return _nse_provider
    return _nasdaq_provider


def _apply_provider_fields(q: Quote, fields: dict) -> None:
    for k, v in fields.items():
        if hasattr(q, k) and v is not None:
            setattr(q, k, v)


def _fetch_quote_yfinance(ticker: str, history_period: str) -> Quote:
    """Original yfinance-only fetch path, used as a fallback for both NSE
    and Nasdaq tickers when the dedicated provider fails.
    """
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
        logger.warning("Failed to fetch %s via yfinance: %s", ticker, exc)
        q.error = str(exc)
    q.source = "yfinance"
    return q


def fetch_quote(ticker: str, history_period: str = "1y", force_refresh: bool = False) -> Quote:
    """Fetch a single ticker's fundamentals + price history.

    Tries the dedicated provider for the ticker's market first (NSE for
    `.NS`/`.BO`, Nasdaq for everything else), falling back to yfinance if
    that provider raises. Checks the local TTL cache before hitting any
    network source, and writes through after a successful fetch.
    """
    cache = get_cache()

    if not force_refresh:
        cached = cache.get("quote", ticker)
        if cached is not None:
            cached_hist = cache.get("history", ticker, period=history_period)
            cached.history = cached_hist if cached_hist is not None else pd.DataFrame()
            return cached

    provider = _provider_for(ticker)
    q = Quote(ticker=ticker)

    try:
        fields = provider.get_quote(ticker)
        _apply_provider_fields(q, fields)
        q.name = q.name or ticker
        q.source = provider.name
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s failed to fetch quote for %s: %s", provider.name, ticker, exc)
        q = _fetch_quote_yfinance(ticker, history_period)
        if q.error is not None:
            return q
        cache.set("quote", ticker, _without_history(q))
        cache.set("history", ticker, q.history, period=history_period)
        return q

    try:
        q.history = provider.get_history(ticker, history_period)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s failed to fetch history for %s: %s", provider.name, ticker, exc)
        try:
            q.history = yf.Ticker(ticker).history(period=history_period, auto_adjust=False)
        except Exception as hist_exc:  # noqa: BLE001
            logger.warning("yfinance history fallback failed for %s: %s", ticker, hist_exc)
            q.history = pd.DataFrame()

    if not q.history.empty:
        if q.price is None:
            q.price = float(q.history["Close"].iloc[-1])
        if q.week52_high is None:
            q.week52_high = float(q.history["High"].max())
        if q.week52_low is None:
            q.week52_low = float(q.history["Low"].min())

    cache.set("quote", ticker, _without_history(q))
    cache.set("history", ticker, q.history, period=history_period)
    return q


def _without_history(q: Quote) -> Quote:
    """A shallow copy of `q` with an empty history frame, for caching the
    quote and history independently under their own TTLs.
    """
    return replace(q, history=pd.DataFrame())


def fetch_quotes(tickers: list[str], history_period: str = "1y",
                  max_workers: int = 8, progress_cb=None,
                  force_refresh: bool = False) -> list[Quote]:
    """Fetch multiple tickers concurrently. progress_cb(done, total) optional."""
    results: list[Quote] = []
    total = len(tickers)
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(fetch_quote, tkr, history_period, force_refresh): tkr
            for tkr in tickers
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
