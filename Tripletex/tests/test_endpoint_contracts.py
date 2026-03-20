from app.workflows.executor import (
    _can_create_customer_prerequisite,
    _can_create_employee_prerequisite,
    _can_create_product_prerequisite,
    _build_customer_payload,
    _build_employee_payload,
    _build_invoice_payload,
    _build_product_payload,
    _build_project_payload,
    _should_resolve_product_for_order_line,
)


def test_invoice_contract_omits_send_by_email() -> None:
    payload = _build_invoice_payload(
        {
            "invoiceDate": "2026-03-20",
            "invoiceDueDate": "2026-03-20",
            "sendByEmail": True,
            "markAsPaid": True,
            "paymentDate": "2026-03-20",
            "amountPaidCurrency": 32200.0,
        },
        customer_id=1,
        order_id=2,
    )

    assert payload["invoiceDate"] == "2026-03-20"
    assert payload["orders"] == [{"id": 2}]
    assert "markAsPaid" not in payload
    assert "paymentDate" not in payload
    assert "amountPaidCurrency" not in payload
    assert "sendByEmail" not in payload


def test_product_contract_omits_proxy_invalid_fields() -> None:
    payload = _build_product_payload(
        {
            "name": "Datenberatung",
            "priceExcludingVatCurrency": 41550,
            "productNumber": "7855",
            "vatPercentage": 25,
        }
    )

    assert payload == {"name": "Datenberatung", "priceExcludingVatCurrency": 41550}


def test_employee_contract_omits_proxy_invalid_start_date_field() -> None:
    payload = _build_employee_payload(
        {
            "first_name": "Gunnhild",
            "last_name": "Eide",
            "email": "gunnhild.eide@example.org",
            "birthDate": "1997-06-21",
            "startDate": "2026-06-28",
        },
        department_id=1,
    )

    assert payload["dateOfBirth"] == "1997-06-21"
    assert "dateFrom" not in payload


def test_project_contract_is_minimal() -> None:
    payload = _build_project_payload({"name": "Implementacao Rio", "startDate": "2026-03-19", "email": "x@y.z"})

    assert payload == {"name": "Implementacao Rio", "startDate": "2026-03-19"}


def test_customer_contract_omits_address_like_fields() -> None:
    payload = _build_customer_payload(
        {
            "name": "Bergvik AS",
            "email": "post@bergvik.no",
            "organizationNumber": "914572479",
            "isCustomer": True,
            "address": "Solveien 74",
            "postalCode": "7010",
            "city": "Trondheim",
        }
    )

    assert payload["organizationNumber"] == "914572479"
    assert "address" not in payload
    assert "postalCode" not in payload
    assert "city" not in payload


def test_product_prerequisite_creation_requires_price_signal() -> None:
    assert _can_create_product_prerequisite({"name": "Consulting"}) is False
    assert _can_create_product_prerequisite({"name": "Consulting", "priceExcludingVatCurrency": 1500}) is True


def test_order_line_with_description_skips_product_resolution() -> None:
    assert _should_resolve_product_for_order_line({"name": "Consulting", "description": "Consulting"}) is False
    assert _should_resolve_product_for_order_line({"name": "Consulting"}) is True


def test_customer_prerequisite_creation_requires_name_plus_strong_identifier() -> None:
    assert _can_create_customer_prerequisite({"name": "Acme AS"}) is False
    assert _can_create_customer_prerequisite({"name": "Acme AS", "organizationNumber": "123456789"}) is True
    assert _can_create_customer_prerequisite({"name": "Acme AS", "email": "post@acme.no"}) is True


def test_employee_prerequisite_creation_requires_email_and_first_name() -> None:
    assert _can_create_employee_prerequisite({"first_name": "Ola"}) is False
    assert _can_create_employee_prerequisite({"email": "ola@example.org"}) is False
    assert _can_create_employee_prerequisite({"first_name": "Ola", "email": "ola@example.org"}) is True
