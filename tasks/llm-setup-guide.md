# ADR-001: On-Device OSS LLM for the Stock Analysis App

**Status:** Proposed
**Date:** 2026-06-28
**Deciders:** ak (app owner)

## Context

The app (Flet, Watchlist + Screener + Macro) is built on a strict
"numbers only, transparent rules, no news/sentiment, no opaque AI score"
philosophy, and is meant to run from one Python codebase on Linux desktop
today (`flet build linux`) and on Android/iOS later (`flet build apk` /
`flet build ipa`).

The request is to add an open-source LLM that:
1. **Explains results in plain language** — turns the existing rule-based
   screener category, technical snapshot (RSI, SMA, golden/death cross),
   and macro tailwind/headwind notes into a readable paragraph per stock,
   strictly narrating numbers the app already computed (not adding news or
   opinion the app doesn't already have).
2. **Answers follow-up questions** in a chat box, grounded only in the
   user's own watchlist/screener/macro data already in memory.
3. **Runs fully on-device** — no API key, no server, no telemetry, working
   offline on both desktop and mobile, consistent with the app's existing
   local-only storage model.

The constraint that most shapes this decision: Flet's mobile build does
**not** ship a generic CPython — it embeds Python via the `serious_python`
Flutter package, which has real limits on which C-extension wheels it can
load on Android/iOS. Most "on-device LLM in Python" tooling
(`llama-cpp-python`, `onnxruntime`, `transformers`+`torch`) is a C/C++
extension under the hood. What runs cleanly on desktop Python is not
guaranteed to run inside the mobile build at all. This is the central risk
this ADR has to address, not just "which model."

## Decision

**Ship on-device inference desktop-first via `llama-cpp-python` + a small
GGUF instruct model, behind a thin internal interface, and treat mobile
on-device inference as an explicitly unproven Phase 2 — validated by a
spike before any UI work targets it.** Until that spike passes, the mobile
build simply omits the LLM features and shows the same numbers-only
Watchlist/Screener/Macro views it does today (graceful degradation, not a
broken feature).

This avoids the trap of designing the whole feature around an assumption
("mobile on-device LLM will just work because desktop did") that's the
single biggest unknown in the request.

## Options Considered

### Option A: `llama-cpp-python` + GGUF model (desktop-first, mobile = Phase 2 spike)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low-Medium — one well-documented Python package, no server |
| Cost | None (one-time model download, no API fees) |
| Scalability | N/A (single-user local app) |
| Team familiarity | High — pure Python integration, same pattern as `yfinance` |
| Mobile viability | **Unproven** — needs a spike against `serious_python` |

**Pros:** simplest desktop implementation; matches the app's existing
"thin wrapper module" pattern (`data_provider.py`-style); fully offline;
no new infra.
**Cons:** mobile support is genuinely uncertain until tested; if the spike
fails, mobile ships without LLM features (acceptable, but worth flagging
now rather than discovering it late).

### Option B: Native Flutter LLM plugin bridge (e.g. `fllama`, `flutter_gemma`) for parity

| Dimension | Assessment |
|-----------|------------|
| Complexity | High — requires Dart/Flutter-side code, breaks "one Python codebase" |
| Cost | None |
| Scalability | N/A |
| Team familiarity | Low — outside the Python/Flet surface entirely |
| Mobile viability | Higher confidence (these plugins are built specifically for Flutter mobile) |

**Pros:** most likely path to a real on-device LLM on phones today.
**Cons:** gives up the "same codebase, no platform code" reason Flet was
chosen in the first place; doubles the integration surface (Python on
desktop, Dart on mobile) for one feature.

### Option C: ONNX Runtime GenAI / pure-Python ONNX model

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium |
| Cost | None |
| Scalability | N/A |
| Team familiarity | Medium |
| Mobile viability | Same underlying problem as Option A — `onnxruntime` is also a native extension; not obviously better-supported under `serious_python` |

**Pros:** ONNX is a more "standard" model format than GGUF.
**Cons:** doesn't actually resolve the mobile-extension risk; adds a
different dependency for no clear benefit over Option A.

### Option D (rejected per stated constraint): Remote OSS model — self-hosted or hosted API

Rejected because the user explicitly wants on-device/local, matching the
app's offline-first, no-telemetry design. Noted here only for completeness:
this would have solved the mobile-runtime problem trivially (any platform
can make an HTTPS call) at the cost of needing a server or API key and
giving up "fully offline."

## Trade-off Analysis

The real decision isn't "which model" — it's **how much of the mobile risk
to absorb now vs. later**. Option A defers that risk behind a cheap spike
and ships real value on desktop immediately. Option B resolves the mobile
risk up front but at a structural cost (a second codebase/language) that
contradicts the reason Flet was picked. Option C doesn't actually reduce
the risk Option A carries, so it has no real advantage.

Given the app already has a "local persistence, no cloud" precedent
(`storage.py`) and a "thin wrapper" precedent (`data_provider.py`), Option
A is the most consistent extension of the existing architecture, and keeps
the door open to Option B later specifically for the mobile target if the
spike fails — without having paid that cost on day one.

## Recommended Models (desktop, Option A)

Default to a small **Apache-2.0 or Llama-license instruct model**, quantized
to GGUF Q4_K_M for a reasonable quality/size/speed balance on a laptop CPU:

- **Qwen2.5-3B-Instruct** (Apache-2.0 — fewest license obligations) — good
  default.
- **Llama-3.2-3B-Instruct** — strong quality, Llama community license
  (acceptable-use terms apply, but no issue for a personal app).
- A **1B-class model** (Qwen2.5-1.5B-Instruct or Llama-3.2-1B) earmarked
  specifically as the mobile candidate if/when the Phase 2 spike succeeds,
  since phone RAM/storage budgets are much tighter than desktop.

Model file adds roughly 1–2 GB to the desktop distributable; recommend
downloading it on first run into `~/.stock_analysis_tool/models/` (same
local-data directory already used by `storage.py`) rather than bundling it
in the installer, so the base app stays small.

## Proposed Internal Interface (design only, not implemented)

A new module, e.g. `llm_provider.py`, sitting alongside `data_provider.py`
and `macro.py`, with two functions the rest of the app would call:

- `summarize(quote, snapshot, screen_result) -> str` — builds a prompt
  strictly from already-computed fields (price, RSI, SMA trend, screener
  category, etc.), not from any new data source, and returns a short
  narrated paragraph.
- `ask(question: str, context_bundle: dict) -> str` — same grounding
  principle, applied to a free-text question; `context_bundle` would be
  the user's current watchlist/screener/macro state, not a web search.

Keeping the LLM behind this interface means: (a) the rest of the UI never
talks to `llama-cpp-python` directly, matching the existing pattern, and
(b) swapping to Option B's native bridge later, if mobile needs it, only
means rewriting this one module's internals, not the UI.

## Consequences

- **Easier:** desktop users get plain-language explanations and a grounded
  chat without any change to the app's privacy/offline posture; the
  feature can ship and be used long before mobile packaging is revisited.
- **Harder:** the distributable grows by ~1-2 GB once the model is
  downloaded; first LLM response will be slow on first load (model
  load time) and noticeably slower than the existing instant rule-based
  output (CPU inference, expect single-digit seconds per response on a
  recent laptop, more on older hardware).
- **To revisit:** mobile on-device support is explicitly unresolved by
  this ADR — it's a follow-up decision gated on the spike result below.

## Action Items

1. [ ] Spike: install `llama-cpp-python` + a small GGUF model on desktop,
   confirm load time and response quality/latency are acceptable.
2. [ ] Spike (mobile risk): attempt a minimal `serious_python` /
   `llama-cpp-python` build for Android; if it fails or isn't feasible in
   a reasonable timeframe, formally close mobile on-device LLM as "not
   supported in Phase 1" and record why.
3. [ ] Pick the default desktop model (recommend starting with
   Qwen2.5-3B-Instruct, Apache-2.0) and confirm its license is acceptable
   for personal use.
4. [ ] Design the exact prompt template for `summarize()` so it only ever
   receives fields the app already computes (no new data sources sneak
   in) — this is what keeps the feature consistent with the app's
   "no news/sentiment" rule.
5. [ ] Decide UI placement: an "Explain" action on the existing Detail
   dialog, plus either a 4th nav tab or a floating panel for free-form
   chat.
6. [ ] Once the above are settled, implement `llm_provider.py` and the UI
   hookup (separate task — no code in this ADR by design).
