from datetime import date

import pytest

from app.parser import parse_prompt
from app.schemas import TaskType
from app.validator import validate_and_normalize_task


TODAY_ISO = date.today().isoformat()


@pytest.mark.parametrize(
    ("language_tag", "prompt", "expected_task_type", "field_checks", "related_checks"),
    [
        (
            "nb",
            "Opprett kunden Nordlys AS med organisasjonsnummer 951285463. E-post: post@nordlys.no.",
            TaskType.CREATE_CUSTOMER,
            {"organizationNumber": "951285463", "isCustomer": True},
            {},
        ),
        (
            "en",
            'Create the customer Northwave Ltd with organization number 964179239. Email: post@northwave.no.',
            TaskType.CREATE_CUSTOMER,
            {"organizationNumber": "964179239", "isCustomer": True},
            {},
        ),
        (
            "es",
            'Crea el proyecto "Implementacion Dorada" vinculado al cliente Dorada SL (org. no 831075392). El director del proyecto es Isabel Rodriguez (isabel.rodriguez@example.org).',
            TaskType.CREATE_PROJECT,
            {"name": "Implementacion Dorada"},
            {"customer.organizationNumber": "831075392", "project_manager.email": "isabel.rodriguez@example.org"},
        ),
        (
            "pt",
            'Crie o projeto "Integracao Porto" vinculado ao cliente Porto Alegre Lda (org. no 872798277). O gerente de projeto e Andre Oliveira (andre.oliveira@example.org).',
            TaskType.CREATE_PROJECT,
            {"name": "Integracao Porto"},
            {"customer.organizationNumber": "872798277", "project_manager.email": "andre.oliveira@example.org"},
        ),
        (
            "nn",
            "Me har ein ny tilsett som heiter Gunnhild Eide, fodd 21. June 1997. Opprett vedkomande som tilsett med e-post gunnhild.eide@example.org og startdato 28. June 2026.",
            TaskType.CREATE_EMPLOYEE,
            {"birthDate": "1997-06-21", "startDate": "2026-06-28"},
            {},
        ),
        (
            "de",
            'Erstellen Sie das Produkt "Datenberatung" mit der Produktnummer 7855. Der Preis betragt 41550 NOK ohne MwSt., mit dem Standardsatz von 25 %.',
            TaskType.CREATE_PRODUCT,
            {"productNumber": "7855", "vatPercentage": 25.0},
            {},
        ),
        (
            "fr",
            "Créez le client Etoile SARL avec le numéro d'organisation 864083323. E-mail : post@etoile.no.",
            TaskType.CREATE_CUSTOMER,
            {"organizationNumber": "864083323", "isCustomer": True},
            {},
        ),
        (
            "nb-invoice",
            "Opprett og send en faktura til kunden Brattli AS (org.nr 845762686) pa 26450 kr eksklusiv MVA. Fakturaen gjelder Skylagring.",
            TaskType.CREATE_INVOICE,
            {"invoiceDate": TODAY_ISO, "sendByEmail": True},
            {"customer.organizationNumber": "845762686", "invoice.description": "Skylagring"},
        ),
        (
            "en-payment",
            'The customer Windmill Ltd (org no. 830362894) has an outstanding invoice for 32200 NOK excluding VAT for "System Development". Register full payment on this invoice.',
            TaskType.CREATE_INVOICE,
            {"markAsPaid": True, "paymentDate": TODAY_ISO},
            {"customer.organizationNumber": "830362894", "invoice.description": "System Development"},
        ),
        (
            "pt-payment",
            'O cliente Floresta Lda (org. no 916058896) tem uma fatura pendente de 30450 NOK sem IVA por "Desenvolvimento de sistemas". Registe o pagamento total desta fatura.',
            TaskType.CREATE_INVOICE,
            {"markAsPaid": True},
            {"customer.organizationNumber": "916058896", "invoice.description": "Desenvolvimento de sistemas"},
        ),
        (
            "fr-invoice",
            "Créez et envoyez une facture au client Etoile SARL (nº org. 995085488) de 7250 NOK hors TVA. La facture concerne Rapport d'analyse.",
            TaskType.CREATE_INVOICE,
            {"sendByEmail": True, "orderDate": TODAY_ISO},
            {"customer.organizationNumber": "995085488", "invoice.description": "Rapport d'analyse"},
        ),
        (
            "de-department",
            'Erstellen Sie drei Abteilungen in Tripletex: "Logistikk", "Salg" und "Drift".',
            TaskType.CREATE_DEPARTMENT,
            {"departmentNames": "Logistikk||Salg||Drift"},
            {},
        ),
    ],
)
def test_language_coverage_matrix(
    language_tag: str,
    prompt: str,
    expected_task_type: TaskType,
    field_checks: dict,
    related_checks: dict,
) -> None:
    validated = validate_and_normalize_task(parse_prompt(prompt)).parsed_task

    assert validated.task_type == expected_task_type, language_tag
    for key, value in field_checks.items():
        assert validated.fields[key] == value, language_tag
    for dotted_key, value in related_checks.items():
        top_key, nested_key = dotted_key.split(".", 1)
        assert validated.related_entities[top_key][nested_key] == value, language_tag
