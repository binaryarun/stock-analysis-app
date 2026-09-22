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

### Quick start (venv already set up)

If `venv/` already exists in the repo (it does by default here), you can
skip straight to running it:

```bash
cd stock_analysis_app
source venv/bin/activate
flet run main.py
```

See [Running it](#running-it) below for the browser-tab alternative and
what to expect on first launch.

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

**Chat** — an optional tab for general stock-market/investing discussion
(terminology, indicators, how to think about screening) powered by a local
LLM via Ollama. It has no access to live prices, news, or your own
Watchlist/Screener data (use those tabs for that), and it isn't a
financial advisor — see [Optional: local "Explain this" summaries](#optional-local-explain-this-summaries)
below. The tab is hidden if Ollama isn't running.

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

## Optional: local "Explain this" summaries & Chat

Two local-LLM features, both served by [Ollama](https://ollama.com) over
loopback only (`localhost:11434`, no other network calls at runtime):

- **Detail view chat** — click any row, then "Explain this," to open a
  chat about that specific stock (`llm_summary.chat_reply`). Its data
  (price, RSI, SMAs, trend, flags, category) is re-injected as context on
  every turn, so it can only restate/explain what `analysis.py` already
  computed — it will decline follow-up questions about anything not in
  that data (e.g. news) rather than guess.
- **Chat tab** — a top-level tab for general market/investing discussion,
  not tied to one stock (`llm_summary.general_chat_reply`). This one may
  use the model's own general knowledge to explain concepts (RSI, golden
  cross, order types, etc.), but has no live prices/news/portfolio access
  and is instructed to stay on stock-market topics. Conversations are
  saved as named sessions in a history panel on the left of the tab (title
  taken from your first message), so past chats persist across app
  restarts at `~/.stock_analysis_tool/chat_sessions.json`; click **+ New
  chat** to start a fresh conversation, click a past session to reopen it,
  or delete one with its trash icon. With small (~3B)
  models this topic restriction is a soft, prompt-only guardrail — it
  reliably declines live-data questions, but may not always refuse a
  fully off-topic request (e.g. asked to write a poem, it may just write
  one). It has never been observed to fabricate stock data/prices.

The app works fully without it: if Ollama isn't installed or isn't
running, the button just stays hidden. It doesn't require one specific
model — it auto-picks from whatever you've already pulled locally
(preferring a small instruct model like `qwen`/`phi3`/`gemma2` if
present, otherwise whatever's installed).

To enable it:

**Desktop (macOS/Linux):**
```bash
# Install Ollama (https://ollama.com/download), then pull a small model:
ollama pull qwen2.5:3b-instruct    # or any small instruct model you prefer
ollama serve                        # if not already running as a background service
```

**Android (via Termux, no root needed):** install [Termux](https://f-droid.org/en/packages/com.termux/)
from F-Droid (not Play Store — that build is outdated), then either:

- **Single-paste command** — open Termux and paste this whole line, then
  press Enter. It installs Ollama, starts the server, and pulls a small
  model in one go (the app's Chat tab shows this exact command too, so
  you can copy it straight from the phone):
  ```bash
  pkg update -y && pkg upgrade -y && pkg install -y wget termux-api proot && termux-wake-lock && wget -O ollama-linux-arm64.tgz https://ollama.com/download/ollama-linux-arm64.tgz && tar -C $PREFIX -xzf ollama-linux-arm64.tgz && rm ollama-linux-arm64.tgz && nohup ollama serve > $HOME/ollama.log 2>&1 & sleep 3 && (ollama pull qwen2.5:3b-instruct || ollama pull qwen:2b) && curl -sf http://localhost:11434/api/tags && echo '' && echo 'Ollama is reachable.'
  ```
- **Or run the script** — `scripts/setup_ollama_termux.sh` does the same
  thing, with more comments/output if you want to see each step.

Either way, Termux must keep running in the background afterward
(Android Settings > Apps > Termux > Battery > disable optimization), and
the app's Chat tab picks it up automatically — no app-side configuration
needed, since Termux and the app share the phone's network stack and both
reach `localhost:11434`. For Ollama to survive a reboot, install
[Termux:Boot](https://f-droid.org/packages/com.termux.boot/) and copy
`scripts/termux_boot_ollama.sh` to `~/.termux/boot/`.

### Testing "Explain this" on macOS

1. Make sure Ollama is running (`Ollama.app`, or `ollama serve` in a
   terminal) with at least one small model pulled (see above).
2. From the venv, run the app: `flet run main.py`.
3. Go to **Watchlist** or run a **Screener** scan, then click any row to
   open the detail dialog.
4. An **"Explain this"** button (sparkle icon) appears near the bottom of
   the dialog — it only shows up when `llm_summary.is_ollama_available()`
   returns true.
5. Click it: you should see a brief loading spinner, then a 1-3 sentence
   plain-English summary plus the disclaimer text underneath.

Worth spot-checking while testing:
- A **Neutral** result (no flags) — the summary should not invent a
  signal that isn't there.
- That the UI stays responsive (you can still interact with the dialog)
  while the summary is loading, since the call runs off the UI thread.
- With Ollama stopped, the button should simply not appear, with no
  crash or delay elsewhere in the app.

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

Your watchlist is saved locally at `~/.stock_analysis_tool/watchlist.json`,
and general Chat tab conversations are saved locally at
`~/.stock_analysis_tool/chat_sessions.json`. Nothing is sent anywhere
except requests to Yahoo Finance for quotes and, if enabled, your local
Ollama instance for chat — no cloud sync, no telemetry, no accounts.

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
llm_summary.py        Optional "Explain this" local LLM summary (Ollama)
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
