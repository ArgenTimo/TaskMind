from fastapi import APIRouter

from app.schemas import ProcessRequest, ProcessResponse
from app.services.process import process_input

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/process", response_model=ProcessResponse)
def process(req: ProcessRequest) -> ProcessResponse:
    return process_input(req)
