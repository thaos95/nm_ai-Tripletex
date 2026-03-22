from datetime import date, datetime, timedelta
import json
from typing import Any, Dict, List, Optional

from app.clients.tripletex import TripletexClient, TripletexClientError
from app.config import settings
from app.error_handling import (
    TripletexErrorCategory,
    classify_tripletex_error,
    extract_tripletex_request_id,
    extract_validation_messages,
    is_company_bank_account_missing,
)
from app.logging_utils import get_logger
from app.schemas import ExecutionPlan, ExecutionResult, OperationResult, TaskType

logger = get_logger()


class MissingPrerequisiteError(Exception):
    def __init__(self, stage: str, task_type: TaskType, issue: str, payload: Dict[str, Any], request_id: Optional[str], validation_messages: List[str]):
        super().__init__(f"{issue} missing prerequisite for {task_type}")
        self.stage = stage
        self.task_type = task_type
        self.issue = issue
        self.payload = payload
        self.request_id = request_id
        self.validation_messages = validation_messages


def _extract_id(response: Dict[str, Any]) -> Optional[int]:
    if "value" in response and isinstance(response["value"], dict):
        return response["value"].get("id")
    return response.get("id")


def _verify_resource_exists(client: TripletexClient, resource: str, resource_id: Optional[int], operations: list, operation_name: str) -> None:
    if resource_id is None:
        operations.append(OperationResult(name="{0}-verify".format(operation_name), payload={"verified": False, "reason": "missing-id"}))
        return
    try:
        resource_payload = client.find_by_id(resource, int(resource_id))
    except TripletexClientError as exc:
        operations.append(
            OperationResult(
                name="{0}-verify".format(operation_name),
                resource_id=int(resource_id),
                payload={"verified": False, "reason": str(exc)},
            )
        )
        return
    operations.append(
        OperationResult(
            name="{0}-verify".format(operation_name),
            resource_id=int(resource_id),
            payload={"verified": bool(resource_payload), "resource": resource_payload},
        )
    )


def _compact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return dict((key, value) for key, value in payload.items() if value is not None)


def _today_iso() -> str:
    return date.today().isoformat()


def _build_employee_payload(spec: Dict[str, Any], department_id: Optional[int]) -> Dict[str, Any]:
    user_type = spec.get("userType", "STANDARD")
    if isinstance(user_type, int):
        user_type = {1: "STANDARD", 2: "EXTENDED", 3: "NO_ACCESS"}.get(user_type, "STANDARD")
    payload = {
        "firstName": spec.get("first_name"),
        "lastName": spec.get("last_name"),
        "email": spec.get("email"),
        "dateOfBirth": spec.get("birthDate") or spec.get("dateOfBirth"),
        "startDate": spec.get("startDate") or _today_iso(),
        "userType": user_type,
        "department": {"id": department_id} if department_id is not None else None,
    }
    return _compact_payload(payload)


def _can_create_employee_prerequisite(spec: Dict[str, Any]) -> bool:
    return bool(spec.get("email") and spec.get("first_name"))


def _build_customer_payload(spec: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "name": spec.get("name"),
        "email": spec.get("email"),
        "isCustomer": spec.get("isCustomer"),
        "isSupplier": spec.get("isSupplier"),
        "organizationNumber": spec.get("organizationNumber"),
        "phoneNumber": spec.get("phoneNumber"),
    }
    return _compact_payload(payload)


def _build_supplier_payload(spec: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "name": spec.get("name"),
        "email": spec.get("email"),
        "organizationNumber": spec.get("organizationNumber"),
        "isSupplier": True,
    }
    return _compact_payload(payload)


def _can_create_customer_prerequisite(spec: Dict[str, Any]) -> bool:
    return bool(spec.get("name") and (spec.get("organizationNumber") or spec.get("email")))


def _can_create_supplier_prerequisite(spec: Dict[str, Any]) -> bool:
    return bool(spec.get("name") and (spec.get("organizationNumber") or spec.get("email")))


def _build_product_payload(spec: Dict[str, Any]) -> Dict[str, Any]:
    payload = {"name": spec.get("name")}
    if spec.get("priceExcludingVatCurrency") is not None:
        payload["priceExcludingVatCurrency"] = spec["priceExcludingVatCurrency"]
    return _compact_payload(payload)


def _build_ledger_account_payload(number: str, name: str) -> Dict[str, Any]:
    return _compact_payload({"number": int(number), "name": name})


def _can_create_product_prerequisite(spec: Dict[str, Any]) -> bool:
    return bool(spec.get("name") and spec.get("priceExcludingVatCurrency") is not None)


def _build_project_payload(fields: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "name": fields.get("name"),
        "startDate": fields.get("startDate") or _today_iso(),
    }
    return _compact_payload(payload)


def _build_invoice_payload(fields: Dict[str, Any], customer_id: int, order_id: Optional[int]) -> Dict[str, Any]:
    today = _today_iso()
    payload = {
        "invoiceDate": fields.get("invoiceDate") or today,
        "invoiceDueDate": fields.get("invoiceDueDate") or fields.get("invoiceDate") or today,
        "isCreditNote": fields.get("creditNote") or fields.get("isCreditNote"),
        "customer": {"id": customer_id},
        "orders": [{"id": order_id}] if order_id is not None else [],
    }
    return _compact_payload(payload)


def _build_supplier_invoice_payload(fields: Dict[str, Any], supplier_id: int) -> Dict[str, Any]:
    today = _today_iso()
    header = _compact_payload({
        "invoiceDate": fields.get("invoiceDate") or today,
        "invoiceNumber": fields.get("invoiceNumber"),
        "vendorId": supplier_id,
        "invoiceAmount": fields.get("amount"),
        "dueDate": fields.get("invoiceDueDate") or fields.get("invoiceDate") or today,
        "description": fields.get("description"),
    })
    order_lines = _build_incoming_invoice_lines(fields)
    payload: Dict[str, Any] = {"invoiceHeader": header}
    if order_lines:
        payload["orderLines"] = order_lines
    return payload


def _build_incoming_invoice_lines(fields: Dict[str, Any]) -> Optional[list]:
    amount = fields.get("amount")
    account_number = fields.get("accountNumber")
    if amount is None:
        return None
    line: Dict[str, Any] = {
        "amountInclVat": amount,
        "externalId": fields.get("invoiceNumber") or "line-1",
    }
    if account_number is not None:
        line["accountId"] = int(account_number)
    description = fields.get("description") or fields.get("invoiceDescription")
    if description:
        line["description"] = description
    # Note: incomingInvoice orderLines do NOT accept vatType or vatPercentage.
    # VAT is derived from the account number by Tripletex.
    return [_compact_payload(line)]


# Standard Norwegian VAT type mappings
_VAT_TYPE_MAP = {
    25: 3,   # 25% MVA (standard)
    15: 4,   # 15% MVA (food)
    12: 32,  # 12% MVA (transport/hotels)
    0: 6,    # 0% MVA (exempt)
}


def _vat_percentage_to_type_id(pct: float) -> Optional[int]:
    """Convert a VAT percentage to Tripletex vatType ID."""
    rounded = round(pct)
    return _VAT_TYPE_MAP.get(rounded)


def _validate_supplier_invoice_fields(fields: Dict[str, Any]) -> None:
    required = ["invoiceNumber", "invoiceDate", "amount", "accountNumber"]
    missing = [name for name in required if not fields.get(name)]
    if missing:
        raise ValueError(
            "Supplier invoice missing required fields: {0}".format(", ".join(missing))
        )


def _build_minimal_invoice_payload(
    fields: Dict[str, Any],
    customer_id: int,
    order_id: Optional[int],
    *,
    include_due_date: bool = False,
) -> Dict[str, Any]:
    payload = {
        "invoiceDate": fields.get("invoiceDate"),
        "invoiceDueDate": fields.get("invoiceDueDate") if include_due_date else None,
        "isCreditNote": fields.get("creditNote") or fields.get("isCreditNote"),
        "customer": {"id": customer_id},
        "orders": [{"id": order_id}] if order_id is not None else [],
    }
    return _compact_payload(payload)


def _build_invoice_payment_payload(fields: Dict[str, Any]) -> Dict[str, Any]:
    # Determine the correct payment amount
    # paidAmountCurrency = amount in the invoice's currency (e.g., EUR)
    # paidAmount = amount in NOK (or accounting currency)
    amount = fields.get("amount")
    paid_currency = fields.get("paidAmountCurrency") or fields.get("amountPaidCurrency")
    exchange_rate = fields.get("exchangeRate")

    # Guard against exchange rate being mistakenly placed in amount fields
    # If paid_currency looks like an exchange rate (small number compared to amount), use amount instead
    if paid_currency is not None and amount is not None:
        try:
            pc = float(paid_currency)
            am = float(amount)
            if am > 0 and pc > 0 and pc < am * 0.01:
                # paid_currency is likely an exchange rate, not an amount
                logger.warning("payment_amount_fix: paidCurrency=%s looks like exchange rate, using amount=%s", pc, am)
                paid_currency = amount
        except (TypeError, ValueError):
            pass

    if paid_currency is None:
        paid_currency = amount

    # Calculate NOK amount if we have currency amount and exchange rate
    paid_nok = paid_currency
    if exchange_rate and paid_currency:
        try:
            paid_nok = float(paid_currency) * float(exchange_rate)
        except (TypeError, ValueError):
            pass

    payload = {
        "paymentDate": fields.get("paymentDate"),
        "paidAmount": paid_nok,
        "paidAmountCurrency": paid_currency,
        "paymentTypeId": fields.get("paymentTypeId", 6),
    }
    return _compact_payload(payload)


def _collect_bank_account_spec(fields: Dict[str, Any], related: Dict[str, Any]) -> Optional[Dict[str, str]]:
    spec = dict(related.get("companyBankAccount", {}))
    spec.setdefault("bankAccountNumber", fields.get("companyBankAccountNumber"))
    spec.setdefault("bankName", fields.get("companyBankAccountName"))
    spec.setdefault("bankAccountType", fields.get("companyBankAccountType"))
    if not spec.get("bankAccountNumber") and settings.default_bank_account_number:
        spec["bankAccountNumber"] = settings.default_bank_account_number
    if not spec.get("bankName") and settings.default_bank_account_name:
        spec["bankName"] = settings.default_bank_account_name
    if not spec.get("bankAccountType") and settings.default_bank_account_type:
        spec["bankAccountType"] = settings.default_bank_account_type
    return spec if spec.get("bankAccountNumber") else None


def _ensure_company_bank_account(client: TripletexClient, spec: Dict[str, str], operations: list) -> None:
    if not settings.enable_bank_account_creation:
        return
    payload = {
        "bankAccountNumber": spec["bankAccountNumber"],
        "bankName": spec.get("bankName"),
        "bankAccountType": spec.get("bankAccountType"),
    }
    try:
        response = client.create_resource("company/bankAccount", _compact_payload(payload))
        operations.append(
            OperationResult(
                name="create-company-bank-account",
                payload={"bankAccount": response},
            )
        )
    except TripletexClientError as exc:
        logger.warning(
            "bank_account_creation_failed payload=%s error=%s",
            json.dumps(payload, ensure_ascii=False, default=str),
            str(exc),
        )


# Hardcoded Norwegian test bank account for sandbox environments
_FALLBACK_BANK_ACCOUNT_NUMBER = "12345678903"


def _force_create_company_bank_account(client: TripletexClient, operations: list) -> None:
    """Create a company bank account unconditionally — used when invoice creation fails due to missing bank account."""
    payload = {"bankAccountNumber": _FALLBACK_BANK_ACCOUNT_NUMBER}
    try:
        response = client.create_resource("company/bankAccount", payload)
        operations.append(
            OperationResult(
                name="auto-create-company-bank-account",
                payload={"bankAccount": response},
            )
        )
        logger.info("auto_created_company_bank_account response=%s", response)
    except TripletexClientError as exc:
        logger.warning("auto_create_bank_account_failed error=%s", str(exc))


def _should_retry_invoice_with_minimal_payload(fields: Dict[str, Any], exc: TripletexClientError) -> bool:
    if fields.get("creditNote"):
        return False
    classified = classify_tripletex_error(exc)
    return classified.category == TripletexErrorCategory.VALIDATION_GENERIC


def _build_travel_expense_payload(fields: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    title = fields.get("title") or fields.get("description") or fields.get("name")
    if title:
        payload["title"] = title
    if fields.get("project"):
        payload["project"] = fields["project"]
    if fields.get("department"):
        payload["department"] = fields["department"]
    return _compact_payload(payload)


def _build_travel_cost_payload(expense_id: int, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    amount = fields.get("amount")
    if amount is None:
        return None
    travel_date = fields.get("expenseDate") or fields.get("date") or _today_iso()
    cost: Dict[str, Any] = {
        "travelExpense": {"id": expense_id},
        "date": travel_date,
        "amountCurrencyIncVat": float(amount),
    }
    description = fields.get("costDescription") or fields.get("description") or fields.get("title")
    if description:
        cost["comments"] = description
    vat_type = fields.get("vatType") or fields.get("vatTypeId")
    if vat_type and str(vat_type).isdigit():
        cost["vatType"] = {"id": int(vat_type)}
    payment_type = fields.get("paymentType") or fields.get("paymentTypeId")
    if payment_type and str(payment_type).isdigit():
        cost["paymentType"] = {"id": int(payment_type)}
    # paymentType is required — will be resolved at creation time if not set
    return _compact_payload(cost)


def _build_dimension_payload(fields: Dict[str, Any]) -> Dict[str, Any]:
    return _compact_payload({"dimensionName": fields.get("dimensionName")})


def _build_dimension_value_payload(dimension_id: int, value_name: str) -> Dict[str, Any]:
    return _compact_payload({"accountingDimensionName": {"id": dimension_id}, "description": value_name})


def _build_voucher_payload(
    client: TripletexClient,
    fields: Dict[str, Any],
    description: str,
    account_number: str,
    amount: float,
    dimension_value_id: Optional[int] = None,
    credit_account_number: str = "2400",
) -> Dict[str, Any]:
    debit_id = _resolve_account_id(client, account_number)
    credit_id = _resolve_account_id(client, credit_account_number)
    debit_ref: Dict[str, Any] = {"id": debit_id} if debit_id else {"number": int(account_number)}
    credit_ref: Dict[str, Any] = {"id": credit_id} if credit_id else {"number": int(credit_account_number)}

    debit_line: Dict[str, Any] = {
        "account": debit_ref,
        "amount": abs(amount),
        "description": description,
    }
    if dimension_value_id is not None:
        debit_line["freeAccountingDimension1"] = {"id": dimension_value_id}

    credit_line: Dict[str, Any] = {
        "account": credit_ref,
        "amount": -abs(amount),
        "description": description,
    }
    payload = {
        "date": fields.get("date") or _today_iso(),
        "description": description,
        "postings": [debit_line, credit_line],
    }
    return _compact_payload(payload)


def _resolve_account_id(client: TripletexClient, account_number: str) -> Optional[int]:
    """Look up a ledger account by number and return its ID."""
    try:
        resp = client.list_resource("ledger/account", fields="id,number,name", count=1, number=int(account_number))
        for item in resp.get("values", []):
            if item.get("id"):
                return int(item["id"])
    except Exception:
        pass
    return None


def _create_journal_voucher(
    client: TripletexClient,
    operations: list,
    *,
    debit_account: str,
    credit_account: str,
    amount: float,
    date: str,
    description: str,
    operation_name: str = "create-journal-voucher",
) -> Optional[Dict[str, Any]]:
    """Create a balanced journal voucher with two postings, using account IDs."""
    debit_id = _resolve_account_id(client, debit_account)
    credit_id = _resolve_account_id(client, credit_account)

    debit_ref: Dict[str, Any] = {"id": debit_id} if debit_id else {"number": int(debit_account)}
    credit_ref: Dict[str, Any] = {"id": credit_id} if credit_id else {"number": int(credit_account)}

    voucher_payload = {
        "date": date,
        "description": description,
        "postings": [
            {"account": debit_ref, "amount": abs(amount), "description": description},
            {"account": credit_ref, "amount": -abs(amount), "description": description},
        ],
    }
    logger.info("creating_journal_voucher payload=%s", voucher_payload)
    response = client.create_resource("ledger/voucher", voucher_payload)
    operations.append(
        OperationResult(name=operation_name, resource_id=_extract_id(response), payload=response)
    )
    return response


def _resolve_customer(
    client: TripletexClient,
    spec: Dict[str, Any],
    operations: list,
    allow_create: bool = True,
) -> Optional[int]:
    if spec.get("id") is not None:
        customer_id = int(spec["id"])
        operations.append(OperationResult(name="reuse-customer", resource_id=customer_id, payload={"id": customer_id}))
        return customer_id

    match_fields = {}
    if spec.get("email"):
        match_fields["email"] = spec["email"]
    elif spec.get("organizationNumber"):
        match_fields["organizationNumber"] = spec["organizationNumber"]
    elif spec.get("name"):
        match_fields["name"] = spec["name"]

    existing = client.find_single("customer", match_fields) if match_fields else None
    if existing:
        customer_id = existing["id"]
        operations.append(OperationResult(name="resolve-customer", resource_id=customer_id, payload=existing))
        return customer_id

    if not allow_create:
        return None

    payload = {"name": spec.get("name", "Unknown Customer"), "isCustomer": True}
    payload.update(_build_customer_payload(spec))
    response = client.create_resource("customer", payload)
    customer_id = _extract_id(response)
    operations.append(OperationResult(name="create-customer", resource_id=customer_id, payload=response))
    return customer_id


def _resolve_employee(
    client: TripletexClient,
    spec: Dict[str, Any],
    operations: list,
    allow_create: bool = True,
) -> Optional[int]:
    if spec.get("id") is not None:
        employee_id = int(spec["id"])
        operations.append(OperationResult(name="reuse-employee", resource_id=employee_id, payload={"id": employee_id}))
        return employee_id

    match_fields = {}
    if spec.get("email"):
        match_fields["email"] = spec["email"]
    else:
        if spec.get("first_name"):
            match_fields["first_name"] = spec["first_name"]
        if spec.get("last_name"):
            match_fields["last_name"] = spec["last_name"]

    existing = client.find_single("employee", match_fields) if match_fields else None
    if existing:
        employee_id = existing["id"]
        operations.append(OperationResult(name="resolve-employee", resource_id=employee_id, payload=existing))
        return employee_id

    if not allow_create:
        return None

    department_id = _resolve_department(client, operations)
    payload = _build_employee_payload(spec, department_id)
    response = client.create_resource("employee", payload)
    employee_id = _extract_id(response)
    operations.append(OperationResult(name="create-employee", resource_id=employee_id, payload=response))
    return employee_id


def _resolve_supplier(
    client: TripletexClient,
    spec: Dict[str, Any],
    operations: list,
    allow_create: bool = True,
) -> Optional[int]:
    if spec.get("id") is not None:
        supplier_id = int(spec["id"])
        operations.append(OperationResult(name="reuse-supplier", resource_id=supplier_id, payload={"id": supplier_id}))
        return supplier_id

    match_fields = {}
    if spec.get("organizationNumber"):
        match_fields["organizationNumber"] = spec["organizationNumber"]
    elif spec.get("email"):
        match_fields["email"] = spec["email"]
    elif spec.get("name"):
        match_fields["name"] = spec["name"]

    existing = client.find_single("supplier", match_fields) if match_fields else None
    if existing:
        supplier_id = existing["id"]
        operations.append(OperationResult(name="resolve-supplier", resource_id=supplier_id, payload=existing))
        return supplier_id

    if not allow_create:
        return None

    response = client.create_resource("supplier", _build_supplier_payload(spec))
    supplier_id = _extract_id(response)
    operations.append(OperationResult(name="create-supplier", resource_id=supplier_id, payload=response))
    return supplier_id


def _resolve_fallback_project_manager(client: TripletexClient, operations: list) -> Optional[int]:
    employees = client.list_resource("employee", fields="id,firstName,lastName,employments,*", count=20)
    for employee in employees.get("values", []):
        if employee.get("employments"):
            employee_id = employee["id"]
            operations.append(
                OperationResult(name="fallback-project-manager", resource_id=employee_id, payload=employee)
            )
            return employee_id
    return None


def _resolve_project_manager(client: TripletexClient, spec: Dict[str, Any], operations: list) -> Optional[int]:
    if not spec:
        return None

    if spec.get("id") is not None:
        employee_id = int(spec["id"])
        operations.append(OperationResult(name="reuse-project-manager", resource_id=employee_id, payload={"id": employee_id}))
        return employee_id

    match_fields = {}
    if spec.get("email"):
        match_fields["email"] = spec["email"]
    if spec.get("first_name"):
        match_fields["first_name"] = spec["first_name"]
    if spec.get("last_name"):
        match_fields["last_name"] = spec["last_name"]
    if not match_fields and spec.get("name"):
        name_parts = str(spec["name"]).split()
        if name_parts:
            match_fields["first_name"] = name_parts[0]
        if len(name_parts) > 1:
            match_fields["last_name"] = " ".join(name_parts[1:])

    if not match_fields:
        return _resolve_fallback_project_manager(client, operations)

    employee = client.find_single("employee", match_fields, fields="id,firstName,lastName,employments,*")
    if employee and employee.get("employments"):
        employee_id = employee["id"]
        operations.append(OperationResult(name="resolve-project-manager", resource_id=employee_id, payload=employee))
        return employee_id

    return _resolve_fallback_project_manager(client, operations)


def _resolve_product(
    client: TripletexClient,
    spec: Dict[str, Any],
    operations: list,
    allow_create: bool = True,
) -> Optional[int]:
    if spec.get("id") is not None:
        product_id = int(spec["id"])
        operations.append(OperationResult(name="reuse-product", resource_id=product_id, payload={"id": product_id}))
        return product_id

    match_fields = {}
    if spec.get("name"):
        match_fields["name"] = spec["name"]

    existing = client.find_single("product", match_fields) if match_fields else None
    if existing:
        product_id = existing["id"]
        operations.append(OperationResult(name="resolve-product", resource_id=product_id, payload=existing))
        return product_id

    if not allow_create or not spec.get("name"):
        return None

    response = client.create_resource("product", _build_product_payload(spec))
    product_id = _extract_id(response)
    operations.append(OperationResult(name="create-product", resource_id=product_id, payload=response))
    return product_id


def _extract_order_line_specs(related_entities: Dict[str, Dict[str, Any]]) -> list:
    specs = []
    for key, value in related_entities.items():
        if key.startswith("order_line_") and isinstance(value, dict):
            specs.append((key, value))
    specs.sort(key=lambda item: item[0])
    return [dict(spec) for _, spec in specs]


def _resolve_department(client: TripletexClient, operations: list) -> Optional[int]:
    departments = client.list_resource("department", fields="id,name", count=1)
    values = departments.get("values", [])
    if not values:
        return None
    department_id = values[0]["id"]
    operations.append(OperationResult(name="resolve-department", resource_id=department_id, payload=departments))
    return department_id


def _resolve_ledger_account(
    client: TripletexClient,
    account_number: str,
    operations: list,
    *,
    create_name: str = "Salgsinntekt",
) -> Optional[str]:
    try:
        existing = client.find_single("ledger/account", {"number": account_number}, fields="id,number,name")
    except TripletexClientError as exc:
        if "404" in str(exc) or "/ledger/account" in str(exc):
            operations.append(OperationResult(name="skip-ledger-account", payload={"reason": "endpoint-unavailable"}))
            return None
        raise
    if existing:
        resolved_number = str(existing.get("number") or account_number)
        operations.append(
            OperationResult(
                name="resolve-ledger-account",
                resource_id=existing.get("id"),
                payload=existing,
            )
        )
        return resolved_number
    operations.append(
        OperationResult(
            name="missing-ledger-account",
            payload={
                "reason": "not-found",
                "accountNumber": account_number,
                "supportedAction": "GET /ledger/account",
            },
        )
    )
    return None


def _create_order(
    client: TripletexClient,
    customer_id: int,
    product_id: Optional[int],
    parsed_fields: Dict[str, Any],
    product_spec: Dict[str, Any],
    operations: list,
    order_line_specs: Optional[list] = None,
    ledger_account_number: Optional[str] = None,
) -> Optional[int]:
    order_lines = []
    if order_line_specs:
        for spec in order_line_specs:
            line = {"count": int(spec.get("count", 1))}
            description = spec.get("description") or spec.get("name") or parsed_fields.get("description")
            if description:
                line["description"] = description
            order_lines.append(_compact_payload(line))
    else:
        line = {}
        if product_id is not None:
            line["product"] = {"id": product_id}
        elif ledger_account_number:
            line["account"] = {"number": ledger_account_number}
        description = product_spec.get("description") or parsed_fields.get("description")
        if description:
            line["description"] = description
        line["count"] = 1
        order_lines.append(_compact_payload(line))

    today = date.today().isoformat()
    order_payload = {
        "customer": {"id": customer_id},
        "orderDate": parsed_fields.get("orderDate") or parsed_fields.get("invoiceDate") or today,
        "deliveryDate": parsed_fields.get("deliveryDate")
        or parsed_fields.get("orderDate")
        or parsed_fields.get("invoiceDate")
        or today,
        "orderLines": order_lines,
    }
    response = client.create_resource("order", _compact_payload(order_payload))
    order_id = _extract_id(response)
    operations.append(OperationResult(name="create-order", resource_id=order_id, payload=response))
    return order_id


def _should_resolve_product_for_order_line(product_spec: Dict[str, Any]) -> bool:
    return not bool(product_spec.get("description"))


def _create_invoice_with_fallback(
    client: TripletexClient,
    fields: Dict[str, Any],
    customer_id: int,
    order_id: Optional[int],
    operations: list,
    related: Dict[str, Any],
    *,
    task_type: TaskType,
    operation_name: str,
    minimal_first: bool = False,
) -> Dict[str, Any]:
    bank_spec = _collect_bank_account_spec(fields, related)
    if bank_spec:
        _ensure_company_bank_account(client, bank_spec, operations)
    payload = (
        _build_minimal_invoice_payload(fields, customer_id, order_id)
        if minimal_first
        else _build_invoice_payload(fields, customer_id, order_id)
    )
    try:
        response = client.create_resource("invoice", payload)
    except TripletexClientError as exc:
        if is_company_bank_account_missing(exc):
            logger.warning(
                "company_bank_account_missing task_type=%s — auto-creating bank account and retrying",
                operation_name,
            )
            _force_create_company_bank_account(client, operations)
            # Retry invoice creation after bank account is in place
            response = client.create_resource("invoice", payload)
        elif minimal_first or not _should_retry_invoice_with_minimal_payload(fields, exc):
            raise
        else:
            fallback_payload = _build_minimal_invoice_payload(fields, customer_id, order_id)
            response = client.create_resource("invoice", fallback_payload)
            operations.append(
                OperationResult(name="invoice-fallback-to-minimal", payload=fallback_payload)
            )
        # If we reach here from the bank-account retry, fall through to normal return
    operations.append(OperationResult(name=operation_name, resource_id=_extract_id(response), payload=response))
    return response


def _register_invoice_payment(
    client: TripletexClient,
    invoice_id: Optional[int],
    fields: Dict[str, Any],
    operations: list,
) -> None:
    if invoice_id is None or not fields.get("markAsPaid"):
        return
    fields.setdefault("paymentDate", fields.get("invoiceDate") or _today_iso())
    if fields.get("amountPaidCurrency") is None and fields.get("amount") is not None:
        fields["amountPaidCurrency"] = fields.get("amount")
    try:
        response = client._request(
            "PUT",
            "/invoice/{0}/:payment".format(int(invoice_id)),
            params=_build_invoice_payment_payload(fields),
        )
    except TripletexClientError as exc:
        classified = classify_tripletex_error(exc)
        if exc.status_code == 404 and classified.category in {
            TripletexErrorCategory.NOT_FOUND,
            TripletexErrorCategory.WRONG_ENDPOINT,
        }:
            operations.append(
                OperationResult(
                    name="register-invoice-payment",
                    resource_id=int(invoice_id),
                    payload={"skipped": True, "reason": "invoice not available for payment"},
                )
            )
            return
        raise
    operations.append(
        OperationResult(name="register-invoice-payment", resource_id=int(invoice_id), payload=response)
    )


def _resolve_credit_note_invoice(
    client: TripletexClient,
    customer_id: int,
    fields: Dict[str, Any],
    related: Dict[str, Any],
    operations: list,
) -> Optional[int]:
    invoice_description = (
        related.get("invoice", {}).get("description")
        or related.get("order", {}).get("description")
        or related.get("product", {}).get("description")
    )
    target_amount = abs(float(fields["amount"])) if fields.get("amount") is not None else None
    invoice_date_to = fields.get("invoiceDate") or _today_iso()
    invoice_date_from = fields.get("invoiceDateFrom")
    if invoice_date_from is None:
        try:
            invoice_date_from = (date.fromisoformat(str(invoice_date_to)) - timedelta(days=3650)).isoformat()
        except ValueError:
            invoice_date_from = "2016-01-01"
    try:
        response = client.list_resource(
            "invoice",
            fields="*",
            count=200,
            customerId=customer_id,
            invoiceDateFrom=invoice_date_from,
            invoiceDateTo=invoice_date_to,
        )
    except TripletexClientError as exc:
        operations.append(
            OperationResult(
                name="resolve-payment-invoice",
                resource_id=None,
                payload={"error": str(exc)},
            )
        )
        return None
    values = response.get("values", [])

    def _candidate_customer_id(candidate: Dict[str, Any]) -> Optional[int]:
        customer = candidate.get("customer")
        if isinstance(customer, dict):
            return customer.get("id")
        return None

    def _candidate_description(candidate: Dict[str, Any]) -> str:
        for key in ("description", "invoiceText", "comment"):
            value = candidate.get(key)
            if value:
                return str(value)
        return ""

    def _candidate_amount(candidate: Dict[str, Any]) -> Optional[float]:
        for key in ("amountExcludingVatCurrency", "amount", "netAmount"):
            value = candidate.get(key)
            if value is not None:
                try:
                    return abs(float(value))
                except (TypeError, ValueError):
                    return None
        return None

    filtered = [
        candidate
        for candidate in values
        if _candidate_customer_id(candidate) in {None, customer_id}
    ]
    if invoice_description:
        desc_norm = str(invoice_description).strip().lower()
        filtered = [
            candidate
            for candidate in filtered
            if desc_norm in _candidate_description(candidate).strip().lower()
        ] or filtered
    if target_amount is not None:
        filtered = [
            candidate
            for candidate in filtered
            if _candidate_amount(candidate) == target_amount
        ] or filtered

    invoice = filtered[0] if filtered else None
    invoice_id = invoice.get("id") if invoice else None
    operations.append(
        OperationResult(
            name="resolve-credit-invoice",
            resource_id=invoice_id,
            payload={"invoice": invoice, "matched_count": len(filtered)},
        )
    )
    return int(invoice_id) if invoice_id is not None else None


def _resolve_invoice_for_payment_reversal(
    client: TripletexClient,
    customer_id: int,
    fields: Dict[str, Any],
    related: Dict[str, Any],
    operations: list,
) -> Optional[int]:
    invoice_description = (
        related.get("invoice", {}).get("description")
        or related.get("order", {}).get("description")
        or related.get("product", {}).get("description")
    )
    target_amount = fields.get("amount")
    invoice_date_to = fields.get("invoiceDate") or _today_iso()
    invoice_date_from = fields.get("invoiceDateFrom")
    if invoice_date_from is None:
        try:
            invoice_date_from = (date.fromisoformat(str(invoice_date_to)) - timedelta(days=3650)).isoformat()
        except ValueError:
            invoice_date_from = "2016-01-01"
    response = client.list_resource(
        "invoice",
        fields="*",
        count=200,
        customerId=customer_id,
        invoiceDateFrom=invoice_date_from,
        invoiceDateTo=invoice_date_to,
    )
    values = response.get("values", [])

    def _candidate_customer_id(candidate: Dict[str, Any]) -> Optional[int]:
        customer = candidate.get("customer")
        if isinstance(customer, dict):
            return customer.get("id")
        return None

    def _candidate_description(candidate: Dict[str, Any]) -> str:
        for key in ("description", "invoiceText", "comment"):
            value = candidate.get(key)
            if value:
                return str(value)
        return ""

    def _candidate_amount(candidate: Dict[str, Any]) -> Optional[float]:
        for key in ("amountExcludingVatCurrency", "amount", "netAmount"):
            value = candidate.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None
        return None

    filtered = [
        candidate
        for candidate in values
        if _candidate_customer_id(candidate) in {None, customer_id}
    ]
    if invoice_description:
        desc_norm = str(invoice_description).strip().lower()
        filtered = [
            candidate
            for candidate in filtered
            if desc_norm in _candidate_description(candidate).strip().lower()
        ] or filtered
    if target_amount is not None:
        filtered = [
            candidate
            for candidate in filtered
            if _candidate_amount(candidate) == target_amount
        ] or filtered

    invoice = filtered[0] if filtered else None
    invoice_id = invoice.get("id") if invoice else None
    logger.info(
        "resolve_invoice matched=%d invoice_id=%s amount=%s amount_incl_vat=%s desc=%s",
        len(filtered), invoice_id,
        _candidate_amount(invoice) if invoice else None,
        invoice.get("amount") if invoice else None,
        _candidate_description(invoice)[:100] if invoice else None,
    )
    operations.append(
        OperationResult(
            name="resolve-payment-invoice",
            resource_id=invoice_id,
            payload={"invoice": invoice, "matched_count": len(filtered)},
        )
    )
    return invoice


def _build_reverse_payment_payload(fields: Dict[str, Any]) -> Dict[str, Any]:
    payload = _build_invoice_payment_payload(fields)
    if "paymentDate" not in payload:
        payload["paymentDate"] = fields.get("paymentDate") or fields.get("invoiceDate") or _today_iso()
    if "paidAmount" not in payload and fields.get("amount") is not None:
        payload["paidAmount"] = fields.get("amount")
    if payload.get("paidAmount") is None:
        raise MissingPrerequisiteError(
            stage="payment_reversal",
            task_type=TaskType.REVERSE_PAYMENT,
            issue="payment_amount_missing",
            payload=fields,
            request_id=None,
            validation_messages=["Payment amount is required for reversal."],
        )
    payload.setdefault("paidAmountCurrency", payload["paidAmount"])
    payload["reverse"] = "true"
    return payload


def _reverse_invoice_payment(
    client: TripletexClient,
    invoice_id: int,
    fields: Dict[str, Any],
    operations: list,
    invoice_data: Optional[Dict[str, Any]] = None,
) -> None:
    # Build list of amounts to try: incl VAT, excl VAT, amountOutstanding-derived
    amounts_to_try = []
    params = _build_reverse_payment_payload(fields)
    primary_amount = params.get("paidAmount")
    if primary_amount:
        amounts_to_try.append(float(primary_amount))

    if invoice_data:
        # Add alternative amounts from the invoice
        for key in ("amount", "amountExcludingVatCurrency", "amountOutstanding", "amountOutstandingCurrency"):
            val = invoice_data.get(key)
            if val is not None:
                fval = float(val)
                if fval > 0 and fval not in amounts_to_try:
                    amounts_to_try.append(fval)
        # If amountOutstanding is 0, the payment equals the full invoice amount
        outstanding = invoice_data.get("amountOutstanding")
        total = invoice_data.get("amount")
        if outstanding is not None and total is not None:
            paid = float(total) - float(outstanding)
            if paid > 0 and paid not in amounts_to_try:
                amounts_to_try.insert(0, paid)  # Most likely correct

    logger.info("reverse_payment invoice=%s amounts_to_try=%s", invoice_id, amounts_to_try)

    last_exc = None
    for amount in amounts_to_try:
        try_params = dict(params)
        try_params["paidAmount"] = amount
        try_params["paidAmountCurrency"] = amount
        try:
            response = client._request("PUT", "/invoice/{0}/:payment".format(int(invoice_id)), params=try_params)
            operations.append(OperationResult(name="reverse-invoice-payment", resource_id=invoice_id, payload=response))
            logger.info("reverse_payment_success invoice=%s amount=%s", invoice_id, amount)
            return
        except TripletexClientError as exc:
            last_exc = exc
            if is_company_bank_account_missing(exc):
                # Auto-create bank account and retry this amount
                _force_create_company_bank_account(client, operations)
                try:
                    response = client._request("PUT", "/invoice/{0}/:payment".format(int(invoice_id)), params=try_params)
                    operations.append(OperationResult(name="reverse-invoice-payment", resource_id=invoice_id, payload=response))
                    return
                except TripletexClientError:
                    pass
            if exc.status_code != 404:
                raise
            logger.info("reverse_payment_404 invoice=%s amount=%s, trying next", invoice_id, amount)

    # All amounts failed
    logger.warning("reverse_payment_all_failed invoice=%s amounts=%s", invoice_id, amounts_to_try)
    operations.append(
        OperationResult(
            name="reverse-invoice-payment",
            resource_id=invoice_id,
            payload={"skipped": True, "reason": "all payment amounts returned 404"},
        )
    )


def _parse_csv_from_prompt(raw_prompt: str) -> List[Dict[str, str]]:
    """Extract CSV rows from the enriched prompt (attachment text appended as '--- Attachment: ... ---')."""
    import csv as csv_mod
    import io

    if not raw_prompt:
        return []

    # Find the attachment section
    csv_text = ""
    idx = raw_prompt.find("--- Attachment:")
    if idx >= 0:
        lines = raw_prompt[idx:].split("\n")
        # Skip the "--- Attachment: ... ---" header line
        csv_lines = [l for l in lines[1:] if l.strip() and not l.startswith("---")]
        csv_text = "\n".join(csv_lines)

    if not csv_text:
        return []

    # Try semicolon delimiter first (common in Norwegian CSVs), then comma
    for delimiter in [";", ","]:
        try:
            reader = csv_mod.DictReader(io.StringIO(csv_text), delimiter=delimiter)
            rows = list(reader)
            if rows and reader.fieldnames and len(reader.fieldnames) > 1:
                return rows
        except Exception:
            continue

    logger.warning("csv_parse_failed: could not parse CSV from prompt")
    return []


def _execute_ledger_corrections(
    client: TripletexClient,
    fields: Dict[str, Any],
    related: Dict[str, Any],
    plan: Any,
    operations: list,
) -> None:
    """Parse correction instructions from the prompt and create correcting journal vouchers.

    Handles 4 common error types:
    1. Wrong account: reverse old account posting, create correct one
    2. Duplicate voucher: create reversing entry
    3. Missing VAT line: create VAT posting
    4. Wrong amount: create correcting entry for the difference
    """
    import re

    raw = plan.raw_prompt or ""
    today = _today_iso()
    # Try to find a date range in the prompt for context
    voucher_date = fields.get("dateTo") or fields.get("date") or today

    # --- 1. Wrong account correction ---
    # Pattern: "konto XXXX brukt i staden for YYYY, beløp ZZZZ"
    wrong_account = re.search(
        r'konto\s+(\d{4})\s+(?:brukt|brukt i staden for|instead of|i stedet for)\s+(?:konto\s+)?(\d{4})[^0-9]*?(\d[\d\s,.]*)\s*kr',
        raw, re.IGNORECASE,
    )
    if wrong_account:
        wrong_acct = wrong_account.group(1)
        correct_acct = wrong_account.group(2)
        amount = float(wrong_account.group(3).replace(",", ".").replace(" ", ""))
        logger.info("ledger_correction: wrong_account %s→%s amount=%s", wrong_acct, correct_acct, amount)
        try:
            _create_journal_voucher(
                client, operations,
                debit_account=correct_acct, credit_account=wrong_acct,
                amount=amount, date=voucher_date,
                description="Korreksjon: feil konto {0} → {1}".format(wrong_acct, correct_acct),
                operation_name="correct-wrong-account",
            )
        except TripletexClientError as exc:
            logger.warning("ledger_correction: wrong_account failed: %s", exc)

    # --- 2. Duplicate voucher reversal ---
    # Pattern: "duplikat bilag (konto XXXX, beløp YYYY)"
    duplicate = re.search(
        r'duplikat\w*\s+(?:bilag|voucher)[^0-9]*?(?:konto\s+)?(\d{4})[^0-9]*?(\d[\d\s,.]*)\s*kr',
        raw, re.IGNORECASE,
    )
    if duplicate:
        dup_acct = duplicate.group(1)
        dup_amount = float(duplicate.group(2).replace(",", ".").replace(" ", ""))
        logger.info("ledger_correction: duplicate on account %s amount=%s", dup_acct, dup_amount)
        # First try to find and delete the duplicate voucher
        deleted = False
        try:
            postings = client.list_resource(
                "ledger/posting", fields="id,voucher,account,amount,*",
                count=500,
                dateFrom=fields.get("dateFrom", "2026-01-01"),
                dateTo=fields.get("dateTo", today),
            ).get("values", [])
            # Find postings on this account with this amount
            candidates = []
            for p in postings:
                acct = p.get("account", {})
                acct_num = acct.get("number") if isinstance(acct, dict) else None
                p_amount = p.get("amount")
                if acct_num == int(dup_acct) and p_amount is not None and abs(float(p_amount) - dup_amount) < 0.01:
                    voucher = p.get("voucher", {})
                    voucher_id = voucher.get("id") if isinstance(voucher, dict) else None
                    if voucher_id:
                        candidates.append(voucher_id)
            # If we found 2+ matching vouchers, delete the last one (the duplicate)
            if len(candidates) >= 2:
                dup_voucher_id = candidates[-1]
                try:
                    client._request("DELETE", "/ledger/voucher/{0}".format(dup_voucher_id))
                    operations.append(OperationResult(
                        name="delete-duplicate-voucher", resource_id=dup_voucher_id, payload={"deleted": True}
                    ))
                    deleted = True
                    logger.info("ledger_correction: deleted duplicate voucher %s", dup_voucher_id)
                except TripletexClientError as exc:
                    logger.warning("ledger_correction: delete duplicate failed: %s", exc)
        except TripletexClientError as exc:
            logger.warning("ledger_correction: listing postings for duplicate failed: %s", exc)

        # Fallback: create reversing entry if delete didn't work
        if not deleted:
            try:
                # Reverse the duplicate by crediting the expense account and debiting a clearing account
                _create_journal_voucher(
                    client, operations,
                    debit_account="1920", credit_account=dup_acct,
                    amount=dup_amount, date=voucher_date,
                    description="Korreksjon: reversering av duplikat bilag konto {0}".format(dup_acct),
                    operation_name="reverse-duplicate-voucher",
                )
            except TripletexClientError as exc:
                logger.warning("ledger_correction: reverse duplicate failed: %s", exc)

    # --- 3. Missing VAT line ---
    # Pattern: "manglande MVA-linje (konto XXXX, beløp ekskl. YYYY kr manglar MVA på konto ZZZZ)"
    missing_vat = re.search(
        r'mangl\w+\s+(?:mva|MVA)[^0-9]*?(?:konto\s+)?(\d{4})[^0-9]*?(\d[\d\s,.]*)\s*kr[^0-9]*?(?:mva|MVA)\s+(?:på\s+)?(?:konto\s+)?(\d{4})',
        raw, re.IGNORECASE,
    )
    if missing_vat:
        expense_acct = missing_vat.group(1)
        excl_amount = float(missing_vat.group(2).replace(",", ".").replace(" ", ""))
        vat_acct = missing_vat.group(3)
        vat_amount = excl_amount * 0.25  # Standard 25% MVA
        logger.info("ledger_correction: missing VAT on %s, amount excl=%s, vat_acct=%s, vat=%s",
                     expense_acct, excl_amount, vat_acct, vat_amount)
        try:
            _create_journal_voucher(
                client, operations,
                debit_account=vat_acct, credit_account="1920",
                amount=vat_amount, date=voucher_date,
                description="Korreksjon: manglande MVA for konto {0}, beløp {1} kr".format(expense_acct, excl_amount),
                operation_name="correct-missing-vat",
            )
        except TripletexClientError as exc:
            logger.warning("ledger_correction: missing VAT failed: %s", exc)

    # --- 4. Wrong amount correction ---
    # Pattern: "feil beløp (konto XXXX, YYYY kr bokført i staden for ZZZZ kr)"
    wrong_amount = re.search(
        r'feil\s+beløp[^0-9]*?(?:konto\s+)?(\d{4})[^0-9]*?(\d[\d\s,.]*)\s*kr\s+(?:bokført|bokfort|registrert)[^0-9]*?(\d[\d\s,.]*)\s*kr',
        raw, re.IGNORECASE,
    )
    if wrong_amount:
        acct = wrong_amount.group(1)
        booked = float(wrong_amount.group(2).replace(",", ".").replace(" ", ""))
        correct = float(wrong_amount.group(3).replace(",", ".").replace(" ", ""))
        diff = booked - correct
        logger.info("ledger_correction: wrong_amount on %s, booked=%s, correct=%s, diff=%s", acct, booked, correct, diff)
        if diff > 0:
            # Overpaid — credit the account to reduce
            try:
                _create_journal_voucher(
                    client, operations,
                    debit_account="1920", credit_account=acct,
                    amount=abs(diff), date=voucher_date,
                    description="Korreksjon: feil beløp konto {0}, {1} → {2} kr".format(acct, booked, correct),
                    operation_name="correct-wrong-amount",
                )
            except TripletexClientError as exc:
                logger.warning("ledger_correction: wrong_amount failed: %s", exc)
        elif diff < 0:
            # Underpaid — debit the account to increase
            try:
                _create_journal_voucher(
                    client, operations,
                    debit_account=acct, credit_account="1920",
                    amount=abs(diff), date=voucher_date,
                    description="Korreksjon: feil beløp konto {0}, {1} → {2} kr".format(acct, booked, correct),
                    operation_name="correct-wrong-amount",
                )
            except TripletexClientError as exc:
                logger.warning("ledger_correction: wrong_amount failed: %s", exc)


def _execute_bank_reconciliation(
    client: TripletexClient,
    fields: Dict[str, Any],
    related: Dict[str, Any],
    plan: Any,
    operations: list,
) -> None:
    """Match bank statement rows to open invoices and register payments."""
    # Parse CSV from the enriched prompt
    csv_rows = _parse_csv_from_prompt(plan.raw_prompt)
    logger.info("bank_reconciliation csv_rows=%d", len(csv_rows))

    if not csv_rows:
        # Try to extract from fields if the LLM put transaction data there
        logger.warning("bank_reconciliation: no CSV rows found in prompt")
        return

    # Fetch all open customer invoices
    today = _today_iso()
    try:
        customer_invoices = client.list_resource(
            "invoice", fields="id,amount,amountOutstanding,customer,invoiceDate,*",
            count=500, invoiceDateFrom="2020-01-01", invoiceDateTo=today,
        ).get("values", [])
    except TripletexClientError:
        customer_invoices = []

    # Fetch all open supplier invoices
    try:
        supplier_invoices = client.list_resource(
            "incomingInvoice", fields="id,invoiceAmount,supplier,invoiceDate,*",
            count=500,
        ).get("values", [])
    except TripletexClientError:
        supplier_invoices = []

    logger.info("bank_reconciliation open_customer_invoices=%d open_supplier_invoices=%d",
                len(customer_invoices), len(supplier_invoices))

    # Process each CSV row
    for row in csv_rows:
        # Try common CSV column names
        amount_str = (
            row.get("Beløp") or row.get("Amount") or row.get("Montant")
            or row.get("beløp") or row.get("amount") or row.get("montant")
            or row.get("Inn") or row.get("Ut") or ""
        )
        date_str = (
            row.get("Dato") or row.get("Date") or row.get("dato")
            or row.get("date") or row.get("Bokført") or ""
        )
        description = (
            row.get("Beskrivelse") or row.get("Description") or row.get("Tekst")
            or row.get("beskrivelse") or row.get("description") or row.get("tekst")
            or ""
        )

        try:
            # Handle Norwegian number format (comma as decimal separator)
            amount = float(amount_str.replace(",", ".").replace(" ", ""))
        except (ValueError, AttributeError):
            logger.warning("bank_reconciliation: skipping row, cannot parse amount=%s", amount_str)
            continue

        payment_date = date_str.strip() if date_str else today

        if amount > 0:
            # Incoming payment → match against customer invoices
            matched = None
            for inv in customer_invoices:
                inv_amount = inv.get("amount") or inv.get("amountOutstanding")
                if inv_amount is not None and abs(float(inv_amount) - amount) < 0.01:
                    matched = inv
                    break
            if matched is None:
                # Try partial match
                for inv in customer_invoices:
                    outstanding = inv.get("amountOutstanding")
                    if outstanding is not None and float(outstanding) > 0:
                        matched = inv
                        break

            if matched:
                invoice_id = int(matched["id"])
                pay_amount = amount
                params = {
                    "paymentDate": payment_date,
                    "paidAmount": pay_amount,
                    "paidAmountCurrency": pay_amount,
                    "paymentTypeId": 6,
                }
                try:
                    resp = client._request("PUT", "/invoice/{0}/:payment".format(invoice_id), params=params)
                    operations.append(OperationResult(
                        name="bank-reconcile-customer-payment",
                        resource_id=invoice_id,
                        payload=resp,
                    ))
                    logger.info("bank_reconcile_customer_payment invoice=%s amount=%s", invoice_id, pay_amount)
                    # Remove from list to avoid double-matching
                    customer_invoices = [i for i in customer_invoices if i.get("id") != matched["id"]]
                except TripletexClientError as exc:
                    logger.warning("bank_reconcile_customer_payment_failed invoice=%s error=%s", invoice_id, exc)
            else:
                logger.warning("bank_reconciliation: no matching customer invoice for amount=%s", amount)

        elif amount < 0:
            # Outgoing payment → match against supplier invoices
            pay_amount = abs(amount)
            matched = None
            for inv in supplier_invoices:
                inv_amount = inv.get("invoiceAmount")
                if inv_amount is not None and abs(float(inv_amount) - pay_amount) < 0.01:
                    matched = inv
                    break

            if matched:
                inv_id = int(matched["id"])
                # For supplier invoices, use the payment endpoint
                params = {
                    "paymentDate": payment_date,
                    "paidAmount": pay_amount,
                    "paymentTypeId": 6,
                }
                try:
                    resp = client._request("PUT", "/incomingInvoice/{0}/:payment".format(inv_id), params=params)
                    operations.append(OperationResult(
                        name="bank-reconcile-supplier-payment",
                        resource_id=inv_id,
                        payload=resp,
                    ))
                    logger.info("bank_reconcile_supplier_payment invoice=%s amount=%s", inv_id, pay_amount)
                    supplier_invoices = [i for i in supplier_invoices if i.get("id") != matched["id"]]
                except TripletexClientError as exc:
                    logger.warning("bank_reconcile_supplier_payment_failed invoice=%s error=%s", inv_id, exc)
            else:
                logger.warning("bank_reconciliation: no matching supplier invoice for amount=%s", pay_amount)


def _create_credit_note(
    client: TripletexClient,
    invoice_id: int,
    operations: list,
) -> Dict[str, Any]:
    response = client._request(
        "PUT",
        "/invoice/{0}/:createCreditNote".format(invoice_id),
        params={"date": datetime.fromisoformat(operations[0].payload.get("invoice", {}).get("invoiceDate", _today_iso())).date().isoformat()},
    )
    operations.append(OperationResult(name="create-credit-note", resource_id=invoice_id, payload=response))
    return response


def execute_plan(client: TripletexClient, plan: ExecutionPlan) -> ExecutionResult:
    task_type = plan.parsed_task.task_type
    fields = dict(plan.parsed_task.fields)
    match_fields = dict(plan.parsed_task.match_fields)
    related = dict(plan.parsed_task.related_entities)
    operations = []
    logger.info("EXECUTE_START task_type=%s fields=%s related=%s", task_type, fields, related)

    if task_type == TaskType.CREATE_EMPLOYEE:
        department_id = _resolve_department(client, operations)
        payload = _build_employee_payload(fields, department_id)
        response = client.create_resource("employee", payload)
        operations.append(
            OperationResult(name="create-employee", resource_id=_extract_id(response), payload=response)
        )

    elif task_type == TaskType.UPDATE_EMPLOYEE:
        employee = client.find_single("employee", match_fields)
        if employee is None:
            raise TripletexClientError(message="Could not uniquely resolve employee for update")
        employee_detail = client.find_by_id("employee", int(employee["id"])) or employee
        payload = dict(employee_detail)
        payload.update(_compact_payload(fields))
        response = client.update_resource("employee", int(employee["id"]), payload)
        operations.append(OperationResult(name="update-employee", resource_id=employee["id"], payload=response))

    elif task_type == TaskType.LIST_EMPLOYEES:
        response = client.list_resource("employee", fields=fields.get("fields", "id,firstName,lastName,email"), count=fields.get("count", 100))
        operations.append(OperationResult(name="list-employees", payload=response))

    elif task_type == TaskType.CREATE_CUSTOMER:
        response = client.create_resource("customer", _build_customer_payload(fields))
        operations.append(
            OperationResult(name="create-customer", resource_id=_extract_id(response), payload=response)
        )

    elif task_type == TaskType.UPDATE_CUSTOMER:
        customer = client.find_single("customer", match_fields)
        if customer is None:
            raise TripletexClientError(message="Could not uniquely resolve customer for update")
        payload = dict(customer)
        payload.update(_compact_payload(fields))
        response = client.update_resource("customer", int(customer["id"]), payload)
        operations.append(OperationResult(name="update-customer", resource_id=customer["id"], payload=response))

    elif task_type == TaskType.SEARCH_CUSTOMERS:
        params = {
            "fields": fields.get("fields", "id,name,email,organizationNumber"),
            "count": fields.get("count", 100),
        }
        if match_fields.get("name"):
            params["name"] = match_fields["name"]
        response = client.list_resource("customer", **params)
        operations.append(OperationResult(name="search-customers", payload=response))

    elif task_type == TaskType.CREATE_PRODUCT:
        response = client.create_resource("product", _build_product_payload(fields))
        operations.append(OperationResult(name="create-product", resource_id=_extract_id(response), payload=response))

    elif task_type == TaskType.CREATE_PROJECT:
        payload = _build_project_payload(fields)
        customer_spec = related.get("customer")
        if customer_spec:
            customer_id = _resolve_customer(
                client,
                customer_spec,
                operations,
                allow_create=_can_create_customer_prerequisite(customer_spec),
            )
            if customer_id is not None:
                payload["customer"] = {"id": customer_id}
        manager_spec = (
            related.get("project_manager")
            or related.get("projectManager")
            or related.get("projectLeader")
            or related.get("employee")
        )
        if manager_spec:
            manager_id = _resolve_project_manager(client, manager_spec, operations)
        else:
            manager_id = _resolve_fallback_project_manager(client, operations)
        if manager_id is not None:
            payload["projectManager"] = {"id": manager_id}
        response = client.create_resource("project", _compact_payload(payload))
        operations.append(OperationResult(name="create-project", resource_id=_extract_id(response), payload=response))

    elif task_type == TaskType.CREATE_DEPARTMENT:
        department_names = []
        if fields.get("departmentNames"):
            department_names.extend([value for value in str(fields["departmentNames"]).split("||") if value])
        elif fields.get("name"):
            department_names.append(str(fields["name"]))
        for department_name in department_names:
            payload = {
                "name": department_name,
                "departmentNumber": fields.get("departmentNumber"),
            }
            response = client.create_resource("department", _compact_payload(payload))
            operations.append(
                OperationResult(name="create-department", resource_id=_extract_id(response), payload=response)
            )

    elif task_type == TaskType.CREATE_ORDER:
        customer_spec = related.get("customer", {})
        product_spec = dict(related.get("product", {}))
        order_spec = dict(related.get("order", {}))
        order_line_specs = _extract_order_line_specs(related)
        if order_spec.get("description") and "description" not in product_spec:
            product_spec["description"] = order_spec["description"]
        if product_spec.get("name") and "description" not in product_spec:
            product_spec["description"] = product_spec["name"]
        customer_id = _resolve_customer(
            client,
            customer_spec,
            operations,
            allow_create=_can_create_customer_prerequisite(customer_spec),
        )
        if customer_id is None:
            raise TripletexClientError(message="Order requires resolvable customer")
        if not order_line_specs and product_spec.get("id") is not None:
            product_id = _resolve_product(client, product_spec, operations, allow_create=False)
        else:
            product_id = (
                _resolve_product(client, product_spec, operations, allow_create=False)
                if (not order_line_specs and _should_resolve_product_for_order_line(product_spec))
                else None
            )
        order_id = _create_order(
            client,
            customer_id,
            product_id,
            fields,
            product_spec,
            operations,
            order_line_specs=order_line_specs,
        )
        operations.append(OperationResult(name="order-ready", resource_id=order_id))

    elif task_type == TaskType.CREATE_INVOICE:
        customer_spec = related.get("customer", {})
        product_spec = dict(related.get("product", {}))
        invoice_spec = dict(related.get("invoice", {}))
        order_spec = dict(related.get("order", {}))
        order_line_specs = _extract_order_line_specs(related)
        if invoice_spec.get("description") and "description" not in product_spec:
            product_spec["description"] = invoice_spec["description"]
        if order_spec.get("description") and "description" not in product_spec:
            product_spec["description"] = order_spec["description"]
        if product_spec.get("name") and "description" not in product_spec:
            product_spec["description"] = product_spec["name"]
        customer_id = _resolve_customer(
            client,
            customer_spec,
            operations,
            allow_create=_can_create_customer_prerequisite(customer_spec),
        )
        if customer_id is None:
            raise TripletexClientError(message="Invoice requires resolvable customer")
        if not order_line_specs and product_spec.get("id") is not None:
            product_id = _resolve_product(client, product_spec, operations, allow_create=False)
        else:
            product_id = (
                _resolve_product(client, product_spec, operations, allow_create=False)
                if (not order_line_specs and _should_resolve_product_for_order_line(product_spec))
                else None
            )
        ledger_account_number = None
        if not order_line_specs and product_id is None and fields.get("accountNumber") is not None:
            ledger_account_number = _resolve_ledger_account(
                client,
                str(fields.get("accountNumber")),
                operations,
            )
        existing_order_id = order_spec.get("id")
        if existing_order_id is not None:
            order_id = int(existing_order_id)
            operations.append(OperationResult(name="reuse-order", resource_id=order_id, payload={"id": order_id}))
        else:
            order_id = _create_order(
                client,
                customer_id,
                product_id,
                fields,
                product_spec,
                operations,
                order_line_specs=order_line_specs,
                ledger_account_number=ledger_account_number,
            )
        invoice_response = _create_invoice_with_fallback(
            client,
            fields,
            customer_id,
            order_id,
            operations,
            related=related,
            task_type=task_type,
            operation_name="create-invoice",
        )
        _register_invoice_payment(client, _extract_id(invoice_response), fields, operations)

    elif task_type == TaskType.CREATE_SUPPLIER_INVOICE:
        supplier_spec = related.get("supplier", {})
        supplier_id = _resolve_supplier(
            client,
            supplier_spec,
            operations,
            allow_create=_can_create_supplier_prerequisite(supplier_spec),
        )
        if supplier_id is None:
            raise TripletexClientError(message="Supplier invoice requires resolvable supplier")
        _validate_supplier_invoice_fields(fields)
        payload = _build_supplier_invoice_payload(fields, supplier_id)
        logger.info("supplier_invoice_payload=%s", json.dumps(payload, ensure_ascii=False, default=str))
        response = client.create_resource("incomingInvoice", payload)
        operations.append(
            OperationResult(name="create-supplier-invoice", resource_id=_extract_id(response), payload=response)
        )

    elif task_type == TaskType.REVERSE_PAYMENT:
        customer_spec = related.get("customer", {})
        customer_id = _resolve_customer(
            client,
            customer_spec,
            operations,
            allow_create=False,
        )
        if customer_id is None:
            raise TripletexClientError(message="Reverse payment requires resolvable customer")
        invoice_data = _resolve_invoice_for_payment_reversal(client, customer_id, fields, related, operations)
        if invoice_data is None:
            raise TripletexClientError(message="Reverse payment requires resolvable invoice")
        invoice_id = int(invoice_data.get("id"))
        # Use the actual invoice amount (incl. VAT) for the payment reversal
        invoice_amount = invoice_data.get("amount") or invoice_data.get("amountOutstanding")
        original_amount = fields.get("amount")
        if invoice_amount is not None:
            fields = dict(fields)  # copy to avoid mutating original
            fields["amount"] = float(invoice_amount)
            logger.info("reverse_payment using invoice amount_incl_vat=%s instead of parsed=%s",
                        invoice_amount, original_amount)
        _reverse_invoice_payment(client, invoice_id, fields, operations, invoice_data=invoice_data)

    elif task_type == TaskType.CREATE_CREDIT_NOTE:
        customer_spec = related.get("customer", {})
        customer_id = _resolve_customer(
            client,
            customer_spec,
            operations,
            allow_create=_can_create_customer_prerequisite(customer_spec),
        )
        if customer_id is None:
            raise TripletexClientError(message="Credit note requires resolvable customer")
        invoice_id = _resolve_credit_note_invoice(client, customer_id, fields, related, operations)
        if invoice_id is None:
            raise TripletexClientError(message="Credit note requires resolvable invoice")
        _create_credit_note(client, invoice_id, operations)

    elif task_type == TaskType.CREATE_PROJECT_BILLING:
        payload = _build_project_payload(fields)
        customer_spec = related.get("customer", {})
        customer_id = _resolve_customer(
            client,
            customer_spec,
            operations,
            allow_create=_can_create_customer_prerequisite(customer_spec),
        )
        if customer_id is None:
            raise TripletexClientError(message="Project billing requires resolvable customer")
        payload["customer"] = {"id": customer_id}
        manager_spec = related.get("project_manager") or related.get("employee") or {}
        manager_id = _resolve_project_manager(client, manager_spec, operations) if manager_spec else None
        if manager_id is not None:
            payload["projectManager"] = {"id": manager_id}
        try:
            project_response = client.create_resource("project", _compact_payload(payload))
        except TripletexClientError as exc:
            if "prosjektleder" not in str(exc).lower():
                raise
            fallback_manager_id = _resolve_fallback_project_manager(client, operations)
            if fallback_manager_id is None:
                raise
            payload["projectManager"] = {"id": fallback_manager_id}
            project_response = client.create_resource("project", _compact_payload(payload))
        project_id = _extract_id(project_response)
        operations.append(OperationResult(name="create-billing-project", resource_id=project_id, payload=project_response))

        # --- Resolve or create activity ---
        activity_id = None
        activity_spec = related.get("activity", {})
        activity_name = activity_spec.get("name") if activity_spec else None
        if activity_name:
            try:
                existing = client.find_single("activity", {"name": activity_name})
                if existing:
                    activity_id = existing.get("id")
            except TripletexClientError:
                pass
            if activity_id is None:
                try:
                    act_response = client.create_resource("activity", {"name": activity_name})
                    activity_id = _extract_id(act_response)
                    operations.append(OperationResult(name="create-activity", resource_id=activity_id, payload=act_response))
                except TripletexClientError as exc:
                    logger.warning("activity_creation_failed name=%s error=%s", activity_name, exc)

        # --- Collect all employees with hours ---
        ts_date = fields.get("startDate") or _today_iso()
        hourly_rate = fields.get("hourlyRateCurrency")

        # Build list of (employee_spec, hours) from related entities
        time_entries_to_register: list = []
        # Primary time_entry
        time_spec = related.get("time_entry") or related.get("time_entries") or {}
        if time_spec.get("hours"):
            time_entries_to_register.append((manager_spec, float(time_spec["hours"]), time_spec.get("hourlyRate") or hourly_rate))

        # Additional numbered employees (employee_1, employee_2, ...)
        for key in sorted(related.keys()):
            if key.startswith("employee_") and key[9:].isdigit():
                emp_spec = related[key]
                emp_hours = emp_spec.get("hours")
                if not emp_hours:
                    # Check for corresponding time_entry_N
                    idx = key.split("_")[1]
                    ts_key = "time_entry_{0}".format(idx)
                    ts_spec = related.get(ts_key, {})
                    emp_hours = ts_spec.get("hours")
                if emp_hours:
                    time_entries_to_register.append((emp_spec, float(emp_hours), emp_spec.get("hourlyRate") or hourly_rate))

        # If no explicit time entries found but manager has hours in their spec
        if not time_entries_to_register and manager_spec.get("hours"):
            time_entries_to_register.append((manager_spec, float(manager_spec["hours"]), hourly_rate))

        # Register all timesheet entries
        for emp_spec, hours, rate in time_entries_to_register:
            emp_id = _resolve_project_manager(client, emp_spec, operations) if emp_spec.get("email") or emp_spec.get("first_name") else manager_id
            if emp_id and project_id:
                ts_payload: Dict[str, Any] = {
                    "employee": {"id": emp_id},
                    "project": {"id": project_id},
                    "date": ts_date,
                    "hours": hours,
                }
                if activity_id:
                    ts_payload["activity"] = {"id": activity_id}
                if rate:
                    ts_payload["hourlyRate"] = float(rate)
                try:
                    ts_response = client.create_resource("timesheet/entry", ts_payload)
                    ts_id = _extract_id(ts_response)
                    operations.append(OperationResult(name="create-timesheet-entry", resource_id=ts_id, payload=ts_response))
                    logger.info("timesheet_entry_created id=%s hours=%s employee=%s project=%s", ts_id, hours, emp_id, project_id)
                except TripletexClientError as exc:
                    logger.warning("timesheet_entry_failed payload=%s error=%s", ts_payload, exc)

        # --- Register supplier invoice if present ---
        supplier_spec = related.get("supplier", {})
        supplier_invoice_spec = related.get("supplier_invoice", {})
        if supplier_spec and supplier_invoice_spec.get("amount"):
            supplier_id = _resolve_customer(
                client, {**supplier_spec, "isSupplier": True}, operations,
                allow_create=bool(supplier_spec.get("name")),
            )
            if supplier_id:
                si_amount = float(supplier_invoice_spec["amount"])
                si_payload: Dict[str, Any] = {
                    "invoiceDate": fields.get("invoiceDate") or _today_iso(),
                    "dueDate": fields.get("invoiceDueDate") or fields.get("invoiceDate") or _today_iso(),
                    "supplier": {"id": supplier_id},
                    "orderLines": [{"amountInclVat": si_amount, "externalId": "supplier-cost-1"}],
                }
                try:
                    si_response = client.create_resource("incomingInvoice", si_payload)
                    operations.append(OperationResult(
                        name="create-supplier-invoice", resource_id=_extract_id(si_response), payload=si_response
                    ))
                    logger.info("supplier_invoice_created for project billing amount=%s supplier=%s", si_amount, supplier_id)
                except TripletexClientError as exc:
                    logger.warning("supplier_invoice_failed payload=%s error=%s", si_payload, exc)

        # --- Create order and invoice ---
        order_description = related.get("order", {}).get("description") or activity_name or "Project partial billing"
        order_id = _create_order(
            client,
            customer_id,
            None,
            fields,
            {"description": order_description},
            operations,
        )
        _create_invoice_with_fallback(
            client,
            fields,
            customer_id,
            order_id,
            operations,
            related=related,
            task_type=task_type,
            operation_name="create-billing-invoice",
        )

    elif task_type == TaskType.CREATE_DIMENSION_VOUCHER:
        debit_account = fields.get("debitAccountNumber") or fields.get("accountNumber")
        credit_account = fields.get("creditAccountNumber")
        amount = float(fields.get("amount", 0))
        description = fields.get("description") or "Journal entry"
        voucher_date = fields.get("date") or _today_iso()
        dimension_name = fields.get("dimensionName")
        dimension_values_raw = fields.get("dimensionValues", "")
        selected_value = fields.get("selectedDimensionValue")

        dimension_value_id = None

        # Path 1: Full dimension voucher (create dimension + values + voucher)
        if dimension_name and debit_account and amount:
            # Step 1: Create the custom dimension
            dim_payload = _build_dimension_payload(fields)
            logger.info("creating_dimension payload=%s", dim_payload)
            dim_response = client.create_resource("ledger/accountingDimensionName", dim_payload)
            dim_id = _extract_id(dim_response)
            operations.append(OperationResult(name="create-dimension", resource_id=dim_id, payload=dim_response))

            # Step 2: Create dimension values
            if dim_id and dimension_values_raw:
                values = [v.strip() for v in str(dimension_values_raw).split("||") if v.strip()]
                for val_name in values:
                    val_payload = _build_dimension_value_payload(dim_id, val_name)
                    logger.info("creating_dimension_value name=%s payload=%s", val_name, val_payload)
                    val_response = client.create_resource("ledger/accountingDimensionValue", val_payload)
                    val_id = _extract_id(val_response)
                    operations.append(OperationResult(name="create-dimension-value", resource_id=val_id, payload=val_response))
                    # Track the selected value ID for the voucher
                    if selected_value and val_name == selected_value and val_id:
                        dimension_value_id = val_id

            # Step 3: Create voucher linked to dimension value
            credit_acct = str(credit_account) if credit_account else "2400"
            voucher_payload = _build_voucher_payload(
                client,
                fields,
                description=description,
                account_number=str(debit_account),
                amount=amount,
                dimension_value_id=dimension_value_id,
                credit_account_number=credit_acct,
            )
            logger.info("creating_dimension_voucher payload=%s", voucher_payload)
            voucher_response = client.create_resource("ledger/voucher", voucher_payload)
            operations.append(
                OperationResult(name="create-dimension-voucher", resource_id=_extract_id(voucher_response), payload=voucher_response)
            )

        # Path 2: Simple journal entry (debit/credit accounts, no dimension)
        elif debit_account and credit_account and amount:
            _create_journal_voucher(
                client, operations,
                debit_account=str(debit_account),
                credit_account=str(credit_account),
                amount=abs(amount),
                date=voucher_date,
                description=description,
            )
        else:
            logger.warning(
                "dimension_voucher_skipped: missing debit=%s credit=%s amount=%s dimension=%s",
                debit_account, credit_account, amount, dimension_name,
            )

    elif task_type == TaskType.CREATE_PAYROLL_VOUCHER:
        employee_spec = related.get("employee", {})
        employee_id = _resolve_employee(
            client,
            employee_spec,
            operations,
            allow_create=False,
        ) if employee_spec else None
        description = "Payroll expense"
        if employee_spec.get("email"):
            description = "Payroll expense {0}".format(employee_spec["email"])
        voucher_payload = _build_voucher_payload(
            client,
            fields,
            description=description,
            account_number="5000",
            amount=float(fields.get("amount", 0)),
        )
        voucher_response = client.create_resource("ledger/voucher", voucher_payload)
        operations.append(
            OperationResult(name="create-payroll-voucher", resource_id=_extract_id(voucher_response), payload=voucher_response)
        )

    elif task_type == TaskType.CREATE_TRAVEL_EXPENSE:
        # Resolve department if specified
        dept_spec = related.get("department", {})
        dept_name = dept_spec.get("name") or fields.get("departmentName")
        if dept_name:
            try:
                dept_resp = client.list_resource("department", fields="id,name", count=5, name=dept_name)
                for dept in dept_resp.get("values", []):
                    if dept.get("id"):
                        fields["department"] = {"id": dept["id"]}
                        break
            except Exception:
                pass
            if "department" not in fields:
                try:
                    dept_create = client.create_resource("department", {"name": dept_name})
                    dept_id = _extract_id(dept_create)
                    if dept_id:
                        fields["department"] = {"id": dept_id}
                        operations.append(OperationResult(name="create-department", resource_id=dept_id, payload=dept_create))
                except Exception:
                    pass
        payload = _build_travel_expense_payload(fields)
        employee_spec = related.get("employee")
        if employee_spec:
            employee_id = _resolve_employee(client, employee_spec, operations, allow_create=False)
            if employee_id is not None:
                payload["employee"] = {"id": employee_id}
        if "employee" not in payload:
            fallback_employee_id = _resolve_fallback_project_manager(client, operations)
            if fallback_employee_id is not None:
                payload["employee"] = {"id": fallback_employee_id}
        response = client.create_resource("travelExpense", _compact_payload(payload))
        expense_id = _extract_id(response)
        # Add cost as separate request
        if expense_id:
            cost_payload = _build_travel_cost_payload(expense_id, fields)
            if cost_payload:
                # Resolve paymentType if not set
                if "paymentType" not in cost_payload:
                    try:
                        pt_resp = client.list_resource("travelExpense/paymentType", fields="id,description", count=10)
                        for pt in pt_resp.get("values", []):
                            if pt.get("id"):
                                cost_payload["paymentType"] = {"id": pt["id"]}
                                break
                    except Exception:
                        pass
                try:
                    cost_response = client.create_resource("travelExpense/cost", cost_payload)
                    operations.append(OperationResult(name="create-travel-cost", resource_id=_extract_id(cost_response), payload=cost_response))
                except Exception as exc:
                    logger.warning("Failed to create travel cost: %s", exc)
        operations.append(
            OperationResult(name="create-travel-expense", resource_id=_extract_id(response), payload=response)
        )

    elif task_type == TaskType.UPDATE_TRAVEL_EXPENSE:
        expense_id = fields.get("travel_expense_id")
        if expense_id is None:
            raise TripletexClientError(message="Travel expense update requires expense id")
        payload = dict(fields)
        payload.pop("travel_expense_id", None)
        existing = client.find_by_id("travelExpense", int(expense_id)) or {}
        merged_payload = dict(existing)
        merged_payload.update(_compact_payload(payload))
        response = client.update_resource("travelExpense", int(expense_id), _compact_payload(merged_payload))
        operations.append(
            OperationResult(name="update-travel-expense", resource_id=int(expense_id), payload=response)
        )

    elif task_type == TaskType.DELETE_TRAVEL_EXPENSE:
        expense_id = fields.get("travel_expense_id")
        if expense_id is None:
            expenses = client.list_resource("travelExpense", count=1, fields="id")
            values = expenses.get("values", [])
            if not values:
                logger.warning("EXECUTE_DONE task_type=%s ops=0 reason=no_travel_expense_found", task_type)
                return ExecutionResult(task_type=task_type, operations=operations)
            expense_id = values[0]["id"]
            operations.append(OperationResult(name="lookup-travel-expense", resource_id=expense_id, payload=expenses))
        client.delete_resource("travelExpense", int(expense_id))
        operations.append(OperationResult(name="delete-travel-expense", resource_id=int(expense_id)))

    elif task_type == TaskType.DELETE_VOUCHER:
        voucher_id = fields.get("voucher_id")
        if voucher_id is None:
            raise TripletexClientError(message="Voucher deletion requires voucher id")
        voucher = client.find_by_id("ledger/voucher", int(voucher_id))
        operations.append(OperationResult(name="lookup-voucher", resource_id=int(voucher_id), payload=voucher))
        client.delete_resource("ledger/voucher", int(voucher_id))
        operations.append(OperationResult(name="delete-voucher", resource_id=int(voucher_id)))

    elif task_type == TaskType.LIST_LEDGER_ACCOUNTS:
        response = client.list_resource(
            "ledger/account",
            fields=fields.get("fields", "id,number,name"),
            count=fields.get("count", 100),
        )
        operations.append(OperationResult(name="list-ledger-accounts", payload=response))

    elif task_type == TaskType.LIST_LEDGER_POSTINGS:
        today = date.today()
        date_from = fields.get("dateFrom") or (today.replace(day=1)).isoformat()
        date_to = fields.get("dateTo") or today.isoformat()
        response = client.list_resource(
            "ledger/posting",
            fields=fields.get("fields", "id,date,amount,description"),
            count=fields.get("count", 100),
            dateFrom=date_from,
            dateTo=date_to,
        )
        operations.append(OperationResult(name="list-ledger-postings", payload=response))

    elif task_type == TaskType.REGISTER_PAYMENT:
        customer_spec = related.get("customer", {})
        customer_id = _resolve_customer(
            client,
            customer_spec,
            operations,
            allow_create=False,
        )
        if customer_id is None:
            raise TripletexClientError(message="Register payment requires resolvable customer")
        invoice_data = _resolve_invoice_for_payment_reversal(client, customer_id, fields, related, operations)
        if invoice_data is None:
            raise TripletexClientError(message="Register payment requires resolvable invoice")
        invoice_id = int(invoice_data.get("id"))
        # Use the actual invoice amount (incl. VAT) for the payment
        invoice_amount = invoice_data.get("amount") or invoice_data.get("amountOutstanding")
        if invoice_amount is not None:
            fields = dict(fields)
            fields["amount"] = float(invoice_amount)
        fields.setdefault("paymentDate", fields.get("invoiceDate") or _today_iso())
        payment_params = _build_invoice_payment_payload(fields)
        logger.info("register_payment invoice_id=%s params=%s", invoice_id, payment_params)
        response = client._request(
            "PUT",
            "/invoice/{0}/:payment".format(int(invoice_id)),
            params=payment_params,
        )
        operations.append(OperationResult(name="register-payment", resource_id=invoice_id, payload=response))

    elif task_type == TaskType.CORRECT_LEDGER_ERRORS:
        _execute_ledger_corrections(client, fields, related, plan, operations)

    elif task_type == TaskType.BANK_RECONCILIATION:
        _execute_bank_reconciliation(client, fields, related, plan, operations)

    result = ExecutionResult(task_type=task_type, operations=operations)
    logger.info("EXECUTE_DONE task_type=%s ops=%d op_names=%s", task_type, len(operations), [o.name for o in operations])
    return result
