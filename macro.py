"""
macro.py
A handful of headline macro/market indicators (rates, volatility, currency,
commodities, equity indices), fetched via yfinance like everything else in
this app - no separate API, no news, no sentiment.

Each indicator gets a simple "Rising / Falling / Flat" read versus its own
50-day average, and - for indicators with a well-known textbook relationship
to equities - a one-line, hardcoded rule-of-thumb note. These notes are
generic finance-101 relationships, not predictions, not derived from news
or any model, and can be wrong in any given period (e.g. correlations break
down). Treat them as a prompt to think, not a signal to act on.
"""

from __future__ import annotations
from dataclasses import dataclass

from data_provider import fetch_quotes
from analysis import sma

# ticker -> human label
MACRO_TICKERS = {
    "^TNX": "US 10Y Treasury Yield",
    "^VIX": "VIX (Volatility Index)",
    "INR=X": "USD/INR",
    "CL=F": "Crude Oil (WTI)",
    "GC=F": "Gold",
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones Industrial",
    "^NSEI": "Nifty 50 Index",
    "^BSESN": "BSE Sensex",
}

# ticker -> (note when Falling, note when Rising). Equity/commodity index
# levels (S&P 500, Dow, Nifty, Sensex) intentionally have no entry here -
# "the index is rising" isn't a tailwind/headwind *for* anything, it just
# is the market, so we only show its level/trend, not a classification.
_NOTES: dict[str, tuple[str, str]] = {
    "^TNX": (
        "Falling yields: typically a tailwind for equities, especially growth/tech.",
        "Rising yields: typically a headwind for equities, especially growth/tech.",
    ),
    "^VIX": (
        "Low/falling VIX: calmer markets, typically risk-on.",
        "High/rising VIX: elevated fear, typically risk-off.",
    ),
    "INR=X": (
        "INR strengthening: eases imported inflation; mixed-to-negative for IT/export earnings in INR terms.",
        "INR weakening: raises imported inflation (e.g. oil); can help IT/export earnings in INR terms.",
    ),
    "CL=F": (
        "Falling oil: tailwind for India as a net importer - lower inflation/fiscal pressure.",
        "Rising oil: headwind for India as a net importer - higher inflation/fiscal pressure.",
    ),
    "GC=F": (
        "Falling gold: often reflects risk-on appetite / lower safe-haven demand.",
        "Rising gold: often reflects risk-off appetite / more hedging demand.",
    ),
}


@dataclass
class MacroSnapshot:
    ticker: str
    label: str
    price: float | None = None
    day_change_pct: float | None = None
    pct_vs_sma50: float | None = None  # % above/below its own 50-day average
    trend: str = "n/a"                  # "Rising" / "Falling" / "Flat" / "n/a"
    note: str | None = None
    error: str | None = None


def fetch_macro_snapshot(flat_band: float = 1.0) -> list[MacroSnapshot]:
    """flat_band: +/- this % vs SMA50 counts as 'Flat' rather than rising/falling."""
    tickers = list(MACRO_TICKERS.keys())
    quotes = fetch_quotes(tickers, history_period="6mo")

    by_ticker = {q.ticker: q for q in quotes}
    out = []
    for tkr in tickers:  # preserve declared order, not fetch-completion order
        q = by_ticker.get(tkr)
        label = MACRO_TICKERS[tkr]
        if q is None or q.error or q.history is None or q.history.empty:
            out.append(MacroSnapshot(ticker=tkr, label=label,
                                      error=(q.error if q else "no data")))
            continue

        close = q.history["Close"].dropna()
        if close.empty:
            out.append(MacroSnapshot(ticker=tkr, label=label, error="no price history"))
            continue

        sma50_s = sma(close, 50).dropna()
        sma50 = float(sma50_s.iloc[-1]) if not sma50_s.empty else None
        price = q.price if q.price is not None else float(close.iloc[-1])
        pct_vs_sma50 = ((price - sma50) / sma50 * 100) if sma50 else None

        if pct_vs_sma50 is None:
            trend = "n/a"
        elif pct_vs_sma50 > flat_band:
            trend = "Rising"
        elif pct_vs_sma50 < -flat_band:
            trend = "Falling"
        else:
            trend = "Flat"

        note = None
        if tkr in _NOTES and trend in ("Rising", "Falling"):
            falling_note, rising_note = _NOTES[tkr]
            note = falling_note if trend == "Falling" else rising_note

        out.append(MacroSnapshot(
            ticker=tkr, label=label, price=price, day_change_pct=q.day_change_pct,
            pct_vs_sma50=pct_vs_sma50, trend=trend, note=note,
        ))
    return out
