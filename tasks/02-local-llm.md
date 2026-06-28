# Phase 3 — Minimal local OSS LLM summarizer

Goal: add an opt-in "Explain this" feature that turns an already-computed
`ScreenResult`/`Quote` into a plain-English summary, using a small local
model via Ollama. It must only summarize existing rule output — never
invent new signals — to stay consistent with the app's "no opaque AI score"
philosophy stated in `README.md`.

## Local model setup

- [ ] Install Ollama locally and pull a small model (e.g. `llama3.2:3b` or
      `phi3-mini`) — confirm it runs acceptably on the target machine
- [ ] Document the Ollama install/model-pull step in `README.md` as an
      optional dependency (app must work fully without it)

## Integration module

- [ ] Add `llm_summary.py` with a function like
      `summarize(quote: Quote, snap: TechnicalSnapshot, result: ScreenResult) -> str | None`
- [ ] Call Ollama's local HTTP API (`http://localhost:11434/api/generate` or
      `/api/chat`) with a prompt built strictly from already-computed fields
      (price, RSI, SMAs, trend, flags, category) — no external data lookups
- [ ] Constrain the prompt so the model explains the *existing* flags/category
      in plain language, not generate new conclusions
- [ ] Return `None` (or a clear "unavailable" string) if Ollama isn't
      installed/running, with no crash or blocking delay

## UI integration

- [ ] Add an "Explain this" button/action in the detail view dialog in
      `main.py`
- [ ] Run the summarization call off the UI thread (reuse the existing
      background-fetch pattern) so it doesn't freeze the app
- [ ] Show a lightweight loading state while the model responds
- [ ] Gracefully hide/disable the button if Ollama isn't reachable
      (quick health check against `localhost:11434`)

## Safety / scope guardrails

- [ ] Add a fixed disclaimer near the summary output reiterating it's a
      restatement of rule-based output, not investment advice
- [ ] Add a basic test/check that the prompt template only references fields
      already present on `Quote`/`TechnicalSnapshot`/`ScreenResult` (no
      accidental new "predictions")

## Validation

- [ ] Manually test summaries for a Value Candidate, a Momentum/Overbought,
      a Golden Cross, and a Neutral result — confirm each summary accurately
      reflects (and doesn't contradict) the underlying flags
- [ ] Confirm app works normally with Ollama stopped (feature just disabled)
- [ ] Confirm no network calls are made for this feature (fully local)
