"""LLM integration: deterministic stub or OpenAI-compatible Chat Completions."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from app.schemas import ProcessMode, ProcessResponse

LLMSourceMode = Literal["stub", "real"]


class LLMConfigurationError(Exception):
    """Missing or invalid LLM configuration (client misconfiguration)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class LLMUpstreamError(Exception):
    """Non-2xx HTTP from provider, network/request failure, or unexpected response shape."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class LLMJsonParseError(Exception):
    """Provider returned assistant content that is not valid JSON."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class LLMSchemaValidationError(Exception):
    """Assistant JSON parsed but does not match ProcessResponse."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def generate_structured(text: str, mode: ProcessMode) -> tuple[ProcessResponse, LLMSourceMode]:
    raw = os.environ.get("LLM_MODE", "stub").strip().lower()
    if raw not in ("stub", "real"):
        raise LLMConfigurationError(
            f"Invalid LLM_MODE={raw!r}; use 'stub' or 'real'.",
        )
    if raw == "stub":
        return _stub_generate(text, mode), "stub"
    return _real_generate(text, mode), "real"


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


def _json_object_mode_enabled() -> bool:
    raw = (os.environ.get("OPENAI_JSON_OBJECT") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _build_real_system_prompt(mode: ProcessMode) -> str:
    mode_rules = {
        ProcessMode.analyze: (
            "Focus priority: make **summary** and **intent** the most detailed and useful fields. "
            "Keep **reply** and **tasks** shorter and supportive, but still non-empty strings "
            "(use a brief placeholder sentence for reply if needed; tasks can be one or two items)."
        ),
        ProcessMode.reply: (
            "Focus priority: make **reply** the most detailed and useful field—this is what the user "
            "will send back. Keep **summary**, **intent**, and **tasks** brief but still meaningful."
        ),
        ProcessMode.extract_tasks: (
            "Focus priority: make **tasks** the richest field—a clear list of actionable strings. "
            "Keep **summary**, **intent**, and **reply** short; do not let them overshadow the task list."
        ),
    }
    return (
        "You output a single JSON object only. The entire reply must be valid JSON with no text "
        "before or after it. Do not use markdown code fences (no ```). Do not add commentary, "
        "headings, or explanations outside the JSON.\n\n"
        "Required keys (exactly these four, all required):\n"
        '- "summary": string\n'
        '- "intent": string\n'
        '- "reply": string\n'
        '- "tasks": array of strings (each item one short actionable task)\n\n'
        f"Selected mode: {mode.value!r}\n"
        f"{mode_rules[mode]}\n\n"
        "Constraints: use double-quoted keys and strings only; no trailing commas; "
        "tasks must be a JSON array (use [] only if there is truly nothing actionable, prefer at least one item)."
    )


def _build_real_user_message(text: str) -> str:
    return (
        "Return one JSON object as specified in the system message. "
        "User input to process:\n\n"
        f"{text}"
    )


def _real_generate(text: str, mode: ProcessMode) -> ProcessResponse:
    raw = os.environ.get("OPENAI_API_KEY", "")
    api_key = raw.strip()
    if not api_key:
        raise LLMConfigurationError(
            "LLM_MODE=real requires OPENAI_API_KEY to be set (non-empty).",
        )

    base = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip()
    url = f"{base}/chat/completions"

    system = _build_real_system_prompt(mode)
    user = _build_real_user_message(text)

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }
    if _json_object_mode_enabled():
        payload["response_format"] = {"type": "json_object"}

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
    except json.JSONDecodeError as exc:
        raise LLMUpstreamError("LLM response body is not valid JSON.") from exc

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMUpstreamError(f"Unexpected LLM response shape: {exc}") from exc

    data = _parse_json_content(content)
    try:
        return ProcessResponse.model_validate(data)
    except ValidationError as exc:
        raise LLMSchemaValidationError(
            "LLM JSON does not match ProcessResponse.",
        ) from exc


_JSON_OBJECT = re.compile(r"\{[\s\S]*\}")


def _parse_json_content(content: str) -> Any:
    text = content.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_OBJECT.search(text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError as exc:
            raise LLMJsonParseError(
                "LLM assistant content is not valid JSON.",
            ) from exc
    raise LLMJsonParseError("LLM assistant content is not valid JSON.")

