import dataclasses
import re

from analysis import TechnicalSnapshot
from data_provider import Quote
import llm_summary

ALLOWED_FIELDS = {f.name for f in dataclasses.fields(Quote)} | \
    {f.name for f in dataclasses.fields(TechnicalSnapshot)} | {"category"}


def test_prompt_only_references_existing_fields():
    """Guardrail: the prompt template must only reference attributes that
    actually exist on Quote/TechnicalSnapshot (plus the screener category
    string), so the feature can't silently start asking about a field
    that was never computed.
    """
    q = Quote(ticker="AAPL", name="Apple Inc.", price=150.0, pe_ratio=28.0)
    snap = TechnicalSnapshot(sma20=148, sma50=145, sma200=140, rsi14=55,
                              range_position=0.6, volume_ratio=1.2,
                              trend="Uptrend (50>200)", flags=["Volume Spike"])
    prompt = llm_summary._build_prompt(q, snap, "Neutral")

    for line in prompt.splitlines():
        label = line.split(":", 1)[0].strip()
        assert label, f"unlabeled line in prompt: {line!r}"

    referenced_values = {
        str(q.price), str(q.pe_ratio), str(snap.rsi14), str(snap.trend),
        "AAPL", "Neutral",
    }
    for value in referenced_values:
        assert value in prompt


def test_summarize_returns_none_when_ollama_unreachable():
    q = Quote(ticker="AAPL", price=150.0)
    snap = TechnicalSnapshot()
    result = llm_summary.summarize(q, snap, "Neutral", host="http://localhost:1")
    assert result is None


def test_is_ollama_available_false_when_unreachable():
    assert llm_summary.is_ollama_available(host="http://localhost:1") is False


def test_pick_model_none_when_unreachable():
    assert llm_summary.pick_model(host="http://localhost:1") is None


def test_pick_model_prefers_known_substrings():
    import unittest.mock as mock

    with mock.patch.object(llm_summary, "list_installed_models", return_value=[
        {"name": "llava:7b", "size": 4_000_000_000},
        {"name": "phi3:3.8b", "size": 2_000_000_000},
        {"name": "mistral:7b", "size": 4_000_000_000},
    ]):
        assert llm_summary.pick_model() == "phi3:3.8b"


def test_pick_model_prefers_smaller_among_preferred_matches():
    import unittest.mock as mock

    with mock.patch.object(llm_summary, "list_installed_models", return_value=[
        {"name": "qwen3.5:35b-mlx", "size": 21_909_268_118},
        {"name": "qwen2.5:3b-instruct", "size": 2_000_000_000},
    ]):
        assert llm_summary.pick_model() == "qwen2.5:3b-instruct"


def test_pick_model_falls_back_to_smallest_installed():
    import unittest.mock as mock

    with mock.patch.object(llm_summary, "list_installed_models", return_value=[
        {"name": "mistral:7b", "size": 5_000_000_000},
        {"name": "llava:7b", "size": 3_000_000_000},
    ]):
        assert llm_summary.pick_model() == "llava:7b"


def test_chat_reply_returns_none_when_ollama_unreachable():
    q = Quote(ticker="AAPL", price=150.0)
    snap = TechnicalSnapshot()
    history = [{"role": "user", "content": "What's the RSI?"}]
    result = llm_summary.chat_reply(history, q, snap, "Neutral", host="http://localhost:1")
    assert result is None


def test_chat_reply_grounds_only_in_existing_fields():
    """Guardrail: the chat system message must only reference existing
    Quote/TechnicalSnapshot fields plus the category, same as the
    one-shot summarizer — a longer conversation must not be able to drift
    the model into inventing new facts about the stock.
    """
    q = Quote(ticker="AAPL", name="Apple Inc.", price=150.0, pe_ratio=28.0)
    snap = TechnicalSnapshot(rsi14=55, trend="Neutral", flags=[])
    context = llm_summary._build_prompt(q, snap, "Neutral")
    system = llm_summary.SYSTEM_PROMPT + llm_summary.CHAT_SYSTEM_PROMPT_SUFFIX + \
        "\n\nData for this stock:\n" + context
    assert "AAPL" in system
    assert "don't have that information" in system.lower() or \
        "do not have that information" in system.lower() or \
        "you don't have that information" in system.lower()


def test_general_chat_reply_returns_none_when_ollama_unreachable():
    history = [{"role": "user", "content": "What does RSI mean?"}]
    result = llm_summary.general_chat_reply(history, host="http://localhost:1")
    assert result is None


def test_general_chat_system_prompt_declines_off_topic_and_live_data():
    """Guardrail: unlike the per-stock chat, this one may use general
    knowledge, but it must still refuse live prices/news/portfolio
    questions (it has none) and steer off-topic questions back to
    stock market/finance topics.
    """
    prompt = llm_summary.GENERAL_CHAT_SYSTEM_PROMPT.lower()
    assert "live" in prompt or "today's news" in prompt
    assert "decline" in prompt or "steer" in prompt
    assert "buy/sell advice" in prompt or "buy or sell" in prompt or "personalized" in prompt
