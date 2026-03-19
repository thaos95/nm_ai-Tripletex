import re
from typing import Dict, List, Optional, Tuple

from app.llm_parser import parse_prompt_with_llm
from app.schemas import ParsedTask, TaskType


EMAIL_RE = re.compile(r"[\w.\-+]+@[\w.\-]+\.\w+")
PHONE_RE = re.compile(
    r"((?:\+\d{1,3}\s?)?(?:\d[\s-]?){8,15}\d)"
)
NUMBER_RE = re.compile(r"(\d+(?:[.,]\d{1,2})?)")
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
QUOTED_RE = re.compile(r"['\"]([^'\"]+)['\"]")

CREATE_WORDS = ["opprett", "registrer", "lag", "create", "crear", "criar", "erstellen", "creer"]
UPDATE_WORDS = ["oppdater", "endre", "set", "update", "actualizar", "aktualisieren", "mettre"]
DELETE_WORDS = ["slett", "fjern", "delete", "remove", "borrar", "excluir", "loschen", "supprimer"]

ENTITY_KEYWORDS = {
    "employee": ["ansatt", "employee", "empleado", "funcionario", "mitarbeiter", "employe"],
    "customer": ["kunde", "customer", "cliente", "kund", "client"],
    "product": ["produkt", "product", "producto", "produto"],
    "project": ["prosjekt", "project", "proyecto", "projekt", "projet"],
    "department": ["avdeling", "department", "departamento", "abteilung", "departement"],
    "invoice": ["faktura", "invoice", "factura", "rechnung", "facture"],
    "order": ["ordre", "order", "pedido", "bestellung", "commande"],
    "travel_expense": ["reiseregning", "travel expense", "expense report", "viagem", "spesen"],
    "voucher": ["bilag", "voucher", "comprobante", "buchung"],
}

ROLE_MAP = {
    "kontoadministrator": "ACCOUNT_MANAGER",
    "account administrator": "ACCOUNT_MANAGER",
    "account manager": "ACCOUNT_MANAGER",
}


def _language_hint(prompt: str) -> str:
    lowered = prompt.lower()
    if any(word in lowered for word in ["opprett", "ansatt", "kunde", "reiseregning", "avdeling"]):
        return "nb"
    if any(word in lowered for word in ["create", "employee", "customer", "travel expense"]):
        return "en"
    if any(word in lowered for word in ["crear", "cliente", "factura"]):
        return "es"
    if any(word in lowered for word in ["criar", "cliente", "fatura"]):
        return "pt"
    if any(word in lowered for word in ["erstellen", "kunde", "rechnung"]):
        return "de"
    if any(word in lowered for word in ["creer", "client", "facture"]):
        return "fr"
    return "unknown"


def _contains_any(text: str, options: List[str]) -> bool:
    return any(option in text for option in options)


def _detect_action(lowered: str) -> Optional[str]:
    if _contains_any(lowered, CREATE_WORDS):
        return "create"
    if _contains_any(lowered, UPDATE_WORDS):
        return "update"
    if _contains_any(lowered, DELETE_WORDS):
        return "delete"
    return None


def _detect_entity(lowered: str) -> Optional[str]:
    priority = [
        "invoice",
        "order",
        "travel_expense",
        "voucher",
        "employee",
        "customer",
        "product",
        "project",
        "department",
    ]
    for entity in priority:
        keywords = ENTITY_KEYWORDS[entity]
        if _contains_any(lowered, keywords):
            return entity
    return None


def _first_match(regex: re.Pattern, text: str) -> Optional[str]:
    match = regex.search(text)
    if match:
        return match.group(1) if match.lastindex else match.group(0)
    return None


def _clean_name(value: str) -> str:
    for marker in [" (org no", " (org.nr", " med ", " with ", " som ", " for ", " linked to ", " knyttet til ", ",", "."]:
        if marker in value:
            value = value.split(marker, 1)[0]
    return value.strip(" .,:;")


def _extract_named_entity(prompt: str, keywords: List[str]) -> Optional[str]:
    keyword_pattern = "|".join(re.escape(keyword) for keyword in keywords)

    quoted_pattern = re.compile(r"(?:{0})[^\n\"']*['\"]([^'\"]+)['\"]".format(keyword_pattern), re.IGNORECASE)
    quoted_match = quoted_pattern.search(prompt)
    if quoted_match:
        return _clean_name(quoted_match.group(1))

    plain_pattern = re.compile(
        r"(?:{0})(?:\s+(?:med|named|name|kalt|called|for))?\s+([A-ZÆØÅ][^,\.\n]+)".format(keyword_pattern),
        re.IGNORECASE,
    )
    plain_match = plain_pattern.search(prompt)
    if plain_match:
        return _clean_name(plain_match.group(1))

    return None


def _split_person_name(name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not name:
        return None, None
    parts = name.split()
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


def _extract_amount(prompt: str) -> Optional[float]:
    amount = _first_match(NUMBER_RE, prompt)
    if amount is None:
        return None
    return float(amount.replace(",", "."))


def _extract_common_fields(prompt: str) -> Dict[str, object]:
    fields = {}
    email = _first_match(EMAIL_RE, prompt)
    date = _first_match(DATE_RE, prompt)
    phone_match = None
    if any(keyword in prompt.lower() for keyword in ["telefon", "phone", "mobil", "mobile"]):
        phone_match = PHONE_RE.search(prompt)
    if email:
        fields["email"] = email
    if phone_match:
        fields["phone"] = phone_match.group(1).replace(" ", "")
    if date:
        fields["date"] = date
    return fields


def _extract_invoice_entities(prompt: str) -> Dict[str, Dict[str, object]]:
    related_entities = {}
    customer_name = _extract_named_entity(prompt, ["kunde", "customer", "cliente", "client"])
    product_name = _extract_named_entity(prompt, ["produkt", "product", "producto", "produto"])
    if customer_name:
        related_entities["customer"] = {"name": customer_name, "isCustomer": True}
    if product_name:
        related_entities["product"] = {"name": product_name}
    return related_entities


def _extract_org_number(prompt: str) -> Optional[str]:
    match = re.search(r"(?:org(?:anization)?\s*no\.?|orgnr\.?|org\.nr\.?)\s*(\d{9})", prompt, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def parse_prompt_rule_based(prompt: str) -> ParsedTask:
    lowered = prompt.lower()
    action = _detect_action(lowered)
    entity = _detect_entity(lowered)
    fields = _extract_common_fields(prompt)
    related_entities = {}
    match_fields = {}
    notes = []

    if "project" in lowered or "prosjekt" in lowered:
        entity = "project"

    if entity == "employee" and action == "create":
        first_name, last_name = _split_person_name(_extract_named_entity(prompt, ["navn"]))
        if first_name:
            fields["first_name"] = first_name
        if last_name:
            fields["last_name"] = last_name
        for token, role in ROLE_MAP.items():
            if token in lowered:
                fields["employee_type"] = role
        return ParsedTask(
            task_type=TaskType.CREATE_EMPLOYEE,
            confidence=0.9,
            language_hint=_language_hint(prompt),
            fields=fields,
            notes=notes,
        )

    if entity == "employee" and action == "update":
        first_name, last_name = _split_person_name(_extract_named_entity(prompt, ["ansatt", "employee", "navn"]))
        if first_name:
            match_fields["first_name"] = first_name
        if last_name:
            match_fields["last_name"] = last_name
        if "phone" in fields:
            fields["mobilePhoneNumber"] = fields.pop("phone")
        return ParsedTask(
            task_type=TaskType.UPDATE_EMPLOYEE,
            confidence=0.84,
            language_hint=_language_hint(prompt),
            fields=fields,
            match_fields=match_fields,
        )

    if entity == "customer" and action == "create":
        customer_name = _extract_named_entity(prompt, ["kunde", "customer", "cliente", "client"])
        fields["name"] = customer_name or "Unknown Customer"
        fields["isCustomer"] = True
        return ParsedTask(
            task_type=TaskType.CREATE_CUSTOMER,
            confidence=0.86,
            language_hint=_language_hint(prompt),
            fields=fields,
        )

    if entity == "customer" and action == "update":
        customer_name = _extract_named_entity(prompt, ["kunde", "customer", "cliente", "client"])
        if customer_name:
            match_fields["name"] = customer_name
        if "phone" in fields:
            fields["phoneNumber"] = fields.pop("phone")
        return ParsedTask(
            task_type=TaskType.UPDATE_CUSTOMER,
            confidence=0.82,
            language_hint=_language_hint(prompt),
            fields=fields,
            match_fields=match_fields,
        )

    if entity == "product" and action == "create":
        product_name = _extract_named_entity(prompt, ["produkt", "product", "producto", "produto"])
        fields["name"] = product_name or "Unknown Product"
        amount = _extract_amount(prompt)
        if amount is not None:
            fields["priceExcludingVatCurrency"] = amount
        return ParsedTask(
            task_type=TaskType.CREATE_PRODUCT,
            confidence=0.82,
            language_hint=_language_hint(prompt),
            fields=fields,
        )

    if entity == "project" and action == "create":
        project_name = _extract_named_entity(prompt, ["prosjekt", "project", "proyecto", "projekt"])
        fields["name"] = project_name or "Unknown Project"
        customer_name = _extract_named_entity(prompt, ["kunde", "customer", "cliente", "client"])
        if customer_name:
            related_entities["customer"] = {"name": customer_name, "isCustomer": True}
            org_number = _extract_org_number(prompt)
            if org_number:
                related_entities["customer"]["organizationNumber"] = org_number
        manager_name = _extract_named_entity(prompt, ["project manager", "prosjektleder"])
        if manager_name:
            fields["projectManagerName"] = manager_name
        return ParsedTask(
            task_type=TaskType.CREATE_PROJECT,
            confidence=0.81,
            language_hint=_language_hint(prompt),
            fields=fields,
            related_entities=related_entities,
        )

    if entity == "department" and action == "create":
        department_name = _extract_named_entity(prompt, ["avdeling", "department", "departamento", "abteilung"])
        fields["name"] = department_name or "Unknown Department"
        number = _extract_amount(prompt)
        if number is not None and number.is_integer():
            fields["departmentNumber"] = str(int(number))
        return ParsedTask(
            task_type=TaskType.CREATE_DEPARTMENT,
            confidence=0.8,
            language_hint=_language_hint(prompt),
            fields=fields,
        )

    if entity == "travel_expense" and action == "delete":
        identifier = _extract_amount(prompt)
        if identifier is not None:
            fields["travel_expense_id"] = int(identifier)
        return ParsedTask(
            task_type=TaskType.DELETE_TRAVEL_EXPENSE,
            confidence=0.8,
            language_hint=_language_hint(prompt),
            fields=fields,
        )

    if entity == "travel_expense" and action == "create":
        amount = _extract_amount(prompt)
        if amount is not None:
            fields["amount"] = amount
        if "date" in fields:
            fields["expenseDate"] = fields.pop("date")
        if "kilometer" in lowered or "km" in lowered:
            fields["distance"] = int(amount) if amount is not None else 0
        return ParsedTask(
            task_type=TaskType.CREATE_TRAVEL_EXPENSE,
            confidence=0.72,
            language_hint=_language_hint(prompt),
            fields=fields,
        )

    if entity == "voucher" and action == "delete":
        identifier = _extract_amount(prompt)
        if identifier is not None:
            fields["voucher_id"] = int(identifier)
        return ParsedTask(
            task_type=TaskType.DELETE_VOUCHER,
            confidence=0.75,
            language_hint=_language_hint(prompt),
            fields=fields,
        )

    if entity == "order" and action == "create":
        fields["orderDate"] = fields.get("date") or "2026-03-19"
        related_entities = _extract_invoice_entities(prompt)
        amount = _extract_amount(prompt)
        if amount is not None and "product" in related_entities:
            related_entities["product"]["priceExcludingVatCurrency"] = amount
        return ParsedTask(
            task_type=TaskType.CREATE_ORDER,
            confidence=0.74,
            language_hint=_language_hint(prompt),
            fields=fields,
            related_entities=related_entities,
        )

    if entity == "invoice" and action == "create":
        fields["invoiceDate"] = fields.get("date") or "2026-03-19"
        fields["invoiceDueDate"] = fields.get("date") or "2026-03-19"
        related_entities = _extract_invoice_entities(prompt)
        amount = _extract_amount(prompt)
        if amount is not None:
            fields["amount"] = amount
            if "product" in related_entities:
                related_entities["product"]["priceExcludingVatCurrency"] = amount
        return ParsedTask(
            task_type=TaskType.CREATE_INVOICE,
            confidence=0.79,
            language_hint=_language_hint(prompt),
            fields=fields,
            related_entities=related_entities,
        )

    return ParsedTask(
        task_type=TaskType.UNSUPPORTED,
        confidence=0.1,
        language_hint=_language_hint(prompt),
        fields=fields,
        notes=["No supported workflow matched prompt."],
    )


def parse_prompt(prompt: str) -> ParsedTask:
    llm_parsed = parse_prompt_with_llm(prompt)
    if llm_parsed is not None and llm_parsed.task_type != TaskType.UNSUPPORTED:
        return llm_parsed
    return parse_prompt_rule_based(prompt)
