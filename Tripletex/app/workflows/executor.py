from datetime import date, datetime, timedelta
import json
from typing import Any, Dict, List, Optional

from app.clients.tripletex import TripletexClient, TripletexClientError
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
    payload = {
        "firstName": spec.get("first_name"),
        "lastName": spec.get("last_name"),
        "email": spec.get("email"),
        "dateOfBirth": spec.get("birthDate"),
        "userType": 1,
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
    payload = {
        "invoiceDate": fields.get("invoiceDate"),
        "invoiceDueDate": fields.get("invoiceDueDate"),
        "creditNote": fields.get("creditNote"),
        "customer": {"id": customer_id},
        "orders": [{"id": order_id}] if order_id is not None else [],
    }
    return _compact_payload(payload)


def _build_supplier_invoice_payload(fields: Dict[str, Any], supplier_id: int) -> Dict[str, Any]:
    payload = {
        "invoiceDate": fields.get("invoiceDate"),
        "invoiceNumber": fields.get("invoiceNumber"),
        "supplier": {"id": supplier_id},
        "amount": fields.get("amount"),
        "invoiceLines": _build_supplier_invoice_lines(fields),
    }
    return _compact_payload(payload)


def _build_supplier_invoice_lines(fields: Dict[str, Any]) -> Optional[list]:
    amount = fields.get("amount")
    account_number = fields.get("accountNumber")
    vat_percentage = fields.get("vatPercentage")
    if amount is None or account_number is None:
        return None
    line = {
        "amount": amount,
        "account": {"number": str(account_number)},
    }
    if vat_percentage is not None:
        line["vatPercentage"] = vat_percentage
    return [_compact_payload(line)]


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
        "creditNote": fields.get("creditNote"),
        "customer": {"id": customer_id},
        "orders": [{"id": order_id}] if order_id is not None else [],
    }
    return _compact_payload(payload)


def _build_invoice_payment_payload(fields: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "paymentDate": fields.get("paymentDate"),
        "paidAmount": fields.get("amountPaidCurrency"),
        "amountPaidCurrency": fields.get("amountPaidCurrency"),
        "paymentTypeId": fields.get("paymentTypeId", 6),
    }
    return _compact_payload(payload)


def _should_retry_invoice_with_minimal_payload(fields: Dict[str, Any], exc: TripletexClientError) -> bool:
    if fields.get("creditNote"):
        return False
    classified = classify_tripletex_error(exc)
    return classified.category == TripletexErrorCategory.VALIDATION_GENERIC


def _build_dimension_payload(fields: Dict[str, Any]) -> Dict[str, Any]:
    return _compact_payload({"dimensionName": fields.get("dimensionName")})


def _build_dimension_value_payload(dimension_id: int, value_name: str) -> Dict[str, Any]:
    return _compact_payload({"accountingDimensionName": {"id": dimension_id}, "description": value_name})


def _build_voucher_payload(
    fields: Dict[str, Any],
    description: str,
    account_number: str,
    amount: float,
    dimension_value_id: Optional[int] = None,
) -> Dict[str, Any]:
    debit_line: Dict[str, Any] = {
        "account": {"number": account_number, "name": description},
        "amount": abs(amount),
        "description": description,
    }
    if dimension_value_id is not None:
        debit_line["dimensions"] = [{"id": dimension_value_id}]

    credit_line: Dict[str, Any] = {
        "account": {"number": "2400", "name": "Offset posting"},
        "amount": -abs(amount),
        "description": description,
    }
    payload = {
        "date": fields.get("date") or _today_iso(),
        "description": description,
        "postings": [debit_line, credit_line],
    }
    return _compact_payload(payload)


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

    order_payload = {
        "customer": {"id": customer_id},
        "orderDate": parsed_fields.get("orderDate") or parsed_fields.get("invoiceDate"),
        "deliveryDate": parsed_fields.get("deliveryDate")
        or parsed_fields.get("orderDate")
        or parsed_fields.get("invoiceDate"),
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
    *,
    task_type: TaskType,
    operation_name: str,
    minimal_first: bool = False,
) -> Dict[str, Any]:
    payload = (
        _build_minimal_invoice_payload(fields, customer_id, order_id)
        if minimal_first
        else _build_invoice_payload(fields, customer_id, order_id)
    )
    try:
        response = client.create_resource("invoice", payload)
    except TripletexClientError as exc:
        if is_company_bank_account_missing(exc):
            request_id = extract_tripletex_request_id(exc)
            validation_messages = extract_validation_messages(exc)
            logger.warning(
                "company_bank_account_missing task_type=%s payload=%s requestId=%s validationMessages=%s",
                operation_name,
                json.dumps(payload, ensure_ascii=False, default=str),
                request_id,
                validation_messages,
            )
            resolved_task_type = task_type if isinstance(task_type, TaskType) else TaskType(task_type)
            raise MissingPrerequisiteError(
                stage="invoice_creation",
                task_type=resolved_task_type,
                issue="company_bank_account_required",
                payload=payload,
                request_id=request_id,
                validation_messages=validation_messages,
            )
        if minimal_first or not _should_retry_invoice_with_minimal_payload(fields, exc):
            raise
        if minimal_first or not _should_retry_invoice_with_minimal_payload(fields, exc):
            raise
        fallback_payload = _build_minimal_invoice_payload(fields, customer_id, order_id)
        response = client.create_resource("invoice", fallback_payload)
        operations.append(
            OperationResult(
                name="{0}-retry-minimal".format(operation_name),
                payload={"invoice": response, "retry": "minimal-payload"},
            )
        )
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
    operations.append(
        OperationResult(
            name="resolve-payment-invoice",
            resource_id=invoice_id,
            payload={"invoice": invoice, "matched_count": len(filtered)},
        )
    )
    return int(invoice_id) if invoice_id is not None else None


def _reverse_invoice_payment(client: TripletexClient, invoice_id: int, fields: Dict[str, Any], operations: list) -> None:
    params = {"reverse": "true"}
    payment_date = fields.get("paymentDate")
    if payment_date:
        params["paymentDate"] = payment_date
    if fields.get("amount"):
        params["amountPaidCurrency"] = fields.get("amount")
    try:
        response = client._request("PUT", "/invoice/{0}/:payment".format(int(invoice_id)), params=params)
    except TripletexClientError as exc:
        classified = classify_tripletex_error(exc)
        if exc.status_code == 404 and classified.category in {
            TripletexErrorCategory.NOT_FOUND,
            TripletexErrorCategory.WRONG_ENDPOINT,
        }:
            operations.append(
                OperationResult(
                    name="reverse-invoice-payment",
                    resource_id=invoice_id,
                    payload={"skipped": True, "reason": "invoice not available for payment reversal"},
                )
            )
            return
        raise
    operations.append(OperationResult(name="reverse-invoice-payment", resource_id=invoice_id, payload=response))


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
            if manager_id is not None:
                payload["projectManager"] = {"id": manager_id}
        try:
            response = client.create_resource("project", _compact_payload(payload))
        except TripletexClientError as exc:
            if "prosjektleder" not in str(exc).lower():
                raise
            fallback_manager_id = _resolve_fallback_project_manager(client, operations)
            if fallback_manager_id is None:
                raise
            payload["projectManager"] = {"id": fallback_manager_id}
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
        response = client.create_resource("supplierInvoice", payload)
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
        invoice_id = _resolve_invoice_for_payment_reversal(client, customer_id, fields, related, operations)
        if invoice_id is None:
            raise TripletexClientError(message="Reverse payment requires resolvable invoice")
        _reverse_invoice_payment(client, invoice_id, fields, operations)

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
        order_description = related.get("order", {}).get("description") or "Project partial billing"
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
            task_type=task_type,
            operation_name="create-billing-invoice",
        )

    elif task_type == TaskType.CREATE_DIMENSION_VOUCHER:
        selected_value_id = None
        value_names = [value for value in str(fields.get("dimensionValues", "")).split("||") if value]
        selected_value_name = str(fields.get("selectedDimensionValue") or "")
        dimension_response = client.create_resource("ledger/accountingDimensionName", _build_dimension_payload(fields))
        dimension_id = _extract_id(dimension_response)
        operations.append(
            OperationResult(name="create-dimension", resource_id=dimension_id, payload=dimension_response)
        )
        for value_name in value_names:
            value_response = client.create_resource(
                "ledger/accountingDimensionValue",
                _build_dimension_value_payload(int(dimension_id), value_name),
            )
            value_id = _extract_id(value_response)
            operations.append(
                OperationResult(name="create-dimension-value", resource_id=value_id, payload=value_response)
            )
            if value_name == selected_value_name:
                selected_value_id = value_id
        voucher_payload = _build_voucher_payload(
            fields,
            description="Dimension voucher {0}".format(fields.get("dimensionName")),
            account_number=str(fields.get("accountNumber")),
            amount=float(fields.get("amount", 0)),
            dimension_value_id=selected_value_id,
        )
        voucher_response = client.create_resource("ledger/voucher", voucher_payload)
        operations.append(
            OperationResult(name="create-dimension-voucher", resource_id=_extract_id(voucher_response), payload=voucher_response)
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
        payload = dict(fields)
        if "employee" not in payload:
            fallback_employee_id = _resolve_fallback_project_manager(client, operations)
            if fallback_employee_id is not None:
                payload["employee"] = {"id": fallback_employee_id}
        response = client.create_resource("travelExpense", _compact_payload(payload))
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
        response = client.list_resource(
            "ledger/posting",
            fields=fields.get("fields", "id,date,amount,description"),
            count=fields.get("count", 100),
        )
        operations.append(OperationResult(name="list-ledger-postings", payload=response))

    return ExecutionResult(task_type=task_type, operations=operations)
