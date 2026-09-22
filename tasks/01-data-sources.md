# Phase 1 — Official-ish data sources (NSE + US) + caching

Goal: reduce reliance on yfinance's Yahoo scrape by introducing per-market
providers that are closer to "official," with yfinance kept as a fallback.
Add a local TTL cache so repeated scans (esp. full S&P 500 / NASDAQ-100 /
Nifty 50) are fast and don't hammer any single source.

## NSE provider (India)

- [x] Research `nseindia.com`'s JSON endpoints used by its own site (quote,
      historical, 52-week high/low) and the request headers/cookies/session
      handling needed to call them reliably from a script
- [x] Add `providers/nse.py` implementing a common provider interface
      (`get_quote(ticker) -> Quote`, `get_history(ticker, period) -> DataFrame`)
- [x] Handle session/cookie bootstrap (NSE requires a warm-up request before
      API calls succeed) and rate-limit backoff
- [x] Map NSE's response fields onto the existing `Quote` dataclass in
      `data_provider.py`
- [x] Fallback to yfinance for any `.NS`/`.BO` ticker the NSE provider fails on
- [ ] **TODO (blocked on network): validate `providers/nse.py` from a
      residential/non-datacenter connection.** From this dev sandbox,
      Akamai 403s even a plain GET to nseindia.com's homepage before any
      cookie logic runs — this is an IP/ASN-level block, not a
      header/cookie problem. The provider code follows the documented
      warm-up + cookie + retry flow but is **unverified end-to-end**; it
      currently always falls through to the yfinance fallback in this
      environment. Re-test from home network/VPN and fix up field mappings
      against real responses before trusting it in production.

## US provider (S&P 500 + NASDAQ)

Covers both major US universes — S&P 500 (NYSE + NASDAQ listings) and the
NASDAQ-100/Composite — through a single provider keyed off `api.nasdaq.com`,
since that endpoint serves quotes for tickers on either index regardless of
listing exchange.

- [x] Research `api.nasdaq.com` quote endpoints (used by nasdaq.com itself)
      and rate limits/headers needed — confirmed `quote/{symbol}/info`,
      `/summary`, and `/historical` all work with just a browser
      User-Agent + Origin/Referer headers, no API key or session/cookies
      needed
- [x] ~~Evaluate Nasdaq Data Link (free tier, API key) for fundamentals/history
      depth vs. yfinance~~ — skipped; the free public `api.nasdaq.com`
      endpoints already cover quote/summary/historical with no API-key
      dependency, decided that's sufficient
- [x] Add `providers/nasdaq.py` implementing the same provider interface,
      used for both S&P 500 and NASDAQ-100/Composite constituents
- [x] Fallback to yfinance for any US ticker (S&P 500 or NASDAQ) the
      provider fails on

## Provider abstraction

- [x] Define a `Provider` protocol/ABC (e.g. in `providers/base.py`) with
      `get_quote` / `get_history`
- [x] Refactor `data_provider.py` so `fetch_quote`/`fetch_quotes` pick a
      provider by ticker suffix (`.NS`/`.BO` → NSE, else → NASDAQ → yfinance)
      instead of calling `yfinance` directly
- [x] Keep `Quote` dataclass and its consumers (`analysis.py`, `main.py`)
      unchanged — only the fetching layer changes
- [x] Surface which provider actually served each quote (for debugging /
      future UI badge), e.g. add `Quote.source: str`

## Local cache

- [x] Add `cache.py` with a simple TTL cache (SQLite or JSON file under
      `~/.stock_analysis_tool/cache/`), keyed by `(ticker, period)`
- [x] Wire cache into the provider layer: check cache before hitting any
      network source, write through after a successful fetch
- [x] Make TTL configurable (e.g. 5 min for quotes, 1 day for history) and
      add a manual "force refresh" path for the UI's refresh button —
      `fetch_quote(..., force_refresh=True)` / `fetch_quotes(...,
      force_refresh=True)`
- [x] Confirm screener scans (Nifty 50 / Dow 30 / S&P 500 / NASDAQ-100) get
      noticeably faster on a second run within the TTL window — Dow 30:
      32.7s cold vs 0.01s cached

## Validation

- [ ] **Blocked here, needs a non-datacenter network — see NSE TODO above.**
      Spot-check NSE provider output against nseindia.com website for a
      handful of tickers (price, 52wk high/low, volume)
- [x] Spot-check US provider output against nasdaq.com for a handful of
      S&P 500 and NASDAQ-100 tickers — verified AAPL quote/summary/history
      fields against live nasdaq.com responses
- [ ] Run a full Nifty 50, full S&P 500, and full NASDAQ-100 screener scan
      end-to-end with the new providers + cache, confirm no regressions vs.
      current yfinance-only behavior — Dow 30 done (30/30 via Nasdaq
      provider, 0 errors); full S&P 500/NASDAQ-100/Nifty 50 runs still
      outstanding (Nifty 50 blocked on the NSE network issue above)
- [x] Add unit tests for the provider selection logic and cache TTL behavior
      — `tests/test_data_provider.py`, `tests/test_cache.py` (20 tests, all
      passing)
