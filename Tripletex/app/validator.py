from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from app.schemas import ParsedTask, TaskType


@dataclass
class ValidationResult:
    parsed_task: ParsedTask
    blocking_error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    safety: str = "safe"


def _copy_task(task: ParsedTask) -> ParsedTask:
    return ParsedTask(
        task_type=task.task_type,
        confidence=task.confidence,
        language_hint=task.language_hint,
        fields=dict(task.fields),
        match_fields=dict(task.match_fields),
        related_entities=dict((key, dict(value)) for key, value in task.related_entities.items()),
        attachments_required=task.attachments_required,
        notes=list(task.notes),
    )


def _normalize_phone_fields(task: ParsedTask) -> None:
    aliases = [
        "phone",
        "mobilePhoneNumber",
        "phoneNumberMobile",
        "mobile_phone",
        "mobile",
    ]
    for alias in aliases:
        if alias in task.fields:
            task.fields["phoneNumberMobile"] = str(task.fields.pop(alias)).replace(" ", "")
            break


def _normalize_customer_phone(task: ParsedTask) -> None:
    for alias in ("phone", "phoneNumberWork", "phoneNumberMobile"):
        if alias in task.fields:
            task.fields["phoneNumber"] = str(task.fields.pop(alias)).replace(" ", "")
            break


def _normalize_travel_expense(task: ParsedTask) -> None:
    date_value = None
    for key in ("travelExpenseDate", "expenseDate", "date"):
        if key in task.fields:
            date_value = task.fields.pop(key)
            break
    if date_value is not None:
        task.fields["date"] = str(date_value)

    if "amount" in task.fields:
        task.fields["amount"] = float(task.fields["amount"])


def _normalize_customer_fields(task: ParsedTask) -> None:
    organization_number = task.fields.get("organizationNumber")
    if organization_number is None:
        return
    digits_only = "".join(ch for ch in str(organization_number) if ch.isdigit())
    if len(digits_only) == 9:
        task.fields["organizationNumber"] = digits_only
    else:
        task.fields.pop("organizationNumber", None)


def _drop_unknown_fields(task: ParsedTask, allowed_fields: Dict[TaskType, Set[str]]) -> List[str]:
    warnings: List[str] = []
    allowed = allowed_fields.get(task.task_type)
    if allowed is None:
        return warnings

    for key in list(task.fields):
        if key not in allowed:
            task.fields.pop(key)
            warnings.append("Dropped unsupported field '{0}' for task {1}".format(key, task.task_type))
    return warnings


def validate_and_normalize_task(task: ParsedTask) -> ValidationResult:
    normalized = _copy_task(task)
    warnings: List[str] = []

    if normalized.task_type == TaskType.UPDATE_EMPLOYEE:
        _normalize_phone_fields(normalized)
    elif normalized.task_type == TaskType.UPDATE_CUSTOMER:
        _normalize_customer_phone(normalized)
    elif normalized.task_type == TaskType.CREATE_CUSTOMER:
        _normalize_customer_fields(normalized)
    elif normalized.task_type == TaskType.CREATE_TRAVEL_EXPENSE:
        _normalize_travel_expense(normalized)

    allowed_fields: Dict[TaskType, Set[str]] = {
        TaskType.CREATE_EMPLOYEE: {"first_name", "last_name", "email", "employee_type"},
        TaskType.UPDATE_EMPLOYEE: {"phoneNumberMobile", "email"},
        TaskType.LIST_EMPLOYEES: {"fields", "count"},
        TaskType.CREATE_CUSTOMER: {"name", "email", "isCustomer", "organizationNumber", "phoneNumber"},
        TaskType.UPDATE_CUSTOMER: {"phoneNumber", "email"},
        TaskType.SEARCH_CUSTOMERS: {"fields", "count"},
        TaskType.CREATE_PRODUCT: {"name", "priceExcludingVatCurrency"},
        TaskType.CREATE_PROJECT: {"name", "startDate"},
        TaskType.CREATE_DEPARTMENT: {"name", "departmentNumber"},
        TaskType.CREATE_ORDER: {"orderDate", "deliveryDate"},
        TaskType.CREATE_INVOICE: {"invoiceDate", "invoiceDueDate", "amount"},
        TaskType.CREATE_TRAVEL_EXPENSE: {"date", "amount", "distance"},
        TaskType.DELETE_TRAVEL_EXPENSE: {"travel_expense_id"},
        TaskType.DELETE_VOUCHER: {"voucher_id"},
        TaskType.LIST_LEDGER_ACCOUNTS: {"fields", "count"},
        TaskType.LIST_LEDGER_POSTINGS: {"fields", "count", "period_hint"},
    }
    warnings.extend(_drop_unknown_fields(normalized, allowed_fields))

    if normalized.task_type == TaskType.CREATE_EMPLOYEE:
        if not normalized.fields.get("first_name") or not normalized.fields.get("email"):
            return ValidationResult(normalized, blocking_error="Employee creation requires name and email")

    if normalized.task_type == TaskType.UPDATE_EMPLOYEE:
        if not normalized.match_fields:
            return ValidationResult(normalized, blocking_error="Employee update requires identifying fields")
        if not normalized.fields:
            return ValidationResult(normalized, blocking_error="Employee update requires at least one mutable field")

    if normalized.task_type == TaskType.LIST_EMPLOYEES:
        normalized.fields.setdefault("fields", "id,firstName,lastName,email")
        normalized.fields.setdefault("count", 100)

    if normalized.task_type == TaskType.CREATE_CUSTOMER:
        if not normalized.fields.get("name"):
            return ValidationResult(normalized, blocking_error="Customer creation requires customer name")

    if normalized.task_type == TaskType.UPDATE_CUSTOMER:
        if not normalized.match_fields:
            return ValidationResult(normalized, blocking_error="Customer update requires identifying fields")
        if not normalized.fields:
            return ValidationResult(normalized, blocking_error="Customer update requires at least one mutable field")

    if normalized.task_type == TaskType.SEARCH_CUSTOMERS:
        normalized.fields.setdefault("fields", "id,name,email,organizationNumber")
        normalized.fields.setdefault("count", 100)

    if normalized.task_type == TaskType.CREATE_PRODUCT:
        if not normalized.fields.get("name"):
            return ValidationResult(normalized, blocking_error="Product creation requires product name")

    if normalized.task_type == TaskType.CREATE_PROJECT:
        if not normalized.fields.get("name"):
            return ValidationResult(normalized, blocking_error="Project creation requires project name")
        if "customer" not in normalized.related_entities:
            warnings.append("Project creation has no linked customer; this is risky")

    if normalized.task_type == TaskType.CREATE_DEPARTMENT:
        if not normalized.fields.get("name"):
            return ValidationResult(normalized, blocking_error="Department creation requires department name")

    if normalized.task_type in {TaskType.CREATE_ORDER, TaskType.CREATE_INVOICE}:
        if "customer" not in normalized.related_entities:
            return ValidationResult(normalized, blocking_error="Order/invoice creation requires customer reference")
        if "product" not in normalized.related_entities:
            warnings.append("Order/invoice creation has no product reference; this is risky")

    if normalized.task_type == TaskType.CREATE_TRAVEL_EXPENSE:
        warnings.append("Travel expense flow is still high risk and only lightly validated")
        if "amount" not in normalized.fields:
            return ValidationResult(normalized, blocking_error="Travel expense creation requires amount")

    if normalized.task_type == TaskType.DELETE_TRAVEL_EXPENSE and "travel_expense_id" not in normalized.fields:
        warnings.append("Delete travel expense without explicit id will fall back to first available record")

    if normalized.task_type == TaskType.DELETE_VOUCHER and "voucher_id" not in normalized.fields:
        return ValidationResult(normalized, blocking_error="Voucher deletion requires voucher id")

    if normalized.task_type == TaskType.LIST_LEDGER_ACCOUNTS:
        normalized.fields.setdefault("fields", "id,number,name")
        normalized.fields.setdefault("count", 100)

    if normalized.task_type == TaskType.LIST_LEDGER_POSTINGS:
        normalized.fields.setdefault("fields", "id,date,amount,description")
        normalized.fields.setdefault("count", 100)

    safety = "safe"
    if warnings:
        safety = "risky"

    normalized.notes.extend(warnings)
    return ValidationResult(normalized, warnings=warnings, safety=safety)
