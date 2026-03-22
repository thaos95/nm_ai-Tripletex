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


def test_classify_server_error_500() -> None:
    from app.clients.tripletex import TripletexClientError

    exc = TripletexClientError(
        message="Internal Server Error",
        status_code=500,
        path="/invoice",
        response_text='{"status":500,"message":"Internal Server Error","requestId":"abc-123"}',
    )
    classified = classify_tripletex_error(exc)
    assert classified.category == TripletexErrorCategory.SERVER_ERROR
    assert classified.recoverable is False


def test_classify_server_error_502() -> None:
    from app.clients.tripletex import TripletexClientError

    exc = TripletexClientError(
        message="Bad Gateway",
        status_code=502,
        path="/customer",
        response_text="Bad Gateway",
    )
    classified = classify_tripletex_error(exc)
    assert classified.category == TripletexErrorCategory.SERVER_ERROR
    assert classified.recoverable is False


def test_classify_not_found_404_generic() -> None:
    # "not found" in message triggers WRONG_ENDPOINT; a bare 404 without that text → NOT_FOUND
    classified = classify_tripletex_error(
        'Tripletex API error 404 on GET /customer/99999: {"status":404,"message":"No such resource"}'
    )
    assert classified.category == TripletexErrorCategory.NOT_FOUND
    assert classified.recoverable is False


def test_classify_no_results() -> None:
    classified = classify_tripletex_error(
        '{"values": [], "fullResultSize": 0}'
    )
    assert classified.category == TripletexErrorCategory.NO_RESULTS
    assert classified.recoverable is True


def test_classify_validation_generic_422() -> None:
    classified = classify_tripletex_error(
        'Tripletex API error 422 on POST /invoice: {"validationMessages":[{"message":"Ugyldig verdi"}]}'
    )
    assert classified.category == TripletexErrorCategory.VALIDATION_GENERIC
    assert classified.recoverable is True


def test_classify_validation_environment_proxy_token() -> None:
    classified = classify_tripletex_error(
        'Tripletex API error 403 on POST /invoice: {"message":"Forbidden: invalid proxy token"}'
    )
    assert classified.category == TripletexErrorCategory.VALIDATION_ENVIRONMENT
    assert classified.recoverable is False


def test_classify_forbidden_403_unknown() -> None:
    classified = classify_tripletex_error(
        'Tripletex API error 403 on POST /incomingInvoice: {"message":"Forbidden"}'
    )
    assert classified.category == TripletexErrorCategory.UNKNOWN
    assert classified.recoverable is False


def test_classify_unknown_unrecognized_error() -> None:
    classified = classify_tripletex_error("Something completely unexpected happened")
    assert classified.category == TripletexErrorCategory.UNKNOWN
    assert classified.recoverable is False


def test_invoice_task_contract_declares_prerequisites_and_terminal_errors() -> None:
    contract = get_task_contract(TaskType.CREATE_INVOICE)

    assert "/invoice" in contract.allowed_endpoints
    assert "/order" in contract.allowed_endpoints
    assert "customer" in contract.prerequisites
    assert TripletexErrorCategory.VALIDATION_ENVIRONMENT in contract.terminal_errors
    assert TripletexErrorCategory.VALIDATION_PREREQUISITE in contract.terminal_errors
    assert TripletexErrorCategory.VALIDATION_GENERIC in contract.recoverable_errors
