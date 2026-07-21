"""Local and authenticated generative summarization adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from urllib.request import Request, urlopen


class SummarizationError(RuntimeError):
    pass


class Summarizer(Protocol):
    def summarize(self, *, title: str, content: str, max_characters: int) -> str: ...


@dataclass(frozen=True, slots=True)
class RewrittenBrief:
    title: str
    summary: str


@dataclass(frozen=True, slots=True)
class OllamaStatus:
    available: bool
    message: str


def check_ollama(endpoint: str, model: str, timeout_seconds: float = 5) -> OllamaStatus:
    request = Request(f"{endpoint.rstrip('/')}/api/tags", method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            document = json.loads(response.read())
        models = document.get("models", []) if isinstance(document, dict) else []
        names = {
            str(item.get("name", ""))
            for item in models
            if isinstance(item, dict)
        }
    except Exception as error:
        return OllamaStatus(False, f"Ollama is unavailable: {error}")
    if model not in names:
        return OllamaStatus(False, f"Ollama is running, but model '{model}' is not installed.")
    return OllamaStatus(True, f"Ollama is ready with model '{model}'.")


def build_prompt(
    *,
    title: str,
    content: str,
    max_characters: int,
    audience: str = "security operations staff",
    instructions: str = "",
) -> str:
    return (
        f"Summarize the following cyber-intelligence item for {audience}. "
        f"Use plain text, no heading, no speculation, and at most {max_characters} characters. "
        "Preserve affected products, exploitation status, impact, and required action when "
        f"present. {instructions.strip()}\n\n"
        f"Title: {title}\nContent: {content}"
    )


@dataclass(frozen=True, slots=True)
class OllamaSummarizer:
    model: str
    endpoint: str = "http://127.0.0.1:11434"
    timeout_seconds: float = 60
    audience: str = "security operations staff"
    instructions: str = ""

    def summarize(self, *, title: str, content: str, max_characters: int) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": build_prompt(
                    title=title,
                    content=content,
                    max_characters=max_characters,
                    audience=self.audience,
                    instructions=self.instructions,
                ),
                "stream": False,
                "options": {"temperature": 0.1},
            }
        ).encode()
        request = Request(
            f"{self.endpoint.rstrip('/')}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                document = json.loads(response.read())
        except Exception as error:
            raise SummarizationError(f"local model request failed: {error}") from error
        result = document.get("response") if isinstance(document, dict) else None
        if not isinstance(result, str) or not result.strip():
            raise SummarizationError("local model returned an empty response")
        return result.strip()[:max_characters]

    def rewrite_brief(self, *, title: str, content: str) -> RewrittenBrief:
        prompt = (
            f"Rewrite this cyber-intelligence item for {self.audience}. "
            "Return JSON with exactly two strings: title and summary. The title must be a "
            "plain, factual headline of at most 12 words. The summary must be one high-level "
            "sentence of at most 35 words. Avoid hype, jargon, headings, and speculation. "
            "Preserve the affected product and required action when known. "
            f"{self.instructions.strip()}\n\n"
            f"Source title: {title}\nSource text: {content}"
        )
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.1},
            }
        ).encode()
        request = Request(
            f"{self.endpoint.rstrip('/')}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                envelope = json.loads(response.read())
            result = json.loads(envelope["response"])
            rewritten_title = result["title"].strip()
            rewritten_summary = result["summary"].strip()
        except Exception as error:
            raise SummarizationError(f"local model rewrite failed: {error}") from error
        if not rewritten_title or not rewritten_summary:
            raise SummarizationError("local model returned an incomplete rewrite")
        return RewrittenBrief(title=rewritten_title[:120], summary=rewritten_summary[:300])
