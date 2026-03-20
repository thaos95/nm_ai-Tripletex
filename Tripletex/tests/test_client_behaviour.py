import httpx
import pytest

from app.clients.tripletex import TripletexClient, TripletexClientError


def client_transport(handler):
    return httpx.MockTransport(handler)


def test_request_returns_empty_dict_for_empty_response_body() -> None:
    client = TripletexClient(
        base_url="https://tx-proxy.ainm.no/v2",
        session_token="token",
        transport=client_transport(lambda request: httpx.Response(204, content=b"")),
    )
    try:
        response = client.delete_resource("travelExpense", 42)
    finally:
        client.close()

    assert response == {}
    assert client.operations[-1]["status_code"] == 204


def test_request_raises_tripletex_client_error_on_4xx() -> None:
    client = TripletexClient(
        base_url="https://tx-proxy.ainm.no/v2",
        session_token="token",
        transport=client_transport(lambda request: httpx.Response(422, text="bad payload")),
    )

    with pytest.raises(TripletexClientError) as exc:
        try:
            client.create_resource("invoice", {"invoiceDate": "2026-03-20"})
        finally:
            client.close()

    assert "422" in str(exc.value)
    assert "POST /invoice" in str(exc.value)


def test_find_single_returns_none_for_empty_match_fields() -> None:
    client = TripletexClient(base_url="https://tx-proxy.ainm.no/v2", session_token="token", transport=client_transport(lambda request: httpx.Response(200, json={})))
    try:
        assert client.find_single("customer", {}) is None
    finally:
        client.close()


def test_find_single_returns_none_when_multiple_candidates_match() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"values": [{"id": 1, "name": "Acme AS"}, {"id": 2, "name": "Acme AS"}]},
        )

    client = TripletexClient(
        base_url="https://tx-proxy.ainm.no/v2",
        session_token="token",
        transport=client_transport(handler),
    )
    try:
        result = client.find_single("customer", {"name": "Acme AS"})
    finally:
        client.close()

    assert result is None


def test_find_single_falls_back_to_single_result_when_exact_match_not_unique() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"values": [{"id": 1, "firstName": "Ola", "lastName": "Nordmann"}]},
        )

    client = TripletexClient(
        base_url="https://tx-proxy.ainm.no/v2",
        session_token="token",
        transport=client_transport(handler),
    )
    try:
        result = client.find_single("employee", {"first_name": "Ola", "last_name": "Nordmann"})
    finally:
        client.close()

    assert result == {"id": 1, "firstName": "Ola", "lastName": "Nordmann"}


def test_find_single_does_not_fallback_to_single_result_for_name_only_queries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"values": [{"id": 1, "name": "Acme AS"}]},
        )

    client = TripletexClient(
        base_url="https://tx-proxy.ainm.no/v2",
        session_token="token",
        transport=client_transport(handler),
    )
    try:
        result = client.find_single("customer", {"name": "Acme"})
    finally:
        client.close()

    assert result is None


def test_find_single_allows_single_result_fallback_for_strong_identifier() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"values": [{"id": 1, "organizationNumber": "914572479", "name": "Bergvik AS"}]},
        )

    client = TripletexClient(
        base_url="https://tx-proxy.ainm.no/v2",
        session_token="token",
        transport=client_transport(handler),
    )
    try:
        result = client.find_single("customer", {"organizationNumber": "914 572 479"})
    finally:
        client.close()

    assert result == {"id": 1, "organizationNumber": "914572479", "name": "Bergvik AS"}


def test_find_by_id_prefers_value_wrapper_and_then_plain_response() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(200, json={"value": {"id": 7, "name": "Voucher"}})
        return httpx.Response(200, json={"id": 8, "name": "Fallback"})

    client = TripletexClient(
        base_url="https://tx-proxy.ainm.no/v2",
        session_token="token",
        transport=client_transport(handler),
    )
    try:
        first = client.find_by_id("ledger/voucher", 7)
        second = client.find_by_id("ledger/voucher", 8)
    finally:
        client.close()

    assert first == {"id": 7, "name": "Voucher"}
    assert second == {"id": 8, "name": "Fallback"}


def test_candidate_matches_full_name_path() -> None:
    client = TripletexClient(base_url="https://tx-proxy.ainm.no/v2", session_token="token", transport=client_transport(lambda request: httpx.Response(200, json={})))
    try:
        assert client._candidate_matches(
            {"firstName": "Ola", "lastName": "Nordmann"},
            {"first_name": "ola", "last_name": "nordmann"},
        )
    finally:
        client.close()


def test_normalize_string_handles_diacritics_and_punctuation_for_entity_matching() -> None:
    client = TripletexClient(base_url="https://tx-proxy.ainm.no/v2", session_token="token", transport=client_transport(lambda request: httpx.Response(200, json={})))
    try:
        assert client._normalize_string("Gonçalo Oliveira") == "goncalo oliveira"
        assert client._normalize_string("Brückentor GmbH") == "bruckentor gmbh"
        assert client._normalize_string("Isabel Rodríguez (PM)") == "isabel rodriguez pm"
        assert client._normalize_string("andre.oliveira@example.org") == "andre.oliveira@example.org"
    finally:
        client.close()


def test_candidate_matches_with_accented_names_after_normalization() -> None:
    client = TripletexClient(base_url="https://tx-proxy.ainm.no/v2", session_token="token", transport=client_transport(lambda request: httpx.Response(200, json={})))
    try:
        assert client._candidate_matches(
            {"firstName": "Goncalo", "lastName": "Oliveira"},
            {"first_name": "gonçalo", "last_name": "oliveira"},
        )
    finally:
        client.close()


def test_find_single_prefers_unique_best_scored_candidate_when_no_full_exact_match() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "values": [
                    {"id": 1, "name": "Rio Azul", "organizationNumber": "111111111"},
                    {"id": 2, "name": "Rio Azul Lda", "organizationNumber": "827937223"},
                ]
            },
        )

    client = TripletexClient(
        base_url="https://tx-proxy.ainm.no/v2",
        session_token="token",
        transport=client_transport(handler),
    )
    try:
        result = client.find_single("customer", {"name": "Rio Azul Lda", "organizationNumber": "827937223"})
    finally:
        client.close()

    assert result == {"id": 2, "name": "Rio Azul Lda", "organizationNumber": "827937223"}


def test_find_single_returns_none_when_scored_candidates_tie() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "values": [
                    {"id": 1, "name": "Acme AS"},
                    {"id": 2, "name": "Acme AS"},
                ]
            },
        )

    client = TripletexClient(
        base_url="https://tx-proxy.ainm.no/v2",
        session_token="token",
        transport=client_transport(handler),
    )
    try:
        result = client.find_single("customer", {"name": "Acme AS", "phoneNumber": "+47 10000000"})
    finally:
        client.close()

    assert result is None


def test_find_single_normalizes_phone_and_org_number_fields_before_matching() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "values": [
                    {
                        "id": 1,
                        "name": "Bergvik AS",
                        "organizationNumber": "914572479",
                        "phoneNumber": "+47 48 00 12 34",
                    }
                ]
            },
        )

    client = TripletexClient(
        base_url="https://tx-proxy.ainm.no/v2",
        session_token="token",
        transport=client_transport(handler),
    )
    try:
        result = client.find_single(
            "customer",
            {"organizationNumber": "914 572 479", "phoneNumber": "+47-48-00-12-34"},
        )
    finally:
        client.close()

    assert result["id"] == 1
