from datetime import date
from typing import Any, Dict, Optional

from app.clients.tripletex import TripletexClient, TripletexClientError
from app.schemas import ExecutionPlan, ExecutionResult, OperationResult, TaskType


def _extract_id(response: Dict[str, Any]) -> Optional[int]:
    if "value" in response and isinstance(response["value"], dict):
        return response["value"].get("id")
    return response.get("id")


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


def _can_create_customer_prerequisite(spec: Dict[str, Any]) -> bool:
    return bool(spec.get("name") and (spec.get("organizationNumber") or spec.get("email")))


def _build_product_payload(spec: Dict[str, Any]) -> Dict[str, Any]:
    payload = {"name": spec.get("name")}
    if spec.get("priceExcludingVatCurrency") is not None:
        payload["priceExcludingVatCurrency"] = spec["priceExcludingVatCurrency"]
    return _compact_payload(payload)


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
        "markAsPaid": fields.get("markAsPaid"),
        "paymentDate": fields.get("paymentDate"),
        "amountPaidCurrency": fields.get("amountPaidCurrency"),
        "creditNote": fields.get("creditNote"),
        "customer": {"id": customer_id},
        "orders": [{"id": order_id}] if order_id is not None else [],
    }
    return _compact_payload(payload)


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


def _should_retry_invoice_with_minimal_payload(fields: Dict[str, Any], exc: TripletexClientError) -> bool:
    message = str(exc).lower()
    if "bankkontonummer" in message:
        return False
    if "bank account" in message:
        return False
    if fields.get("markAsPaid"):
        return False
    if fields.get("creditNote"):
        return False
    return " 422 " in message or "error 422" in message


def _build_dimension_payload(fields: Dict[str, Any]) -> Dict[str, Any]:
    return _compact_payload({"name": fields.get("dimensionName")})


def _build_dimension_value_payload(dimension_id: int, value_name: str) -> Dict[str, Any]:
    return _compact_payload({"dimension": {"id": dimension_id}, "name": value_name})


def _build_voucher_payload(
    fields: Dict[str, Any],
    description: str,
    account_number: str,
    amount: float,
    dimension_value_id: Optional[int] = None,
) -> Dict[str, Any]:
    debit_line: Dict[str, Any] = {
        "account": {"number": account_number},
        "amount": abs(amount),
        "description": description,
    }
    if dimension_value_id is not None:
        debit_line["dimensions"] = [{"id": dimension_value_id}]

    credit_line: Dict[str, Any] = {
        "account": {"number": "2400"},
        "amount": -abs(amount),
        "description": description,
    }
    payload = {
        "date": fields.get("date") or _today_iso(),
        "description": description,
        "voucherLines": [debit_line, credit_line],
    }
    return _compact_payload(payload)


def _resolve_customer(
    client: TripletexClient,
    spec: Dict[str, Any],
    operations: list,
    allow_create: bool = True,
) -> Optional[int]:
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


def _create_order(
    client: TripletexClient,
    customer_id: int,
    product_id: Optional[int],
    parsed_fields: Dict[str, Any],
    product_spec: Dict[str, Any],
    operations: list,
    order_line_specs: Optional[list] = None,
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
            raise TripletexClientError("Could not uniquely resolve employee for update")
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
            raise TripletexClientError("Could not uniquely resolve customer for update")
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
            raise TripletexClientError("Order requires resolvable customer")
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
            raise TripletexClientError("Invoice requires resolvable customer")
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
        _create_invoice_with_fallback(
            client,
            fields,
            customer_id,
            order_id,
            operations,
            operation_name="create-invoice",
        )

    elif task_type == TaskType.CREATE_CREDIT_NOTE:
        customer_spec = related.get("customer", {})
        product_spec = dict(related.get("product", {}))
        invoice_spec = dict(related.get("invoice", {}))
        order_spec = dict(related.get("order", {}))
        if invoice_spec.get("description") and "description" not in product_spec:
            product_spec["description"] = invoice_spec["description"]
        if order_spec.get("description") and "description" not in product_spec:
            product_spec["description"] = order_spec["description"]
        customer_id = _resolve_customer(
            client,
            customer_spec,
            operations,
            allow_create=_can_create_customer_prerequisite(customer_spec),
        )
        if customer_id is None:
            raise TripletexClientError("Credit note requires resolvable customer")
        order_id = _create_order(client, customer_id, None, fields, product_spec, operations)
        _create_invoice_with_fallback(
            client,
            fields,
            customer_id,
            order_id,
            operations,
            operation_name="create-credit-note",
            minimal_first=True,
        )

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
            raise TripletexClientError("Project billing requires resolvable customer")
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
            operation_name="create-billing-invoice",
            minimal_first=True,
        )

    elif task_type == TaskType.CREATE_DIMENSION_VOUCHER:
        dimension_response = client.create_resource("dimension", _build_dimension_payload(fields))
        dimension_id = _extract_id(dimension_response)
        operations.append(OperationResult(name="create-dimension", resource_id=dimension_id, payload=dimension_response))
        selected_value_id = None
        value_names = [value for value in str(fields.get("dimensionValues", "")).split("||") if value]
        selected_value_name = str(fields.get("selectedDimensionValue") or "")
        for value_name in value_names:
            value_response = client.create_resource("dimension/value", _build_dimension_value_payload(int(dimension_id), value_name))
            value_id = _extract_id(value_response)
            operations.append(OperationResult(name="create-dimension-value", resource_id=value_id, payload=value_response))
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
        if employee_id is not None:
            voucher_payload["employee"] = {"id": employee_id}
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
            raise TripletexClientError("Travel expense update requires expense id")
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
            raise TripletexClientError("Voucher deletion requires voucher id")
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
