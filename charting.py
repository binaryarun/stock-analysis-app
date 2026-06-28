"""
charting.py
Renders a price + moving-average chart with an RSI subplot to a base64
PNG string so it can be displayed inside the Flet UI via ft.Image(src=...).
Uses the non-interactive "Agg" backend since there's no display server
needed for plotting (Flet renders its own native window separately).
"""

from __future__ import annotations
import base64
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis import sma, rsi


def render_price_chart(history, ticker: str, currency_symbol: str = "") -> str | None:
    """Return a base64-encoded PNG (no 'data:image/png;base64,' prefix)."""
    if history is None or history.empty or "Close" not in history:
        return None

    close = history["Close"].dropna()
    if close.empty:
        return None

    sma20 = sma(close, 20)
    sma50 = sma(close, 50)
    sma200 = sma(close, 200)
    rsi14 = rsi(close, 14)

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(7, 5), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )

    ax1.plot(close.index, close.values, label="Close", color="#1f77b4", linewidth=1.4)
    if sma20.notna().any():
        ax1.plot(sma20.index, sma20.values, label="SMA20", color="#ff7f0e", linewidth=1.0)
    if sma50.notna().any():
        ax1.plot(sma50.index, sma50.values, label="SMA50", color="#2ca02c", linewidth=1.0)
    if sma200.notna().any():
        ax1.plot(sma200.index, sma200.values, label="SMA200", color="#d62728", linewidth=1.0)
    ax1.set_title(f"{ticker} — Price & Moving Averages")
    ax1.set_ylabel(f"Price ({currency_symbol})" if currency_symbol else "Price")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(alpha=0.25)

    ax2.plot(rsi14.index, rsi14.values, color="#9467bd", linewidth=1.0)
    ax2.axhline(70, color="red", linestyle="--", linewidth=0.8)
    ax2.axhline(30, color="green", linestyle="--", linewidth=0.8)
    ax2.set_ylabel("RSI(14)")
    ax2.set_ylim(0, 100)
    ax2.grid(alpha=0.25)

    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")
