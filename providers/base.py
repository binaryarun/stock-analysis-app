"""
providers/base.py
Common interface that every market data provider (NSE, Nasdaq, yfinance
fallback) implements, so data_provider.py can pick one by ticker suffix
without knowing the fetching details of each source.
"""

from __future__ import annotations
from abc import ABC, abstractmethod

import pandas as pd


class Provider(ABC):
    """A source of quote/history data for a set of tickers.

    Implementations should raise on failure (network error, unparsable
    response, ticker not found) rather than returning partially-filled
    data, so the caller can fall back to another provider.
    """

    name: str

    @abstractmethod
    def get_quote(self, ticker: str) -> dict:
        """Return a dict of raw fields for `ticker`, keyed to match the
        attributes on data_provider.Quote (price, prev_close, market_cap,
        pe_ratio, etc). Missing fields should be omitted, not set to None,
        so the caller can tell "not provided" apart from "provided as null".
        """

    @abstractmethod
    def get_history(self, ticker: str, period: str = "1y") -> pd.DataFrame:
        """Return an OHLCV DataFrame indexed by date, matching the shape of
        yfinance's Ticker.history() output (Open/High/Low/Close/Volume
        columns).
        """
