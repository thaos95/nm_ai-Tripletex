"""Tests for the lightweight executor agent and programmatic retry."""
import json
import pytest

from app.agent.tools import (
    extract_rejected_fields,
    fix_payload_from_error,
    get_task_spec,
    resolve_entity,
    search_api_docs,
    get_endpoint_schema,
)
from app.clients.tripletex import TripletexClient, TripletexClientError


class TestExtractRejectedFields:
    """Test field extraction from Tripletex 422 validation messages."""

    def test_field_does_not_exist_norwegian(self):
        exc = TripletexClientError(
            status_code=422,
            method="POST",
            path="/employee",
            response_text=json.dumps({
                "validationMessages": [
                    {"message": "startDate: Feltet eksisterer ikke i objektet"}
                ]
            }),
        )
        fields = extract_rejected_fields(exc)
        assert "startDate" in fields

    def test_field_does_not_exist_english(self):
        exc = TripletexClientError(
            status_code=422,
            method="POST",
            path="/incomingInvoice",
            response_text=json.dumps({
                "validationMessages": [
                    {"message": "vatType: Feltet eksisterer ikke i objektet"}
                ]
            }),
        )
        fields = extract_rejected_fields(exc)
        assert "vatType" in fields

    def test_multiple_rejected_fields(self):
        exc = TripletexClientError(
            status_code=422,
            method="POST",
            path="/employee",
            response_text=json.dumps({
                "validationMessages": [
                    {"message": "isActive: Feltet eksisterer ikke i objektet"},
                    {"message": "dueDate: Feltet eksisterer ikke i objektet"},
                ]
            }),
        )
        fields = extract_rejected_fields(exc)
        assert "isActive" in fields
        assert "dueDate" in fields

    def test_no_validation_messages(self):
        exc = TripletexClientError(
            status_code=422,
            method="POST",
            path="/employee",
            response_text="Some generic error",
        )
        fields = extract_rejected_fields(exc)
        assert fields == []


class TestFixPayloadFromError:
    """Test programmatic payload fixing."""

    def test_removes_rejected_field(self):
        payload = {"firstName": "Test", "lastName": "User", "isActive": True}
        exc = TripletexClientError(
            status_code=422,
            method="POST",
            path="/employee",
            response_text=json.dumps({
                "validationMessages": [
                    {"message": "isActive: Feltet eksisterer ikke i objektet"}
                ]
            }),
        )
        fixed = fix_payload_from_error(payload, exc)
        assert fixed is not None
        assert "isActive" not in fixed
        assert fixed["firstName"] == "Test"
        assert fixed["lastName"] == "User"

    def test_removes_nested_field(self):
        payload = {
            "invoiceHeader": {"invoiceDate": "2026-01-01", "vatType": "HIGH"},
            "orderLines": [{"amount": 100, "vatType": "25%"}],
        }
        exc = TripletexClientError(
            status_code=422,
            method="POST",
            path="/incomingInvoice",
            response_text=json.dumps({
                "validationMessages": [
                    {"message": "vatType: Feltet eksisterer ikke i objektet"}
                ]
            }),
        )
        fixed = fix_payload_from_error(payload, exc)
        assert fixed is not None
        assert "vatType" not in fixed.get("invoiceHeader", {})
        assert "vatType" not in fixed.get("orderLines", [{}])[0]

    def test_returns_none_when_nothing_to_fix(self):
        payload = {"firstName": "Test"}
        exc = TripletexClientError(
            status_code=422,
            method="POST",
            path="/employee",
            response_text=json.dumps({
                "validationMessages": [
                    {"message": "Generell valideringsfeil"}
                ]
            }),
        )
        fixed = fix_payload_from_error(payload, exc)
        assert fixed is None


class TestSearchApiDocs:
    """Test KB search tools."""

    def test_search_finds_employee_docs(self):
        result = search_api_docs("POST /employee required fields")
        assert "employee" in result.lower()

    def test_search_finds_invoice_docs(self):
        result = search_api_docs("invoice bank account")
        assert "invoice" in result.lower() or "faktura" in result.lower()

    def test_get_endpoint_schema_employee(self):
        result = get_endpoint_schema("/employee")
        assert "firstName" in result
        assert "lastName" in result

    def test_get_endpoint_schema_unknown(self):
        result = get_endpoint_schema("/nonexistent")
        assert "No schema found" in result


class TestResilientCreate:
    """Test that create_resource auto-retries on 422 with field removal."""

    def test_retries_after_removing_rejected_field(self):
        from app.clients.tripletex import TripletexClient

        client = TripletexClient(
            base_url="https://example.com/v2",
            session_token="test",
        )

        call_count = 0
        def mock_post(path, payload=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TripletexClientError(
                    status_code=422,
                    method="POST",
                    path=path,
                    response_text=json.dumps({
                        "validationMessages": [
                            {"message": "isActive: Feltet eksisterer ikke i objektet"}
                        ]
                    }),
                )
            return {"id": 123, "firstName": "Test"}

        client.post = mock_post

        result = client.create_resource("employee", {
            "firstName": "Test",
            "lastName": "User",
            "isActive": True,
        })
        assert result["id"] == 123
        assert call_count == 2

    def test_raises_when_no_field_to_remove(self):
        from app.clients.tripletex import TripletexClient

        client = TripletexClient(
            base_url="https://example.com/v2",
            session_token="test",
        )

        def mock_post(path, payload=None, **kwargs):
            raise TripletexClientError(
                status_code=422,
                method="POST",
                path=path,
                response_text=json.dumps({
                    "validationMessages": [
                        {"message": "Generell valideringsfeil"}
                    ]
                }),
            )

        client.post = mock_post

        with pytest.raises(TripletexClientError):
            client.create_resource("employee", {"firstName": "Test"})


class TestGetTaskSpec:
    """Test task spec retrieval from KB."""

    def test_get_employee_spec(self):
        result = get_task_spec("create_employee")
        parsed = json.loads(result)
        assert parsed["endpoint"] == "/employee"
        assert parsed["method"] == "POST"
        assert "payload_fields" in parsed
        assert "gotchas" in parsed

    def test_get_invoice_spec(self):
        result = get_task_spec("create_invoice")
        parsed = json.loads(result)
        assert "/invoice" in parsed["endpoint"]

    def test_get_unknown_spec(self):
        result = get_task_spec("nonexistent_task")
        assert "No task spec found" in result
        assert "create_employee" in result  # lists available tasks


class TestResolveEntity:
    """Test entity resolution tool."""

    def test_resolve_finds_customer(self):
        client = TripletexClient(
            base_url="https://example.com/v2",
            session_token="test",
        )

        def mock_get(path, params=None, **kwargs):
            return {"values": [{"id": 42, "name": "Acme Inc", "organizationNumber": "123456789"}]}

        client.get = mock_get
        result = resolve_entity(client, "customer", {"organizationNumber": "123456789"})
        parsed = json.loads(result)
        assert parsed["id"] == 42

    def test_resolve_not_found(self):
        client = TripletexClient(
            base_url="https://example.com/v2",
            session_token="test",
        )

        def mock_get(path, params=None, **kwargs):
            return {"values": []}

        client.get = mock_get
        result = resolve_entity(client, "customer", {"name": "Nonexistent"})
        parsed = json.loads(result)
        assert parsed["found"] is False


class TestAgentToolParsing:
    """Test the tool call parser."""

    def test_parse_simple_tool_call(self):
        from app.agent.loop import _parse_tool_call
        text = '{"tool": "search_api_docs", "args": {"query": "test"}}'
        result = _parse_tool_call(text)
        assert result is not None
        assert result["tool"] == "search_api_docs"

    def test_parse_tool_call_with_text(self):
        from app.agent.loop import _parse_tool_call
        text = 'I will search the docs. {"tool": "get_endpoint_schema", "args": {"endpoint": "/employee"}} done.'
        result = _parse_tool_call(text)
        assert result is not None
        assert result["tool"] == "get_endpoint_schema"

    def test_parse_no_tool_call(self):
        from app.agent.loop import _parse_tool_call
        text = "I don't know what to do."
        result = _parse_tool_call(text)
        assert result is None

    def test_parse_json_without_tool_key_ignored(self):
        from app.agent.loop import _parse_tool_call
        text = '{"name": "test", "value": 123}'
        result = _parse_tool_call(text)
        assert result is None
