import app.parser as parser_module

from app.parser import parse_prompt
from app.schemas import TaskType


def test_update_customer_prompt_with_find_word_stays_update(monkeypatch) -> None:
    monkeypatch.setattr(parser_module, "parse_prompt_with_llm", lambda _prompt: None)

    parsed = parse_prompt("Finn kunden Acme AS og oppdater telefon til +47 12345678")

    assert parsed.task_type == TaskType.UPDATE_CUSTOMER
    assert parsed.fields["phoneNumber"] == "+4712345678"


def test_delete_travel_expense_with_customer_name_stays_delete(monkeypatch) -> None:
    monkeypatch.setattr(parser_module, "parse_prompt_with_llm", lambda _prompt: None)

    parsed = parse_prompt("Slett reiseregning 42 for kunden Acme AS")

    assert parsed.task_type == TaskType.DELETE_TRAVEL_EXPENSE
    assert parsed.fields["travel_expense_id"] == 42


def test_search_customer_named_credit_partner_is_not_credit_note(monkeypatch) -> None:
    monkeypatch.setattr(parser_module, "parse_prompt_with_llm", lambda _prompt: None)

    parsed = parse_prompt("Finn kunden Credit Partner AS med orgnr 923456781")

    assert parsed.task_type == TaskType.SEARCH_CUSTOMERS
    assert parsed.match_fields["organizationNumber"] == "923456781"


def test_list_ledger_postings_with_voucher_word_stays_listing(monkeypatch) -> None:
    monkeypatch.setattr(parser_module, "parse_prompt_with_llm", lambda _prompt: None)

    parsed = parse_prompt("Vis hovedboksposteringer for januar med voucher reference")

    assert parsed.task_type == TaskType.LIST_LEDGER_POSTINGS
    assert parsed.fields["period_hint"] == "januar"
