from app.schemas import ExecutionPlan, ParsedTask, PlannedStep, TaskType


def _invoice_requires_product_resolution(parsed_task: ParsedTask) -> bool:
    product_spec = parsed_task.related_entities.get("product", {})
    if product_spec.get("description"):
        return False
    invoice_spec = parsed_task.related_entities.get("invoice", {})
    if invoice_spec.get("description"):
        return False
    order_spec = parsed_task.related_entities.get("order", {})
    if order_spec.get("description"):
        return False
    if product_spec.get("name"):
        return False
    return True


def build_plan(parsed_task: ParsedTask) -> ExecutionPlan:
    task_type = parsed_task.task_type
    steps = []

    if task_type == TaskType.CREATE_EMPLOYEE:
        steps.append(PlannedStep(name="create-employee", resource="employee", action="create"))
    elif task_type == TaskType.UPDATE_EMPLOYEE:
        steps.extend(
            [
                PlannedStep(name="find-employee", resource="employee", action="find"),
                PlannedStep(name="update-employee", resource="employee", action="update"),
            ]
        )
    elif task_type == TaskType.LIST_EMPLOYEES:
        steps.append(PlannedStep(name="list-employees", resource="employee", action="list"))
    elif task_type == TaskType.CREATE_CUSTOMER:
        steps.append(PlannedStep(name="create-customer", resource="customer", action="create"))
    elif task_type == TaskType.UPDATE_CUSTOMER:
        steps.extend(
            [
                PlannedStep(name="find-customer", resource="customer", action="find"),
                PlannedStep(name="update-customer", resource="customer", action="update"),
            ]
        )
    elif task_type == TaskType.SEARCH_CUSTOMERS:
        steps.append(PlannedStep(name="search-customers", resource="customer", action="list"))
    elif task_type == TaskType.CREATE_PRODUCT:
        steps.append(PlannedStep(name="create-product", resource="product", action="create"))
    elif task_type == TaskType.CREATE_PROJECT:
        steps.extend(
            [
                PlannedStep(name="resolve-project-customer", resource="customer", action="resolve"),
                PlannedStep(name="create-project", resource="project", action="create"),
            ]
        )
    elif task_type == TaskType.CREATE_DEPARTMENT:
        steps.append(PlannedStep(name="create-department", resource="department", action="create"))
    elif task_type == TaskType.CREATE_ORDER:
        steps.append(PlannedStep(name="resolve-order-customer", resource="customer", action="resolve"))
        if _invoice_requires_product_resolution(parsed_task):
            steps.append(PlannedStep(name="resolve-order-product", resource="product", action="resolve"))
        steps.append(PlannedStep(name="create-order", resource="order", action="create"))
    elif task_type == TaskType.CREATE_INVOICE:
        steps.append(PlannedStep(name="resolve-invoice-customer", resource="customer", action="resolve"))
        if _invoice_requires_product_resolution(parsed_task):
            steps.append(PlannedStep(name="resolve-invoice-product", resource="product", action="resolve"))
        steps.extend(
            [
                PlannedStep(name="create-order", resource="order", action="create"),
                PlannedStep(name="create-invoice", resource="invoice", action="create"),
            ]
        )
    elif task_type == TaskType.CREATE_CREDIT_NOTE:
        steps.extend(
            [
                PlannedStep(name="resolve-credit-customer", resource="customer", action="resolve"),
                PlannedStep(name="create-credit-order", resource="order", action="create"),
                PlannedStep(name="create-credit-note", resource="invoice", action="create"),
            ]
        )
    elif task_type == TaskType.CREATE_PROJECT_BILLING:
        steps.extend(
            [
                PlannedStep(name="resolve-billing-customer", resource="customer", action="resolve"),
                PlannedStep(name="resolve-billing-project-manager", resource="employee", action="resolve"),
                PlannedStep(name="create-billing-project", resource="project", action="create"),
                PlannedStep(name="create-billing-order", resource="order", action="create"),
                PlannedStep(name="create-billing-invoice", resource="invoice", action="create"),
            ]
        )
    elif task_type == TaskType.CREATE_DIMENSION_VOUCHER:
        steps.extend(
            [
                PlannedStep(name="create-dimension", resource="dimension", action="create"),
                PlannedStep(name="create-dimension-values", resource="dimension/value", action="create"),
                PlannedStep(name="create-dimension-voucher", resource="ledger/voucher", action="create"),
            ]
        )
    elif task_type == TaskType.CREATE_PAYROLL_VOUCHER:
        steps.append(PlannedStep(name="create-payroll-voucher", resource="ledger/voucher", action="create"))
    elif task_type == TaskType.CREATE_TRAVEL_EXPENSE:
        steps.append(PlannedStep(name="create-travel-expense", resource="travelExpense", action="create"))
    elif task_type == TaskType.UPDATE_TRAVEL_EXPENSE:
        steps.extend(
            [
                PlannedStep(name="find-travel-expense", resource="travelExpense", action="find"),
                PlannedStep(name="update-travel-expense", resource="travelExpense", action="update"),
            ]
        )
    elif task_type == TaskType.DELETE_TRAVEL_EXPENSE:
        steps.extend(
            [
                PlannedStep(name="lookup-travel-expense", resource="travelExpense", action="find"),
                PlannedStep(name="delete-travel-expense", resource="travelExpense", action="delete"),
            ]
        )
    elif task_type == TaskType.DELETE_VOUCHER:
        steps.append(PlannedStep(name="delete-voucher", resource="ledger/voucher", action="delete"))
    elif task_type == TaskType.LIST_LEDGER_ACCOUNTS:
        steps.append(PlannedStep(name="list-ledger-accounts", resource="ledger/account", action="list"))
    elif task_type == TaskType.LIST_LEDGER_POSTINGS:
        steps.append(PlannedStep(name="list-ledger-postings", resource="ledger/posting", action="list"))

    return ExecutionPlan(parsed_task=parsed_task, steps=steps)
