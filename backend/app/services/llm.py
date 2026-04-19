"""LLM integration: deterministic stub or OpenAI-compatible Chat Completions."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from app.schemas import (
    ModelsListResponse,
    ModelsListSource,
    ProcessMode,
    ProcessResponse,
    RuntimeConfigResponse,
    RuntimeOverrides,
)

LLMSourceMode = Literal["stub", "real"]

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
_DEFAULT_PROMPT_VERSION = "v1"


@dataclass(frozen=True)
class EffectiveRuntime:
    """Resolved per-request settings (not global env mutation)."""

    llm_mode: Literal["stub", "real"]
    prompt_version: str
    model: str
    base_url: str


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


def list_available_prompt_versions() -> list[str]:
    versions: list[str] = []
    if not _PROMPTS_DIR.is_dir():
        return versions
    for path in _PROMPTS_DIR.glob("process_*.md"):
        stem = path.stem
        if stem.startswith("process_"):
            versions.append(stem[len("process_") :])
    return sorted(set(versions))


def _default_prompt_version_from_env() -> str:
    raw = (os.environ.get("PROMPT_VERSION") or _DEFAULT_PROMPT_VERSION).strip()
    return raw or _DEFAULT_PROMPT_VERSION


def get_prompt_version() -> str:
    """PROMPT_VERSION from environment (for legacy callers)."""
    return _default_prompt_version_from_env()


def resolve_effective_runtime(overrides: RuntimeOverrides | None) -> EffectiveRuntime:
    """Merge optional request overrides with process environment defaults."""
    raw_env = os.environ.get("LLM_MODE", "stub").strip().lower()
    if overrides is not None and overrides.llm_mode is not None:
        mode: Literal["stub", "real"] = overrides.llm_mode.value
    else:
        if raw_env not in ("stub", "real"):
            raise LLMConfigurationError(
                f"Invalid LLM_MODE={raw_env!r}; use 'stub' or 'real', or pass runtime.llm_mode.",
            )
        mode = raw_env  # type: ignore[assignment]

    pv_raw = (
        overrides.prompt_version.strip()
        if overrides is not None and overrides.prompt_version
        else _default_prompt_version_from_env()
    )
    prompt_version = pv_raw or _DEFAULT_PROMPT_VERSION

    model_raw = (
        overrides.model.strip()
        if overrides is not None and overrides.model
        else (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip()
    )
    model = model_raw or "gpt-4o-mini"

    default_base = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    if overrides is not None and overrides.base_url is not None:
        base_url = str(overrides.base_url).rstrip("/")
    else:
        base_url = default_base

    if mode == "stub":
        return EffectiveRuntime(
            llm_mode="stub",
            prompt_version="-",
            model="-",
            base_url="-",
        )

    path = _PROMPTS_DIR / f"process_{prompt_version}.md"
    if not path.is_file():
        raise LLMConfigurationError(
            f"PROMPT_VERSION={prompt_version!r}: prompt file not found: {path}",
        )

    return EffectiveRuntime(
        llm_mode="real",
        prompt_version=prompt_version,
        model=model,
        base_url=base_url,
    )


def _default_openai_base_url() -> str:
    return (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")


def build_runtime_config_response() -> RuntimeConfigResponse:
    raw_mode = os.environ.get("LLM_MODE", "stub").strip().lower()
    default_llm_mode = raw_mode if raw_mode in ("stub", "real") else "stub"
    return RuntimeConfigResponse(
        default_llm_mode=default_llm_mode,
        default_prompt_version=_default_prompt_version_from_env(),
        default_model=(os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip(),
        default_base_url=_default_openai_base_url(),
        available_prompt_versions=list_available_prompt_versions(),
        real_mode_supported=bool(os.environ.get("OPENAI_API_KEY", "").strip()),
        json_object_request_enabled=_json_object_mode_enabled(),
    )


def build_models_list_response() -> ModelsListResponse:
    """List models from the configured provider using server-side credentials only."""
    base_url = _default_openai_base_url()
    raw_mode = os.environ.get("LLM_MODE", "stub").strip().lower()
    if raw_mode != "real":
        return ModelsListResponse(
            models=[],
            source=ModelsListSource.stub_mode,
            detail="Server LLM_MODE is not real; provider model list is not queried.",
            base_url=base_url,
        )

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return ModelsListResponse(
            models=[],
            source=ModelsListSource.no_api_key,
            detail="OPENAI_API_KEY is not set; cannot query provider models.",
            base_url=base_url,
        )

    url = f"{base_url}/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, headers=headers)
    except httpx.RequestError as exc:
        return ModelsListResponse(
            models=[],
            source=ModelsListSource.provider_error,
            detail=f"Provider request failed: {exc}",
            base_url=base_url,
        )

    if response.status_code >= 400:
        snippet = response.text[:500] if response.text else ""
        return ModelsListResponse(
            models=[],
            source=ModelsListSource.provider_error,
            detail=f"Provider HTTP {response.status_code}: {snippet}",
            base_url=base_url,
        )

    try:
        body = response.json()
    except json.JSONDecodeError:
        return ModelsListResponse(
            models=[],
            source=ModelsListSource.provider_error,
            detail="Provider response body is not valid JSON.",
            base_url=base_url,
        )

    raw_items = body.get("data")
    if not isinstance(raw_items, list):
        return ModelsListResponse(
            models=[],
            source=ModelsListSource.provider_error,
            detail='Unexpected provider shape: expected top-level "data" array.',
            base_url=base_url,
        )

    ids: list[str] = []
    for item in raw_items:
        if isinstance(item, dict) and "id" in item and item["id"] is not None:
            ids.append(str(item["id"]).strip())

    ids = sorted(set(ids))
    return ModelsListResponse(
        models=ids,
        source=ModelsListSource.live,
        detail=None,
        base_url=base_url,
    )


def generate_structured(
    text: str,
    mode: ProcessMode,
    eff: EffectiveRuntime,
) -> tuple[ProcessResponse, LLMSourceMode]:
    if eff.llm_mode == "stub":
        return _stub_generate(text, mode), "stub"
    return _real_generate(text, mode, eff), "real"


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


def _parse_prompt_markdown_sections(content: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current: str | None = None
    lines_out: list[str] = []
    for line in content.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(lines_out).strip()
            current = line[3:].strip()
            lines_out = []
        elif current is not None:
            lines_out.append(line)
    if current is not None:
        sections[current] = "\n".join(lines_out).strip()
    return sections


def _build_real_system_prompt(mode: ProcessMode, prompt_version: str) -> str:
    path = _PROMPTS_DIR / f"process_{prompt_version}.md"
    if not path.is_file():
        raise LLMConfigurationError(
            f"PROMPT_VERSION={prompt_version!r}: prompt file not found: {path}",
        )
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LLMConfigurationError(
            f"PROMPT_VERSION={prompt_version!r}: cannot read prompt file {path}: {exc}",
        ) from exc

    sections = _parse_prompt_markdown_sections(raw_text)
    mode_key = f"MODE_{mode.value}"
    for key in ("HEAD", mode_key, "TAIL"):
        if key not in sections or not sections[key].strip():
            raise LLMConfigurationError(
                f"PROMPT_VERSION={prompt_version!r}: prompt file {path.name} missing or empty section "
                f"{key!r}",
            )

    return (
        sections["HEAD"]
        + f"\n\nSelected mode: {mode.value!r}\n\n"
        + sections[mode_key]
        + "\n\n"
        + sections["TAIL"]
    )


def _build_real_user_message(text: str) -> str:
    return (
        "Return one JSON object as specified in the system message. "
        "User input to process:\n\n"
        f"{text}"
    )


def _real_generate(text: str, mode: ProcessMode, eff: EffectiveRuntime) -> ProcessResponse:
    raw = os.environ.get("OPENAI_API_KEY", "")
    api_key = raw.strip()
    if not api_key:
        raise LLMConfigurationError(
            "LLM_MODE=real requires OPENAI_API_KEY to be set (non-empty).",
        )

    url = f"{eff.base_url}/chat/completions"

    system = _build_real_system_prompt(mode, eff.prompt_version)
    user = _build_real_user_message(text)

    payload: dict[str, Any] = {
        "model": eff.model,
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
