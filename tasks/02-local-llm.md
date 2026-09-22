# Phase 3 — Minimal local OSS LLM summarizer

Goal: add an opt-in "Explain this" feature that turns an already-computed
`ScreenResult`/`Quote` into a plain-English summary, using a small local
model via Ollama. It must only summarize existing rule output — never
invent new signals — to stay consistent with the app's "no opaque AI score"
philosophy stated in `README.md`.

## Local model setup

Both desktop and mobile talk to a local Ollama instance over loopback
(`localhost:11434`) — no external network calls happen at runtime. The only
steps requiring internet are one-time setup (installing the runtime and
pulling the model weights).

- [x] **Desktop (Mac)**: install Ollama, pull a small instruct model —
      confirmed with `qwen2.5:3b-instruct` (1.9 GB); model-picking is
      auto-detected/size-aware (see `llm_summary.pick_model()`) rather than
      one hardcoded tag, so any small model works
- [ ] **Mobile (Pixel 10)**: install Termux (F-Droid/GitHub, not Play
      Store), then run `scripts/setup_ollama_termux.sh` on-device (installs
      Ollama's Linux ARM64 binary, takes a wake lock, starts `ollama serve`,
      pulls a small instruct model) — **written but not yet run/validated
      on the actual Pixel 10**
- [ ] Set up `termux-wake-lock` so Android doesn't kill the Ollama process
      mid-session (done by the setup script above); install Termux:Boot
      and copy `scripts/termux_boot_ollama.sh` to `~/.termux/boot/` so
      Ollama restarts after a reboot — **not yet done on-device**
- [x] Document both setup paths in `README.md` as an optional dependency
      (app must work fully without it) — desktop path documented; mobile
      Termux path still pending manual validation on the Pixel 10

## Integration module

- [x] Add `llm_summary.py` with a function like
      `summarize(quote: Quote, snap: TechnicalSnapshot, result: ScreenResult) -> str | None`
      — implemented as `summarize(quote, snap, category, ...)`
- [x] Call Ollama's local HTTP API (`http://localhost:11434/api/generate` or
      `/api/chat`) with a prompt built strictly from already-computed fields
      (price, RSI, SMAs, trend, flags, category) — no external data lookups
- [x] Constrain the prompt so the model explains the *existing* flags/category
      in plain language, not generate new conclusions
- [x] Return `None` (or a clear "unavailable" string) if Ollama isn't
      installed/running, with no crash or blocking delay

## UI integration

- [x] Add an "Explain this" button/action in the detail view dialog in
      `main.py`
- [x] Run the summarization call off the UI thread (reuse the existing
      background-fetch pattern) so it doesn't freeze the app
- [x] Show a lightweight loading state while the model responds
- [x] Gracefully hide/disable the button if Ollama isn't reachable
      (quick health check against `localhost:11434`)

## Safety / scope guardrails

- [x] Add a fixed disclaimer near the summary output reiterating it's a
      restatement of rule-based output, not investment advice
- [x] Add a basic test/check that the prompt template only references fields
      already present on `Quote`/`TechnicalSnapshot`/`ScreenResult` (no
      accidental new "predictions") — `tests/test_llm_summary.py`

## Validation

- [x] Manually test summaries for a Value Candidate, a Momentum/Overbought,
      a Golden Cross, and a Neutral result — confirm each summary accurately
      reflects (and doesn't contradict) the underlying flags — tested on
      macOS with `qwen2.5:3b-instruct`: AAPL (Value Candidate, 2.2s), MSFT
      (Momentum/Overbought, 1.0s), JNJ (Neutral, 1.2s) — all correct, no
      invented signals. Golden Cross case not yet separately spot-checked
      (Momentum case did include a "Golden Cross" flag and was described
      correctly)
- [x] Confirm app works normally with Ollama stopped (feature just disabled)
      — validated via unit tests hitting an unreachable host
      (`test_summarize_returns_none_when_ollama_unreachable`,
      `test_is_ollama_available_false_when_unreachable`); didn't force-quit
      the real Ollama.app on this machine since it's the user's normal
      running instance
- [x] Confirm no network calls are made for this feature (fully local) —
      `llm_summary.py` only ever calls `OLLAMA_HOST` (localhost:11434),
      no other network code path exists in the module

## Extension: chat interfaces (beyond original scope)

The original design above was a one-shot "Explain this" restatement.
Two chat-style extensions were added on top of it:

- [x] **Per-stock chat** — the detail dialog's "Explain this" now opens a
      real chat transcript (`llm_summary.chat_reply`, Ollama `/api/chat`),
      re-injecting that stock's data as a system message on every turn so
      a longer conversation can't drift the model into inventing new
      facts. Verified it correctly declines out-of-scope questions (e.g.
      "what's the latest news on Apple?") instead of guessing.
- [x] **General market chat tab** — a new top-level "Chat" nav item for
      stock-market/investing discussion not tied to a specific loaded
      stock (`llm_summary.general_chat_reply`). Unlike the above, this
      one is allowed to use the model's general knowledge (explaining
      concepts like RSI, golden cross, etc.), restricted only by topic —
      it correctly declined a live-price question, but **did not reliably
      refuse an off-topic request** (asked to write a poem, it just wrote
      one instead of declining) — a known limitation of small (~3B)
      instruction-following models, accepted as-is rather than adding a
      keyword pre-filter or switching to a larger/slower model for this
      tab. The important guarantee (no fabricated stock data/prices)
      still held in testing.
- [x] **Chat history + new chat** — the general Chat tab now persists
      conversations as named sessions (`storage.load_chat_sessions` /
      `save_chat_sessions`, `~/.stock_analysis_tool/chat_sessions.json`),
      shown in a left-hand history panel with a "+ New chat" button and a
      delete action per session. Session title auto-derives from the
      first user message. Only the general Chat tab has history; the
      per-stock "Explain this" dialog chat is intentionally still
      ephemeral (scoped to one stock's detail dialog session).
