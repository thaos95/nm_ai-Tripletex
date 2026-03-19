import base64
import binascii
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


Scalar = Union[str, int, float, bool]


class TaskType(str, Enum):
    CREATE_EMPLOYEE = "create_employee"
    UPDATE_EMPLOYEE = "update_employee"
    CREATE_CUSTOMER = "create_customer"
    UPDATE_CUSTOMER = "update_customer"
    CREATE_PRODUCT = "create_product"
    CREATE_PROJECT = "create_project"
    CREATE_DEPARTMENT = "create_department"
    CREATE_ORDER = "create_order"
    CREATE_INVOICE = "create_invoice"
    CREATE_TRAVEL_EXPENSE = "create_travel_expense"
    DELETE_TRAVEL_EXPENSE = "delete_travel_expense"
    DELETE_VOUCHER = "delete_voucher"
    UNSUPPORTED = "unsupported"


class FilePayload(BaseModel):
    filename: str
    content_base64: str
    mime_type: str

    @field_validator("filename", "mime_type", "content_base64")
    @classmethod
    def validate_non_empty_strings(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Field must not be empty")
        return value

    @field_validator("content_base64")
    @classmethod
    def validate_base64_payload(cls, value: str) -> str:
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
    def validate_session_token(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("session_token must not be empty")
        return value

    @model_validator(mode="after")
    def validate_https_base_url(self) -> "TripletexCredentials":
        if self.base_url.scheme != "https":
            raise ValueError("base_url must use https")
        return self


class SolveRequest(BaseModel):
    prompt: str
    files: List[FilePayload] = Field(default_factory=list)
    tripletex_credentials: TripletexCredentials

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("prompt must not be empty")
        return value


class SolveResponse(BaseModel):
    status: str = "completed"


class ParsedTask(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    task_type: TaskType
    confidence: float
    language_hint: str = "unknown"
    fields: Dict[str, Scalar] = Field(default_factory=dict)
    match_fields: Dict[str, Scalar] = Field(default_factory=dict)
    related_entities: Dict[str, Dict[str, Scalar]] = Field(default_factory=dict)
    attachments_required: bool = False
    notes: List[str] = Field(default_factory=list)


class PlannedStep(BaseModel):
    name: str
    resource: str
    action: str


class ExecutionPlan(BaseModel):
    parsed_task: ParsedTask
    steps: List[PlannedStep] = Field(default_factory=list)


class OperationResult(BaseModel):
    name: str
    resource_id: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None


class ExecutionResult(BaseModel):
    task_type: TaskType
    operations: List[OperationResult] = Field(default_factory=list)
