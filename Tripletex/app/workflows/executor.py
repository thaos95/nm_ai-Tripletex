from typing import Any, Dict, Optional

from app.clients.tripletex import TripletexClient, TripletexClientError
from app.schemas import ExecutionPlan, ExecutionResult, OperationResult, TaskType


def _extract_id(response: Dict[str, Any]) -> Optional[int]:
    if "value" in response and isinstance(response["value"], dict):
        return response["value"].get("id")
    return response.get("id")


def _compact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return dict((key, value) for key, value in payload.items() if value is not None)


def _resolve_customer(client: TripletexClient, spec: Dict[str, Any], operations: list) -> Optional[int]:
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

    payload = {"name": spec.get("name", "Unknown Customer"), "isCustomer": True}
    if spec.get("email"):
        payload["email"] = spec["email"]
    if spec.get("organizationNumber"):
        payload["organizationNumber"] = spec["organizationNumber"]
    if spec.get("isSupplier") is not None:
        payload["isSupplier"] = spec["isSupplier"]
    if spec.get("isCustomer") is not None:
        payload["isCustomer"] = spec["isCustomer"]
    for key in ("phoneNumber",):
        if spec.get(key):
            payload[key] = spec[key]
    response = client.create_resource("customer", _compact_payload(payload))
    customer_id = _extract_id(response)
    operations.append(OperationResult(name="create-customer", resource_id=customer_id, payload=response))
    return customer_id


def _resolve_employee(client: TripletexClient, spec: Dict[str, Any], operations: list) -> Optional[int]:
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

    department_id = _resolve_department(client, operations)
    payload = {
        "firstName": spec.get("first_name"),
        "lastName": spec.get("last_name"),
        "email": spec.get("email"),
        "dateOfBirth": spec.get("birthDate"),
        "dateFrom": spec.get("startDate"),
        "userType": 1,
        "department": {"id": department_id} if department_id is not None else None,
    }
    response = client.create_resource("employee", _compact_payload(payload))
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


def _resolve_product(client: TripletexClient, spec: Dict[str, Any], operations: list) -> Optional[int]:
    match_fields = {}
    if spec.get("name"):
        match_fields["name"] = spec["name"]

    existing = client.find_single("product", match_fields) if match_fields else None
    if existing:
        product_id = existing["id"]
        operations.append(OperationResult(name="resolve-product", resource_id=product_id, payload=existing))
        return product_id

    if not spec.get("name"):
        return None

    payload = {"name": spec["name"]}
    if spec.get("priceExcludingVatCurrency") is not None:
        payload["priceExcludingVatCurrency"] = spec["priceExcludingVatCurrency"]
    if spec.get("productNumber"):
        payload["productNumber"] = spec["productNumber"]
    if spec.get("vatPercentage") is not None:
        payload["vatPercentage"] = spec["vatPercentage"]
    response = client.create_resource("product", _compact_payload(payload))
    product_id = _extract_id(response)
    operations.append(OperationResult(name="create-product", resource_id=product_id, payload=response))
    return product_id


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
) -> Optional[int]:
    line = {}
    if product_id is not None:
        line["product"] = {"id": product_id}
    description = product_spec.get("description") or parsed_fields.get("description")
    if description:
        line["description"] = description
    line["count"] = 1

    order_payload = {
        "customer": {"id": customer_id},
        "orderDate": parsed_fields.get("orderDate") or parsed_fields.get("invoiceDate"),
        "deliveryDate": parsed_fields.get("deliveryDate")
        or parsed_fields.get("orderDate")
        or parsed_fields.get("invoiceDate"),
        "orderLines": [_compact_payload(line)],
    }
    response = client.create_resource("order", _compact_payload(order_payload))
    order_id = _extract_id(response)
    operations.append(OperationResult(name="create-order", resource_id=order_id, payload=response))
    return order_id


def execute_plan(client: TripletexClient, plan: ExecutionPlan) -> ExecutionResult:
    task_type = plan.parsed_task.task_type
    fields = dict(plan.parsed_task.fields)
    match_fields = dict(plan.parsed_task.match_fields)
    related = dict(plan.parsed_task.related_entities)
    operations = []

    if task_type == TaskType.CREATE_EMPLOYEE:
        department_id = _resolve_department(client, operations)
        payload = {
            "firstName": fields.get("first_name"),
            "lastName": fields.get("last_name"),
            "email": fields.get("email"),
            "dateOfBirth": fields.get("birthDate"),
            "dateFrom": fields.get("startDate"),
            "userType": 1,
            "department": {"id": department_id} if department_id is not None else None,
        }
        response = client.create_resource("employee", _compact_payload(payload))
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
        payload = {
            "name": fields.get("name"),
            "email": fields.get("email"),
            "isCustomer": fields.get("isCustomer"),
            "isSupplier": fields.get("isSupplier"),
            "organizationNumber": fields.get("organizationNumber"),
            "phoneNumber": fields.get("phoneNumber"),
        }
        response = client.create_resource("customer", _compact_payload(payload))
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
        response = client.create_resource("product", _compact_payload(fields))
        operations.append(OperationResult(name="create-product", resource_id=_extract_id(response), payload=response))

    elif task_type == TaskType.CREATE_PROJECT:
        payload = {
            "name": fields.get("name"),
            "startDate": fields.get("startDate") or "2026-03-19",
        }
        customer_spec = related.get("customer")
        if customer_spec:
            customer_id = _resolve_customer(client, customer_spec, operations)
            if customer_id is not None:
                payload["customer"] = {"id": customer_id}
        manager_spec = related.get("project_manager")
        if manager_spec:
            manager_id = _resolve_employee(client, manager_spec, operations)
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
        if order_spec.get("description") and "description" not in product_spec:
            product_spec["description"] = order_spec["description"]
        customer_id = _resolve_customer(client, customer_spec, operations)
        if customer_id is None:
            raise TripletexClientError("Order requires resolvable customer")
        product_id = _resolve_product(client, product_spec, operations)
        order_id = _create_order(client, customer_id, product_id, fields, product_spec, operations)
        operations.append(OperationResult(name="order-ready", resource_id=order_id))

    elif task_type == TaskType.CREATE_INVOICE:
        customer_spec = related.get("customer", {})
        product_spec = dict(related.get("product", {}))
        invoice_spec = dict(related.get("invoice", {}))
        order_spec = dict(related.get("order", {}))
        if invoice_spec.get("description") and "description" not in product_spec:
            product_spec["description"] = invoice_spec["description"]
        if order_spec.get("description") and "description" not in product_spec:
            product_spec["description"] = order_spec["description"]
        customer_id = _resolve_customer(client, customer_spec, operations)
        if customer_id is None:
            raise TripletexClientError("Invoice requires resolvable customer")
        product_id = _resolve_product(client, product_spec, operations)
        order_id = _create_order(client, customer_id, product_id, fields, product_spec, operations)
        # Tripletex sandbox may reject invoice creation until company bank settings exist.
        # Keep the flow narrow and deterministic; rely on logged 422 details if this task appears.
        invoice_payload = {
            "invoiceDate": fields.get("invoiceDate"),
            "invoiceDueDate": fields.get("invoiceDueDate"),
            "customer": {"id": customer_id},
            "orders": [{"id": order_id}] if order_id is not None else [],
            "sendByEmail": fields.get("sendByEmail"),
        }
        response = client.create_resource("invoice", _compact_payload(invoice_payload))
        operations.append(OperationResult(name="create-invoice", resource_id=_extract_id(response), payload=response))

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
