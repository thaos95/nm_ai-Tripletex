import pytest

from app.parser import parse_prompt
from app.schemas import TaskType
from app.validator import validate_and_normalize_task
from app.workflow import parse_workflow


@pytest.mark.parametrize(
    ("prompt", "expected_task"),
    [
        (
            "Kan du vennligst opprette kunden Brattli AS med org.nr 845762686 og e-post post@brattli.no i Tripletex, takk.",
            TaskType.CREATE_CUSTOMER,
        ),
        (
            'Please create and send an invoice to customer Brattli AS (org no. 845762686) for 26450 NOK excluding VAT. The invoice is for Skylagring.',
            TaskType.CREATE_INVOICE,
        ),
        (
            'Vennligst legg til produktet "Analyserapport" for 18050 kr.',
            TaskType.CREATE_PRODUCT,
        ),
        (
            "Kan du ta bort bilag 7?",
            TaskType.DELETE_VOUCHER,
        ),
        (
            "Vis meg kontoplan i Tripletex.",
            TaskType.LIST_LEDGER_ACCOUNTS,
        ),
        (
            'Could you kindly run payroll for James Williams (james.williams@example.org) this month with base salary 34950 NOK and bonus 15450 NOK? Salary API unavailable, use manual vouchers.',
            TaskType.CREATE_PAYROLL_VOUCHER,
        ),
        (
            'Kan du gjerne opprette ei full kreditnota for kunden Fossekraft AS (org.nr 918737227) for "Konsulenttimar" på 16200 kr.',
            TaskType.CREATE_CREDIT_NOTE,
        ),
    ],
)
def test_competition_prompt_robustness_parsing(prompt: str, expected_task: TaskType) -> None:
    validated = validate_and_normalize_task(parse_prompt(prompt))
    assert validated.parsed_task.task_type == expected_task
    assert validated.blocking_error is None


@pytest.mark.parametrize(
    ("prompt", "expected_description"),
    [
        (
            'Could you kindly register full payment on the invoice for customer Windmill Ltd (org no. 830362894) for "System Development" 32200 NOK excluding VAT?',
            "System Development",
        ),
        (
            'Kan du vennligst reverser betalinga for fakturaen "Nettverksteneste" til Strandvik AS (org.nr 859256333) slik at ho står uteståande igjen.',
            "Nettverksteneste",
        ),
    ],
)
def test_competition_prompt_robustness_payment_variants(prompt: str, expected_description: str) -> None:
    validated = validate_and_normalize_task(parse_prompt(prompt))
    assert validated.parsed_task.task_type == TaskType.CREATE_INVOICE
    assert validated.parsed_task.related_entities["invoice"]["description"] == expected_description


@pytest.mark.parametrize(
    ("prompt", "expected_tasks"),
    [
        (
            'Opprett kunde Acme AS, acme@example.org og så opprett produktet "Consulting" for 1500 kr og så opprett faktura.',
            [TaskType.CREATE_CUSTOMER, TaskType.CREATE_PRODUCT, TaskType.CREATE_INVOICE],
        ),
        (
            'Create customer Acme AS, acme@example.org und dann create the project "ERP Loft".',
            [TaskType.CREATE_CUSTOMER, TaskType.CREATE_PROJECT],
        ),
        (
            'Opprett kunde Acme AS, acme@example.org e depois opprett prosjektet "Implementering".',
            [TaskType.CREATE_CUSTOMER, TaskType.CREATE_PROJECT],
        ),
    ],
)
def test_competition_prompt_robustness_workflow_splitting(prompt: str, expected_tasks: list) -> None:
    tasks, _ = parse_workflow(prompt)
    assert [task.task_type for task in tasks] == expected_tasks
