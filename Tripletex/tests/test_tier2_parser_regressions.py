from app.parser import parse_prompt
from app.schemas import TaskType
from app.validator import validate_and_normalize_task


def test_parse_german_payment_prompt_maps_to_invoice_flow() -> None:
    parsed = parse_prompt(
        'Der Kunde Brueckentor GmbH (Org.-Nr. 995557681) hat eine offene Rechnung ueber 9400 NOK ohne MwSt. fuer "Webdesign". Registrieren Sie die vollstandige Zahlung dieser Rechnung.'
    )
    validated = validate_and_normalize_task(parsed)

    assert validated.parsed_task.task_type == TaskType.CREATE_INVOICE
    assert validated.parsed_task.fields["markAsPaid"] is True
    assert validated.parsed_task.related_entities["customer"]["organizationNumber"] == "995557681"
    assert validated.parsed_task.related_entities["invoice"]["description"] == "Webdesign"


def test_parse_german_send_invoice_sets_send_intent() -> None:
    parsed = parse_prompt(
        "Senden Sie eine Rechnung an den Kunden Datenkraft GmbH (Org.-Nr. 831306742) ueber 48600 NOK ohne MwSt. Die Rechnung betrifft Lizenz."
    )
    validated = validate_and_normalize_task(parsed)

    assert validated.parsed_task.task_type == TaskType.CREATE_INVOICE
    assert "sendByEmail" not in validated.parsed_task.fields
    assert validated.parsed_task.related_entities["invoice"]["description"] == "Lizenz"
