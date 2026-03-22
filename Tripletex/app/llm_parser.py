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
IMPORTANT: Almost every prompt maps to a supported task type. Only use "unsupported" for tasks that truly cannot map to any type below.
Do not invent fields, entities, IDs, or prerequisites that are not grounded in the prompt.
Prefer conservative extraction over speculative extraction.
When a prompt implies a prerequisite-aware workflow, choose the final supported task and include enough related_entities for the deterministic executor to create prerequisites.

Task types and what maps to them:
- create_employee: hire, add staff, register employee, new worker
- update_employee: change employee details, update address/phone/email
- list_employees: show employees, list staff
- create_customer: new customer, add client, register company as customer
- update_customer: change customer details
- search_customers: find customer, look up client
- create_product: new product, add item/service
- create_project: new project, set up project
- create_department: new department, add division
- create_order: new order, purchase order
- create_invoice: send invoice, bill customer, faktura, factura, Rechnung, sende ein faktura (Nynorsk), envoyer une facture, enviar factura. NOTE: "sende faktura" / "send invoice" = create_invoice, NOT register_payment
- create_credit_note: credit note, kreditnota, refund invoice
- create_project_billing: bill project, project invoice with fixed price, fastpris
- create_supplier_invoice: received invoice from vendor/supplier, leverandørfaktura, factura de proveedor, inngående faktura
- create_dimension_voucher: journal entry, accrual, periodization, month-end closing, year-end adjustment, move costs between accounts, bilagføring, periodisering, månedsavslutning, kontering, Buchung
- create_payroll_voucher: salary payment, payroll entry, lønnsbilag, lønnskjøring
- create_travel_expense: travel claim, reiseregning, expense report, Reisekostenabrechnung, despesa, recibo, receipt expense, kvittering, utlegg, coffee meeting expense, meal expense
- update_travel_expense: modify existing travel expense
- delete_travel_expense: remove travel expense
- delete_voucher: delete/remove voucher or journal entry
- register_payment: record payment RECEIVED on existing invoice, mark invoice as paid, registrer betaling. NOTE: only use when explicitly about recording/registering a payment on an existing invoice, NOT for sending/creating invoices
- reverse_payment: undo/reverse a payment, tilbakefør betaling
- list_ledger_accounts: show chart of accounts, list accounts, kontoplan
- list_ledger_postings: show ledger entries, list postings, hovedbok, analyze costs/revenue over period. Use fields dateFrom/dateTo for date ranges.
- unsupported: ONLY for tasks that truly cannot map to any type above (e.g. bank reconciliation, tax filing, Altinn reporting)

Map natural language from Norwegian, English, Spanish, Portuguese, Nynorsk, German, or French.
Use Tripletex-style field names in fields when known, for example:
- first_name, last_name, email
- phoneNumberMobile, phoneNumber
- priceExcludingVatCurrency
- invoiceDate, invoiceDueDate, orderDate, deliveryDate
- date, amount, description, accountNumber, debitAccountNumber, creditAccountNumber
- travel_expense_id, voucher_id

For related_entities, use nested objects like:
{
  "customer": {"name": "Acme AS", "email": "x@example.org", "isCustomer": true},
  "product": {"name": "Consulting", "priceExcludingVatCurrency": 1500}
}
Return `fields_json`, `match_fields_json`, and `related_entities_json` as JSON-encoded strings.

Examples:
User: Opprett og send en faktura til kunden Brattli AS (org.nr 845762686) på 26450 kr eksklusiv MVA. Fakturaen gjelder Skylagring.
Assistant: {"task_type":"create_invoice","confidence":0.95,"language_hint":"nb","fields_json":"{\\"invoiceDate\\":\\"2026-03-20\\",\\"invoiceDueDate\\":\\"2026-03-20\\",\\"orderDate\\":\\"2026-03-20\\",\\"deliveryDate\\":\\"2026-03-20\\",\\"amount\\":26450.0}","match_fields_json":"{}","related_entities_json":"{\\"customer\\":{\\"name\\":\\"Brattli AS\\",\\"organizationNumber\\":\\"845762686\\",\\"isCustomer\\":true},\\"invoice\\":{\\"description\\":\\"Skylagring\\",\\"amountExcludingVatCurrency\\":26450.0},\\"order\\":{\\"description\\":\\"Skylagring\\"}}","attachments_required":false,"notes":[]}

User: Utfør månedsavslutning for mars 2026. Periodiser forskuddsbetalt kostnad (10150 kr per måned fra konto 1720 til kostnadskonto 6300).
Assistant: {"task_type":"create_dimension_voucher","confidence":0.95,"language_hint":"nb","fields_json":"{\\"date\\":\\"2026-03-31\\",\\"amount\\":10150.0,\\"description\\":\\"Periodisering forskuddsbetalt kostnad mars 2026\\",\\"debitAccountNumber\\":\\"6300\\",\\"creditAccountNumber\\":\\"1720\\"}","match_fields_json":"{}","related_entities_json":"{}","attachments_required":false,"notes":[]}

User: Vi sendte en faktura på 4644 EUR til Stormberg AS (org.nr 917157812) da kursen var 11.51. Registrer fakturaen i Tripletex.
Assistant: {"task_type":"create_invoice","confidence":0.96,"language_hint":"nb","fields_json":"{\\"invoiceDate\\":\\"2026-03-22\\",\\"invoiceDueDate\\":\\"2026-03-22\\",\\"orderDate\\":\\"2026-03-22\\",\\"deliveryDate\\":\\"2026-03-22\\",\\"amount\\":4644.0,\\"currency\\":\\"EUR\\",\\"exchangeRate\\":11.51}","match_fields_json":"{}","related_entities_json":"{\\"customer\\":{\\"name\\":\\"Stormberg AS\\",\\"organizationNumber\\":\\"917157812\\",\\"isCustomer\\":true},\\"invoice\\":{\\"description\\":\\"Faktura\\",\\"amountExcludingVatCurrency\\":4644.0,\\"currency\\":\\"EUR\\"}}","attachments_required":false,"notes":[]}

User: The customer Windmill Ltd (org no. 830362894) has an outstanding invoice for 32200 NOK excluding VAT for "System Development". Register full payment on this invoice.
Assistant: {"task_type":"register_payment","confidence":0.94,"language_hint":"en","fields_json":"{\\"paymentDate\\":\\"2026-03-20\\",\\"amount\\":32200.0,\\"paidAmountCurrency\\":32200.0}","match_fields_json":"{}","related_entities_json":"{\\"customer\\":{\\"name\\":\\"Windmill Ltd\\",\\"organizationNumber\\":\\"830362894\\",\\"isCustomer\\":true},\\"invoice\\":{\\"description\\":\\"System Development\\",\\"amountExcludingVatCurrency\\":32200.0}}","attachments_required":false,"notes":[]}

User: Crie o projeto "Implementacao Rio" vinculado ao cliente Rio Azul Lda (org. no 827937223). O gerente de projeto e Goncalo Oliveira (goncalo.oliveira@example.org).
Assistant: {"task_type":"create_project","confidence":0.93,"language_hint":"pt","fields_json":"{\\"name\\":\\"Implementacao Rio\\",\\"startDate\\":\\"2026-03-20\\"}","match_fields_json":"{}","related_entities_json":"{\\"customer\\":{\\"name\\":\\"Rio Azul Lda\\",\\"organizationNumber\\":\\"827937223\\",\\"isCustomer\\":true},\\"project_manager\\":{\\"first_name\\":\\"Goncalo\\",\\"last_name\\":\\"Oliveira\\",\\"email\\":\\"goncalo.oliveira@example.org\\"}}","attachments_required":false,"notes":[]}

User: Sett fastpris 203000 kr på prosjektet "Digital transformasjon" for Stormberg AS (org.nr 834028719). Prosjektleder er Hilde Hansen (hilde.hansen@example.org). Fakturer kunden for 75 % av fastprisen som en delbetaling.
Assistant: {"task_type":"create_project_billing","confidence":0.93,"language_hint":"nb","fields_json":"{\\"name\\":\\"Digital transformasjon\\",\\"startDate\\":\\"2026-03-20\\",\\"invoiceDate\\":\\"2026-03-20\\",\\"invoiceDueDate\\":\\"2026-03-20\\",\\"orderDate\\":\\"2026-03-20\\",\\"deliveryDate\\":\\"2026-03-20\\",\\"fixedPriceAmountCurrency\\":203000.0,\\"billingPercentage\\":75.0,\\"amount\\":152250.0}","match_fields_json":"{}","related_entities_json":"{\\"customer\\":{\\"name\\":\\"Stormberg AS\\",\\"organizationNumber\\":\\"834028719\\",\\"isCustomer\\":true},\\"project_manager\\":{\\"first_name\\":\\"Hilde\\",\\"last_name\\":\\"Hansen\\",\\"email\\":\\"hilde.hansen@example.org\\"},\\"invoice\\":{\\"description\\":\\"Partial billing 75% of fixed price\\",\\"amountExcludingVatCurrency\\":152250.0},\\"order\\":{\\"description\\":\\"Partial billing 75% of fixed price\\"}}","attachments_required":false,"notes":[]}
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


def _build_parsed_task(parsed: Dict[str, Any]) -> ParsedTask:
    fields = _sanitize_scalar_mapping(_safe_json_mapping(parsed["fields_json"]))
    match_fields_raw = _safe_json_mapping(parsed["match_fields_json"])
    related_entities = _sanitize_related_mapping(_safe_json_mapping(parsed["related_entities_json"]))
    match_fields = _sanitize_scalar_mapping(match_fields_raw)
    notes = list(parsed.get("notes", []))
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
        attachments_required=bool(parsed.get("attachments_required", False)),
        notes=notes,
    )


def _extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    return None


def _parse_prompt_with_replicate(prompt: str) -> Optional[ParsedTask]:
    if not settings.replicate_api_token:
        return None

    payload = {
        "input": {
            "system_instruction": SYSTEM_PROMPT,
            "prompt": prompt,
            "temperature": 0.1,
            "top_p": 0.95,
            "thinking_level": "low",
            "max_output_tokens": 4096,
        },
    }

    headers = {
        "Authorization": "Bearer {0}".format(settings.replicate_api_token),
        "Content-Type": "application/json",
        "Prefer": "wait",
    }

    model = settings.replicate_model
    url = "https://api.replicate.com/v1/models/{0}/predictions".format(model)

    try:
        response = httpx.post(
            url,
            headers=headers,
            json=payload,
            timeout=90.0,
            trust_env=False,
        )
        if response.is_error:
            logger.error(
                "replicate_parse_failed status=%s body=%r model=%s",
                response.status_code,
                response.text[:4000],
                model,
            )
            return None

        data = response.json()
        output = data.get("output")
        if output is None:
            logger.warning("replicate_no_output data_keys=%s", list(data.keys()))
            return None

        if isinstance(output, list):
            output_text = "".join(str(chunk) for chunk in output)
        elif isinstance(output, str):
            output_text = output
        else:
            logger.warning("replicate_unexpected_output_type type=%s", type(output).__name__)
            return None

        if not output_text.strip():
            return None

        parsed = _extract_json_from_text(output_text)
        if parsed is None:
            logger.warning("replicate_no_json_found output=%r", output_text[:500])
            return None

        return _build_parsed_task(parsed)
    except Exception:
        logger.exception("replicate_parse_exception model=%s", model)
        return None


def _parse_prompt_with_openai(prompt: str) -> Optional[ParsedTask]:
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
        return _build_parsed_task(parsed)
    except Exception:
        logger.exception("openai_parse_exception model=%s", settings.openai_model)
        return None


def parse_prompt_with_llm(prompt: str) -> Optional[ParsedTask]:
    result = _parse_prompt_with_replicate(prompt)
    if result is not None:
        logger.info("replicate_parse_success task_type=%s confidence=%.2f", result.task_type, result.confidence)
        return result

    result = _parse_prompt_with_openai(prompt)
    if result is not None:
        logger.info("openai_parse_success task_type=%s confidence=%.2f", result.task_type, result.confidence)
        return result

    return None
