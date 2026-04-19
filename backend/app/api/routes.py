import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from app.schemas import (
    BatchItemError,
    BatchItemFailure,
    BatchItemSuccess,
    ProcessBatchRequest,
    ProcessBatchResponse,
    ProcessRequest,
    ProcessResponse,
    RuntimeConfigResponse,
)
from app.services.llm import build_runtime_config_response
from app.services.process import process_input

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/runtime_config", response_model=RuntimeConfigResponse)
def runtime_config() -> RuntimeConfigResponse:
    return build_runtime_config_response()


@router.post("/process", response_model=ProcessResponse)
def process(request: Request, req: ProcessRequest) -> ProcessResponse:
    rid = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    return process_input(req, request_id=rid)


def _http_exception_detail(detail: str | list | dict | None) -> str:
    if isinstance(detail, str):
        return detail
    try:
        return json.dumps(detail, default=str)
    except TypeError:
        return str(detail)


@router.post("/process_batch", response_model=ProcessBatchResponse)
def process_batch(request: Request, body: ProcessBatchRequest) -> ProcessBatchResponse:
    base_rid = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    out: list[BatchItemSuccess | BatchItemFailure] = []

    for i, row in enumerate(body.items):
        rid = f"{base_rid}-b{i}"
        try:
            item_req = ProcessRequest.model_validate({"text": row.text, "mode": row.mode})
        except ValidationError as exc:
            out.append(
                BatchItemFailure(
                    success=False,
                    error=BatchItemError(
                        status_code=422,
                        detail=json.dumps(exc.errors(), default=str),
                    ),
                ),
            )
            continue
        try:
            result = process_input(item_req, request_id=rid, runtime=body.runtime)
        except HTTPException as exc:
            out.append(
                BatchItemFailure(
                    success=False,
                    error=BatchItemError(
                        status_code=exc.status_code,
                        detail=_http_exception_detail(exc.detail),
                    ),
                ),
            )
        else:
            out.append(BatchItemSuccess(success=True, result=result))

    n_ok = sum(1 for x in out if x.success)
    n_fail = len(out) - n_ok
    logger.info(
        "process_batch request_id=%s items=%s ok=%s fail=%s",
        base_rid,
        len(out),
        n_ok,
        n_fail,
    )
    return ProcessBatchResponse(items=out)
