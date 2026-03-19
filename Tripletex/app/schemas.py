from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


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


class TripletexCredentials(BaseModel):
    base_url: HttpUrl
    session_token: str


class SolveRequest(BaseModel):
    prompt: str
    files: List[FilePayload] = Field(default_factory=list)
    tripletex_credentials: TripletexCredentials


class SolveResponse(BaseModel):
    status: str = "completed"
    task_type: TaskType
    operations: int


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
