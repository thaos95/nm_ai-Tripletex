from app.schemas import ExecutionPlan, ParsedTask, PlannedStep, TaskType


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
    elif task_type == TaskType.CREATE_CUSTOMER:
        steps.append(PlannedStep(name="create-customer", resource="customer", action="create"))
    elif task_type == TaskType.UPDATE_CUSTOMER:
        steps.extend(
            [
                PlannedStep(name="find-customer", resource="customer", action="find"),
                PlannedStep(name="update-customer", resource="customer", action="update"),
            ]
        )
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
        steps.extend(
            [
                PlannedStep(name="resolve-order-customer", resource="customer", action="resolve"),
                PlannedStep(name="resolve-order-product", resource="product", action="resolve"),
                PlannedStep(name="create-order", resource="order", action="create"),
            ]
        )
    elif task_type == TaskType.CREATE_INVOICE:
        steps.extend(
            [
                PlannedStep(name="resolve-invoice-customer", resource="customer", action="resolve"),
                PlannedStep(name="resolve-invoice-product", resource="product", action="resolve"),
                PlannedStep(name="create-order", resource="order", action="create"),
                PlannedStep(name="create-invoice", resource="invoice", action="create"),
            ]
        )
    elif task_type == TaskType.CREATE_TRAVEL_EXPENSE:
        steps.append(PlannedStep(name="create-travel-expense", resource="travelExpense", action="create"))
    elif task_type == TaskType.DELETE_TRAVEL_EXPENSE:
        steps.extend(
            [
                PlannedStep(name="lookup-travel-expense", resource="travelExpense", action="find"),
                PlannedStep(name="delete-travel-expense", resource="travelExpense", action="delete"),
            ]
        )
    elif task_type == TaskType.DELETE_VOUCHER:
        steps.append(PlannedStep(name="delete-voucher", resource="ledger/voucher", action="delete"))

    return ExecutionPlan(parsed_task=parsed_task, steps=steps)
