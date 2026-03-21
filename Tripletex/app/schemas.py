import base64
import binascii
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class InputFile(BaseModel):
    filename: str
    content_base64: str
    mime_type: str

    @field_validator("filename", "mime_type", "content_base64")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("content_base64")
    @classmethod
    def _validate_base64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("content_base64 must be valid base64") from exc
        return value


class TripletexCredentials(BaseModel):
    base_url: HttpUrl
    session_token: str

    @field_validator("session_token")
    @classmethod
    def _non_empty_token(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("session_token must not be empty")
        return value


class SolveRequest(BaseModel):
    prompt: str
    files: List[InputFile] = Field(default_factory=list)
    tripletex_credentials: TripletexCredentials

    @field_validator("prompt")
    @classmethod
    def _non_empty_prompt(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("prompt must not be empty")
        return value


class PlanStep(BaseModel):
    id: str
    name: str
    action: str
    details: Dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    language: str
    task_type: str
    primary_entity: Optional[str] = None
    entities: Dict[str, Any] = Field(default_factory=dict)
    steps: List[PlanStep] = Field(default_factory=list)


class SolveResponse(BaseModel):
    status: str = "completed"
    plan: Optional[Plan] = None
