from app.workflows.executor import (
    _build_customer_payload,
    _build_employee_payload,
    _build_invoice_payload,
    _build_product_payload,
    _build_project_payload,
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
    assert payload["markAsPaid"] is True
    assert payload["paymentDate"] == "2026-03-20"
    assert payload["amountPaidCurrency"] == 32200.0
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
