import pytest
from typing import Optional

from app.parser import parse_prompt
from app.schemas import TaskType
from app.validator import validate_and_normalize_task


@pytest.mark.parametrize(
    ("prompt", "expected_task_type", "expected_description"),
    [
        (
            'Créez un avoir complet pour le client Montagne SARL (nº org. 842138248) pour "Conseil" à 12500 NOK.',
            TaskType.CREATE_CREDIT_NOTE,
            "Conseil",
        ),
        (
            'Erstellen Sie eine vollständige Gutschrift für den Kunden Alpen GmbH (Org.-Nr. 923456781) für "Hosting" über 11000 NOK.',
            TaskType.CREATE_CREDIT_NOTE,
            "Hosting",
        ),
        (
            'Crie o projeto "Transformação Azul" para o cliente Azul Lda (org. nº 872798277). Fature o cliente por 50 % do preço fixo de 88000 NOK.',
            TaskType.CREATE_PROJECT_BILLING,
            "Partial billing",
        ),
        (
            'Registrieren Sie 12 Stunden für Max Berger (max.berger@example.org) für die Aktivität "Analyse" im Projekt "ERP" für Alpen GmbH (Org.-Nr. 923456781). Stundensatz: 1400 NOK. Erstellen Sie eine Projektfaktura basierend auf den erfassten Stunden.',
            TaskType.CREATE_PROJECT_BILLING,
            "Analyse",
        ),
        (
            'Registe uma despesa de viagem para Ines Costa (ines.costa@example.org). A viagem durou 2 dias com diária de 900 NOK. Despesas: hotel 1800 NOK e táxi 250 NOK.',
            TaskType.CREATE_TRAVEL_EXPENSE,
            None,
        ),
    ],
)
def test_adversarial_multilingual_variants(
    prompt: str,
    expected_task_type: TaskType,
    expected_description: Optional[str],
) -> None:
    validated = validate_and_normalize_task(parse_prompt(prompt))

    assert validated.parsed_task.task_type == expected_task_type
    assert validated.blocking_error is None
    if expected_description is not None:
        assert expected_description in validated.parsed_task.related_entities["invoice"]["description"]
