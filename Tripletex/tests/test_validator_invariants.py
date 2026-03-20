from app.schemas import ParsedTask, TaskType
from app.validator import validate_and_normalize_task


def test_validator_blocks_invoice_without_product_or_description() -> None:
    task = ParsedTask(
        task_type=TaskType.CREATE_INVOICE,
        confidence=1.0,
        fields={"invoiceDate": "2026-03-20"},
        related_entities={"customer": {"name": "Acme AS", "organizationNumber": "123456789", "isCustomer": True}},
    )

    validated = validate_and_normalize_task(task)

    assert validated.blocking_error == "Order/invoice creation requires product reference or line description"


def test_validator_accepts_invoice_with_order_description_only() -> None:
    task = ParsedTask(
        task_type=TaskType.CREATE_INVOICE,
        confidence=1.0,
        fields={"invoiceDate": "2026-03-20"},
        related_entities={
            "customer": {"name": "Acme AS", "organizationNumber": "123456789", "isCustomer": True},
            "order": {"description": "Skylagring"},
        },
    )

    validated = validate_and_normalize_task(task)

    assert validated.blocking_error is None
    assert "Order/invoice creation has no product reference; this is risky" in validated.warnings


def test_validator_fills_payment_defaults_for_mark_as_paid_invoice() -> None:
    task = ParsedTask(
        task_type=TaskType.CREATE_INVOICE,
        confidence=1.0,
        fields={"invoiceDate": "2026-03-20", "markAsPaid": True, "amount": 32200.0},
        related_entities={
            "customer": {"name": "Windmill Ltd", "organizationNumber": "830362894", "isCustomer": True},
            "order": {"description": "System Development"},
        },
    )

    validated = validate_and_normalize_task(task)

    assert validated.blocking_error is None
    assert validated.parsed_task.fields["paymentDate"] == "2026-03-20"
    assert validated.parsed_task.fields["amountPaidCurrency"] == 32200.0
