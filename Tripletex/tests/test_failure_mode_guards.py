from app.schemas import ParsedTask, TaskType
from app.validator import validate_and_normalize_task


def test_validator_blocks_project_billing_without_customer() -> None:
    task = ParsedTask(
        task_type=TaskType.CREATE_PROJECT_BILLING,
        confidence=1.0,
        fields={"name": "ERP-løft", "amount": 15000.0},
        related_entities={"project": {"name": "ERP-løft"}},
    )

    validated = validate_and_normalize_task(task)

    assert validated.blocking_error == "Project billing requires customer reference"


def test_validator_uses_related_project_name_for_project_billing() -> None:
    task = ParsedTask(
        task_type=TaskType.CREATE_PROJECT_BILLING,
        confidence=1.0,
        fields={"amount": 15000.0},
        related_entities={
            "project": {"name": "ERP-løft"},
            "customer": {"name": "Sjø AS", "organizationNumber": "923450001", "isCustomer": True},
            "invoice": {"description": "Rådgivning"},
        },
    )

    validated = validate_and_normalize_task(task)

    assert validated.blocking_error is None
    assert validated.parsed_task.fields["name"] == "ERP-løft"


def test_validator_blocks_dimension_voucher_without_account_number() -> None:
    task = ParsedTask(
        task_type=TaskType.CREATE_DIMENSION_VOUCHER,
        confidence=1.0,
        fields={
            "dimensionName": "Marked",
            "dimensionValues": "Bedrift||Privat",
            "selectedDimensionValue": "Bedrift",
            "amount": 1000.0,
        },
    )

    validated = validate_and_normalize_task(task)

    assert validated.blocking_error == "Dimension voucher requires account number"


def test_validator_blocks_payroll_voucher_without_amount() -> None:
    task = ParsedTask(
        task_type=TaskType.CREATE_PAYROLL_VOUCHER,
        confidence=1.0,
        fields={"date": "2026-03-20"},
        related_entities={"employee": {"email": "emma.stone@example.org"}},
    )

    validated = validate_and_normalize_task(task)

    assert validated.blocking_error == "Payroll voucher requires salary amount"
