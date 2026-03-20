from app.parser import parse_prompt
from app.schemas import TaskType
from app.validator import validate_and_normalize_task


def test_parse_credit_note_prompt() -> None:
    parsed = parse_prompt(
        'Kunden Fossekraft AS (org.nr 918737227) har reklamert pA fakturaen for "Konsulenttimar" (16200 kr ekskl. MVA). Opprett ei fullstendig kreditnota som reverserer heile fakturaen.'
    )
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.CREATE_CREDIT_NOTE
    assert validated.parsed_task.fields["creditNote"] is True
    assert validated.parsed_task.fields["amount"] == -16200.0
    assert validated.parsed_task.related_entities["customer"]["organizationNumber"] == "918737227"
    assert validated.parsed_task.related_entities["invoice"]["description"] == "Konsulenttimar"


def test_parse_project_billing_prompt() -> None:
    parsed = parse_prompt(
        'Sett fastpris 203000 kr pA prosjektet "Digital transformasjon" for Stormberg AS (org.nr 834028719). Prosjektleder er Hilde Hansen (hilde.hansen@example.org). Fakturer kunden for 75 % av fastprisen som en delbetaling.'
    )
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.CREATE_PROJECT_BILLING
    assert validated.parsed_task.fields["fixedPriceAmountCurrency"] == 203000.0
    assert validated.parsed_task.fields["billingPercentage"] == 75.0
    assert validated.parsed_task.fields["amount"] == 152250.0
    assert validated.parsed_task.related_entities["customer"]["organizationNumber"] == "834028719"


def test_parse_dimension_voucher_prompt() -> None:
    parsed = parse_prompt(
        'Crie uma dimensao contabilistica personalizada "Marked" com os valores "Bedrift" e "Privat". Em seguida, lance um documento na conta 6590 por 16750 NOK, vinculado ao valor de dimensao "Bedrift".'
    )
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.UNSUPPORTED
    assert validated.parsed_task.fields["dimensionName"] == "Marked"
    assert validated.parsed_task.fields["dimensionValues"] == "Bedrift||Privat"
    assert validated.parsed_task.fields["selectedDimensionValue"] == "Bedrift"
    assert validated.parsed_task.fields["accountNumber"] == "6590"
    assert validated.parsed_task.fields["amount"] == 16750.0
    assert "NOT_SUPPORTED_VIA_AVAILABLE_API" in validated.parsed_task.notes[0]


def test_parse_payroll_voucher_prompt() -> None:
    parsed = parse_prompt(
        "Run payroll for James Williams (james.williams@example.org) for this month. The base salary is 34950 NOK. Add a one-time bonus of 15450 NOK on top of the base salary. If the salary API is unavailable, you can use manual vouchers on salary accounts (5000-series) to record the payroll expense."
    )
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.CREATE_PAYROLL_VOUCHER
    assert validated.parsed_task.fields["baseSalaryCurrency"] == 34950.0
    assert validated.parsed_task.fields["bonusCurrency"] == 15450.0
    assert validated.parsed_task.fields["amount"] == 50400.0
    assert validated.parsed_task.related_entities["employee"]["email"] == "james.williams@example.org"
