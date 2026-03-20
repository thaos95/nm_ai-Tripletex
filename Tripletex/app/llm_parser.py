import json
from typing import Any, Dict, Optional

import httpx

from app.config import settings
from app.logging_utils import get_logger
from app.schemas import ParsedTask, TaskType

logger = get_logger("tripletex-agent.llm")


TASK_TYPES = [task.value for task in TaskType]

TASK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "task_type": {"type": "string", "enum": TASK_TYPES},
        "confidence": {"type": "number"},
        "language_hint": {"type": "string"},
        "fields_json": {"type": "string"},
        "match_fields_json": {"type": "string"},
        "related_entities_json": {"type": "string"},
        "attachments_required": {"type": "boolean"},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "task_type",
        "confidence",
        "language_hint",
        "fields_json",
        "match_fields_json",
        "related_entities_json",
        "attachments_required",
        "notes",
    ],
}

SYSTEM_PROMPT = """You classify Tripletex accounting tasks into a fixed schema.
Return only structured JSON.
Prefer the closest supported task type over unsupported when the intent is reasonably clear.
Use these task types exactly:
- create_employee
- update_employee
- list_employees
- create_customer
- update_customer
- search_customers
- create_product
- create_project
- create_department
- create_order
- create_invoice
- create_credit_note
- create_project_billing
- create_dimension_voucher
- create_payroll_voucher
- create_travel_expense
- delete_travel_expense
- delete_voucher
- list_ledger_accounts
- list_ledger_postings
- unsupported

Map natural language from Norwegian, English, Spanish, Portuguese, Nynorsk, German, or French.
Use Tripletex-style field names in fields when known, for example:
- first_name, last_name, email
- phoneNumberMobile, phoneNumber
- priceExcludingVatCurrency
- invoiceDate, invoiceDueDate, orderDate, deliveryDate
- date, amount, description
- travel_expense_id, voucher_id

For related_entities, use nested objects like:
{
  "customer": {"name": "Acme AS", "email": "x@example.org", "isCustomer": true},
  "product": {"name": "Consulting", "priceExcludingVatCurrency": 1500}
}
Return `fields_json`, `match_fields_json`, and `related_entities_json` as JSON-encoded strings, for example:
- fields_json = "{\"name\":\"Acme AS\",\"isCustomer\":true}"
- match_fields_json = "{}"
- related_entities_json = "{\"customer\":{\"name\":\"Acme AS\",\"isCustomer\":true}}"
"""


def _sanitize_scalar_mapping(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    sanitized: Dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, (str, int, float, bool)):
            sanitized[str(key)] = item
    return sanitized


def _sanitize_related_mapping(value: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    sanitized: Dict[str, Dict[str, Any]] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            nested = _sanitize_scalar_mapping(item)
            if nested:
                sanitized[str(key)] = nested
    return sanitized


def _safe_json_mapping(raw: str) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads(raw, strict=False)


def parse_prompt_with_llm(prompt: str) -> Optional[ParsedTask]:
    if not settings.openai_api_key:
        return None

    payload: Dict[str, Any] = {
        "model": settings.openai_model,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "tripletex_task",
                "schema": TASK_SCHEMA,
                "strict": True,
            }
        },
    }

    headers = {
        "Authorization": "Bearer {0}".format(settings.openai_api_key),
        "Content-Type": "application/json",
    }

    try:
        response = httpx.post(
            "{0}/responses".format(settings.openai_base_url.rstrip("/")),
            headers=headers,
            json=payload,
            timeout=25.0,
            trust_env=False,
        )
        if response.is_error:
            logger.error(
                "openai_parse_failed status=%s body=%r payload_model=%s",
                response.status_code,
                response.text[:4000],
                settings.openai_model,
            )
            return None
        data = response.json()
        output_text = data.get("output_text")
        if not output_text:
            for item in data.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text" and content.get("text"):
                        output_text = content["text"]
                        break
                if output_text:
                    break
        if not output_text:
            return None
        parsed = json.loads(output_text)
        fields = _sanitize_scalar_mapping(_safe_json_mapping(parsed["fields_json"]))
        match_fields_raw = _safe_json_mapping(parsed["match_fields_json"])
        related_entities = _sanitize_related_mapping(_safe_json_mapping(parsed["related_entities_json"]))
        match_fields = _sanitize_scalar_mapping(match_fields_raw)
        notes = list(parsed["notes"])
        if isinstance(match_fields_raw, dict):
            for key, value in match_fields_raw.items():
                if isinstance(value, dict):
                    nested = _sanitize_scalar_mapping(value)
                    if nested:
                        existing = related_entities.get(str(key), {})
                        existing.update(nested)
                        related_entities[str(key)] = existing
                        notes.append("Moved nested match_fields.{0} into related_entities".format(key))
        return ParsedTask(
            task_type=TaskType(parsed["task_type"]),
            confidence=float(parsed["confidence"]),
            language_hint=str(parsed["language_hint"]),
            fields=fields,
            match_fields=match_fields,
            related_entities=related_entities,
            attachments_required=bool(parsed["attachments_required"]),
            notes=notes,
        )
    except Exception:
        logger.exception("openai_parse_exception model=%s", settings.openai_model)
        return None
