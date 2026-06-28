# Phase 1 — Official-ish data sources (NSE + US) + caching

Goal: reduce reliance on yfinance's Yahoo scrape by introducing per-market
providers that are closer to "official," with yfinance kept as a fallback.
Add a local TTL cache so repeated scans (esp. full S&P 500 / NASDAQ-100 /
Nifty 50) are fast and don't hammer any single source.

## NSE provider (India)

- [ ] Research `nseindia.com`'s JSON endpoints used by its own site (quote,
      historical, 52-week high/low) and the request headers/cookies/session
      handling needed to call them reliably from a script
- [ ] Add `providers/nse.py` implementing a common provider interface
      (`get_quote(ticker) -> Quote`, `get_history(ticker, period) -> DataFrame`)
- [ ] Handle session/cookie bootstrap (NSE requires a warm-up request before
      API calls succeed) and rate-limit backoff
- [ ] Map NSE's response fields onto the existing `Quote` dataclass in
      `data_provider.py`
- [ ] Fallback to yfinance for any `.NS`/`.BO` ticker the NSE provider fails on

## US provider (S&P 500 + NASDAQ)

Covers both major US universes — S&P 500 (NYSE + NASDAQ listings) and the
NASDAQ-100/Composite — through a single provider keyed off `api.nasdaq.com`,
since that endpoint serves quotes for tickers on either index regardless of
listing exchange.

- [ ] Research `api.nasdaq.com` quote endpoints (used by nasdaq.com itself)
      and rate limits/headers needed
- [ ] Evaluate Nasdaq Data Link (free tier, API key) for fundamentals/history
      depth vs. yfinance
- [ ] Add `providers/nasdaq.py` implementing the same provider interface,
      used for both S&P 500 and NASDAQ-100/Composite constituents
- [ ] Fallback to yfinance for any US ticker (S&P 500 or NASDAQ) the
      provider fails on

## Provider abstraction

- [ ] Define a `Provider` protocol/ABC (e.g. in `providers/base.py`) with
      `get_quote` / `get_history`
- [ ] Refactor `data_provider.py` so `fetch_quote`/`fetch_quotes` pick a
      provider by ticker suffix (`.NS`/`.BO` → NSE, else → NASDAQ → yfinance)
      instead of calling `yfinance` directly
- [ ] Keep `Quote` dataclass and its consumers (`analysis.py`, `main.py`)
      unchanged — only the fetching layer changes
- [ ] Surface which provider actually served each quote (for debugging /
      future UI badge), e.g. add `Quote.source: str`

## Local cache

- [ ] Add `cache.py` with a simple TTL cache (SQLite or JSON file under
      `~/.stock_analysis_tool/cache/`), keyed by `(ticker, period)`
- [ ] Wire cache into the provider layer: check cache before hitting any
      network source, write through after a successful fetch
- [ ] Make TTL configurable (e.g. 5 min for quotes, 1 day for history) and
      add a manual "force refresh" path for the UI's refresh button
- [ ] Confirm screener scans (Nifty 50 / Dow 30 / S&P 500 / NASDAQ-100) get
      noticeably faster on a second run within the TTL window

## Validation

- [ ] Spot-check NSE provider output against nseindia.com website for a
      handful of tickers (price, 52wk high/low, volume)
- [ ] Spot-check US provider output against nasdaq.com for a handful of
      S&P 500 and NASDAQ-100 tickers
- [ ] Run a full Nifty 50, full S&P 500, and full NASDAQ-100 screener scan
      end-to-end with the new providers + cache, confirm no regressions vs.
      current yfinance-only behavior
- [ ] Add unit tests for the provider selection logic and cache TTL behavior
