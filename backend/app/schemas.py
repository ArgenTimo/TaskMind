from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class ProcessMode(str, Enum):
    analyze = "analyze"
    reply = "reply"
    extract_tasks = "extract_tasks"


class ProcessRequest(BaseModel):
    text: str = Field(..., min_length=1)
    mode: ProcessMode

    @model_validator(mode="after")
    def normalize_text(self) -> "ProcessRequest":
        stripped = self.text.strip()
        if not stripped:
            raise ValueError("text must not be empty")
        self.text = stripped
        return self


class ProcessResponse(BaseModel):
    summary: str
    intent: str
    reply: str
    tasks: list[str]


class ProcessBatchItemIn(BaseModel):
    """One row in POST /process_batch (validated per-item in the handler)."""

    text: str = ""
    mode: str


class ProcessBatchRequest(BaseModel):
    items: list[ProcessBatchItemIn] = Field(..., min_length=1, max_length=100)


class BatchItemError(BaseModel):
    status_code: int
    detail: str


class BatchItemSuccess(BaseModel):
    success: Literal[True] = True
    result: ProcessResponse


class BatchItemFailure(BaseModel):
    success: Literal[False] = False
    error: BatchItemError


class ProcessBatchResponse(BaseModel):
    items: list[Annotated[BatchItemSuccess | BatchItemFailure, Field(discriminator="success")]]
