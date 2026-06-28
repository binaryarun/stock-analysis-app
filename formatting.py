"""formatting.py - small helpers to render numbers nicely in the UI."""

from __future__ import annotations


def fmt_num(x, decimals=2, default="-"):
    if x is None:
        return default
    try:
        return f"{x:,.{decimals}f}"
    except (TypeError, ValueError):
        return default


def fmt_pct(x, decimals=2, default="-", already_fraction=True):
    """already_fraction=True means x is e.g. 0.034 for 3.4%."""
    if x is None:
        return default
    try:
        val = x * 100 if already_fraction else x
        return f"{val:,.{decimals}f}%"
    except (TypeError, ValueError):
        return default


def fmt_compact(x, default="-"):
    """Compact large numbers: 1.2T / 345.6B / 12.3M / 4,200"""
    if x is None:
        return default
    try:
        x = float(x)
    except (TypeError, ValueError):
        return default
    abs_x = abs(x)
    if abs_x >= 1e12:
        return f"{x / 1e12:,.2f}T"
    if abs_x >= 1e9:
        return f"{x / 1e9:,.2f}B"
    if abs_x >= 1e6:
        return f"{x / 1e6:,.2f}M"
    if abs_x >= 1e3:
        return f"{x / 1e3:,.2f}K"
    return f"{x:,.0f}"


def currency_symbol(currency: str | None) -> str:
    if not currency:
        return ""
    return {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£"}.get(currency.upper(), currency + " ")
