import uuid

from fastapi import APIRouter, Request

from app.schemas import ProcessRequest, ProcessResponse
from app.services.process import process_input

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/process", response_model=ProcessResponse)
def process(request: Request, req: ProcessRequest) -> ProcessResponse:
    rid = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    return process_input(req, request_id=rid)
