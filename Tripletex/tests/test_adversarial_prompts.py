import pytest

from app.parser import parse_prompt
from app.schemas import TaskType
from app.validator import validate_and_normalize_task


@pytest.mark.parametrize(
    ("prompt", "expected_task_type", "expected_amount"),
    [
        (
            'Lag en full kreditnota for kunden Nordlys AS (org.nr 912345678) for "Analyse" på 9800 kr ekskl. MVA.',
            TaskType.CREATE_CREDIT_NOTE,
            -9800.0,
        ),
        (
            'Create a full credit note for customer Fjord Ltd (org no. 923456781) for "Hosting" 12500 NOK.',
            TaskType.CREATE_CREDIT_NOTE,
            -12500.0,
        ),
        (
            'Sett fastpris 100000 kr på prosjektet "Løft" for Kunde AS (org.nr 923456789). Fakturer kunden for 40 % som delbetaling.',
            TaskType.CREATE_PROJECT_BILLING,
            40000.0,
        ),
        (
            'Registrer 10 timar for Ola Hansen (ola.hansen@example.org) på aktiviteten "Rådgivning" i prosjektet "ERP-løft" for Sjø AS (org.nr 923450001). Timesats: 1500 kr/t. Generer ein prosjektfaktura til kunden basert på dei registrerte timane.',
            TaskType.CREATE_PROJECT_BILLING,
            15000.0,
        ),
        (
            'Run payroll for Emma Stone (emma.stone@example.org). Base salary 40000 NOK and one-time bonus 5000 NOK. Use manual vouchers on salary accounts.',
            TaskType.CREATE_PAYROLL_VOUCHER,
            45000.0,
        ),
        (
            'Registrer ei reiseregning for Kari Lie (kari.lie@example.org). Reisa varte 3 dagar med diett (dagssats 900 kr). Utlegg: hotell 3200 kr og taxi 300 kr.',
            TaskType.CREATE_TRAVEL_EXPENSE,
            6200.0,
        ),
    ],
)
def test_adversarial_prompt_matrix(prompt: str, expected_task_type: TaskType, expected_amount: float) -> None:
    validated = validate_and_normalize_task(parse_prompt(prompt))

    assert validated.parsed_task.task_type == expected_task_type
    if expected_task_type == TaskType.CREATE_PAYROLL_VOUCHER:
        assert validated.blocking_error == "Payroll voucher fallback is not supported safely with the current Tripletex contract"
    else:
        assert validated.blocking_error is None
    assert validated.parsed_task.fields["amount"] == expected_amount


def test_dimension_prompt_deduplicates_repeated_selected_value_mentions() -> None:
    validated = validate_and_normalize_task(
        parse_prompt(
            'Crie uma dimensão contabilística personalizada "Marked" com os valores "Bedrift" e "Privat". Lance um documento na conta 6590 por 1000 NOK usando o valor "Bedrift".'
        )
    )

    assert validated.parsed_task.task_type == TaskType.CREATE_DIMENSION_VOUCHER
    assert validated.blocking_error is None
    assert validated.parsed_task.fields["dimensionValues"] == "Bedrift||Privat"
    assert validated.parsed_task.fields["selectedDimensionValue"] == "Bedrift"
