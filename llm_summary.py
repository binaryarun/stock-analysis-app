"""
llm_summary.py
Optional "Explain this" feature: turns an already-computed Quote +
TechnicalSnapshot + screener category into a plain-English paragraph,
using a small local model served by Ollama (http://localhost:11434).

This module never calls out to the network beyond loopback, and the
prompt is built strictly from fields the app already computed (price,
RSI, SMAs, trend, flags, category) — it restates existing rule output,
it does not ask the model to invent new signals. If Ollama isn't
installed/running, every function here degrades to returning None /
False rather than raising, so the rest of the app works normally with
the feature simply hidden.
"""

from __future__ import annotations

import os

import requests

from analysis import TechnicalSnapshot
from data_provider import Quote

OLLAMA_HOST = "http://localhost:11434"

_ON_ANDROID = "ANDROID_ARGUMENT" in os.environ or "ANDROID_DATA" in os.environ

# "localhost" on Android is the phone itself, so the desktop install
# instructions (below) don't apply - Ollama has to actually run somewhere
# reachable at that address. The most self-contained option is Termux
# (no root needed): it shares the phone's network stack, so an `ollama
# serve` started there is reachable at localhost:11434 from this app too.
UNAVAILABLE_MESSAGE_DESKTOP = (
    "Local LLM chat isn't available right now — Ollama doesn't seem to be "
    "running. Install it from ollama.com, pull a small model "
    "(e.g. `ollama pull qwen2.5:3b-instruct`), and make sure it's running, "
    "then reopen this tab."
)

TERMUX_ONE_LINER = (
    "pkg update -y && pkg upgrade -y && "
    "pkg install -y wget termux-api proot && termux-wake-lock && "
    "wget -O ollama-linux-arm64.tgz "
    "https://ollama.com/download/ollama-linux-arm64.tgz && "
    "tar -C $PREFIX -xzf ollama-linux-arm64.tgz && "
    "rm ollama-linux-arm64.tgz && "
    "OLLAMA_KEEP_ALIVE=30m nohup ollama serve > $HOME/ollama.log 2>&1 & "
    "sleep 3 && "
    "(ollama pull qwen2.5:1.5b-instruct || ollama pull qwen:1.8b) && "
    "curl -sf http://localhost:11434/api/tags && "
    "echo '' && echo 'Ollama is reachable.'"
)

UNAVAILABLE_MESSAGE_ANDROID = (
    "Local LLM chat isn't available right now — Ollama doesn't seem to be "
    "running. On Android, this app can't reach an Ollama server running on "
    "another machine unless the app is reconfigured for that; the "
    "self-contained option is to run Ollama on this phone via Termux "
    "(no root needed). See the \"LLM Setup\" tab for step-by-step, "
    "copyable commands."
)


def unavailable_message() -> str:
    return UNAVAILABLE_MESSAGE_ANDROID if _ON_ANDROID else UNAVAILABLE_MESSAGE_DESKTOP


def is_android() -> bool:
    return _ON_ANDROID


# Short "run it / check it" command list for the Chat tab's own status panel,
# for desktop (a normal shell, not Termux — no wake-lock needed, and desktops
# generally have enough RAM that the 3B model is fine).
DESKTOP_QUICK_COMMANDS: list[dict] = [
    {
        "title": "Start (or restart) the server",
        "command": "ollama serve",
    },
    {
        "title": "Verify it's reachable",
        "command": "curl -sf http://localhost:11434/api/tags",
    },
    {
        "title": "Check qwen is pulled",
        "command": "ollama list",
    },
    {
        "title": "Pull qwen if it's missing",
        "command": "ollama pull qwen2.5:3b-instruct",
    },
]

# Same idea, but for Termux on Android (as opposed to TERMUX_SETUP_STEPS
# below, which is the full first-time install walkthrough on its own
# "LLM Setup" tab). These assume Termux and Ollama are already installed -
# they're for the day-to-day "is it up, and if not, how do I bring qwen
# back up" loop. Phones have much less free RAM than a desktop, so this
# defaults to a 1.5B model rather than the 3B one used above.
ANDROID_QUICK_COMMANDS: list[dict] = [
    {
        "title": "Restart the server with a longer keep-alive",
        "command": "pkill ollama; OLLAMA_KEEP_ALIVE=30m nohup ollama serve "
                    "> $HOME/ollama.log 2>&1 &",
        "detail": "By default Ollama unloads the model after 5 minutes idle, "
                  "so every gap between messages forces a slow reload from "
                  "disk. This restarts it with a 30-minute keep-alive so it "
                  "stays warm between chats. Run this once after any Termux/"
                  "phone restart.",
    },
    {
        "title": "Verify it's reachable",
        "command": "curl -sf http://localhost:11434/api/tags",
        "detail": "This only confirms the server process is up, not that a "
                  "model can actually load — see the note below.",
    },
    {
        "title": "Check qwen is pulled",
        "command": "ollama list",
    },
    {
        "title": "Pull a small model that fits phone RAM",
        "command": "ollama pull qwen2.5:1.5b-instruct || ollama pull qwen:1.8b",
    },
    {
        "title": "Free RAM: remove the 3B model if you pulled it earlier",
        "command": "ollama rm qwen2.5:3b-instruct",
        "detail": "A 3B model needs ~2-3GB free RAM to load. On a phone that's "
                   "already low on memory, Ollama's health check can still say "
                   "\"running\" while the model itself silently fails to load "
                   "for each chat request — this is the fix for that.",
    },
    {
        "title": "Keep the server alive in the background",
        "command": "termux-wake-lock",
    },
]

# Shown as a standing note in the Chat tab (not tied to any one command),
# so the "is it stuck or just slow" question has an answer before someone
# gives up and reports it as broken.
ANDROID_CHAT_TIMING_NOTE = (
    "First message after Ollama starts (or after ~5 minutes idle without "
    "the keep-alive command above) can take a couple of minutes while the "
    "model loads from disk — this is normal on phone CPUs with no GPU "
    "offload. After that, replies should come back much faster while the "
    "model stays warm."
)


def quick_commands() -> list[dict]:
    """Quick-command list for the Chat tab's status panel, for whichever
    platform the app is actually running on right now."""
    return ANDROID_QUICK_COMMANDS if _ON_ANDROID else DESKTOP_QUICK_COMMANDS


# Step-by-step Termux setup, broken into individually-copyable commands for
# the app's "LLM Setup" tab, rather than one long one-liner (TERMUX_ONE_LINER
# above still exists for anyone who wants to paste it all at once).
# Each step is {"title": ..., "detail": optional extra text, "command": optional str}.
TERMUX_SETUP_STEPS: list[dict] = [
    {
        "title": "1. Install Termux",
        "detail": "From F-Droid, not the Play Store — that build is outdated "
                   "and can't install newer packages: "
                   "f-droid.org/en/packages/com.termux",
    },
    {
        "title": "2. Update packages",
        "command": "pkg update -y && pkg upgrade -y",
    },
    {
        "title": "3. Install prerequisites",
        "command": "pkg install -y wget termux-api proot",
    },
    {
        "title": "4. Keep the CPU awake while Ollama runs",
        "command": "termux-wake-lock",
    },
    {
        "title": "5. Download Ollama",
        "command": "wget -O ollama-linux-arm64.tgz "
                    "https://ollama.com/download/ollama-linux-arm64.tgz",
    },
    {
        "title": "6. Install it",
        "command": "tar -C $PREFIX -xzf ollama-linux-arm64.tgz && "
                    "rm ollama-linux-arm64.tgz",
    },
    {
        "title": "7. Start the server",
        "command": "OLLAMA_KEEP_ALIVE=30m nohup ollama serve > $HOME/ollama.log 2>&1 &",
        "detail": "OLLAMA_KEEP_ALIVE keeps a loaded model resident for 30 "
                  "minutes instead of the 5-minute default, so it doesn't "
                  "cold-reload from disk between every chat message.",
    },
    {
        "title": "8. Pull a small model",
        "command": "ollama pull qwen2.5:1.5b-instruct || ollama pull qwen:1.8b",
        "detail": "1.5B, not 3B — phones typically don't have the 2-3GB free "
                  "RAM a 3B model needs to actually load, even though Ollama's "
                  "own health check will still report \"running\" either way. "
                  "The first message after this server starts can still take "
                  "a couple of minutes while the model loads from disk — "
                  "that's normal on a phone CPU, not stuck.",
    },
    {
        "title": "9. Verify it's reachable",
        "command": "curl -sf http://localhost:11434/api/tags",
        "detail": "Should print JSON with your model listed. If this "
                   "succeeds, reopen the Chat tab in the app.",
    },
    {
        "title": "10. Keep Termux alive in the background",
        "detail": "Android Settings > Apps > Termux > Battery > "
                   "Unrestricted (disable battery optimization). On some "
                   "phones (Samsung, Xiaomi, OnePlus) also whitelist Termux "
                   "in the manufacturer's own battery/auto-start settings.",
    },
    {
        "title": "11. Survive a phone reboot (optional)",
        "detail": "Install Termux:Boot from F-Droid, open it once, then run "
                   "this to register a startup script:",
        "command": "mkdir -p ~/.termux/boot && cat > ~/.termux/boot/ollama.sh "
                    "<<'EOF'\ntermux-wake-lock\nnohup ollama serve > "
                    "\"$HOME/ollama.log\" 2>&1 &\nEOF\nchmod +x "
                    "~/.termux/boot/ollama.sh",
    },
]
# Ordered by preference: the first installed model whose name contains one
# of these substrings is used. Falls back to whatever else is installed if
# none of these match, so we don't have to hardcode one exact model/tag
# that the user must have pulled under that exact name.
PREFERRED_MODEL_SUBSTRINGS = ("qwen", "phi3", "phi-3", "llama3.2", "gemma2")
HEALTH_TIMEOUT = 3
LIST_MODELS_TIMEOUT = 2
# CPU-only inference on a phone (no GPU offload) can take a couple of
# minutes for even a small model, especially cold-start / under memory
# pressure - a short timeout here just makes a working setup look "down".
# Desktops have real CPU/GPU headroom, so keep those calls snappier.
GENERATE_TIMEOUT = 240 if _ON_ANDROID else 60

DISCLAIMER = (
    "This is a plain-language restatement of the rule-based numbers above, "
    "generated by a local model — not investment advice."
)

SYSTEM_PROMPT = (
    "You explain stock screener output in plain English for a personal "
    "research tool. You must ONLY restate and explain the numbers and "
    "flags given to you below — never invent a new fact, new number, "
    "trend, opinion, or recommendation that isn't already present in "
    "the input. Do not tell the user to buy or sell. Keep it to 2-4 "
    "short sentences."
)

CHAT_SYSTEM_PROMPT_SUFFIX = (
    "\n\nThe user may ask follow-up questions about this stock. Answer "
    "ONLY using the data given above — never look up or guess at news, "
    "other companies, future prices, or anything not present in this "
    "data. If a question asks for something not covered by this data, "
    "say plainly that you don't have that information, rather than "
    "guessing or inventing an answer. Never give buy/sell advice."
)

GENERAL_CHAT_DISCLAIMER = (
    "General market/finance discussion from a local model — not "
    "investment advice, and not aware of your specific portfolio or "
    "today's live prices/news."
)

GENERAL_CHAT_SYSTEM_PROMPT = (
    "You are a knowledgeable assistant discussing the stock market and "
    "investing in general for a personal research tool — things like "
    "financial terminology, technical indicators (RSI, moving averages, "
    "golden/death cross, P/E ratio, etc.), how markets and order types "
    "work, historical/general market concepts, and how to think about "
    "screening or evaluating stocks. You do NOT have access to live "
    "prices, today's news, or the user's own portfolio/watchlist — if "
    "asked about a specific current price, quote, or breaking news, say "
    "you don't have live data and that the app's Watchlist/Screener "
    "views are the place for that. Never give personalized buy/sell "
    "advice or tell the user what to do with their money — explain "
    "concepts and general reasoning only. If the user asks about "
    "something unrelated to stocks, investing, or markets, politely "
    "decline and steer back to market/finance topics."
)


def _chat_completion(messages: list[dict], host: str, model: str | None) -> str | None:
    if model is None:
        model = pick_model(host)
        if model is None:
            return None
    try:
        resp = requests.post(
            f"{host}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
            timeout=GENERATE_TIMEOUT,
        )
        resp.raise_for_status()
        text = resp.json().get("message", {}).get("content", "").strip()
        return text or None
    except requests.RequestException:
        return None


def is_ollama_available(host: str = OLLAMA_HOST) -> bool:
    """Quick health check so the UI can hide the feature when Ollama isn't
    reachable, with no blocking delay.
    """
    try:
        resp = requests.get(f"{host}/api/tags", timeout=HEALTH_TIMEOUT)
        return resp.ok
    except requests.RequestException:
        return False


def list_installed_models(host: str = OLLAMA_HOST) -> list[dict]:
    """Models already pulled into the local Ollama instance, as
    {"name": ..., "size": <bytes>} dicts. Returns an empty list if Ollama
    is unreachable or has nothing pulled.
    """
    try:
        resp = requests.get(f"{host}/api/tags", timeout=LIST_MODELS_TIMEOUT)
        resp.raise_for_status()
        return [
            {"name": m["name"], "size": m.get("size") or 0}
            for m in resp.json().get("models", [])
            if m.get("name")
        ]
    except requests.RequestException:
        return []


def pick_model(host: str = OLLAMA_HOST) -> str | None:
    """Pick a model to use from whatever's already installed locally,
    instead of assuming one fixed model name was pulled. Prefers a small
    instruct-style model (see PREFERRED_MODEL_SUBSTRINGS), and among
    matches (or, failing any match, among all installed models) picks the
    smallest by size — this feature favors a fast response over a
    marginally better one. Returns None if nothing is installed / Ollama
    is unreachable.
    """
    installed = list_installed_models(host)
    if not installed:
        return None

    matches = [m for m in installed
               if any(substr in m["name"].lower() for substr in PREFERRED_MODEL_SUBSTRINGS)]
    candidates = matches or installed
    return min(candidates, key=lambda m: m["size"])["name"]


def _build_prompt(quote: Quote, snap: TechnicalSnapshot, category: str) -> str:
    """Build a prompt referencing only fields already present on
    Quote/TechnicalSnapshot/the screener category — no external lookups.
    """
    lines = [
        f"Ticker: {quote.ticker} ({quote.name or quote.ticker})",
        f"Price: {quote.price}",
        f"P/E ratio: {quote.pe_ratio}",
        f"RSI (14): {snap.rsi14}",
        f"SMA20 / SMA50 / SMA200: {snap.sma20} / {snap.sma50} / {snap.sma200}",
        f"Trend: {snap.trend}",
        f"52-week range position (0=low, 1=high): {snap.range_position}",
        f"Volume ratio (volume / avg volume): {snap.volume_ratio}",
        f"Flags: {', '.join(snap.flags) if snap.flags else 'None'}",
        f"Screener category: {category}",
    ]
    return "\n".join(lines)


def summarize(quote: Quote, snap: TechnicalSnapshot, category: str,
              host: str = OLLAMA_HOST, model: str | None = None) -> str | None:
    """Ask a local Ollama model to explain the given screener output in
    plain language. If `model` isn't given, auto-picks from whatever's
    already installed (see `pick_model`). Returns None if Ollama isn't
    reachable, nothing is installed, or the request fails for any
    reason — callers should treat that as "unavailable", not an error.
    """
    if model is None:
        model = pick_model(host)
        if model is None:
            return None

    prompt = _build_prompt(quote, snap, category)
    try:
        resp = requests.post(
            f"{host}/api/generate",
            json={
                "model": model,
                "system": SYSTEM_PROMPT,
                "prompt": prompt,
                "stream": False,
            },
            timeout=GENERATE_TIMEOUT,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        return text or None
    except requests.RequestException:
        return None


def chat_reply(history: list[dict], quote: Quote, snap: TechnicalSnapshot, category: str,
                host: str = OLLAMA_HOST, model: str | None = None) -> str | None:
    """Continue a chat about this stock. `history` is a list of
    {"role": "user"|"assistant", "content": str} turns, ending with the
    latest user message. The stock's data is (re)injected as a system
    message on every call so the model can't drift into inventing facts
    partway through a longer conversation. Returns None on any failure
    (Ollama unreachable, nothing installed, request error) — callers
    should treat that as "unavailable".
    """
    system = SYSTEM_PROMPT + CHAT_SYSTEM_PROMPT_SUFFIX + \
        "\n\nData for this stock:\n" + _build_prompt(quote, snap, category)
    messages = [{"role": "system", "content": system}] + history
    return _chat_completion(messages, host, model)


def general_chat_reply(history: list[dict], host: str = OLLAMA_HOST,
                        model: str | None = None) -> str | None:
    """Continue a general stock-market/investing discussion, not tied to
    any specific loaded stock. `history` is a list of
    {"role": "user"|"assistant", "content": str} turns, ending with the
    latest user message. Grounded only by topic (stock market/investing
    concepts) via the system prompt — the model may use its own general
    knowledge here, unlike `summarize`/`chat_reply` which are restricted
    to restating already-computed app data. Returns None on any failure
    (Ollama unreachable, nothing installed, request error).
    """
    messages = [{"role": "system", "content": GENERAL_CHAT_SYSTEM_PROMPT}] + history
    return _chat_completion(messages, host, model)
