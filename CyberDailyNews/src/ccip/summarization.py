"""Local and authenticated generative summarization adapters."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Protocol
from urllib.request import Request, urlopen


class SummarizationError(RuntimeError):
    pass


class Summarizer(Protocol):
    def summarize(self, *, title: str, content: str, max_characters: int) -> str: ...


def build_prompt(*, title: str, content: str, max_characters: int) -> str:
    return (
        "Summarize the following cyber-intelligence item for security operations staff. "
        f"Use plain text, no heading, no speculation, and at most {max_characters} characters. "
        "Preserve affected products, exploitation status, impact, and required action when "
        "present.\n\n"
        f"Title: {title}\nContent: {content}"
    )


@dataclass(frozen=True, slots=True)
class OllamaSummarizer:
    model: str
    endpoint: str = "http://127.0.0.1:11434"
    timeout_seconds: float = 60

    def summarize(self, *, title: str, content: str, max_characters: int) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": build_prompt(
                    title=title,
                    content=content,
                    max_characters=max_characters,
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


@dataclass(frozen=True, slots=True)
class CopilotCLISummarizer:
    model: str
    binary: str = "copilot"
    timeout_seconds: float = 60

    def summarize(self, *, title: str, content: str, max_characters: int) -> str:
        prompt = build_prompt(title=title, content=content, max_characters=max_characters)
        try:
            completed = subprocess.run(  # noqa: S603
                [self.binary, "-p", prompt, "-s", "--no-ask-user", "--model", self.model],
                capture_output=True,
                check=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise SummarizationError(f"Copilot CLI request failed: {error}") from error
        result = completed.stdout.strip()
        if not result:
            raise SummarizationError("Copilot CLI returned an empty response")
        return result[:max_characters]
