from app.error_handling import TripletexErrorCategory, classify_tripletex_error
from app.schemas import TaskType
from app.task_contracts import get_task_contract


def test_classify_tripletex_wrong_endpoint_error() -> None:
    classified = classify_tripletex_error(
        'Tripletex API error 404 on POST /foo: {"detail":"Wrong endpoint path"}'
    )

    assert classified.category == TripletexErrorCategory.WRONG_ENDPOINT
    assert classified.recoverable is False


def test_classify_tripletex_unauthorized_error() -> None:
    classified = classify_tripletex_error(
        'Tripletex API error 401 on GET /customer: {"status":401,"message":"Unauthorized"}'
    )

    assert classified.category == TripletexErrorCategory.UNAUTHORIZED
    assert classified.recoverable is False


def test_classify_tripletex_environment_validation_error() -> None:
    classified = classify_tripletex_error(
        'Tripletex API error 422 on POST /invoice: {"validationMessages":[{"message":"Faktura kan ikke opprettes før selskapet har registrert et bankkontonummer."}]}'
    )

    assert classified.category == TripletexErrorCategory.VALIDATION_PREREQUISITE
    assert classified.recoverable is False


def test_classify_tripletex_missing_fields_validation_error() -> None:
    classified = classify_tripletex_error(
        'Tripletex API error 422 on POST /invoice: {"validationMessages":[{"message":"Missing required fields"}]}'
    )

    assert classified.category == TripletexErrorCategory.VALIDATION_MISSING_FIELDS
    assert classified.recoverable is True


def test_classify_tripletex_timeout_error() -> None:
    classified = classify_tripletex_error(
        "Tripletex request timed out after 300 seconds"
    )

    assert classified.category == TripletexErrorCategory.TIMEOUT
    assert classified.recoverable is False


def test_invoice_task_contract_declares_prerequisites_and_terminal_errors() -> None:
    contract = get_task_contract(TaskType.CREATE_INVOICE)

    assert "/invoice" in contract.allowed_endpoints
    assert "/order" in contract.allowed_endpoints
    assert "customer" in contract.prerequisites
    assert TripletexErrorCategory.VALIDATION_ENVIRONMENT in contract.terminal_errors
    assert TripletexErrorCategory.VALIDATION_PREREQUISITE in contract.terminal_errors
    assert TripletexErrorCategory.VALIDATION_GENERIC in contract.recoverable_errors
