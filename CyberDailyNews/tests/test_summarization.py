import io
import json
from typing import Any

import pytest

from ccip.summarization import OllamaSummarizer, SummarizationError, build_prompt


class FakeResponse(io.BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_build_prompt_constrains_security_summary() -> None:
    prompt = build_prompt(title="Issue", content="Details", max_characters=300)

    assert "at most 300 characters" in prompt
    assert "no speculation" in prompt
    assert "Title: Issue" in prompt


def test_ollama_summarizer_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> FakeResponse:
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse(b'{"response":"Actionable summary."}')

    monkeypatch.setattr("ccip.summarization.urlopen", fake_urlopen)
    summarizer = OllamaSummarizer("local-model", timeout_seconds=12)

    result = summarizer.summarize(title="Issue", content="Details", max_characters=200)

    assert result == "Actionable summary."
    assert captured["body"]["model"] == "local-model"
    assert captured["timeout"] == 12


def test_ollama_summarizer_rejects_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ccip.summarization.urlopen",
        lambda request, timeout: FakeResponse(b'{"response":""}'),
    )

    with pytest.raises(SummarizationError, match="empty response"):
        OllamaSummarizer("model").summarize(title="Issue", content="Details", max_characters=200)
