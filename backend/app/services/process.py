import logging

from fastapi import HTTPException

from app.schemas import ProcessMode, ProcessRequest, ProcessResponse
from app.services.llm import (
    LLMConfigurationError,
    LLMJsonParseError,
    LLMSchemaValidationError,
    LLMUpstreamError,
    generate_structured,
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


def process_input(req: ProcessRequest) -> ProcessResponse:
    try:
        resp, llm_source = generate_structured(req.text, req.mode)
    except LLMConfigurationError as exc:
        logger.warning(
            "llm_failure kind=configuration mode=%s",
            req.mode.value,
        )
        raise HTTPException(status_code=503, detail=exc.message) from exc
    except LLMJsonParseError as exc:
        logger.warning(
            "llm_failure kind=json_parse mode=%s",
            req.mode.value,
        )
        raise HTTPException(status_code=502, detail=exc.message) from exc
    except LLMSchemaValidationError as exc:
        logger.warning(
            "llm_failure kind=schema_validation mode=%s",
            req.mode.value,
        )
        raise HTTPException(status_code=502, detail=exc.message) from exc
    except LLMUpstreamError as exc:
        logger.warning(
            "llm_failure kind=upstream mode=%s",
            req.mode.value,
        )
        raise HTTPException(status_code=502, detail=exc.message) from exc

    if llm_source == "real":
        resp = _apply_llm_output_guardrails(resp, req.mode)
    return resp
