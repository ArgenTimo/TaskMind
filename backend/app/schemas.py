from enum import Enum
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, BaseModel, Field, model_validator


class ProcessMode(str, Enum):
    analyze = "analyze"
    reply = "reply"
    extract_tasks = "extract_tasks"


class LLMMode(str, Enum):
    stub = "stub"
    real = "real"


class RuntimeOverrides(BaseModel):
    """Optional per-request overrides; does not change server environment."""

    llm_mode: LLMMode | None = None
    prompt_version: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    base_url: AnyHttpUrl | None = None


class ProcessRequest(BaseModel):
    text: str = Field(..., min_length=1)
    mode: ProcessMode
    runtime: RuntimeOverrides | None = None

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
    runtime: RuntimeOverrides | None = None


class RuntimeConfigResponse(BaseModel):
    default_llm_mode: str
    default_prompt_version: str
    default_model: str
    default_base_url: str
    available_prompt_versions: list[str]
    real_mode_supported: bool
    json_object_request_enabled: bool


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
