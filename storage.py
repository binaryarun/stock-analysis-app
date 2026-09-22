"""
storage.py
Persists the user's watchlist to a small JSON file in the user's home
directory so it survives app restarts. No cloud sync, no telemetry -
everything stays on the local machine.
"""

from __future__ import annotations
import json
import os
from pathlib import Path

from universe import DEFAULT_WATCHLIST

if "ANDROID_ARGUMENT" in os.environ or "ANDROID_DATA" in os.environ:
    # Path.home() resolves to a non-writable system path (e.g. "/data") in
    # the Android sandbox rather than a real per-user home directory, so
    # fall back to the app's own writable files directory (where this
    # script itself runs from) instead.
    APP_DIR = Path(__file__).resolve().parent / ".stock_analysis_tool"
else:
    APP_DIR = Path.home() / ".stock_analysis_tool"
WATCHLIST_FILE = APP_DIR / "watchlist.json"
CHAT_SESSIONS_FILE = APP_DIR / "chat_sessions.json"


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


def load_chat_sessions() -> list[dict]:
    """Load saved general-chat sessions (newest-first). Each session is
    {"id": str, "title": str, "created_at": iso-str, "messages": [...]}.
    Returns [] if none exist yet or the file is missing/corrupt."""
    ensure_app_dir()
    if CHAT_SESSIONS_FILE.exists():
        try:
            data = json.loads(CHAT_SESSIONS_FILE.read_text())
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def save_chat_sessions(sessions: list[dict]) -> None:
    ensure_app_dir()
    CHAT_SESSIONS_FILE.write_text(json.dumps(sessions, indent=2))
