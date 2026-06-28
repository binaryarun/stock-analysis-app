# Stock Analysis Tool

**Version:** 0.1.0 (unreleased — pre-mobile-packaging)

A personal desktop app for tracking and screening Indian (NSE) and US stocks
using real fundamentals and technicals — instead of news-article "tips".
Built with [Flet](https://flet.dev) (Python + Flutter), so the same codebase
can later be packaged as a Linux desktop app or a mobile app.

This is a personal research tool. Nothing in it is investment advice.

## Project setup

- **Python**: 3.13.13 (see `.python-version` at the repo root)
- **Dependencies**: listed in `requirements.txt` (Flet, yfinance, pandas,
  numpy, matplotlib, requests)

```bash
# from stock_analysis_app/
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## What it does

**Watchlist** — your own list of tickers (defaults to a starter mix of NSE
and US large caps). Shows live price, day change, P/E, dividend yield,
RSI(14), trend, and rule-based signals (oversold/overbought, near 52-week
high/low, volume spikes, golden/death cross). Add or remove tickers anytime;
the list is saved locally and persists between runs.

**Screener** — scans a whole index (Nifty 50, Dow 30, or S&P 500) and flags
stocks into transparent categories:
- *Value Candidate*: RSI oversold + near 52-week low + P/E under your max
- *Momentum / Overbought*: RSI overbought + near 52-week high
- *Watch (Golden Cross)* / *Watch (Death Cross)*: SMA50 just crossed SMA200

You control the thresholds (max P/E, RSI bands) with the fields above the
scan button.

**Detail view** — click any row to see full fundamentals plus a price chart
with SMA20/50/200 overlays and an RSI subplot.

**Macro** — a handful of headline rates/volatility/currency/commodity
indicators (US 10Y Treasury yield, VIX, USD/INR, crude oil, gold) plus the
major equity indices (S&P 500, Dow, Nifty 50, Sensex), fetched the same way
as everything else via `yfinance` — no separate API, no news. Each one gets
a Rising/Falling/Flat read versus its own 50-day average, and for the
indicators with a well-known textbook relationship to equities, a one-line
hardcoded tailwind/headwind note (e.g. "rising oil: headwind for India as a
net importer"). These notes are generic finance-101 relationships, not
predictions and not derived from news or sentiment — useful context, not a
signal to act on by itself.

All the screening logic lives in `analysis.py` as plain, readable rules —
no opaque "AI score." Treat flagged stocks as a starting point for your own
research.

## Data source

Live data comes from Yahoo Finance via the `yfinance` library. No API key
needed.

- US stocks: plain ticker, e.g. `AAPL`, `MSFT`
- NSE (India) stocks: ticker + `.NS`, e.g. `RELIANCE.NS`, `TCS.NS`
- BSE (India) stocks: ticker + `.BO`, e.g. `RELIANCE.BO`

This needs a normal internet connection (not a restricted/proxied network)
to reach Yahoo Finance.

## Running it

With the venv from [Project setup](#project-setup) active:

```bash
# Native desktop window
flet run main.py

# Or in a browser tab instead
flet run --web main.py
```

On first launch the app loads a default watchlist and starts fetching
quotes in the background — give it a few seconds on slower connections.

## Where your data lives

Your watchlist is saved locally at `~/.stock_analysis_tool/watchlist.json`.
Nothing is sent anywhere except requests to Yahoo Finance for quotes — no
cloud sync, no telemetry, no accounts.

## Packaging as a standalone app

Flet can package this same code into installable apps for several
platforms without rewriting anything.

**Linux desktop:**
```bash
flet build linux
```
This produces a self-contained build under `build/linux` that you can run
directly or wrap into a `.deb`/AppImage with your preferred packaging tool.

**Android / iOS (future):**
```bash
flet build apk     # Android
flet build ipa      # iOS (requires a Mac + Apple developer setup)
```

See the [Flet packaging docs](https://flet.dev/docs/publish) for platform
prerequisites (Flutter SDK, Android SDK/NDK for `apk`, Xcode for `ipa`) —
these aren't needed for `flet run` during normal use, only for building a
distributable installer.

## Project layout

```
main.py            Flet UI: Watchlist + Screener + Macro + Detail dialog
data_provider.py    yfinance wrapper (Quote dataclass, concurrent fetching)
analysis.py         SMA/RSI calculations, golden/death cross, screening rules
macro.py             Macro indicators: trend vs 50-day avg + tailwind/headwind notes
charting.py          matplotlib price/RSI chart rendered as an in-app image
universe.py          Nifty 50 / Dow 30 / S&P 500 ticker lists + default watchlist
storage.py           Local JSON persistence for your watchlist
formatting.py        Number/currency/percent display helpers
requirements.txt
```

## Customizing

- **Change the default watchlist**: edit `DEFAULT_WATCHLIST` in `universe.py`
  (only affects first run — after that, your saved list in
  `~/.stock_analysis_tool/watchlist.json` takes over).
- **Adjust screening rules**: edit the thresholds or logic in
  `screen_quote()` in `analysis.py`.
- **Add another index universe**: add an entry to `UNIVERSE_CHOICES` in
  `universe.py`.
- **Add/remove macro indicators or notes**: edit `MACRO_TICKERS` (ticker →
  label) and `_NOTES` (ticker → tailwind/headwind text) in `macro.py`.
