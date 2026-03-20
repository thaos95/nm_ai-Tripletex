import pytest

from app.parser import _classify_intent, _normalized_text


INTENT_CONTEXTS = {
    "supplier_customer": [
        "create the record now",
        "for acme as",
        "with email post@example.org",
        "using organization number 923456781",
        "before invoicing",
        "in tripletex",
    ],
    "travel_expense": [
        "for ola hansen",
        "with hotel expense 2200 nok",
        "for a 3 day trip",
        "with taxi and flight",
        "dated 2026-03-20",
        "to trondheim",
    ],
    "credit_note": [
        "for customer acme as",
        "for hosting 12000 nok",
        "reverse the original invoice",
        "full reversal requested",
        "after a complaint",
        "in tripletex",
    ],
    "project_billing": [
        "for project erp loft and customer acme as",
        "for project erp loft using hourly rate 1200 nok",
        "for project erp loft based on registered hours",
        "for project erp loft with 12 timer",
        "for project erp loft and consulting work",
        "for project erp loft in tripletex",
    ],
    "dimension_voucher": [
        "with account 6590",
        "amount 16750 nok",
        "value bedrift",
        "in accounting",
        "for a posted document",
    ],
    "payroll_voucher": [
        "base salary 40000 nok",
        "bonus 5000 nok",
        "for emma stone",
        "use manual vouchers",
        "salary api unavailable",
    ],
}

INTENT_TRIGGERS = {
    "supplier_customer": [
        "supplier",
        "vendor",
        "fornecedor",
        "fournisseur",
        "lieferant",
        "leverandor",
    ],
    "travel_expense": [
        "reiseregning",
        "reiserekning",
        "travel expense",
        "expense report",
        "despesa de viagem",
        "relatorio de despesas",
    ],
    "credit_note": [
        "kreditnota",
        "credit note",
        "credit memo",
        "nota de credito",
        "avoir",
        "gutschrift",
    ],
    "project_billing": [
        "fastpris",
        "fixed price",
        "delbetaling",
        "fakturer kunden",
        "bill the customer",
        "based on the registered hours",
        "fature o cliente",
    ],
    "dimension_voucher": [
        "custom accounting dimension voucher",
        "accounting dimension document",
        "dimensjon bilag",
        "dimensao contabilistica documento",
    ],
    "payroll_voucher": [
        "run payroll with salary api unavailable",
        "payroll expense with salary and bonus",
        "salary api failed use manual vouchers",
        "payroll with salary bonus",
    ],
}


POSITIVE_CASES = []
for expected_intent, triggers in INTENT_TRIGGERS.items():
    contexts = INTENT_CONTEXTS[expected_intent]
    for trigger in triggers:
        for context in contexts:
            case_id = f"{expected_intent}-{trigger}-{context}"
            POSITIVE_CASES.append((case_id, f"{trigger} {context}", expected_intent))


NEGATIVE_CASES = [
    "create customer acme as with email post@example.org",
    "create product consulting for 12000 nok",
    "create project erp loft for acme as",
    "create invoice for acme as",
    "update customer phone number",
    "search customer by organization number",
    "delete voucher 7",
    "list ledger postings for januar",
    "list ledger accounts",
    "create department okonomi",
    "create employee ola hansen with email ola@example.org",
]


@pytest.mark.parametrize(
    "case_id,text,expected_intent",
    POSITIVE_CASES,
    ids=[case[0] for case in POSITIVE_CASES],
)
def test_large_intent_positive_matrix(case_id: str, text: str, expected_intent: str) -> None:
    assert _classify_intent(_normalized_text(text)) == expected_intent, case_id


@pytest.mark.parametrize("text", NEGATIVE_CASES)
def test_large_intent_negative_matrix(text: str) -> None:
    assert _classify_intent(_normalized_text(text)) is None
