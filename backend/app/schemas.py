from enum import Enum

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
