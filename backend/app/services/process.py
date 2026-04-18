from app.schemas import ProcessRequest, ProcessResponse
from app.services.llm import generate_structured


def process_input(req: ProcessRequest) -> ProcessResponse:
    return generate_structured(req.text, req.mode)
