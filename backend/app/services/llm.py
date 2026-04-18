"""LLM integration: deterministic stub or OpenAI-compatible Chat Completions."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from app.schemas import ProcessMode, ProcessResponse


class LLMConfigurationError(Exception):
    """Missing or invalid LLM configuration (client misconfiguration)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class LLMUpstreamError(Exception):
    """Provider HTTP error, timeout, or unparseable response."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def generate_structured(text: str, mode: ProcessMode) -> ProcessResponse:
    raw = os.environ.get("LLM_MODE", "stub").strip().lower()
    if raw not in ("stub", "real"):
        raise LLMConfigurationError(
            f"Invalid LLM_MODE={raw!r}; use 'stub' or 'real'.",
        )
    if raw == "stub":
        return _stub_generate(text, mode)
    return _real_generate(text, mode)


def _stub_generate(text: str, mode: ProcessMode) -> ProcessResponse:
    snippet = text[:160] + ("..." if len(text) > 160 else "")

    if mode == ProcessMode.analyze:
        return ProcessResponse(
            summary=f"[analyze] {snippet}",
            intent="Understand what the user is trying to accomplish.",
            reply="(stub) Consider the analysis above before responding.",
            tasks=["Decide on next steps based on the summary"],
        )

    if mode == ProcessMode.reply:
        return ProcessResponse(
            summary=snippet,
            intent="Produce a helpful reply to the user.",
            reply=f"[reply] Acknowledged: {text[:120]}{'...' if len(text) > 120 else ''}",
            tasks=["Review the draft reply and send when ready"],
        )

    lines = [ln.strip().lstrip("-•").strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        tasks = lines[:10]
    else:
        parts = text.split()
        tasks = [f"Follow up: {w}" for w in parts[:5]] if parts else ["Define one concrete next action"]

    return ProcessResponse(
        summary=snippet,
        intent="Extract actionable tasks from the message.",
        reply="(stub) Tasks listed below.",
        tasks=tasks,
    )


def _real_generate(text: str, mode: ProcessMode) -> ProcessResponse:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise LLMConfigurationError(
            "LLM_MODE=real requires OPENAI_API_KEY to be set (non-empty).",
        )

    base = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip()
    url = f"{base}/chat/completions"

    system = (
        "You are a work assistant. Respond with a single JSON object only, no markdown fences, "
        'with keys: "summary" (string), "intent" (string), "reply" (string), "tasks" (array of strings). '
        "Tasks must be short actionable strings. "
        f"The user selected mode is {mode.value!r}: "
        "analyze emphasizes summary and intent; reply emphasizes the reply text; "
        "extract_tasks emphasizes a rich tasks list."
    )
    user = f"User message:\n{text}"

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
    except httpx.RequestError as exc:
        raise LLMUpstreamError(f"LLM request failed: {exc}") from exc

    if response.status_code >= 400:
        raise LLMUpstreamError(
            f"LLM HTTP {response.status_code}: {response.text[:500]}",
        )

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMUpstreamError(f"Unexpected LLM response shape: {exc}") from exc

    data = _parse_json_content(content)
    try:
        return ProcessResponse.model_validate(data)
    except Exception as exc:
        raise LLMUpstreamError(f"LLM JSON did not match schema: {exc}") from exc


_JSON_OBJECT = re.compile(r"\{[\s\S]*\}")


def _parse_json_content(content: str) -> Any:
    text = content.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_OBJECT.search(text)
    if match:
        return json.loads(match.group())
    raise LLMUpstreamError("Could not parse JSON from LLM content.")

