"""
cache.py
A small SQLite-backed TTL cache shared by the provider layer, so repeated
screener scans (Nifty 50 / Dow 30 / S&P 500 / NASDAQ-100) within the TTL
window don't re-hit NSE/Nasdaq/yfinance for every ticker.

Quotes and history are cached separately with different TTLs: quotes move
fast (price, day change) so they expire in minutes, while a day of OHLCV
history barely changes intraday so it's cached far longer.
"""

from __future__ import annotations
import os
import pickle
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

if "ANDROID_ARGUMENT" in os.environ or "ANDROID_DATA" in os.environ:
    # See storage.py: Path.home() isn't writable in the Android sandbox.
    _APP_DIR = Path(__file__).resolve().parent / ".stock_analysis_tool"
else:
    _APP_DIR = Path.home() / ".stock_analysis_tool"

CACHE_DIR = _APP_DIR / "cache"
DB_PATH = CACHE_DIR / "cache.sqlite3"

DEFAULT_TTLS = {
    "quote": 5 * 60,
    "history": 24 * 60 * 60,
}


class TTLCache:
    def __init__(self, db_path: Path = DB_PATH, ttls: dict[str, int] | None = None):
        self.ttls = {**DEFAULT_TTLS, **(ttls or {})}
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache ("
            "key TEXT PRIMARY KEY, value BLOB NOT NULL, created_at REAL NOT NULL"
            ")"
        )
        self._conn.commit()
        self._lock = threading.Lock()

    @staticmethod
    def _key(kind: str, ticker: str, period: str | None) -> str:
        return f"{kind}:{ticker.upper()}:{period or ''}"

    def get(self, kind: str, ticker: str, period: str | None = None) -> Any | None:
        key = self._key(kind, ticker, period)
        with self._lock:
            row = self._conn.execute(
                "SELECT value, created_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        value_blob, created_at = row
        ttl = self.ttls.get(kind, 300)
        if time.time() - created_at > ttl:
            return None
        return pickle.loads(value_blob)

    def set(self, kind: str, ticker: str, value: Any, period: str | None = None) -> None:
        key = self._key(kind, ticker, period)
        blob = pickle.dumps(value)
        with self._lock:
            self._conn.execute(
                "INSERT INTO cache (key, value, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "created_at = excluded.created_at",
                (key, blob, time.time()),
            )
            self._conn.commit()

    def invalidate(self, kind: str, ticker: str, period: str | None = None) -> None:
        key = self._key(kind, ticker, period)
        with self._lock:
            self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._conn.commit()


_default_cache: TTLCache | None = None
_default_cache_lock = threading.Lock()


def get_cache() -> TTLCache:
    """Process-wide cache instance, lazily created on first use."""
    global _default_cache
    if _default_cache is None:
        with _default_cache_lock:
            if _default_cache is None:
                _default_cache = TTLCache()
    return _default_cache
