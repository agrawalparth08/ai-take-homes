"""Model access. The only module that talks to an LLM.

Every call is schema-constrained and returns a plain dict, or raises LLMError after
bounded retries. The model gets no tools: it reads text and returns JSON, nothing else.

Backends:
  api   Anthropic SDK (needs ANTHROPIC_API_KEY). Forced single tool = structured output.
  cli   `claude -p --json-schema` (uses a logged-in Claude Code CLI; handy for local dev).
  fake  Deterministic canned responses for tests.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

DEFAULT_MODEL = os.environ.get("JUNE_TAPES_MODEL", "claude-sonnet-5")


class LLMError(RuntimeError):
    pass


@dataclass
class Completion:
    data: dict[str, Any]
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    attempts: int = 1


class LLM(Protocol):
    name: str

    def complete(self, *, system: str, prompt: str, schema: dict, tool_name: str) -> Completion: ...


def _retry(fn: Callable[[], Completion], *, attempts: int = 3, base_delay: float = 2.0) -> Completion:
    last: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            out = fn()
            out.attempts = i
            return out
        except LLMError as e:  # transient or malformed: retry with backoff
            last = e
            if i < attempts:
                time.sleep(base_delay * 2 ** (i - 1))
    raise LLMError(f"gave up after {attempts} attempts: {last}")


class AnthropicAPI:
    def __init__(self, model: str = DEFAULT_MODEL, timeout: float = 180.0):
        import anthropic  # imported lazily so tests and the cli backend don't need it

        self.client = anthropic.Anthropic(timeout=timeout, max_retries=2)
        self.model = model
        self.name = f"api:{model}"

    def complete(self, *, system: str, prompt: str, schema: dict, tool_name: str) -> Completion:
        def once() -> Completion:
            t0 = time.monotonic()
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=8000,
                    system=system,
                    tools=[{"name": tool_name, "description": "Return the result.", "input_schema": schema}],
                    tool_choice={"type": "tool", "name": tool_name},
                    messages=[{"role": "user", "content": prompt}],
                )
            except Exception as e:  # network, 429, 5xx after SDK retries
                raise LLMError(f"{type(e).__name__}: {e}") from e
            blocks = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
            if not blocks:
                raise LLMError(f"no tool_use block (stop_reason={resp.stop_reason})")
            return Completion(
                data=dict(blocks[0].input),
                model=resp.model,
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
                latency_s=time.monotonic() - t0,
            )

        return _retry(once)


class ClaudeCLI:
    """`claude -p` with project settings, tools and dynamic context switched off."""

    def __init__(self, model: str = "sonnet", timeout: float = 300.0):
        self.model = model
        self.timeout = timeout
        self.name = f"cli:{model}"

    def complete(self, *, system: str, prompt: str, schema: dict, tool_name: str) -> Completion:
        cmd = [
            "claude", "-p",
            "--model", self.model,
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
            "--system-prompt", system,
            "--setting-sources", "",
            "--tools", "",
            "--exclude-dynamic-system-prompt-sections",
        ]

        def once() -> Completion:
            t0 = time.monotonic()
            try:
                proc = subprocess.run(
                    cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout,
                    cwd=os.environ.get("TMPDIR", "/tmp"),
                )
            except subprocess.TimeoutExpired as e:
                raise LLMError(f"timeout after {self.timeout}s") from e
            try:
                out = json.loads(proc.stdout)
            except json.JSONDecodeError as e:
                raise LLMError(f"non-JSON CLI output (rc={proc.returncode}): {proc.stderr[:300]}") from e
            if out.get("is_error") or not isinstance(out.get("structured_output"), dict):
                raise LLMError(f"CLI error: {str(out.get('result'))[:300]}")
            usage = out.get("usage", {})
            models = list(out.get("modelUsage", {}).keys())
            return Completion(
                data=out["structured_output"],
                model=models[0] if models else self.model,
                input_tokens=usage.get("input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                latency_s=time.monotonic() - t0,
            )

        return _retry(once)


@dataclass
class FakeLLM:
    """Test double. `responder(tool_name, prompt) -> dict`, or raise LLMError."""

    responder: Callable[[str, str], dict]
    name: str = "fake"
    calls: list[str] = field(default_factory=list)

    def complete(self, *, system: str, prompt: str, schema: dict, tool_name: str) -> Completion:
        self.calls.append(tool_name)
        return Completion(data=self.responder(tool_name, prompt), model="fake")


def make(backend: str | None = None, model: str | None = None) -> LLM:
    backend = backend or os.environ.get("JUNE_TAPES_BACKEND") or (
        "api" if os.environ.get("ANTHROPIC_API_KEY") else "cli"
    )
    if backend == "api":
        return AnthropicAPI(model or DEFAULT_MODEL)
    if backend == "cli":
        return ClaudeCLI(model or "sonnet")
    raise ValueError(f"unknown backend {backend!r}")
