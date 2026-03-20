from app.schemas import ParsedTask, TaskType
from app.validator import validate_and_normalize_task


def test_validator_normalizes_project_manager_aliases() -> None:
    task = ParsedTask(
        task_type=TaskType.CREATE_PROJECT,
        confidence=0.8,
        language_hint="pt",
        fields={"name": "Implementacao Rio"},
        related_entities={
            "customer": {"name": "Rio Azul Lda", "orgNumber": "827937223", "isCustomer": True},
            "projectManager": {"firstName": "Goncalo", "lastName": "Oliveira", "email": "goncalo.oliveira@example.org"},
        },
    )

    validated = validate_and_normalize_task(task)

    assert validated.parsed_task.related_entities["customer"]["organizationNumber"] == "827937223"
    assert validated.parsed_task.related_entities["project_manager"]["first_name"] == "Goncalo"
    assert validated.parsed_task.related_entities["project_manager"]["last_name"] == "Oliveira"
    assert "projectManager" not in validated.parsed_task.related_entities


def test_validator_normalizes_customer_address_aliases_inside_related_entities() -> None:
    task = ParsedTask(
        task_type=TaskType.CREATE_CUSTOMER,
        confidence=0.8,
        language_hint="no",
        fields={"name": "Bergvik AS", "isCustomer": True},
        related_entities={"customer_address": {"address": "Solveien 74", "postalCode": "7010", "city": "Trondheim"}},
    )

    validated = validate_and_normalize_task(task)

    assert validated.parsed_task.related_entities["customer_address"]["addressStreet"] == "Solveien 74"
    assert "address" not in validated.parsed_task.related_entities["customer_address"]
