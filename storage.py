"""
storage.py
Persists the user's watchlist to a small JSON file in the user's home
directory so it survives app restarts. No cloud sync, no telemetry -
everything stays on the local machine.
"""

from __future__ import annotations
import json
from pathlib import Path

from universe import DEFAULT_WATCHLIST

APP_DIR = Path.home() / ".stock_analysis_tool"
WATCHLIST_FILE = APP_DIR / "watchlist.json"


def ensure_app_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


def load_watchlist() -> list[str]:
    ensure_app_dir()
    if WATCHLIST_FILE.exists():
        try:
            data = json.loads(WATCHLIST_FILE.read_text())
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
    save_watchlist(DEFAULT_WATCHLIST)
    return list(DEFAULT_WATCHLIST)


def save_watchlist(tickers: list[str]) -> None:
    ensure_app_dir()
    # de-dupe, preserve order
    seen = set()
    deduped = []
    for t in tickers:
        t = t.strip().upper()
        if t and t not in seen:
            seen.add(t)
            deduped.append(t)
    WATCHLIST_FILE.write_text(json.dumps(deduped, indent=2))
