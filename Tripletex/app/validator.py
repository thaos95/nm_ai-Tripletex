import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from app.schemas import ParsedTask, TaskType

_logger = logging.getLogger(__name__)


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
    explicit_lines = [
        value
        for key, value in task.related_entities.items()
        if key.startswith("order_line_") and isinstance(value, dict)
    ]
    return bool(
        order.get("id")
        or
        product.get("id")
        or product.get("name")
        or product.get("description")
        or order.get("description")
        or invoice.get("description")
        or any(
            line.get("id")
            or line.get("name")
            or line.get("description")
            or line.get("productNumber")
            for line in explicit_lines
        )
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
    elif normalized.task_type == TaskType.UPDATE_TRAVEL_EXPENSE:
        _normalize_travel_expense(normalized)

    _normalize_related_entity_aliases(normalized)

    allowed_fields: Dict[TaskType, Set[str]] = {
        TaskType.CREATE_EMPLOYEE: {
            "first_name", "last_name", "email", "employee_type", "birthDate", "dateOfBirth", "startDate", "userType",
            "nationalIdentityNumber", "bankAccountNumber", "employmentPercentage", "annualSalary", "occupationCode",
        },
        TaskType.UPDATE_EMPLOYEE: {"phoneNumberMobile", "email"},
        TaskType.LIST_EMPLOYEES: {"fields", "count"},
        TaskType.CREATE_CUSTOMER: {
            "name", "email", "isCustomer", "isSupplier", "organizationNumber", "phoneNumber",
        },
        TaskType.UPDATE_CUSTOMER: {"phoneNumber", "email"},
        TaskType.SEARCH_CUSTOMERS: {"fields", "count"},
        TaskType.CREATE_PRODUCT: {"name", "priceExcludingVatCurrency", "productNumber", "vatPercentage"},
        TaskType.CREATE_PROJECT: {"name", "startDate"},
        TaskType.CREATE_PROJECT_BILLING: {
            "name", "startDate", "invoiceDate", "invoiceDueDate", "orderDate", "deliveryDate",
            "fixedPriceAmountCurrency", "billingPercentage", "hourlyRateCurrency", "amount",
            "budget", "budgetAmount",
        },
        TaskType.CREATE_DEPARTMENT: {"name", "departmentNumber", "departmentNames"},
        TaskType.CREATE_ORDER: {"orderDate", "deliveryDate"},
        TaskType.CREATE_INVOICE: {
            "invoiceDate", "invoiceDueDate", "orderDate", "deliveryDate",
            "amount", "accountNumber", "sendByEmail", "markAsPaid",
            "paymentDate", "amountPaidCurrency", "paymentTypeId",
            "currency", "exchangeRate",
        },
        TaskType.CREATE_SUPPLIER_INVOICE: {
            "invoiceDate", "invoiceNumber", "amount", "accountNumber", "vatPercentage",
            "description", "invoiceDescription", "invoiceDueDate",
            "dueDate", "bankAccountNumber",
        },
        TaskType.CREATE_CREDIT_NOTE: {
            "invoiceDate", "invoiceDueDate", "orderDate", "deliveryDate", "amount", "creditNote",
        },
        TaskType.CREATE_DIMENSION_VOUCHER: {
            "date", "dimensionName", "dimensionValues", "selectedDimensionValue",
            "accountNumber", "amount", "description", "debitAccountNumber", "creditAccountNumber",
            "journalEntries",
        },
        TaskType.CREATE_PAYROLL_VOUCHER: {
            "date", "amount", "baseSalaryCurrency", "bonusCurrency", "email",
        },
        TaskType.CREATE_TRAVEL_EXPENSE: {
            "date", "amount", "distance", "title", "description", "name",
            "departmentName", "vatType", "vatTypeId", "expenseDate",
            "costDescription", "paymentType", "paymentTypeId",
            "project", "department", "costItems",
        },
        TaskType.UPDATE_TRAVEL_EXPENSE: {"date", "amount", "distance", "travel_expense_id"},
        TaskType.DELETE_TRAVEL_EXPENSE: {"travel_expense_id"},
        TaskType.DELETE_VOUCHER: {"voucher_id"},
        TaskType.REGISTER_PAYMENT: {
            "paymentDate", "invoiceDate", "amount", "amountPaidCurrency",
            "paidAmount", "paidAmountCurrency", "paymentTypeId",
            "currency", "exchangeRate", "markAsPaid",
            "invoiceDueDate", "orderDate", "deliveryDate",
        },
        TaskType.LIST_LEDGER_ACCOUNTS: {"fields", "count"},
        TaskType.LIST_LEDGER_POSTINGS: {"fields", "count", "period_hint", "dateFrom", "dateTo"},
        TaskType.REVERSE_PAYMENT: {"invoiceDate", "invoiceDueDate", "orderDate", "amount", "paymentDate"},
    }
    warnings.extend(_drop_unknown_fields(normalized, allowed_fields))

    # KB-driven forbidden fields check — catch fields that would cause API errors
    try:
        from app.kb import get_forbidden_fields
        task_type_str = normalized.task_type.value if isinstance(normalized.task_type, TaskType) else str(normalized.task_type)
        forbidden = get_forbidden_fields(task_type_str)
        for fb in forbidden:
            if fb in normalized.fields:
                _logger.info("kb_removing_forbidden_field task=%s field=%s", task_type_str, fb)
                del normalized.fields[fb]
                warnings.append(f"Removed forbidden field '{fb}' for {task_type_str} (would cause API error)")
    except ImportError:
        pass

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

    if normalized.task_type == TaskType.CREATE_PROJECT_BILLING:
        if not normalized.fields.get("name") and normalized.related_entities.get("project", {}).get("name"):
            normalized.fields["name"] = normalized.related_entities["project"]["name"]
        if not normalized.fields.get("name"):
            return ValidationResult(normalized, blocking_error="Project billing requires project name")
        if "customer" not in normalized.related_entities:
            return ValidationResult(normalized, blocking_error="Project billing requires customer reference")
        # Use budget or fixedPriceAmountCurrency as fallback for amount
        if normalized.fields.get("amount") is None:
            fallback = (normalized.fields.get("budget")
                        or normalized.fields.get("budgetAmount")
                        or normalized.fields.get("fixedPriceAmountCurrency"))
            if fallback is not None:
                normalized.fields["amount"] = fallback
        normalized.related_entities.setdefault("order", {})
        normalized.related_entities.setdefault("invoice", {})
        normalized.related_entities["order"].setdefault(
            "description",
            normalized.related_entities["invoice"].get("description") or "Project partial billing",
        )
        normalized.related_entities["invoice"].setdefault(
            "description",
            normalized.related_entities["order"]["description"],
        )

    if normalized.task_type == TaskType.CREATE_DEPARTMENT:
        if not normalized.fields.get("name") and not normalized.fields.get("departmentNames"):
            return ValidationResult(normalized, blocking_error="Department creation requires department name")

    if normalized.task_type in {TaskType.CREATE_ORDER, TaskType.CREATE_INVOICE, TaskType.CREATE_CREDIT_NOTE}:
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

    if normalized.task_type == TaskType.CREATE_SUPPLIER_INVOICE:
        if "supplier" not in normalized.related_entities:
            return ValidationResult(normalized, blocking_error="Supplier invoice requires supplier reference")
        if not normalized.fields.get("invoiceNumber"):
            return ValidationResult(normalized, blocking_error="Supplier invoice requires supplier invoice number")
        if normalized.fields.get("amount") is None:
            return ValidationResult(normalized, blocking_error="Supplier invoice requires amount")

    if normalized.task_type == TaskType.CREATE_CREDIT_NOTE:
        normalized.fields["creditNote"] = True
        if normalized.fields.get("amount") is not None:
            normalized.fields["amount"] = -abs(float(normalized.fields["amount"]))

    if normalized.task_type == TaskType.REVERSE_PAYMENT:
        invoice = normalized.related_entities.setdefault("invoice", {})
        order = normalized.related_entities.get("order", {})
        description = invoice.get("description") or order.get("description")
        if "customer" not in normalized.related_entities:
            return ValidationResult(
                normalized,
                blocking_error="Payment reversal requires customer reference",
            )
        if not description and normalized.fields.get("amount") is None:
            return ValidationResult(
                normalized,
                blocking_error="Payment reversal requires invoice reference or amount",
            )
        if description:
            invoice["description"] = description
        invoice.setdefault("amountExcludingVatCurrency", normalized.fields.get("amount"))

    if normalized.task_type == TaskType.CREATE_DIMENSION_VOUCHER:
        has_debit_credit = normalized.fields.get("debitAccountNumber") and normalized.fields.get("creditAccountNumber")
        has_dimension = normalized.fields.get("dimensionName")
        has_journal_entries = normalized.fields.get("journalEntries") and len(normalized.fields["journalEntries"]) >= 1
        if has_dimension:
            # Full dimension voucher path: needs dimension values + account + amount
            if not normalized.fields.get("dimensionValues"):
                return ValidationResult(normalized, blocking_error="Dimension voucher requires dimension values")
            if not normalized.fields.get("selectedDimensionValue"):
                first_value = str(normalized.fields["dimensionValues"]).split("||")[0]
                normalized.fields["selectedDimensionValue"] = first_value
            if normalized.fields.get("accountNumber") is None:
                return ValidationResult(normalized, blocking_error="Dimension voucher requires account number")
            if normalized.fields.get("amount") is None:
                return ValidationResult(normalized, blocking_error="Dimension voucher requires amount")
        elif has_debit_credit:
            # Simple journal entry path: debit/credit accounts + amount
            if normalized.fields.get("amount") is None:
                return ValidationResult(normalized, blocking_error="Journal entry requires amount")
        elif has_journal_entries:
            # Multi-entry journal path: journalEntries extracted from parsing
            if not normalized.fields.get("amount"):
                normalized.fields["amount"] = normalized.fields["journalEntries"][0].get("amount", 0)
            if not normalized.fields.get("debitAccountNumber"):
                normalized.fields["debitAccountNumber"] = normalized.fields["journalEntries"][0].get("debitAccountNumber")
            if not normalized.fields.get("creditAccountNumber"):
                normalized.fields["creditAccountNumber"] = normalized.fields["journalEntries"][0].get("creditAccountNumber")
        else:
            return ValidationResult(normalized, blocking_error="Dimension voucher requires debit/credit accounts or dimension name")

    if normalized.task_type == TaskType.CREATE_PAYROLL_VOUCHER:
        if normalized.fields.get("amount") is None:
            return ValidationResult(normalized, blocking_error="Payroll voucher requires salary amount")
        if "employee" not in normalized.related_entities and normalized.fields.get("email"):
            normalized.related_entities["employee"] = {"email": normalized.fields["email"]}
        return ValidationResult(
            normalized,
            blocking_error="Payroll voucher fallback is not supported safely with the current Tripletex contract",
        )

    if normalized.task_type == TaskType.CREATE_TRAVEL_EXPENSE:
        warnings.append("Travel expense flow is still high risk and only lightly validated")
        if "amount" not in normalized.fields:
            return ValidationResult(normalized, blocking_error="Travel expense creation requires amount")

    if normalized.task_type == TaskType.UPDATE_TRAVEL_EXPENSE:
        warnings.append("Travel expense update flow is still high risk and only lightly validated")
        if "travel_expense_id" not in normalized.fields:
            return ValidationResult(normalized, blocking_error="Travel expense update requires expense id")
        mutable_fields = dict(normalized.fields)
        mutable_fields.pop("travel_expense_id", None)
        if not mutable_fields:
            return ValidationResult(normalized, blocking_error="Travel expense update requires at least one mutable field")

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
