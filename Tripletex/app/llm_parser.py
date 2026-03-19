import json
from typing import Any, Dict, Optional

import httpx

from app.config import settings
from app.schemas import ParsedTask, TaskType


TASK_TYPES = [task.value for task in TaskType]

TASK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "task_type": {"type": "string", "enum": TASK_TYPES},
        "confidence": {"type": "number"},
        "language_hint": {"type": "string"},
        "fields": {"type": "object", "additionalProperties": True},
        "match_fields": {"type": "object", "additionalProperties": True},
        "related_entities": {"type": "object", "additionalProperties": True},
        "attachments_required": {"type": "boolean"},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "task_type",
        "confidence",
        "language_hint",
        "fields",
        "match_fields",
        "related_entities",
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
- create_customer
- update_customer
- create_product
- create_project
- create_department
- create_order
- create_invoice
- create_travel_expense
- delete_travel_expense
- delete_voucher
- unsupported

Map natural language from Norwegian, English, Spanish, Portuguese, Nynorsk, German, or French.
Use Tripletex-style field names in fields when known, for example:
- first_name, last_name, email
- mobilePhoneNumber, phoneNumber
- priceExcludingVatCurrency
- invoiceDate, invoiceDueDate, orderDate, deliveryDate
- travel_expense_id, voucher_id

For related_entities, use nested objects like:
{
  "customer": {"name": "Acme AS", "email": "x@example.org", "isCustomer": true},
  "product": {"name": "Consulting", "priceExcludingVatCurrency": 1500}
}
"""


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
        response.raise_for_status()
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
        return ParsedTask(
            task_type=TaskType(parsed["task_type"]),
            confidence=float(parsed["confidence"]),
            language_hint=str(parsed["language_hint"]),
            fields=dict(parsed["fields"]),
            match_fields=dict(parsed["match_fields"]),
            related_entities=dict(parsed["related_entities"]),
            attachments_required=bool(parsed["attachments_required"]),
            notes=list(parsed["notes"]),
        )
    except Exception:
        return None
