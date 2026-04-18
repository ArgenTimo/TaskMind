from fastapi import HTTPException

from app.schemas import ProcessRequest, ProcessResponse
from app.services.llm import (
    LLMConfigurationError,
    LLMUpstreamError,
    generate_structured,
)


def process_input(req: ProcessRequest) -> ProcessResponse:
    try:
        return generate_structured(req.text, req.mode)
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=exc.message) from exc
    except LLMUpstreamError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc
