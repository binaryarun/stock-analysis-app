import time

from cache import TTLCache


def _new_cache(tmp_path, ttls=None):
    return TTLCache(db_path=tmp_path / "cache.sqlite3", ttls=ttls)


def test_set_then_get_returns_value(tmp_path):
    cache = _new_cache(tmp_path)
    cache.set("quote", "AAPL", {"price": 100})
    assert cache.get("quote", "AAPL") == {"price": 100}


def test_get_missing_key_returns_none(tmp_path):
    cache = _new_cache(tmp_path)
    assert cache.get("quote", "MSFT") is None


def test_quote_and_history_are_independent_per_period(tmp_path):
    cache = _new_cache(tmp_path)
    cache.set("history", "AAPL", "1mo-data", period="1mo")
    cache.set("history", "AAPL", "1y-data", period="1y")
    assert cache.get("history", "AAPL", period="1mo") == "1mo-data"
    assert cache.get("history", "AAPL", period="1y") == "1y-data"


def test_ticker_lookup_is_case_insensitive(tmp_path):
    cache = _new_cache(tmp_path)
    cache.set("quote", "aapl", {"price": 100})
    assert cache.get("quote", "AAPL") == {"price": 100}


def test_entry_expires_after_ttl(tmp_path):
    cache = _new_cache(tmp_path, ttls={"quote": 0})
    cache.set("quote", "AAPL", {"price": 100})
    time.sleep(0.01)
    assert cache.get("quote", "AAPL") is None


def test_entry_survives_within_ttl(tmp_path):
    cache = _new_cache(tmp_path, ttls={"quote": 60})
    cache.set("quote", "AAPL", {"price": 100})
    assert cache.get("quote", "AAPL") == {"price": 100}


def test_set_overwrites_existing_entry(tmp_path):
    cache = _new_cache(tmp_path)
    cache.set("quote", "AAPL", {"price": 100})
    cache.set("quote", "AAPL", {"price": 200})
    assert cache.get("quote", "AAPL") == {"price": 200}


def test_invalidate_removes_entry(tmp_path):
    cache = _new_cache(tmp_path)
    cache.set("quote", "AAPL", {"price": 100})
    cache.invalidate("quote", "AAPL")
    assert cache.get("quote", "AAPL") is None


def test_default_ttls_used_when_not_overridden(tmp_path):
    cache = _new_cache(tmp_path)
    assert cache.ttls["quote"] == 5 * 60
    assert cache.ttls["history"] == 24 * 60 * 60


def test_custom_ttls_merge_with_defaults(tmp_path):
    cache = _new_cache(tmp_path, ttls={"quote": 10})
    assert cache.ttls["quote"] == 10
    assert cache.ttls["history"] == 24 * 60 * 60
