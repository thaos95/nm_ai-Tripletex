import pytest

from app.planner import build_plan
from app.schemas import ParsedTask, TaskType


@pytest.mark.parametrize(
    ("task_type", "expected_steps"),
    [
        (TaskType.CREATE_EMPLOYEE, ["create-employee"]),
        (TaskType.UPDATE_EMPLOYEE, ["find-employee", "update-employee"]),
        (TaskType.LIST_EMPLOYEES, ["list-employees"]),
        (TaskType.CREATE_CUSTOMER, ["create-customer"]),
        (TaskType.UPDATE_CUSTOMER, ["find-customer", "update-customer"]),
        (TaskType.SEARCH_CUSTOMERS, ["search-customers"]),
        (TaskType.CREATE_PRODUCT, ["create-product"]),
        (TaskType.CREATE_PROJECT, ["resolve-project-customer", "create-project"]),
        (TaskType.CREATE_DEPARTMENT, ["create-department"]),
        (TaskType.CREATE_ORDER, ["resolve-order-customer", "resolve-order-product", "create-order"]),
        (TaskType.CREATE_INVOICE, ["resolve-invoice-customer", "resolve-invoice-product", "create-order", "create-invoice"]),
        (TaskType.CREATE_CREDIT_NOTE, ["resolve-credit-customer", "create-credit-order", "create-credit-note"]),
        (
            TaskType.CREATE_PROJECT_BILLING,
            [
                "resolve-billing-customer",
                "resolve-billing-project-manager",
                "create-billing-project",
                "create-billing-order",
                "create-billing-invoice",
            ],
        ),
        (
            TaskType.CREATE_DIMENSION_VOUCHER,
            ["create-dimension", "create-dimension-values", "create-dimension-voucher"],
        ),
        (TaskType.CREATE_PAYROLL_VOUCHER, ["create-payroll-voucher"]),
        (TaskType.CREATE_TRAVEL_EXPENSE, ["create-travel-expense"]),
        (TaskType.UPDATE_TRAVEL_EXPENSE, ["find-travel-expense", "update-travel-expense"]),
        (TaskType.DELETE_TRAVEL_EXPENSE, ["lookup-travel-expense", "delete-travel-expense"]),
        (TaskType.DELETE_VOUCHER, ["delete-voucher"]),
        (TaskType.LIST_LEDGER_ACCOUNTS, ["list-ledger-accounts"]),
        (TaskType.LIST_LEDGER_POSTINGS, ["list-ledger-postings"]),
        (TaskType.UNSUPPORTED, []),
    ],
)
def test_build_plan_matrix(task_type: TaskType, expected_steps: list) -> None:
    parsed_task = ParsedTask(task_type=task_type, confidence=1.0)

    plan = build_plan(parsed_task)

    assert [step.name for step in plan.steps] == expected_steps


def test_build_plan_skips_invoice_product_resolution_when_description_is_present() -> None:
    parsed_task = ParsedTask(
        task_type=TaskType.CREATE_INVOICE,
        confidence=1.0,
        related_entities={
            "customer": {"name": "Brattli AS", "organizationNumber": "845762686"},
            "invoice": {"description": "Skylagring"},
            "order": {"description": "Skylagring"},
        },
    )

    plan = build_plan(parsed_task)

    assert [step.name for step in plan.steps] == [
        "resolve-invoice-customer",
        "create-order",
        "create-invoice",
    ]
