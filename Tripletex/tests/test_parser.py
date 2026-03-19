from app.parser import parse_prompt
from app.schemas import TaskType


def test_parse_create_employee_prompt() -> None:
    parsed = parse_prompt(
        "Opprett en ansatt med navn Ola Nordmann, ola@example.org. Han skal vaere kontoadministrator."
    )

    assert parsed.task_type == TaskType.CREATE_EMPLOYEE
    assert parsed.fields["first_name"] == "Ola"
    assert parsed.fields["last_name"] == "Nordmann"
    assert parsed.fields["email"] == "ola@example.org"
    assert parsed.fields["employee_type"] == "ACCOUNT_MANAGER"


def test_parse_update_customer_prompt() -> None:
    parsed = parse_prompt("Oppdater kunde Acme AS med telefon +47 12345678")
    assert parsed.task_type == TaskType.UPDATE_CUSTOMER
    assert parsed.match_fields["name"] == "Acme AS"
    assert parsed.fields["phoneNumber"] == "+4712345678"


def test_parse_create_invoice_prompt() -> None:
    parsed = parse_prompt('Create invoice for customer "Acme AS" with product "Consulting" 1500')
    assert parsed.task_type == TaskType.CREATE_INVOICE
    assert parsed.related_entities["customer"]["name"] == "Acme AS"
    assert parsed.related_entities["product"]["name"] == "Consulting"
    assert parsed.related_entities["product"]["priceExcludingVatCurrency"] == 1500.0


def test_parse_delete_travel_expense_prompt() -> None:
    parsed = parse_prompt("Slett reiseregning 42")
    assert parsed.task_type == TaskType.DELETE_TRAVEL_EXPENSE
    assert parsed.fields["travel_expense_id"] == 42
