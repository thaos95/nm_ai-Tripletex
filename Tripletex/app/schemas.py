import base64
import binascii
from dataclasses import dataclass, field as dataclass_field
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


# ---------------------------------------------------------------------------
# TaskType enum — covers all 30 competition task types
# ---------------------------------------------------------------------------

class TaskType(str, Enum):
    CREATE_EMPLOYEE = "create_employee"
    UPDATE_EMPLOYEE = "update_employee"
    LIST_EMPLOYEES = "list_employees"
    CREATE_CUSTOMER = "create_customer"
    UPDATE_CUSTOMER = "update_customer"
    SEARCH_CUSTOMERS = "search_customers"
    CREATE_PRODUCT = "create_product"
    CREATE_PROJECT = "create_project"
    CREATE_DEPARTMENT = "create_department"
    CREATE_ORDER = "create_order"
    CREATE_INVOICE = "create_invoice"
    CREATE_CREDIT_NOTE = "create_credit_note"
    CREATE_PROJECT_BILLING = "create_project_billing"
    CREATE_SUPPLIER_INVOICE = "create_supplier_invoice"
    CREATE_DIMENSION_VOUCHER = "create_dimension_voucher"
    CREATE_PAYROLL_VOUCHER = "create_payroll_voucher"
    CREATE_TRAVEL_EXPENSE = "create_travel_expense"
    UPDATE_TRAVEL_EXPENSE = "update_travel_expense"
    DELETE_TRAVEL_EXPENSE = "delete_travel_expense"
    DELETE_VOUCHER = "delete_voucher"
    REGISTER_PAYMENT = "register_payment"
    REVERSE_PAYMENT = "reverse_payment"
    LIST_LEDGER_ACCOUNTS = "list_ledger_accounts"
    LIST_LEDGER_POSTINGS = "list_ledger_postings"
    BANK_RECONCILIATION = "bank_reconciliation"
    CORRECT_LEDGER_ERRORS = "correct_ledger_errors"
    UNSUPPORTED = "unsupported"


# ---------------------------------------------------------------------------
# ParsedTask — produced by the LLM / rule-based parser
# ---------------------------------------------------------------------------

@dataclass
class ParsedTask:
    task_type: TaskType
    confidence: float = 0.0
    language_hint: str = "unknown"
    fields: Dict[str, Any] = dataclass_field(default_factory=dict)
    match_fields: Dict[str, Any] = dataclass_field(default_factory=dict)
    related_entities: Dict[str, Dict[str, Any]] = dataclass_field(default_factory=dict)
    attachments_required: bool = False
    notes: List[str] = dataclass_field(default_factory=list)


# ---------------------------------------------------------------------------
# Execution models — used by workflows/executor
# ---------------------------------------------------------------------------

@dataclass
class OperationResult:
    name: str
    resource_id: Optional[int] = None
    payload: Dict[str, Any] = dataclass_field(default_factory=dict)


@dataclass
class ExecutionResult:
    task_type: str = ""
    status: str = "pending"
    operations: List[OperationResult] = dataclass_field(default_factory=list)
    warnings: List[str] = dataclass_field(default_factory=list)
    error: Optional[str] = None


@dataclass
class ExecutionPlan:
    task: Optional[ParsedTask] = None
    steps: List[Any] = dataclass_field(default_factory=list)
    raw_prompt: str = ""

    @property
    def parsed_task(self) -> Optional[ParsedTask]:
        return self.task


# ---------------------------------------------------------------------------
# Preflight / validation models
# ---------------------------------------------------------------------------

@dataclass
class ValidationCheck:
    name: str
    result: str  # "OK", "FAIL", "UNKNOWN"
    code: Optional[str] = None
    message: str = ""
    suggested_action: Optional[str] = None
    endpoint: Optional[str] = None


@dataclass
class ValidateResponse:
    status: str  # "OK" or "AVVIK"
    operation: str = ""
    checks: List[ValidationCheck] = dataclass_field(default_factory=list)
    summary: str = ""
    can_continue: bool = True


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


# Alias for backward compatibility with tests
FilePayload = InputFile


class SolveResponse(BaseModel):
    status: str = "completed"
