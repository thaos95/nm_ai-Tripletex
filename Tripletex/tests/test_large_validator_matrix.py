import pytest

from app.schemas import ParsedTask, TaskType
from app.validator import validate_and_normalize_task


PHONE_ALIASES = ["phone", "mobilePhoneNumber", "phoneNumberMobile", "mobile_phone", "mobile"]
PHONE_VALUES = ["+47 12345678", "+47-123-45-678", "47 12345678", "12345678", "+4712345678", "+47 41234567"]


@pytest.mark.parametrize("alias", PHONE_ALIASES)
@pytest.mark.parametrize("value", PHONE_VALUES)
def test_validator_employee_phone_alias_matrix(alias: str, value: str) -> None:
    task = ParsedTask(
        task_type=TaskType.UPDATE_EMPLOYEE,
        confidence=1.0,
        fields={alias: value},
        match_fields={"email": "marte@example.org"},
    )

    validated = validate_and_normalize_task(task)

    assert validated.blocking_error is None
    assert validated.parsed_task.fields["phoneNumberMobile"].startswith("+47") or validated.parsed_task.fields["phoneNumberMobile"].isdigit()


@pytest.mark.parametrize("alias", ["phone", "phoneNumberWork", "phoneNumberMobile"])
@pytest.mark.parametrize("value", PHONE_VALUES)
def test_validator_customer_phone_alias_matrix(alias: str, value: str) -> None:
    task = ParsedTask(
        task_type=TaskType.UPDATE_CUSTOMER,
        confidence=1.0,
        fields={alias: value},
        match_fields={"name": "Acme AS"},
    )

    validated = validate_and_normalize_task(task)

    assert validated.blocking_error is None
    assert "phoneNumber" in validated.parsed_task.fields


@pytest.mark.parametrize(
    "task_type,task,blocking_error",
    [
        (
            TaskType.CREATE_EMPLOYEE,
            ParsedTask(task_type=TaskType.CREATE_EMPLOYEE, confidence=1.0, fields={"first_name": "Ola"}),
            "Employee creation requires name and email",
        ),
        (
            TaskType.UPDATE_EMPLOYEE,
            ParsedTask(task_type=TaskType.UPDATE_EMPLOYEE, confidence=1.0, fields={"phoneNumberMobile": "+4712345678"}),
            "Employee update requires identifying fields",
        ),
        (
            TaskType.UPDATE_CUSTOMER,
            ParsedTask(task_type=TaskType.UPDATE_CUSTOMER, confidence=1.0, fields={"phoneNumber": "+4712345678"}),
            "Customer update requires identifying fields",
        ),
        (
            TaskType.CREATE_PRODUCT,
            ParsedTask(task_type=TaskType.CREATE_PRODUCT, confidence=1.0, fields={}),
            "Product creation requires product name",
        ),
        (
            TaskType.CREATE_PROJECT,
            ParsedTask(task_type=TaskType.CREATE_PROJECT, confidence=1.0, fields={}),
            "Project creation requires project name",
        ),
        (
            TaskType.CREATE_PROJECT_BILLING,
            ParsedTask(task_type=TaskType.CREATE_PROJECT_BILLING, confidence=1.0, fields={"name": "ERP"}),
            "Project billing requires customer reference",
        ),
        (
            TaskType.CREATE_ORDER,
            ParsedTask(task_type=TaskType.CREATE_ORDER, confidence=1.0, related_entities={"customer": {"name": "Acme AS"}}),
            "Order/invoice creation requires product reference or line description",
        ),
        (
            TaskType.CREATE_INVOICE,
            ParsedTask(task_type=TaskType.CREATE_INVOICE, confidence=1.0, related_entities={"order": {"description": "Hosting"}}),
            "Order/invoice creation requires customer reference",
        ),
        (
            TaskType.CREATE_DIMENSION_VOUCHER,
            ParsedTask(
                task_type=TaskType.CREATE_DIMENSION_VOUCHER,
                confidence=1.0,
                fields={"dimensionName": "Marked", "dimensionValues": "Bedrift||Privat", "amount": 1000.0},
            ),
            "Dimension voucher requires account number",
        ),
        (
            TaskType.CREATE_PAYROLL_VOUCHER,
            ParsedTask(task_type=TaskType.CREATE_PAYROLL_VOUCHER, confidence=1.0, fields={"date": "2026-03-20"}),
            "Payroll voucher requires salary amount",
        ),
        (
            TaskType.CREATE_TRAVEL_EXPENSE,
            ParsedTask(task_type=TaskType.CREATE_TRAVEL_EXPENSE, confidence=1.0, fields={"date": "2026-03-20"}),
            "Travel expense creation requires amount",
        ),
        (
            TaskType.DELETE_VOUCHER,
            ParsedTask(task_type=TaskType.DELETE_VOUCHER, confidence=1.0, fields={}),
            "Voucher deletion requires voucher id",
        ),
    ],
)
def test_validator_blocking_matrix(task_type: TaskType, task: ParsedTask, blocking_error: str) -> None:
    validated = validate_and_normalize_task(task)

    assert validated.blocking_error == blocking_error


@pytest.mark.parametrize("amount", [12500.0, 20000.0, 9800.0, 3500.0, 16400.0, 7777.0])
def test_validator_credit_note_negates_amount_matrix(amount: float) -> None:
    task = ParsedTask(
        task_type=TaskType.CREATE_CREDIT_NOTE,
        confidence=1.0,
        fields={"amount": amount, "invoiceDate": "2026-03-20"},
        related_entities={"customer": {"name": "Acme AS"}, "order": {"description": "Hosting"}},
    )

    validated = validate_and_normalize_task(task)

    assert validated.blocking_error is None
    assert validated.parsed_task.fields["creditNote"] is True
    assert validated.parsed_task.fields["amount"] == -abs(amount)


@pytest.mark.parametrize("amount", [12500.0, 20000.0, 9800.0, 3500.0, 16400.0, 7777.0])
def test_validator_paid_invoice_defaults_amount_paid_matrix(amount: float) -> None:
    task = ParsedTask(
        task_type=TaskType.CREATE_INVOICE,
        confidence=1.0,
        fields={"invoiceDate": "2026-03-20", "amount": amount, "markAsPaid": True},
        related_entities={"customer": {"name": "Acme AS"}, "order": {"description": "Hosting"}},
    )

    validated = validate_and_normalize_task(task)

    assert validated.blocking_error is None
    assert validated.parsed_task.fields["paymentDate"] == "2026-03-20"
    assert validated.parsed_task.fields["amountPaidCurrency"] == amount


@pytest.mark.parametrize(
    "values,selected",
    [
        ("Bedrift||Privat", "Bedrift"),
        ("Alpha||Beta", "Alpha"),
        ("One||Two||Three", "One"),
        ("Nord||Sor", "Nord"),
        ("Red||Blue", "Red"),
        ("A||B||C||D", "A"),
    ],
)
def test_validator_dimension_selected_default_matrix(values: str, selected: str) -> None:
    task = ParsedTask(
        task_type=TaskType.CREATE_DIMENSION_VOUCHER,
        confidence=1.0,
        fields={"dimensionName": "Marked", "dimensionValues": values, "accountNumber": "6590", "amount": 1000.0},
    )

    validated = validate_and_normalize_task(task)

    assert validated.blocking_error is None
    assert validated.parsed_task.fields["selectedDimensionValue"] == selected


@pytest.mark.parametrize("project_name", ["ERP", "Systemloft", "Portal", "Sky", "Dataflyt", "Montagne"])
def test_validator_project_billing_uses_related_project_name_matrix(project_name: str) -> None:
    task = ParsedTask(
        task_type=TaskType.CREATE_PROJECT_BILLING,
        confidence=1.0,
        fields={"amount": 15000.0},
        related_entities={
            "project": {"name": project_name},
            "customer": {"name": "Acme AS", "organizationNumber": "923456781", "isCustomer": True},
            "invoice": {"description": "Consulting"},
        },
    )

    validated = validate_and_normalize_task(task)

    assert validated.blocking_error is None
    assert validated.parsed_task.fields["name"] == project_name


@pytest.mark.parametrize("org_value", ["923456781", "923 456 781", "923-456-781", " 923456781 ", "org 923456781", "923456781."])
def test_validator_related_org_number_normalization_matrix(org_value: str) -> None:
    task = ParsedTask(
        task_type=TaskType.CREATE_PROJECT,
        confidence=1.0,
        fields={"name": "ERP"},
        related_entities={"customer": {"name": "Acme AS", "organizationNumber": org_value}},
    )

    validated = validate_and_normalize_task(task)

    assert validated.parsed_task.related_entities["customer"]["organizationNumber"] == "923456781"


@pytest.mark.parametrize("email_value", ["TEST@EXAMPLE.ORG", " Test@Example.ORG ", "test@example.org", "USER+1@EXAMPLE.ORG"])
def test_validator_related_email_normalization_matrix(email_value: str) -> None:
    task = ParsedTask(
        task_type=TaskType.CREATE_PROJECT,
        confidence=1.0,
        fields={"name": "ERP"},
        related_entities={"projectManager": {"firstName": "Ola", "lastName": "Hansen", "email": email_value}},
    )

    validated = validate_and_normalize_task(task)

    assert validated.parsed_task.related_entities["project_manager"]["email"] == email_value.strip().lower()
