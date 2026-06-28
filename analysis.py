"""
analysis.py
Technical indicator calculations and rule-based screening logic.

All screening rules here are deliberately simple and transparent (no
opaque "AI score") so you can see exactly why a stock was flagged. Treat
everything as a starting point for your own research, not investment
advice.
"""

from __future__ import annotations
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from data_provider import Quote


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    out[(avg_loss == 0) & (avg_gain > 0)] = 100   # no losses, some gains -> maxed out
    out[(avg_loss == 0) & (avg_gain == 0)] = 50   # totally flat -> neutral, not "overbought"
    return out


@dataclass
class TechnicalSnapshot:
    sma20: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    rsi14: float | None = None
    range_position: float | None = None  # 0 = at 52wk low, 1 = at 52wk high
    volume_ratio: float | None = None    # volume / avg_volume
    trend: str = "n/a"                   # "Golden Cross" / "Death Cross" / "Neutral"
    flags: list[str] = field(default_factory=list)


def compute_technical_snapshot(q: Quote) -> TechnicalSnapshot:
    snap = TechnicalSnapshot()
    hist = q.history
    if hist is None or hist.empty or "Close" not in hist:
        return snap

    close = hist["Close"].dropna()
    if close.empty:
        return snap

    sma20_s = sma(close, 20)
    sma50_s = sma(close, 50)
    sma200_s = sma(close, 200)
    rsi_s = rsi(close, 14)

    snap.sma20 = _last_valid(sma20_s)
    snap.sma50 = _last_valid(sma50_s)
    snap.sma200 = _last_valid(sma200_s)
    snap.rsi14 = _last_valid(rsi_s)

    # 52-week range position from quote (falls back to history min/max)
    hi = q.week52_high or float(hist["High"].max())
    lo = q.week52_low or float(hist["Low"].min())
    price = q.price or float(close.iloc[-1])
    if hi and lo and hi > lo:
        snap.range_position = (price - lo) / (hi - lo)

    if q.volume and q.avg_volume:
        snap.volume_ratio = q.volume / q.avg_volume

    # Golden / death cross detection: compare SMA50 vs SMA200 now vs ~10 sessions ago
    if sma50_s.notna().sum() > 10 and sma200_s.notna().sum() > 10:
        now_diff = sma50_s.iloc[-1] - sma200_s.iloc[-1]
        past_diff = sma50_s.iloc[-11] - sma200_s.iloc[-11]
        if past_diff < 0 <= now_diff:
            snap.trend = "Golden Cross"
        elif past_diff > 0 >= now_diff:
            snap.trend = "Death Cross"
        elif now_diff > 0:
            snap.trend = "Uptrend (50>200)"
        else:
            snap.trend = "Downtrend (50<200)"

    flags = []
    if snap.rsi14 is not None:
        if snap.rsi14 < 30:
            flags.append("Oversold (RSI<30)")
        elif snap.rsi14 > 70:
            flags.append("Overbought (RSI>70)")
    if snap.range_position is not None:
        if snap.range_position <= 0.1:
            flags.append("Near 52wk Low")
        elif snap.range_position >= 0.9:
            flags.append("Near 52wk High")
    if snap.volume_ratio is not None and snap.volume_ratio >= 2:
        flags.append("Volume Spike")
    if snap.trend in ("Golden Cross", "Death Cross"):
        flags.append(snap.trend)
    snap.flags = flags
    return snap


def _last_valid(series: pd.Series) -> float | None:
    s = series.dropna()
    return float(s.iloc[-1]) if not s.empty else None


# ---------------------------------------------------------------------------
# Screening
# ---------------------------------------------------------------------------

@dataclass
class ScreenResult:
    quote: Quote
    snapshot: TechnicalSnapshot
    category: str  # "Value Candidate" / "Momentum" / "Watch" / "Neutral"


def screen_quote(q: Quote, snap: TechnicalSnapshot, *,
                  pe_max: float = 25.0,
                  rsi_oversold: float = 35.0,
                  rsi_overbought: float = 70.0,
                  near_low_threshold: float = 0.3,
                  near_high_threshold: float = 0.85) -> ScreenResult:
    """Classify a stock into a simple category based on transparent rules."""
    category = "Neutral"

    is_value = (
        snap.rsi14 is not None and snap.rsi14 <= rsi_oversold
        and snap.range_position is not None and snap.range_position <= near_low_threshold
        and (q.pe_ratio is None or q.pe_ratio <= pe_max)
    )
    is_momentum = (
        snap.rsi14 is not None and snap.rsi14 >= rsi_overbought
        and snap.range_position is not None and snap.range_position >= near_high_threshold
    )

    if is_value:
        category = "Value Candidate"
    elif is_momentum:
        category = "Momentum / Overbought"
    elif snap.trend == "Golden Cross":
        category = "Watch (Golden Cross)"
    elif snap.trend == "Death Cross":
        category = "Watch (Death Cross)"

    return ScreenResult(quote=q, snapshot=snap, category=category)


def run_screen(quotes: list[Quote], **kwargs) -> list[ScreenResult]:
    results = []
    for q in quotes:
        if q.error:
            continue
        snap = compute_technical_snapshot(q)
        results.append(screen_quote(q, snap, **kwargs))
    return results
