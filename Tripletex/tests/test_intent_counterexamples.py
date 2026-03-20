import app.parser as parser_module

from app.parser import parse_prompt
from app.schemas import TaskType


def test_product_name_with_timar_routes_to_create_product(monkeypatch) -> None:
    monkeypatch.setattr(parser_module, "parse_prompt_with_llm", lambda _prompt: None)

    parsed = parse_prompt(
        'Opprett produktet "Konsulenttimar" med produktnummer 3923. Prisen er 26400 kr eksklusiv MVA.'
    )

    assert parsed.task_type == TaskType.CREATE_PRODUCT


def test_plain_project_creation_does_not_route_to_project_billing(monkeypatch) -> None:
    monkeypatch.setattr(parser_module, "parse_prompt_with_llm", lambda _prompt: None)

    parsed = parse_prompt(
        'Créez le projet "Implémentation Montagne" lié au client Montagne SARL (nº org. 842138248). Le chef de projet est Jules Martin (jules.martin@example.org).'
    )

    assert parsed.task_type == TaskType.CREATE_PROJECT


def test_paid_invoice_prompt_stays_on_invoice_flow(monkeypatch) -> None:
    monkeypatch.setattr(parser_module, "parse_prompt_with_llm", lambda _prompt: None)

    parsed = parse_prompt(
        'Register full payment for customer Acme AS (org.nr 912345678) on this invoice for "Hosting" 12500 NOK.'
    )

    assert parsed.task_type == TaskType.CREATE_INVOICE
    assert parsed.fields["markAsPaid"] is True


def test_credit_customer_name_does_not_route_to_credit_note(monkeypatch) -> None:
    monkeypatch.setattr(parser_module, "parse_prompt_with_llm", lambda _prompt: None)

    parsed = parse_prompt(
        'Create invoice for customer Credit Partner AS (org no. 923456781) for "Hosting" 12500 NOK.'
    )

    assert parsed.task_type == TaskType.CREATE_INVOICE
