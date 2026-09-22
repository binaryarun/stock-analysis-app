import pandas as pd
import pytest

import data_provider as dp
from cache import TTLCache


class FakeProvider:
    def __init__(self, name, quote_fields=None, history=None,
                 quote_error=None, history_error=None):
        self.name = name
        self._quote_fields = quote_fields or {}
        self._history = history if history is not None else pd.DataFrame(
            {"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5], "Volume": [100.0]},
            index=pd.to_datetime(["2026-01-01"]),
        )
        self._quote_error = quote_error
        self._history_error = history_error
        self.quote_calls = []
        self.history_calls = []

    def get_quote(self, ticker):
        self.quote_calls.append(ticker)
        if self._quote_error:
            raise self._quote_error
        return self._quote_fields

    def get_history(self, ticker, period="1y"):
        self.history_calls.append((ticker, period))
        if self._history_error:
            raise self._history_error
        return self._history


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Every test gets its own on-disk cache so they can't see each other's
    writes, and so a real fetch_quote() call doesn't hit the shared
    ~/.stock_analysis_tool cache used by the running app.
    """
    test_cache = TTLCache(db_path=tmp_path / "cache.sqlite3")
    monkeypatch.setattr(dp, "get_cache", lambda: test_cache)
    return test_cache


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

def test_ns_suffix_selects_nse_provider():
    assert dp._provider_for("RELIANCE.NS") is dp._nse_provider


def test_bo_suffix_selects_nse_provider():
    assert dp._provider_for("RELIANCE.BO") is dp._nse_provider


def test_plain_ticker_selects_nasdaq_provider():
    assert dp._provider_for("AAPL") is dp._nasdaq_provider


def test_suffix_match_is_case_insensitive():
    assert dp._provider_for("reliance.ns") is dp._nse_provider


# ---------------------------------------------------------------------------
# fetch_quote dispatch + fallback + caching
# ---------------------------------------------------------------------------

def test_fetch_quote_uses_dedicated_provider_on_success(monkeypatch):
    fake = FakeProvider("fake-us", quote_fields={"price": 100.0, "name": "Fake Co"})
    monkeypatch.setattr(dp, "_provider_for", lambda ticker: fake)

    q = dp.fetch_quote("FAKE", history_period="1mo")

    assert q.source == "fake-us"
    assert q.price == 100.0
    assert q.name == "Fake Co"
    assert len(fake.quote_calls) == 1
    assert len(fake.history_calls) == 1


def test_fetch_quote_falls_back_to_yfinance_on_quote_error(monkeypatch):
    fake = FakeProvider("fake-us", quote_error=RuntimeError("boom"))
    monkeypatch.setattr(dp, "_provider_for", lambda ticker: fake)

    fallback_quote = dp.Quote(ticker="FAKE", price=42.0, source="yfinance")
    monkeypatch.setattr(
        dp, "_fetch_quote_yfinance", lambda ticker, period: fallback_quote
    )

    q = dp.fetch_quote("FAKE", history_period="1mo")

    assert q.source == "yfinance"
    assert q.price == 42.0


def test_fetch_quote_falls_back_to_yfinance_history_on_history_error(monkeypatch):
    fake = FakeProvider(
        "fake-us", quote_fields={"price": 100.0}, history_error=RuntimeError("boom")
    )
    monkeypatch.setattr(dp, "_provider_for", lambda ticker: fake)

    fallback_hist = pd.DataFrame(
        {"Open": [8.0], "High": [9.5], "Low": [7.5], "Close": [9.0], "Volume": [50.0]},
        index=pd.to_datetime(["2026-01-02"]),
    )

    class _FakeTicker:
        def history(self, period, auto_adjust=False):
            return fallback_hist

    monkeypatch.setattr(dp.yf, "Ticker", lambda ticker: _FakeTicker())

    q = dp.fetch_quote("FAKE", history_period="1mo")

    assert q.source == "fake-us"  # quote still came from the dedicated provider
    assert q.history.equals(fallback_hist)


def test_fetch_quote_uses_cache_on_second_call(monkeypatch):
    fake = FakeProvider("fake-us", quote_fields={"price": 100.0})
    monkeypatch.setattr(dp, "_provider_for", lambda ticker: fake)

    dp.fetch_quote("FAKE", history_period="1mo")
    dp.fetch_quote("FAKE", history_period="1mo")

    assert len(fake.quote_calls) == 1  # second call served from cache


def test_force_refresh_bypasses_cache(monkeypatch):
    fake = FakeProvider("fake-us", quote_fields={"price": 100.0})
    monkeypatch.setattr(dp, "_provider_for", lambda ticker: fake)

    dp.fetch_quote("FAKE", history_period="1mo")
    dp.fetch_quote("FAKE", history_period="1mo", force_refresh=True)

    assert len(fake.quote_calls) == 2


def test_cached_quote_carries_no_history_until_history_reattached(monkeypatch):
    fake = FakeProvider("fake-us", quote_fields={"price": 100.0})
    monkeypatch.setattr(dp, "_provider_for", lambda ticker: fake)

    first = dp.fetch_quote("FAKE", history_period="1mo")
    second = dp.fetch_quote("FAKE", history_period="1mo")

    assert not first.history.empty
    assert not second.history.empty
    assert second.history.equals(first.history)
