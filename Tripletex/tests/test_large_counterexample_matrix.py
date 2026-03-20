import pytest

import app.parser as parser_module

from app.parser import parse_prompt
from app.schemas import TaskType


DECOY_NAMES = [
    "Credit Partner",
    "Credit Reversal",
    "Konsulenttimar",
    "Partial Billing",
    "Hours Ledger",
    "Marked Dimension",
    "Servicegrunnlag",
    "Supportgrunnlag",
    "Dataunderlag",
]

PRODUCT_TEMPLATE = 'Opprett produktet "{name}" for {amount} kr.'
CUSTOMER_TEMPLATE = "Create customer {name} AS with organization number {org}. Email: {email}."
PROJECT_TEMPLATE = 'Creez le projet "{name}" lie au client Montagne SARL (n org. {org}). Le chef de projet est Jules Martin ({email}).'
INVOICE_TEMPLATE = 'Create and send an invoice to customer {name} AS (org no. {org}) for {amount} NOK excluding VAT. The invoice is for Hosting.'
SEARCH_TEMPLATE = "Finn kunden {name} AS med orgnr {org}"

COUNTEREXAMPLE_CASES = []
for variant, amount in enumerate([9500, 12500, 17100], start=1):
    for index, name in enumerate(DECOY_NAMES, start=1):
        org = f"91{variant}{index:02d}5678"
        email = f"case{variant}_{index}@example.org"
        decorated = f"{name} {variant}"
        COUNTEREXAMPLE_CASES.extend(
            [
                (f"product-{variant}-{index}", PRODUCT_TEMPLATE.format(name=decorated, amount=amount), TaskType.CREATE_PRODUCT),
                (
                    f"customer-{variant}-{index}",
                    CUSTOMER_TEMPLATE.format(name=decorated, org=org, email=email),
                    TaskType.CREATE_CUSTOMER,
                ),
                (
                    f"project-{variant}-{index}",
                    PROJECT_TEMPLATE.format(name=decorated, org=org, email=email),
                    TaskType.CREATE_PROJECT,
                ),
                (
                    f"invoice-{variant}-{index}",
                    INVOICE_TEMPLATE.format(name=decorated, org=org, amount=amount),
                    TaskType.CREATE_INVOICE,
                ),
                (
                    f"search-{variant}-{index}",
                    SEARCH_TEMPLATE.format(name=decorated, org=org),
                    TaskType.SEARCH_CUSTOMERS,
                ),
            ]
        )


@pytest.mark.parametrize(
    "case_id,prompt,expected_task",
    COUNTEREXAMPLE_CASES,
    ids=[case[0] for case in COUNTEREXAMPLE_CASES],
)
def test_large_counterexample_matrix(monkeypatch, case_id: str, prompt: str, expected_task: TaskType) -> None:
    monkeypatch.setattr(parser_module, "parse_prompt_with_llm", lambda _prompt: None)

    parsed = parse_prompt(prompt)

    assert parsed.task_type == expected_task, case_id
