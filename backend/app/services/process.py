import logging
import os
import time

from fastapi import HTTPException

from app.schemas import ProcessMode, ProcessRequest, ProcessResponse, RuntimeOverrides
from app.services.llm import (
    LLMConfigurationError,
    LLMJsonParseError,
    LLMSchemaValidationError,
    LLMUpstreamError,
    generate_structured,
    get_prompt_version,
    resolve_effective_runtime,
)

logger = logging.getLogger(__name__)

_SUMMARY_MAX_CHARS = 400
_INTENT_EMPTY_FALLBACK = "unknown"
_REPLY_MODE_EMPTY_FALLBACK = "No reply text was produced."


def _apply_llm_output_guardrails(resp: ProcessResponse, mode: ProcessMode) -> ProcessResponse:
    tasks: list[str] = []
    for item in resp.tasks:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if s:
            tasks.append(s)

    summary = resp.summary.strip()
    if len(summary) > _SUMMARY_MAX_CHARS:
        summary = summary[:_SUMMARY_MAX_CHARS]

    intent = resp.intent.strip() or _INTENT_EMPTY_FALLBACK

    reply = resp.reply.strip()
    if mode == ProcessMode.reply and not reply:
        reply = _REPLY_MODE_EMPTY_FALLBACK

    return ProcessResponse(summary=summary, intent=intent, reply=reply, tasks=tasks)


def _env_llm_mode_label() -> str:
    raw = os.environ.get("LLM_MODE", "stub").strip().lower()
    return raw if raw in ("stub", "real") else "-"


def _log_process_summary(
    *,
    request_id: str,
    mode: str,
    llm_source: str,
    prompt_version: str,
    model: str,
    latency_ms: int,
    result_status: str,
) -> None:
    logger.info(
        "process request_id=%s mode=%s llm_source=%s prompt_version=%s model=%s "
        "latency_ms=%s result_status=%s",
        request_id,
        mode,
        llm_source,
        prompt_version,
        model,
        latency_ms,
        result_status,
    )


def process_input(
    req: ProcessRequest,
    *,
    request_id: str,
    runtime: RuntimeOverrides | None = None,
) -> ProcessResponse:
    t0 = time.perf_counter()

    def elapsed_ms() -> int:
        return int((time.perf_counter() - t0) * 1000)

    merged = runtime if runtime is not None else req.runtime

    try:
        eff = resolve_effective_runtime(merged)
    except LLMConfigurationError as exc:
        src = _env_llm_mode_label()
        pv = get_prompt_version() if src == "real" else "-"
        md = (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip() if src == "real" else "-"
        _log_process_summary(
            request_id=request_id,
            mode=req.mode.value,
            llm_source=src,
            prompt_version=pv,
            model=md,
            latency_ms=elapsed_ms(),
            result_status="config_error",
        )
        raise HTTPException(status_code=503, detail=exc.message) from exc

    try:
        resp, llm_source = generate_structured(req.text, req.mode, eff)
    except LLMConfigurationError as exc:
        _log_process_summary(
            request_id=request_id,
            mode=req.mode.value,
            llm_source=eff.llm_mode,
            prompt_version=eff.prompt_version,
            model=eff.model,
            latency_ms=elapsed_ms(),
            result_status="config_error",
        )
        raise HTTPException(status_code=503, detail=exc.message) from exc
    except LLMJsonParseError as exc:
        _log_process_summary(
            request_id=request_id,
            mode=req.mode.value,
            llm_source="real",
            prompt_version=eff.prompt_version,
            model=eff.model,
            latency_ms=elapsed_ms(),
            result_status="json_parse_error",
        )
        raise HTTPException(status_code=502, detail=exc.message) from exc
    except LLMSchemaValidationError as exc:
        _log_process_summary(
            request_id=request_id,
            mode=req.mode.value,
            llm_source="real",
            prompt_version=eff.prompt_version,
            model=eff.model,
            latency_ms=elapsed_ms(),
            result_status="schema_validation_error",
        )
        raise HTTPException(status_code=502, detail=exc.message) from exc
    except LLMUpstreamError as exc:
        _log_process_summary(
            request_id=request_id,
            mode=req.mode.value,
            llm_source="real",
            prompt_version=eff.prompt_version,
            model=eff.model,
            latency_ms=elapsed_ms(),
            result_status="upstream_error",
        )
        raise HTTPException(status_code=502, detail=exc.message) from exc

    if llm_source == "real":
        resp = _apply_llm_output_guardrails(resp, req.mode)

    _log_process_summary(
        request_id=request_id,
        mode=req.mode.value,
        llm_source=llm_source,
        prompt_version=eff.prompt_version,
        model=eff.model,
        latency_ms=elapsed_ms(),
        result_status="ok",
    )
    return resp
