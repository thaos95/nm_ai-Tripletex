import json

import httpx

import app.llm_parser as llm_parser
from app.schemas import TaskType


def test_sanitize_scalar_mapping_filters_non_scalar_values() -> None:
    assert llm_parser._sanitize_scalar_mapping({"name": "Acme", "nested": {"x": 1}, "count": 2}) == {
        "name": "Acme",
        "count": 2,
    }


def test_sanitize_related_mapping_filters_non_dict_and_empty_nested() -> None:
    assert llm_parser._sanitize_related_mapping({"customer": {"name": "Acme"}, "bad": "x", "empty": {"nested": []}}) == {
        "customer": {"name": "Acme"}
    }


def test_safe_json_mapping_handles_invalid_control_chars() -> None:
    assert llm_parser._safe_json_mapping('{"name":"Acme \n AS"}') == {"name": "Acme \n AS"}


def test_parse_prompt_with_llm_returns_none_without_api_key(monkeypatch) -> None:
    monkeypatch.setattr(llm_parser.settings, "openai_api_key", None)

    assert llm_parser.parse_prompt_with_llm("Opprett kunde Acme AS") is None


def test_parse_prompt_with_llm_returns_none_on_error_response(monkeypatch) -> None:
    monkeypatch.setattr(llm_parser.settings, "openai_api_key", "key")

    def fake_post(*args, **kwargs):
        return httpx.Response(500, text="boom", request=httpx.Request("POST", "https://example.com"))

    monkeypatch.setattr(llm_parser.httpx, "post", fake_post)

    assert llm_parser.parse_prompt_with_llm("Opprett kunde Acme AS") is None


def test_parse_prompt_with_llm_parses_output_text_and_moves_nested_match_fields(monkeypatch) -> None:
    monkeypatch.setattr(llm_parser.settings, "openai_api_key", "key")
    monkeypatch.setattr(llm_parser.settings, "openai_base_url", "https://example.com/v1")
    monkeypatch.setattr(llm_parser.settings, "openai_model", "gpt-5-mini")

    payload = {
        "task_type": "create_project",
        "confidence": 0.91,
        "language_hint": "pt",
        "fields_json": json.dumps({"name": "Implementacao Rio"}),
        "match_fields_json": json.dumps({"customer": {"organizationNumber": "827937223"}}),
        "related_entities_json": json.dumps({"project_manager": {"email": "goncalo.oliveira@example.org"}}),
        "attachments_required": False,
        "notes": ["from llm"],
    }

    def fake_post(*args, **kwargs):
        return httpx.Response(
            200,
            json={"output_text": json.dumps(payload)},
            request=httpx.Request("POST", "https://example.com/v1/responses"),
        )

    monkeypatch.setattr(llm_parser.httpx, "post", fake_post)

    parsed = llm_parser.parse_prompt_with_llm("prompt")

    assert parsed is not None
    assert parsed.task_type == TaskType.CREATE_PROJECT
    assert parsed.fields["name"] == "Implementacao Rio"
    assert parsed.related_entities["customer"]["organizationNumber"] == "827937223"
    assert "Moved nested match_fields.customer into related_entities" in parsed.notes


def test_parse_prompt_with_llm_parses_nested_output_blocks(monkeypatch) -> None:
    monkeypatch.setattr(llm_parser.settings, "openai_api_key", "key")

    payload = {
        "task_type": "create_customer",
        "confidence": 0.99,
        "language_hint": "nb",
        "fields_json": json.dumps({"name": "Acme AS", "isCustomer": True}),
        "match_fields_json": json.dumps({}),
        "related_entities_json": json.dumps({}),
        "attachments_required": True,
        "notes": [],
    }

    def fake_post(*args, **kwargs):
        return httpx.Response(
            200,
            json={"output": [{"content": [{"type": "output_text", "text": json.dumps(payload)}]}]},
            request=httpx.Request("POST", "https://example.com/v1/responses"),
        )

    monkeypatch.setattr(llm_parser.httpx, "post", fake_post)

    parsed = llm_parser.parse_prompt_with_llm("prompt")

    assert parsed is not None
    assert parsed.task_type == TaskType.CREATE_CUSTOMER
    assert parsed.attachments_required is True


def test_parse_prompt_with_llm_returns_none_on_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(llm_parser.settings, "openai_api_key", "key")

    def fake_post(*args, **kwargs):
        return httpx.Response(
            200,
            json={"output_text": "not json"},
            request=httpx.Request("POST", "https://example.com/v1/responses"),
        )

    monkeypatch.setattr(llm_parser.httpx, "post", fake_post)

    assert llm_parser.parse_prompt_with_llm("prompt") is None
