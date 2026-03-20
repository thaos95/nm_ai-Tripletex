from app.parser import parse_prompt
from app.schemas import TaskType
from app.validator import validate_and_normalize_task


def test_parse_travel_expense_with_per_diem_and_expenses_aggregates_amount() -> None:
    parsed = parse_prompt(
        'Registrer ei reiserekning for Svein Berge (svein.berge@example.org) for "Kundebesok Trondheim". Reisa varte 5 dagar med diett (dagssats 800 kr). Utlegg: flybillett 2850 kr og taxi 200 kr.'
    )
    validated = validate_and_normalize_task(parsed)

    assert validated.parsed_task.task_type == TaskType.CREATE_TRAVEL_EXPENSE
    assert validated.blocking_error is None
    assert validated.parsed_task.fields["amount"] == 7050.0


def test_parse_norwegian_travel_expense_with_dagsats_aggregates_amount() -> None:
    parsed = parse_prompt(
        'Registrer en reiseregning for Ragnhild Bakken (ragnhild.bakken@example.org) for "Kundebesøk Kristiansand". Reisen varte 4 dager med diett (dagsats 800 kr). Utlegg: flybillett 5450 kr og taxi 550 kr.'
    )
    validated = validate_and_normalize_task(parsed)

    assert validated.parsed_task.task_type == TaskType.CREATE_TRAVEL_EXPENSE
    assert validated.blocking_error is None
    assert validated.parsed_task.fields["amount"] == 9200.0


def test_parse_spanish_travel_expense_with_tarifa_diaria_aggregates_amount() -> None:
    parsed = parse_prompt(
        'Registre una nota de gastos de viaje para Pablo Rodríguez (pablo.rodriguez@example.org) por "Conferencia Ålesund". El viaje duró 5 días con dietas (tarifa diaria 800 NOK). Gastos: billete de avión 2750 NOK y taxi 700 NOK.'
    )
    validated = validate_and_normalize_task(parsed)

    assert validated.parsed_task.task_type == TaskType.CREATE_TRAVEL_EXPENSE
    assert validated.blocking_error is None
    assert validated.parsed_task.fields["amount"] == 7450.0


def test_parse_hour_based_project_billing_uses_project_name_and_hourly_amount() -> None:
    parsed = parse_prompt(
        'Registrer 28 timar for Bjorn Kvamme (bjrn.kvamme@example.org) pa aktiviteten "Analyse" i prosjektet "Datamigrering" for Fjelltopp AS (org.nr 986191127). Timesats: 1200 kr/t. Generer ein prosjektfaktura til kunden basert pa dei registrerte timane.'
    )
    validated = validate_and_normalize_task(parsed)

    assert validated.parsed_task.task_type == TaskType.CREATE_PROJECT_BILLING
    assert validated.blocking_error is None
    assert validated.parsed_task.fields["name"] == "Datamigrering"
    assert validated.parsed_task.fields["hourlyRateCurrency"] == 1200.0
    assert validated.parsed_task.fields["amount"] == 33600.0
    assert validated.parsed_task.related_entities["invoice"]["description"] == "Analyse"
