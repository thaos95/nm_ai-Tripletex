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
            task.fields["phoneNumberMobile"] = "".join(ch for ch in str(task.fields.pop(alias)) if ch.isdigit() or ch == "+")
            break


def _normalize_customer_phone(task: ParsedTask) -> None:
    for alias in ("phone", "phoneNumberWork", "phoneNumberMobile"):
        if alias in task.fields:
            task.fields["phoneNumber"] = "".join(ch for ch in str(task.fields.pop(alias)) if ch.isdigit() or ch == "+")
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
    organization_number = task.fields.get("organizationNumber") or task.fields.pop("orgNumber", None)
    if organization_number is None:
        return
    digits_only = "".join(ch for ch in str(organization_number) if ch.isdigit())
    if len(digits_only) == 9:
        task.fields["organizationNumber"] = digits_only
    else:
        task.fields.pop("organizationNumber", None)
    if "email" in task.fields:
        task.fields["email"] = str(task.fields["email"]).strip().lower()


def _normalize_customer_address_fields(task: ParsedTask) -> None:
    address_fields = {}
    for source_key, target_key in (
        ("address", "address"),
        ("addressStreet", "addressStreet"),
        ("postalCode", "postalCode"),
        ("zip", "postalCode"),
        ("zipCode", "postalCode"),
        ("city", "city"),
        ("country", "country"),
    ):
        if source_key in task.fields:
            address_fields[target_key] = task.fields.pop(source_key)

    if not address_fields:
        return

    customer_address = task.related_entities.setdefault("customer_address", {})
    customer_address.update(address_fields)


def _normalize_related_entity_aliases(task: ParsedTask) -> None:
    for alias in ("projectManager", "projectLeader"):
        if alias in task.related_entities:
            canonical = task.related_entities.setdefault("project_manager", {})
            canonical.update(task.related_entities.pop(alias))

    if "employee" in task.related_entities and "project_manager" not in task.related_entities:
        task.related_entities["project_manager"] = dict(task.related_entities["employee"])

    for key, value in list(task.related_entities.items()):
        if not isinstance(value, dict):
            continue

        if "orgNumber" in value and "organizationNumber" not in value:
            value["organizationNumber"] = value.pop("orgNumber")

        if "organizationNumber" in value:
            digits_only = "".join(ch for ch in str(value["organizationNumber"]) if ch.isdigit())
            if len(digits_only) == 9:
                value["organizationNumber"] = digits_only

        if "firstName" in value and "first_name" not in value:
            value["first_name"] = value.pop("firstName")
        if "lastName" in value and "last_name" not in value:
            value["last_name"] = value.pop("lastName")

        if "email" in value:
            value["email"] = str(value["email"]).strip().lower()

        for phone_key in ("phoneNumber", "phoneNumberMobile", "mobilePhoneNumber"):
            if phone_key in value:
                value[phone_key] = "".join(ch for ch in str(value[phone_key]) if ch.isdigit() or ch == "+")

        if key == "customer_address":
            if "address" in value and "addressStreet" not in value:
                value["addressStreet"] = value.pop("address")


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


def _has_order_line_source(task: ParsedTask) -> bool:
    product = task.related_entities.get("product", {})
    order = task.related_entities.get("order", {})
    invoice = task.related_entities.get("invoice", {})
    return bool(
        product.get("id")
        or product.get("name")
        or product.get("description")
        or order.get("description")
        or invoice.get("description")
    )


def validate_and_normalize_task(task: ParsedTask) -> ValidationResult:
    normalized = _copy_task(task)
    warnings: List[str] = []

    if normalized.task_type == TaskType.UPDATE_EMPLOYEE:
        _normalize_phone_fields(normalized)
    elif normalized.task_type == TaskType.UPDATE_CUSTOMER:
        _normalize_customer_phone(normalized)
    elif normalized.task_type == TaskType.CREATE_CUSTOMER:
        _normalize_customer_fields(normalized)
        _normalize_customer_address_fields(normalized)
    elif normalized.task_type == TaskType.CREATE_TRAVEL_EXPENSE:
        _normalize_travel_expense(normalized)

    _normalize_related_entity_aliases(normalized)

    allowed_fields: Dict[TaskType, Set[str]] = {
        TaskType.CREATE_EMPLOYEE: {"first_name", "last_name", "email", "employee_type", "birthDate", "startDate"},
        TaskType.UPDATE_EMPLOYEE: {"phoneNumberMobile", "email"},
        TaskType.LIST_EMPLOYEES: {"fields", "count"},
        TaskType.CREATE_CUSTOMER: {
            "name",
            "email",
            "isCustomer",
            "isSupplier",
            "organizationNumber",
            "phoneNumber",
        },
        TaskType.UPDATE_CUSTOMER: {"phoneNumber", "email"},
        TaskType.SEARCH_CUSTOMERS: {"fields", "count"},
        TaskType.CREATE_PRODUCT: {"name", "priceExcludingVatCurrency", "productNumber", "vatPercentage"},
        TaskType.CREATE_PROJECT: {"name", "startDate"},
        TaskType.CREATE_DEPARTMENT: {"name", "departmentNumber", "departmentNames"},
        TaskType.CREATE_ORDER: {"orderDate", "deliveryDate"},
        TaskType.CREATE_INVOICE: {
            "invoiceDate",
            "invoiceDueDate",
            "orderDate",
            "deliveryDate",
            "amount",
            "sendByEmail",
            "markAsPaid",
            "paymentDate",
            "amountPaidCurrency",
        },
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
        normalized.match_fields.setdefault("organizationNumber", normalized.fields.get("organizationNumber"))

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
        if not normalized.fields.get("name") and not normalized.fields.get("departmentNames"):
            return ValidationResult(normalized, blocking_error="Department creation requires department name")

    if normalized.task_type in {TaskType.CREATE_ORDER, TaskType.CREATE_INVOICE}:
        if "customer" not in normalized.related_entities:
            return ValidationResult(normalized, blocking_error="Order/invoice creation requires customer reference")
        if not _has_order_line_source(normalized):
            return ValidationResult(
                normalized,
                blocking_error="Order/invoice creation requires product reference or line description",
            )
        if "product" not in normalized.related_entities:
            warnings.append("Order/invoice creation has no product reference; this is risky")

    if normalized.task_type == TaskType.CREATE_INVOICE and normalized.fields.get("markAsPaid"):
        normalized.fields.setdefault("paymentDate", normalized.fields.get("invoiceDate"))
        if normalized.fields.get("amountPaidCurrency") is None and normalized.fields.get("amount") is not None:
            normalized.fields["amountPaidCurrency"] = normalized.fields["amount"]

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
