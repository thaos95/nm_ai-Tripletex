import app.parser as parser_module

from app.parser import _classify_intent, parse_prompt
from app.schemas import TaskType


def test_intent_classifier_prefers_travel_expense_over_customer_like_words(monkeypatch) -> None:
    monkeypatch.setattr(parser_module, "parse_prompt_with_llm", lambda _prompt: None)

    parsed = parse_prompt(
        'Registrer ei reiserekning for Svein Berge (svein.berge@example.org) for "Kundebesok Trondheim". Reisa varte 5 dagar med diett (dagssats 800 kr). Utlegg: flybillett 2850 kr og taxi 200 kr.'
    )

    assert parsed.task_type == TaskType.CREATE_TRAVEL_EXPENSE


def test_intent_classifier_prefers_credit_note_over_invoice(monkeypatch) -> None:
    monkeypatch.setattr(parser_module, "parse_prompt_with_llm", lambda _prompt: None)

    parsed = parse_prompt(
        'Erstellen Sie eine vollstandige Gutschrift fur den Kunden Alpen GmbH (Org.-Nr. 923456781) fur "Hosting" uber 11000 NOK.'
    )

    assert parsed.task_type == TaskType.CREATE_CREDIT_NOTE


def test_intent_classifier_prefers_project_billing_over_plain_project(monkeypatch) -> None:
    monkeypatch.setattr(parser_module, "parse_prompt_with_llm", lambda _prompt: None)

    parsed = parse_prompt(
        'Registrieren Sie 12 Stunden fur Max Berger (max.berger@example.org) fur die Aktivitat "Analyse" im Projekt "ERP" fur Alpen GmbH (Org.-Nr. 923456781). Stundensatz: 1400 NOK. Erstellen Sie eine Projektfaktura basierend auf den erfassten Stunden.'
    )

    assert parsed.task_type == TaskType.CREATE_PROJECT_BILLING


def test_intent_classifier_prefers_payroll_voucher_over_unsupported(monkeypatch) -> None:
    monkeypatch.setattr(parser_module, "parse_prompt_with_llm", lambda _prompt: None)

    parsed = parse_prompt(
        "Run payroll for Emma Stone (emma.stone@example.org). Base salary 40000 NOK and one-time bonus 5000 NOK. Use manual vouchers on salary accounts."
    )

    assert parsed.task_type == TaskType.CREATE_PAYROLL_VOUCHER


def test_intent_classifier_does_not_treat_product_names_with_timar_as_project_billing() -> None:
    lowered = parser_module._normalized_text(
        'Opprett produktet "Konsulenttimar" med produktnummer 3923. Prisen er 26400 kr eksklusiv MVA.'
    )

    assert _classify_intent(lowered) is None


def test_intent_classifier_prefers_dimension_voucher_over_generic_voucher_language() -> None:
    lowered = parser_module._normalized_text(
        'Crie uma dimensão contabilística personalizada "Marked" com os valores "Bedrift" e "Privat". Em seguida, lance um documento na conta 6590 por 16750 NOK.'
    )

    assert _classify_intent(lowered) == "dimension_voucher"
